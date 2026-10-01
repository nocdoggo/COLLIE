"""Tests for the freeze runner (``freeze.py``) with made-up step commands in a temporary folder.

No test builds the study's corpus, reads the study's sealed folder or writes under
``analysis/coling/out``. Each test works in a temporary folder that stands for the repository:
small files for the code, the guide, the lists and a plan whose section 17 states their hashes,
and one script (``fake/step.py``) that plays every step. It writes the files the real command
would write (a made-up "sealed" file among them, inside the temporary folder) and prints lines
in the builders' formats, with a line marked SECRET that no output or record may hold. A file
of knobs makes it fail, change a list, or build other bytes.

Covered: the order of the step list; the dry run of every mode; the rehearsal (no sealed step,
sealed fields ``not run``); the freeze run (its flag, the hashes passed from step to step, the
record and its Markdown rendering, the times from the clock passed in, its notes); what is
shown and kept of a sealed step; the stop at the first failure; the refusals (an API key in the
environment, a hash the plan states that the file does not have, a record of a started sealed
build or one that cannot be read, a counts file already there, uncommitted files); a list that
changes and is put back; a dataset build that did not read the lists; a changed rule reading; a
builder that does not give the same bytes twice; a report without the Gate 1 counts; the
continuation (after a failed step, after a changed guide, with another builder or capture set,
with an eligible list or code that is no longer what the sealed counts were taken on); the one
rerun (agreement, a difference, a crash, a second attempt, a capture set that is not the
manifest's); the lock of a run and the mark of the sealed build (a second terminal, a record
that is gone or edited, a mark made by another checkout); a run killed during the sealed
build, during the counts and during power, and the flag that lets the counts run again; an
availability list that changes; a cutoff of another month; a hashed input that is missing or
ignored; a terminal that has gone away; and, against the real modules, the lines of the corpus
builder's report on a synthetic capture set, the code list of the study plan, and the command
lines and file layouts this module relies on.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_freeze.py -q -p no:cacheprovider
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
from collections.abc import Callable
from dataclasses import replace
from itertools import count
from pathlib import Path

import pytest

from analysis.coling import freeze as F

SECRET = "SECRET"
ORDER = [
    F.MANIFEST_CHECK,
    F.STRING_LIST,
    F.PINS,
    F.OPEN_BUILD,
    F.FORM_CHECK,
    F.FORMS,
    F.SAMPLE_LISTS,
    F.DATASET,
    F.SEALED_BUILD,
    F.COUNTS,
    F.POWER,
]
CLEAN_ENV = {"HOME": "/nowhere"}

FAKE = r"""
import gzip, hashlib, json, sys
from pathlib import Path

name, args = sys.argv[1], sys.argv[2:]
knobs = json.loads(Path("fake/knobs.json").read_text())
OUT = Path("analysis/coling/out")
SEALED = Path("external_data/sealed")
LISTS = [OUT / "audit" / "samples" / f"sample_{n}.csv" for n in ("pilot", "check", "reserve", "literal")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def gz(text):
    return gzip.compress(text.encode(), mtime=0)


def build(sealed):
    drift = "e9\n" if sealed and knobs.get("drift") else ""
    print("captures read: 3; skipped: 0")
    print("Gate 1: shortage events dated 2023-01-01..2025-12-31, Current at statement, with a date-like phrase")
    print("  statement events 900; distinct statements 700 (need >= 600)")
    print("  observable outcome (bracket <= 31 d), definition A: presentation-level events 90, distinct statements 80 (secondary, no threshold)")
    print("  observable outcome (bracket <= 31 d), definition B: presentation-level events 400, distinct statements 300 (need >= 250)")
    print(f"  shortage episodes {knobs.get('sealed_episodes', 120) if sealed else 120} (need >= 100)")
    print("  dated after 2023-12-31, observable outcome, definition A: presentation-level events 50, distinct statements 40 (secondary, no threshold)")
    print(f"  dated after 2023-12-31, observable outcome, definition B: presentation-level events 200, distinct statements {knobs.get('post_cutoff', 160)} (need >= 150)")
    print("  dated after 2023-12-31: events 500, distinct statements 400; with follow-up 499, distinct with follow-up 399 (no threshold)")
    for file, text in (("events.csv.gz", "event_id\ne1\n" + drift), ("outcomes_train.csv.gz", "event_id,outcome\ne1,recovered\n")):
        print(f"wrote {OUT / file} sha256 {sha(put(OUT / file, gz(text)))}")
    if sealed:
        print("row e2 recovered 2024-02-01 SECRET")
        print("warning about a cell: SECRET", file=sys.stderr)
        for file in ("outcomes_test.csv.gz", "outcomes_train_uncensored.csv.gz"):
            print(f"sealed {SEALED / file} sha256 {sha(put(SEALED / file, gz(file + knobs.get('sealed_extra', ''))))}")


def strings():
    path = OUT / "availability_strings.csv"
    extra = b"in stock soon,other,available,2\n" if knobs.get("change_strings") else b""
    put(path, path.read_bytes() + extra)
    Path("fake/strings_written").write_text("yes")


def lists():
    for path in LISTS:
        put(path, path.read_bytes())
    if knobs.get("change_list"):
        changed = LISTS[-1] if knobs["change_list"] == "the last" else LISTS[0]
        put(changed, changed.read_bytes() + b"e7,s7,t7\n")
    if knobs.get("change_list") == "and fail":
        sys.exit("the draw stopped half way")
    put(OUT / "audit" / "samples" / "strata.csv", "sample,stratum\n")
    put(OUT / "audit" / "manifest.json", json.dumps({"draws": knobs.get("draws", 1)}))
    print("pilot: 1 statements (kept from disk)")


def dataset():
    guide = Path("analysis/coling/plan/AUDIT_GUIDE.md").read_text()
    put(OUT / "statements.csv.gz", gz("statement_group_id\ns1\n"))
    put(OUT / "eligible_e3.csv", "statement_group_id\ns1\n" + ("s2\n" if "Appendix" in guide else ""))
    missing = ["pilot"] if knobs.get("lists_missing") else []
    counts = {
        "e3": {"statements": 650, "ids_sha256": "a" * 64},
        "secondary_lists_test": {k: {"statements": 10, "ids_sha256": c * 64} for k, c in (("tbd", "b"), ("silent", "c"), ("stale", "d"))},
        "subsets": {
            "pool": 650,
            "first_draw": {"lists_missing": missing, "ids_not_in_the_statement_table": 0},
            "reference_check": {"final": not missing},
        },
    }
    put(OUT / "dataset_counts.json", json.dumps(counts))
    print("E3 eligible: 650 statements")


def sealed_counts():
    expected = dict(zip(args[2::2], args[3::2]))
    out = Path(expected["--out"])
    print("scoreable by outcome: SECRET")
    if knobs.get("refuse"):
        sys.exit("refused: " + knobs["refuse"])
    if out.exists():
        sys.exit("refused: the counts file is already there")
    if expected["--expect-sha256"] != sha(SEALED / "outcomes_test.csv.gz"):
        sys.exit("refused: the sealed file is not the expected file")
    if expected["--expect-eligible-sha256"] != sha(OUT / "eligible_e3.csv"):
        sys.exit("refused: the eligible list is not the expected file")
    record = {
        "about": "counts",
        "inputs": {
            "sealed_outcomes": {"file": "outcomes_test.csv.gz", "sha256": knobs.get("counted_file", expected["--expect-sha256"])},
            "eligible_list": {"file": "eligible_e3.csv", "sha256": sha(OUT / "eligible_e3.csv")},
            "events": {"file": "events.csv.gz", "sha256": sha(OUT / "events.csv.gz")},
            "capture_manifest": {"file": "capture_manifest.csv", "sha256": sha(OUT / "capture_manifest.csv")},
            "code_sha256": {n: sha(Path("analysis/coling") / n) for n in ("sealed_counts.py", "dataset.py", "corpus.py", "forms.py", "rules.py")},
        },
        "masked_below": 5,
        "e3_eligible_test": {"eligible_statements": 650, "eligible_episodes": 110, "scoreable_statements": knobs.get("scoreable", 500), "scoreable_episodes": knobs.get("scoreable_episodes", 90), "undetermined_statements": 150},
        "post_cutoff_slices": {"scoreable_statements": {"llama-3.3-70b": 300}, "models_without_a_slice": ["grok-4.20"]},
        "gate1_on_the_eligible_list": {"model": "llama-3.3-70b", "observable_statements": 260, "observable_statements_after_cutoff": ">155"},
    }
    if "--gate-observable" not in args:
        del record["gate1_on_the_eligible_list"]
    put(out, json.dumps(record))


def pins():
    pending = knobs.get("pending", [])
    one = {"kind": "literal", "sha256": "e" * 64, "pinned": "e" * 64, "matches_pin": True, "pending": pending}
    print(json.dumps({"templates": {"literal-v1": one}, "read_py_sha256": "f" * 64}, indent=2))


if knobs.get("fail") == name:
    print("Traceback (most recent call last):", file=sys.stderr)
    print("ValueError: a cell reads SECRET", file=sys.stderr)
    sys.exit(1)
if name == "capture manifest":
    print("as in the manifest")
elif name == "availability strings":
    strings()
elif name == "template pins":
    pins()
elif name == "open tables":
    build(sealed=False)
elif name == "sealed build":
    build(sealed=True)
elif name == "form readings":
    changed = knobs.get("changed_readings")
    if changed is not None:
        print(f"golden file: readings changed on shared pairs: {changed}; pairs on one side only: 2")
        print("differs from a fresh run: analysis/coling/out/form_counts.json")
        sys.exit(1)
    print("up to date")
elif name == "form counts":
    put(OUT / "form_counts.json", "{}")
    put(OUT / "rule_readings_train_golden.csv.gz", gz("text_sha256\n"))
elif name == "sample lists":
    lists()
elif name == "dataset":
    dataset()
elif name == "sealed counts":
    sealed_counts()
elif name == "power":
    put(OUT / "dev_losses.json", "{}")
    put(OUT / "power.json", json.dumps({"arguments": args}))
"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def plan_text() -> str:
    """A small plan whose section 17 states the four hashes in the words of the real one."""
    pin = {name: sha(path)[:16] for name, (path, _) in F.PINNED.items()}
    return (
        "# A study plan\n\nOpening.\n\n## 16. Before\n\nText.\n\n"
        "## 17. Registration record\n\n"
        f"**Environment.** Python 3; the lock file `uv.lock`, hash `{pin['uv.lock']}` on 1 October.\n\n"
        "**Captures.**\n\n"
        "- The capture manifest `analysis/coling/out/capture_manifest.csv` (3 files): hash\n"
        f"  `{pin['capture_manifest.csv']}` on 1 October, re-read at the freeze run.\n\n"
        "**Code (hashed at registration).**\n\n"
        "- `corpus.py`: to come.\n"
        f"- `rules.py` (the rule reader): `{pin['rules.py']}`.\n\n"
        "**Annotation.**\n\n"
        "- The availability-string check (section 2.2): done; the list as read has hash\n"
        f"  `{pin['availability_strings.csv']}`, re-read at the freeze run.\n\n"
        "## Amendments\n\nNone.\n"
    )


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Lay a temporary folder out like the repository and make it the working directory."""
    monkeypatch.chdir(tmp_path)
    for name in (*F.CODE, *F.CODE_OTHER):
        put(F.HERE / name, f"# {name}\n")
    put(F.GUIDE, "# Guide\n\n**Version v1, 2 October 2026.** Frozen.\n")
    put(F.MODELS, "# Models\n")
    put(F.LOCK, "lock\n")
    put(F.MANIFEST, "file,timestamp,bytes,sha256\n")
    put(F.STRINGS, "string,class_after_fix,class_before_fix,n_rows\n")
    for name in F.FIRST_DRAW:
        put(
            F.SAMPLES / f"sample_{name}.csv", f"event_id,statement_group_id,thread_id\n{name},s,t\n"
        )
    put(F.OUTCOME_SAMPLE, "event_id\ne5\ne6\n")
    put(F.PLAN, plan_text())
    put(Path("fake/step.py"), FAKE)
    knobs()
    return tmp_path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return make_repo(tmp_path, monkeypatch)


def knobs(**values: object) -> None:
    put(Path("fake/knobs.json"), json.dumps(values))


def fake_steps(pin: str, cutoff: str = F.CUTOFF) -> tuple[F.Step, ...]:
    """The real step list with every command played by ``fake/step.py``; the arguments stay."""
    return tuple(
        replace(step, command=(sys.executable, "fake/step.py", step.name, *step.command[1:]))
        for step in F.steps(pin, cutoff)
    )


def runtime(
    env: dict[str, str] | None = None, dirty: Callable[[object], list[str] | None] | None = None
) -> F.Runtime:
    ticks = count(1)
    return F.Runtime(
        clock=lambda: f"2026-10-02T00:00:{next(ticks):02d}Z",
        environ=CLEAN_ENV if env is None else env,
        uncommitted=dirty or (lambda paths: []),
        head=lambda: "0123abc",
    )


def freeze(*flags: str, rt: F.Runtime | None = None) -> int:
    return F.main(list(flags), rt=rt or runtime(), steps_of=fake_steps)


def record() -> dict:
    return json.loads(F.RECORD.read_text(encoding="utf-8"))


def step(name: str) -> dict:
    return next(entry for entry in record()["steps"] if entry["name"] == name)


def sealed_folder() -> Path:
    """The made-up sealed folder of the temporary repository (never the study's)."""
    return Path("external_data") / F.SEALED_FOLDER


# --------------------------------------------------------------------------------------------
# The step list and the dry run
# --------------------------------------------------------------------------------------------


def test_steps_are_in_the_freeze_order() -> None:
    all_steps = F.steps("abc")
    names = [s.name for s in all_steps]
    assert names == ORDER
    assert [s.name for s in all_steps if s.sealed] == [F.SEALED_BUILD, F.COUNTS]
    # the lists before the builder that reads them; the one sealed write after every open step
    # that could stop the run; the counts after the build and the eligible list; power last
    assert names.index(F.SAMPLE_LISTS) < names.index(F.DATASET) < names.index(F.SEALED_BUILD)
    assert names.index(F.SEALED_BUILD) < names.index(F.COUNTS) < names.index(F.POWER)
    assert [s.name for s in all_steps[names.index(F.SEALED_BUILD) :]] == ORDER[-3:]
    # no step before the sealed build is sealed, and every open step but power comes before it
    assert not any(s.sealed for s in all_steps[: names.index(F.SEALED_BUILD)])
    assert [s.name for s in all_steps if not s.sealed][-1] == F.POWER
    # the availability list is written again before anything is built or sealed
    assert names.index(F.MANIFEST_CHECK) < names.index(F.STRING_LIST) < names.index(F.OPEN_BUILD)
    by_name = {s.name: s for s in all_steps}
    assert by_name[F.STRING_LIST].fixed == by_name[F.STRING_LIST].writes == (F.STRINGS.as_posix(),)
    assert by_name[F.STRING_LIST].command[-1].endswith("corpus.write_availability_strings()")
    assert by_name[F.MANIFEST_CHECK].command[-2:] == ("--pin", "abc")
    assert by_name[F.SEALED_BUILD].command[-2:] == ("--cutoff", F.CUTOFF)
    assert by_name[F.SEALED_BUILD].command[2] == "analysis.coling.corpus"
    assert f'cutoff="{F.CUTOFF}"' in by_name[F.OPEN_BUILD].command[-1]
    assert "open_build" in by_name[F.OPEN_BUILD].command[-1]
    assert by_name[F.COUNTS].command[-1:] == F.COUNTS_FLAGS == ("--gate-observable",)
    assert by_name[F.POWER].command[2:] == ("analysis.coling.power",)
    assert [s.name for s in all_steps if s.fixed] == [F.STRING_LIST, F.SAMPLE_LISTS]
    assert by_name[F.SAMPLE_LISTS].command[-5:] == ("--fixed", *F.FIRST_DRAW)
    assert set(by_name[F.SAMPLE_LISTS].fixed) <= set(by_name[F.SAMPLE_LISTS].writes)
    sealed_writes = [w for s in all_steps for w in s.writes if F.in_sealed_folder(Path(w))]
    assert sorted(set(sealed_writes)) == sorted(F.SEALED_TABLES)
    assert all(s.sealed for s in all_steps if set(s.writes) & set(F.SEALED_TABLES))


def test_only_the_named_lines_of_a_sealed_step_are_kept() -> None:
    build = next(s for s in F.steps("abc") if s.name == F.SEALED_BUILD)
    out = "\n".join(
        [
            "rows kept: 10",
            "Gate 1: shortage events dated 2023-01-01..2025-12-31",
            "  statement events 9; distinct statements 7 (need >= 600)",
            "  20230101000000: 3",
            "  e1 recovered 2024-02-01",
            f"wrote analysis/coling/out/events.csv.gz sha256 {'a' * 64}",
            f"sealed external_data/sealed/outcomes_test.csv.gz sha256 {'b' * 64}",
            "sealed external_data/sealed/outcomes_test.csv.gz sha256 short",
        ]
    )
    kept = F.kept_lines(build, F.Finished(0, out, ""))
    assert [line.split()[0] for line in kept] == ["Gate", "statement", "wrote", "sealed"]
    assert [line for line in kept if F.matches(build.echo, line)] == kept[2:]


@pytest.mark.parametrize("flag", [None, *F.MODE_FLAGS.values()])
def test_dry_run_prints_the_steps_and_runs_nothing(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str | None
) -> None:
    def never(*args: object) -> F.Finished:
        raise AssertionError("a dry run runs nothing")

    rt = replace(runtime(), run=never, uncommitted=never, head=never)
    before = sorted(p.as_posix() for p in repo.rglob("*"))
    assert F.main(["--dry-run", *([flag] if flag else [])], rt=rt, steps_of=fake_steps) == 0
    out = capsys.readouterr().out
    listed = out.split("steps:")[1]
    for one in fake_steps("x"):
        assert one.name in listed and one.command[-1] in listed
    assert re.findall(r"^ +\d+\. (.+?) \[", listed, re.MULTILINE) == ORDER
    assert "--pin " + F.stated_pins(F.PLAN.read_text())["capture_manifest.csv"] in out
    assert out.count("not run in this mode") == {None: 0, "--write-sealed-once": 0}.get(
        flag, {"--open-only": 2, "--continue-after-sealed": 2, "--verify-rerun": 9}.get(flag)
    )
    assert (F.COUNTS_AGAIN in listed) == (flag == "--continue-after-sealed")
    assert F.RUN_LOCK.as_posix() in out
    assert (F.SEALED_MARK.as_posix() in out) == (
        flag in (None, "--open-only", "--write-sealed-once")
    )
    assert sorted(p.as_posix() for p in repo.rglob("*")) == before


def test_a_mode_must_be_named(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        freeze()
    assert "--write-sealed-once" in capsys.readouterr().err
    assert not F.RECORD.exists() and not sealed_folder().exists()
    with pytest.raises(SystemExit):
        freeze("--open-only", "--write-sealed-once")
    with pytest.raises(SystemExit):
        freeze("--open-only", "--cutoff", "December 2023")
    with pytest.raises(SystemExit):
        freeze("--open-only", "--plan", "analysis/coling/plan/MISSING.md")
    hidden = put(sealed_folder() / "PLAN.md", plan_text())
    with pytest.raises(SystemExit, match="never opens the sealed folder"):
        freeze("--dry-run", "--plan", hidden.as_posix())


# --------------------------------------------------------------------------------------------
# The rehearsal
# --------------------------------------------------------------------------------------------


def test_open_only_runs_no_sealed_step(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--open-only", rt=runtime(dirty=lambda paths: ["?? x"])) == 0
    rec = record()
    assert rec["mode"] == F.OPEN_ONLY and rec["status"] == "complete"
    assert not sealed_folder().exists() and not F.SEALED_COUNTS.exists()
    assert set(rec["tables"]["sealed"].values()) == {F.NOT_RUN}
    assert [e["name"] for e in rec["steps"] if e["status"] == F.NOT_RUN] == [
        F.SEALED_BUILD,
        F.COUNTS,
    ]
    assert all(e["status"] == "ok" for e in rec["steps"] if not e["sealed"])
    gate = rec["counts"]["gate1"]
    assert gate["eligible_list"] == F.NOT_RUN and gate["builder_gate_set"]["passes"] is True
    assert rec["counts"]["sealed_counts"] == F.NOT_RUN
    assert rec["tables"]["open"]["events.csv.gz"]["gzip_sha256"] == sha(F.OPEN_TABLES[0])
    assert "Sealed, as printed by the freeze run: `outcomes_test.csv.gz` `not run`" in (
        F.RECORD_MD.read_text()
    )
    assert "builder's gate set: met" in capsys.readouterr().out
    # a rehearsal can be repeated, and does not stand in the way of the freeze run
    assert freeze("--open-only") == 0
    assert freeze("--write-sealed-once") == 0
    assert record()["mode"] == F.FREEZE


# --------------------------------------------------------------------------------------------
# The freeze run
# --------------------------------------------------------------------------------------------


def test_freeze_run_writes_the_record(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--write-sealed-once") == 0
    rec = record()
    assert (rec["mode"], rec["status"], rec["seed"]) == (F.FREEZE, "complete", 20261001)
    assert all(e["status"] == "ok" and e["exit_status"] == 0 for e in rec["steps"])
    # the sealed hashes are the ones the build printed; both go on to the counts-only code
    test_hash = sha(sealed_folder() / F.SEALED_TEST)
    assert rec["tables"]["sealed"] == {
        F.SEALED_TEST: test_hash,
        "outcomes_train_uncensored.csv.gz": sha(
            sealed_folder() / "outcomes_train_uncensored.csv.gz"
        ),
    }
    said = step(F.COUNTS)["command"]
    assert f"--expect-sha256 {test_hash}" in said
    assert f"--expect-eligible-sha256 {sha(F.ELIGIBLE)}" in said
    assert said.endswith(f"--out {F.SEALED_COUNTS.as_posix()} --gate-observable")
    assert said.startswith("PYTHONPATH=. python ") and sys.executable not in said
    # inputs, environment, code, tables, lists, guide, models, pins
    assert rec["inputs"]["cutoff"] == F.CUTOFF and rec["inputs"]["commit"] == "0123abc"
    assert rec["inputs"]["plan_states"] == F.stated_pins(F.PLAN.read_text())
    assert rec["environment"]["python"] and rec["environment"]["lock_file"]["sha256"] == sha(F.LOCK)
    assert set(rec["environment"]["packages"]) == {"pandas", "numpy", "scikit-learn", "scipy"}
    assert rec["code"] == {name: sha(F.HERE / name) for name in F.CODE}
    assert set(rec["code_other"]) == set(F.CODE_OTHER)
    events = rec["tables"]["open"]["events.csv.gz"]
    assert events["gzip_sha256"] == sha(F.OPEN_TABLES[0])
    assert events["content_sha256"] == hashlib.sha256(b"event_id\ne1\n").hexdigest()
    assert rec["tables"]["eligible_list"]["sha256"] == sha(F.ELIGIBLE)
    assert rec["tables"]["eligible_list"]["statements"] == 650
    assert rec["tables"]["secondary_lists"]["silent"] == {"ids_sha256": "c" * 64, "statements": 10}
    assert set(rec["sample_lists"]) == {*F.FIRST_DRAW, "outcome_audit_train"}
    assert rec["sample_lists"]["outcome_audit_train"]["rows"] == 2
    assert rec["annotation"]["guide"] == {
        "file": F.GUIDE.as_posix(),
        "sha256": sha(F.GUIDE),
        "version": "v1",
    }
    assert rec["models"]["sha256"] == sha(F.MODELS)
    assert rec["prompts"]["templates"]["literal-v1"]["sha256"] == "e" * 64
    assert rec["outputs"][F.SEALED_COUNTS.as_posix()] == sha(F.SEALED_COUNTS)
    assert not any(F.SEALED_FOLDER in Path(name).parts for name in rec["outputs"])
    # Gate 1: the builder's lines and counts, and the counts on the eligible list
    gate = rec["counts"]["gate1"]
    assert gate["builder_gate_set"]["lines"][0].startswith("Gate 1:")
    assert {k: v["count"] for k, v in gate["builder_gate_set"]["thresholds"].items()} == {
        "statements": 700,
        "observable": 300,
        "episodes": 120,
        "post_cutoff": 160,
    }
    listed = gate["eligible_list"]
    assert {k: v["count"] for k, v in listed["thresholds"].items()} == {
        "statements": 650,
        "observable": 260,
        "episodes": 110,
        "post_cutoff": ">155",
    }
    assert listed["passes"] is True and listed["scoreable_statements"] == 500
    # every count of the counts file as registered, and nothing else of it
    assert rec["counts"]["sealed_counts"] == [
        "e3_eligible_test.eligible_statements: 650",
        "e3_eligible_test.eligible_episodes: 110",
        "e3_eligible_test.scoreable_statements: 500",
        "e3_eligible_test.scoreable_episodes: 90",
        "e3_eligible_test.undetermined_statements: 150",
        "post_cutoff_slices.scoreable_statements.llama-3.3-70b: 300",
        "gate1_on_the_eligible_list.observable_statements: 260",
        "gate1_on_the_eligible_list.observable_statements_after_cutoff: >155",
    ]
    assert "post_cutoff_slices.scoreable_statements.llama-3.3-70b: 300" in F.RECORD_MD.read_text()
    out = capsys.readouterr().out
    assert "eligible list: met" in out and f"complete: wrote {F.RECORD.as_posix()}" in out
    assert "e3_eligible_test.scoreable_statements: 500" in out


def test_every_step_has_its_command_status_and_the_times_of_the_clock(repo: Path) -> None:
    assert freeze("--write-sealed-once") == 0
    rec = record()
    times = [t for e in rec["steps"] for t in (e["started"], e["finished"])]
    assert times == sorted(times) and len(set(times)) == 2 * len(rec["steps"])
    assert all(t.startswith("2026-10-02T00:00:") for t in times)
    assert rec["inputs"]["started"] < times[0] and times[-1] < rec["inputs"]["finished"]
    assert all(e["command"].startswith("PYTHONPATH=. python fake/step.py") for e in rec["steps"])
    assert step(F.DATASET)["lines"] == ["E3 eligible: 650 statements"]
    assert step(F.COUNTS)["lines"] == []


def test_markdown_follows_the_order_of_section_17(repo: Path) -> None:
    assert freeze("--write-sealed-once") == 0
    text = F.RECORD_MD.read_text(encoding="utf-8")
    heads = [
        "Environment",
        "Captures",
        "Code",
        "Tables",
        "Annotation",
        "Counts",
        "Models",
        "Prompts",
    ]
    places = [text.index(f"**{head}") for head in heads]
    assert places == sorted(places)
    rec = record()
    for label, value in F.registered_hashes(rec).items():
        assert F.short(value) in text, label
    for value in rec["tables"]["sealed"].values():
        assert f"`{value[:16]}`" in text
    for name, (path, _) in F.PINNED.items():
        if name != "rules.py":
            assert sha(path)[:16] in text
    assert "(need >= 600)" in text and "not run yet" in text and "/nowhere" not in text


def test_sealed_output_is_neither_shown_nor_kept(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--write-sealed-once") == 0
    shown = capsys.readouterr()
    assert SECRET not in shown.out + shown.err
    assert SECRET not in F.RECORD.read_text() + F.RECORD_MD.read_text()
    kept = step(F.SEALED_BUILD)["lines"]
    assert len(kept) == 12 and all(F.matches((F.HASH_LINE, F.GATE_LINE), line) for line in kept)
    # shown at once: the four hash lines, and not the gate lines, which come with the gate record
    build_part = shown.out.split(f"[{F.SEALED_BUILD}]")[1].split(f"[{F.COUNTS}]")[0]
    assert build_part.count(" sha256 ") == 4 and "Gate 1" not in build_part


@pytest.mark.parametrize("name", [F.SEALED_BUILD, F.COUNTS])
def test_a_failed_sealed_step_shows_the_error_type_only(
    repo: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    knobs(fail=name)
    assert freeze("--write-sealed-once") == 1
    shown = capsys.readouterr()
    assert SECRET not in shown.out + shown.err and "error type: ValueError" in shown.out
    assert SECRET not in F.RECORD.read_text() + F.RECORD_MD.read_text()
    assert step(name)["status"] == "failed" and step(name)["problem"] == "exit status 1"


def test_a_refusal_of_the_counts_only_code_is_shown(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    knobs(refuse="the eligible list is not the expected file")
    assert freeze("--write-sealed-once") == 1
    out = capsys.readouterr().out
    assert "refused: the eligible list is not the expected file" in out and SECRET not in out
    assert record()["status"] == "failed" and step(F.POWER)["status"] == F.NOT_RUN
    assert record()["tables"]["sealed"][F.SEALED_TEST] == sha(sealed_folder() / F.SEALED_TEST)


def test_run_stops_at_the_first_failure(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    knobs(fail=F.OPEN_BUILD)
    assert freeze("--write-sealed-once") == 1
    rec = record()
    assert rec["status"] == "failed"
    assert [e["status"] for e in rec["steps"]] == ["ok", "ok", "ok", "failed", *[F.NOT_RUN] * 7]
    assert not sealed_folder().exists()
    assert "code" not in rec and set(rec["tables"]["sealed"].values()) == {F.NOT_RUN}
    out = capsys.readouterr().out
    assert f"FAILED at [{F.OPEN_BUILD}]: exit status 1" in out and "a cell reads SECRET" in out
    assert "The run did not finish." in F.RECORD_MD.read_text()
    # nothing sealed was started, so the freeze run can be tried again
    knobs()
    assert freeze("--write-sealed-once") == 0


# --------------------------------------------------------------------------------------------
# Refusals before the first step
# --------------------------------------------------------------------------------------------


def test_key_like_names() -> None:
    env = {
        "OPENROUTER_API_KEY": "x",
        "GEMINI_API_KEY": "x",
        "XAI_API_KEY": "",
        "provider_apikey": "x",
        "SOME_API_TOKEN": "x",
        "AWS_SECRET_KEY": "x",
        "PATH": "/bin",
        "KEYBOARD": "us",
        "EDITOR_REQUIRE_TOKEN": "x",
    }
    assert F.key_like(env) == [
        "AWS_SECRET_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "SOME_API_TOKEN",
        "provider_apikey",
    ]


@pytest.mark.parametrize("flag", ["--open-only", "--write-sealed-once"])
def test_an_api_key_in_the_environment_refuses(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    assert freeze(flag, rt=runtime(env={"GEMINI_API_KEY": "not-a-real-key"})) == 1
    out = capsys.readouterr().out
    assert "refused: the environment holds GEMINI_API_KEY" in out and "not-a-real-key" not in out
    assert not F.RECORD.exists() and not F.OPEN_TABLES[0].exists()


@pytest.mark.parametrize("name", list(F.PINNED))
def test_a_file_without_the_hash_the_plan_states_refuses(
    repo: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    path = F.PINNED[name][0]
    stated = sha(path)[:16]
    put(path, path.read_text() + "changed\n")
    assert freeze("--write-sealed-once") == 1
    assert f"refused: {name}: the plan states {stated}, the file has {sha(path)[:16]}" in (
        capsys.readouterr().out
    )
    assert not F.RECORD.exists() and not F.OPEN_TABLES[0].exists()


def test_a_plan_that_states_no_hash_refuses(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stated = F.stated_pins(F.PLAN.read_text())["uv.lock"]
    put(F.PLAN, F.PLAN.read_text().replace(f"`{stated}`", "to come"))
    assert freeze("--open-only") == 1
    assert "refused: PLAN.md section 17 states no hash for uv.lock" in capsys.readouterr().out


def test_freeze_run_needs_committed_files(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    asked: list[str] = []

    def dirty(paths: list[str]) -> list[str]:
        asked.extend(paths)
        return [" M analysis/coling/corpus.py", "?? analysis/coling/dataset.py"]

    assert freeze("--write-sealed-once", rt=runtime(dirty=dirty)) == 1
    out = capsys.readouterr().out
    assert "refused: not committed: M analysis/coling/corpus.py" in out
    assert "refused: not committed: ?? analysis/coling/dataset.py" in out
    assert not F.RECORD.exists() and not sealed_folder().exists()
    assert {(F.HERE / name).as_posix() for name in (*F.CODE, *F.CODE_OTHER)} <= set(asked)
    assert {p.as_posix() for p in (F.GUIDE, F.MODELS, F.LOCK, F.MANIFEST, F.STRINGS)} <= set(asked)
    # git that cannot answer is a refusal too
    assert freeze("--write-sealed-once", rt=runtime(dirty=lambda paths: None)) == 1
    assert "git could not say" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--open-only", "--write-sealed-once"])
def test_a_record_of_a_started_sealed_build_refuses_both_runs(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    assert freeze("--write-sealed-once") == 0
    before = F.RECORD.read_bytes(), sha(sealed_folder() / F.SEALED_TEST)
    capsys.readouterr()
    knobs(sealed_extra="another build")
    assert freeze(flag) == 1
    assert "started the sealed build, which is run once" in capsys.readouterr().out
    assert (F.RECORD.read_bytes(), sha(sealed_folder() / F.SEALED_TEST)) == before


def test_a_sealed_build_that_failed_is_not_tried_again(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    knobs(fail=F.SEALED_BUILD)
    assert freeze("--write-sealed-once") == 1
    assert F.sealed_started(record()) and step(F.SEALED_BUILD)["status"] == "failed"
    knobs()
    assert freeze("--write-sealed-once") == 1
    assert freeze("--continue-after-sealed") == 1
    out = capsys.readouterr().out
    assert "not the record of a freeze run whose sealed build finished" in out


def test_the_record_is_written_before_the_sealed_build_starts(repo: Path) -> None:
    seen: list[dict] = []

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        if command[2] == F.SEALED_BUILD:
            seen.append(record())
        return F.run_command(command, environ)

    assert freeze("--write-sealed-once", rt=replace(runtime(), run=run)) == 0
    assert seen[0]["status"] == "running" and F.sealed_started(seen[0])
    assert [e["status"] for e in seen[0]["steps"]] == [*["ok"] * 8, "started"]


@pytest.mark.parametrize("flag", list(F.MODE_FLAGS.values())[:3])
def test_a_record_that_cannot_be_read_is_not_written_over(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    put(F.RECORD, "{ cut off")
    assert freeze(flag) == 1
    assert "cannot be read as a record" in capsys.readouterr().out
    assert F.RECORD.read_text() == "{ cut off" and not F.OPEN_TABLES[0].exists()


def test_freeze_run_notes_a_draft_guide_and_a_missing_rehearsal(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--open-only") == 0
    capsys.readouterr()
    assert freeze("--write-sealed-once", "--dry-run") == 0
    assert freeze("--write-sealed-once") == 0
    assert "note: " not in capsys.readouterr().out  # v1, nothing pending, rehearsed


def test_freeze_run_goes_on_after_its_notes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    put(F.GUIDE, "# Guide\n\n**Version v1 draft, 1 October 2026.** Text.\n")
    knobs(pending=["D1", "D3"])
    assert freeze("--write-sealed-once") == 0
    out = capsys.readouterr().out
    assert "note: the guide's version line says 'v1 draft'" in out
    assert "note: no complete rehearsal (--open-only) of the present code is on record" in out
    assert "note: literal-v1 still waits for D1, D3" in out
    assert record()["annotation"]["guide"]["version"] == "v1 draft"


def test_a_rehearsal_of_other_code_is_noted(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--open-only") == 0
    put(F.HERE / "dataset.py", "# changed after the rehearsal\n")
    capsys.readouterr()
    assert freeze("--write-sealed-once") == 0
    assert "note: no complete rehearsal" in capsys.readouterr().out


def test_a_counts_file_already_there_refuses_before_anything_is_built(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(F.SEALED_COUNTS, "{}")
    assert freeze("--write-sealed-once") == 1
    assert "the counts-only code runs once" in capsys.readouterr().out
    assert not sealed_folder().exists() and not F.RECORD.exists()


@pytest.mark.parametrize("flag", ["--open-only", "--write-sealed-once"])
def test_a_cutoff_of_another_month_refuses(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    assert freeze(flag, "--cutoff", "2024-12-31") == 1
    assert "refused: --cutoff 2024-12-31 is not a day of 2023-12" in capsys.readouterr().out
    assert not F.RECORD.exists() and not F.OPEN_TABLES[0].exists()
    # another day of the month is the same cutoff, and is passed on as given
    assert freeze(flag, "--cutoff", "2023-12-01") == 0
    assert record()["inputs"]["cutoff"] == "2023-12-01"
    assert 'cutoff="2023-12-01"' in step(F.OPEN_BUILD)["command"]
    assert F.check_cutoff(F.CUTOFF) == [] and F.check_cutoff("2023-11-30") != []


def test_a_hashed_input_that_is_missing_or_ignored_refuses(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (F.HERE / "gbm.py").unlink()
    ignored = runtime(dirty=lambda paths: ["!! analysis/coling/power.py"])
    assert freeze("--write-sealed-once", rt=ignored) == 1
    out = capsys.readouterr().out
    assert "refused: not on disk: analysis/coling/gbm.py" in out
    assert "refused: not committed: !! analysis/coling/power.py" in out
    assert not F.RECORD.exists() and not sealed_folder().exists()


def test_git_is_asked_about_untracked_and_ignored_files(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, ...]] = []

    def git(*args: str) -> str:
        asked.append(args)
        return " M a.py\n?? b.py\n!! c.py\n"

    monkeypatch.setattr(F, "git", git)
    assert F.uncommitted(["a.py", "b.py", "c.py"]) == [" M a.py", "?? b.py", "!! c.py"]
    assert asked == [
        (
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignored",
            "--",
            "a.py",
            "b.py",
            "c.py",
        )
    ]
    monkeypatch.setattr(F, "git", lambda *args: None)
    assert F.uncommitted(["a.py"]) is None
    monkeypatch.setattr(F, "git", lambda *args: "")
    assert F.uncommitted(["a.py"]) == []


# --------------------------------------------------------------------------------------------
# One sealed build: the lock, the mark, and a run that is killed
# --------------------------------------------------------------------------------------------


def killed_at(name: str, after: bool = False) -> F.Runtime:
    """A runtime whose run is stopped, as by a kill, at one step: before the step is launched,
    or (``after``) when it has run and nothing of it has been recorded yet."""

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        if command[2] == name and after:
            F.run_command(command, environ)
        if command[2] == name:
            raise KeyboardInterrupt
        return F.run_command(command, environ)

    return replace(runtime(), run=run)


@pytest.mark.parametrize("flag", list(F.MODE_FLAGS.values()))
def test_a_run_under_way_refuses_every_mode(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    put(F.RUN_LOCK, "--open-only, process 1\n")
    assert freeze(flag) == 1
    assert f"refused: {F.RUN_LOCK.as_posix()} is there: another run is under way" in (
        capsys.readouterr().out
    )
    assert F.RUN_LOCK.read_text() == "--open-only, process 1\n"  # not this run's to remove
    assert not F.RECORD.exists() and not F.OPEN_TABLES[0].exists() and not sealed_folder().exists()
    assert not Path("fake/strings_written").exists()


def test_the_lock_is_held_while_a_run_lasts(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    held: list[str] = []
    second: list[int] = []

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        held.append(F.RUN_LOCK.read_text())
        if command[2] == F.DATASET:  # a second terminal, while the first run is at work
            second.append(freeze("--write-sealed-once"))
        return F.run_command(command, environ)

    assert freeze("--write-sealed-once", rt=replace(runtime(), run=run)) == 0
    assert second == [1] and "another run is under way" in capsys.readouterr().out
    assert len(held) == len(ORDER)
    assert all(text.startswith("--write-sealed-once, process ") for text in held)
    assert not F.RUN_LOCK.exists() and record()["status"] == "complete"
    # it is removed after a refusal, after a failed run and after a run that was stopped
    assert freeze("--write-sealed-once") == 1 and not F.RUN_LOCK.exists()
    knobs(fail=F.FORMS)
    assert freeze("--continue-after-sealed") == 1 and not F.RUN_LOCK.exists()
    knobs()
    with pytest.raises(KeyboardInterrupt):
        freeze("--continue-after-sealed", rt=killed_at(F.POWER))
    assert not F.RUN_LOCK.exists()


def test_the_mark_is_made_before_the_sealed_build_and_stays(repo: Path) -> None:
    there: dict[str, bool] = {}

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        there[command[2]] = F.SEALED_MARK.exists()
        return F.run_command(command, environ)

    assert freeze("--write-sealed-once", rt=replace(runtime(), run=run)) == 0
    assert there[F.DATASET] is False and there[F.SEALED_BUILD] is True
    mark = json.loads(F.SEALED_MARK.read_text())
    assert mark["started"] < step(F.SEALED_BUILD)["started"]
    assert (mark["commit"], mark["cutoff"], mark["record"]) == (
        "0123abc",
        F.CUTOFF,
        F.RECORD.as_posix(),
    )
    # beside the sealed folder, not in it, and not among the files the record hashes
    assert F.SEALED_MARK.parent == sealed_folder().parent and not F.in_sealed_folder(F.SEALED_MARK)
    assert F.SEALED_MARK.as_posix() not in record()["outputs"]
    before = F.SEALED_MARK.read_bytes()
    assert freeze("--continue-after-sealed") == 0 and freeze("--verify-rerun") == 0
    assert F.SEALED_MARK.read_bytes() == before


def test_no_mark_without_a_sealed_build(repo: Path) -> None:
    assert freeze("--dry-run") == 0 and freeze("--open-only") == 0
    knobs(fail=F.DATASET)
    assert freeze("--write-sealed-once") == 1
    assert not F.SEALED_MARK.exists() and not sealed_folder().exists()
    assert F.sealed_mark() is None


@pytest.mark.parametrize("flag", ["--open-only", "--write-sealed-once"])
def test_the_mark_refuses_a_second_build_when_the_record_is_gone_or_edited(
    repo: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    assert freeze("--write-sealed-once") == 0
    sealed_before = sha(sealed_folder() / F.SEALED_TEST)
    for path in (F.RECORD, F.RECORD_MD, F.SEALED_COUNTS):
        path.unlink()
    knobs(sealed_extra="another build")
    capsys.readouterr()
    assert freeze(flag) == 1
    said = f"refused: {F.SEALED_MARK.as_posix()} is there: a sealed build was started (on 2026-"
    assert said in capsys.readouterr().out
    assert not F.RECORD.exists()
    # a record made to look like a rehearsal's does not help
    looks_open = {"mode": F.OPEN_ONLY, "status": "complete", "steps": [], "tables": {"sealed": {}}}
    put(F.RECORD, json.dumps(looks_open))
    assert not F.sealed_started(looks_open) and freeze(flag) == 1
    # nor does a mark that was emptied
    put(F.SEALED_MARK, "")
    assert F.sealed_mark() == "not readable" and freeze(flag) == 1
    assert "a day the mark does not give" in capsys.readouterr().out
    assert sha(sealed_folder() / F.SEALED_TEST) == sealed_before
    assert json.loads(F.RECORD.read_text()) == looks_open


def test_a_mark_made_by_another_run_stops_this_one_before_the_sealed_build(repo: Path) -> None:
    assert freeze("--open-only") == 0
    before = F.RECORD.read_bytes()

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        if command[2] == F.DATASET:  # another checkout that shares the sealed folder
            put(F.SEALED_MARK, '{"started": "elsewhere"}')
        if command[2] == F.SEALED_BUILD:
            raise AssertionError("the sealed build must not start")
        return F.run_command(command, environ)

    with pytest.raises(SystemExit, match="a sealed build was started by another run"):
        freeze("--write-sealed-once", rt=replace(runtime(), run=run))
    assert F.RECORD.read_bytes() == before and not sealed_folder().exists()
    assert F.SEALED_MARK.read_text() == '{"started": "elsewhere"}' and not F.RUN_LOCK.exists()


def test_a_sealed_build_that_was_killed_is_known_and_not_run_again(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(KeyboardInterrupt):
        freeze("--write-sealed-once", rt=killed_at(F.SEALED_BUILD, after=True))
    rec = record()
    assert rec["status"] == "running" and step(F.SEALED_BUILD)["status"] == "started"
    assert set(rec["tables"]["sealed"].values()) == {F.NOT_RUN}  # the hashes were not recorded
    assert F.sealed_started(rec) and F.SEALED_MARK.exists() and not F.RUN_LOCK.exists()
    before = F.RECORD.read_bytes(), sha(sealed_folder() / F.SEALED_TEST)
    knobs(sealed_extra="another build")
    for flags in (
        ["--write-sealed-once"],
        ["--open-only"],
        ["--continue-after-sealed"],
        ["--continue-after-sealed", F.COUNTS_AGAIN],
        ["--verify-rerun"],
    ):
        assert freeze(*flags) == 1, flags
    assert (F.RECORD.read_bytes(), sha(sealed_folder() / F.SEALED_TEST)) == before
    assert capsys.readouterr().out.count("refused: ") >= 5


def test_a_kill_during_power_keeps_the_counts_that_were_taken(repo: Path) -> None:
    with pytest.raises(KeyboardInterrupt):
        freeze("--write-sealed-once", rt=killed_at(F.POWER))
    rec = record()
    assert rec["status"] == "running"
    assert [e["status"] for e in rec["steps"]] == ["ok"] * (len(ORDER) - 1)
    assert rec["tables"]["sealed"][F.SEALED_TEST] == sha(sealed_folder() / F.SEALED_TEST)
    counted = F.SEALED_COUNTS.read_bytes()
    ran: list[str] = []

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        ran.append(command[2])
        return F.run_command(command, environ)

    assert freeze("--continue-after-sealed", rt=replace(runtime(), run=run)) == 0
    assert F.COUNTS not in ran and F.SEALED_BUILD not in ran and ran[-1] == F.POWER
    assert F.SEALED_COUNTS.read_bytes() == counted
    rec = record()
    assert rec["status"] == "complete" and rec["inputs"]["counts_again"] is False
    assert [run["status"] for run in rec["inputs"]["earlier_runs"]] == ["running"]


def test_counts_that_stopped_half_way_are_run_again_only_by_the_owner_s_flag(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(KeyboardInterrupt):
        freeze("--write-sealed-once", rt=killed_at(F.COUNTS))
    assert step(F.SEALED_BUILD)["status"] == "ok" and step(F.COUNTS)["status"] == "started"
    before = F.RECORD.read_bytes()
    capsys.readouterr()
    assert freeze("--continue-after-sealed") == 1
    out = capsys.readouterr().out
    assert "the counts-only code was started in the freeze run and did not finish" in out
    assert f"pass {F.COUNTS_AGAIN}" in out
    assert F.RECORD.read_bytes() == before and not F.SEALED_COUNTS.exists()
    assert freeze("--continue-after-sealed", F.COUNTS_AGAIN) == 0
    assert record()["inputs"]["counts_again"] is True and step(F.COUNTS)["status"] == "ok"
    # the record goes on saying so, and the flag is refused once the counts are there
    assert freeze("--continue-after-sealed", F.COUNTS_AGAIN) == 1
    assert f"{F.COUNTS_AGAIN} does not apply" in capsys.readouterr().out
    assert freeze("--continue-after-sealed") == 0
    rec = record()
    assert rec["inputs"]["counts_again"] is True and len(rec["inputs"]["earlier_runs"]) == 2
    assert f"run a second time after it had stopped half way ({F.COUNTS_AGAIN})" in (
        F.RECORD_MD.read_text()
    )


def test_counts_written_before_a_kill_are_not_taken_twice(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(KeyboardInterrupt):
        freeze("--write-sealed-once", rt=killed_at(F.COUNTS, after=True))
    assert step(F.COUNTS)["status"] == "started" and F.SEALED_COUNTS.exists()
    counted = F.SEALED_COUNTS.read_bytes()
    assert freeze("--continue-after-sealed") == 1
    assert freeze("--continue-after-sealed", F.COUNTS_AGAIN) == 1
    assert "the counts-only code runs once" in capsys.readouterr().out
    assert F.SEALED_COUNTS.read_bytes() == counted


def test_which_counts_steps_stopped_half_way() -> None:
    def rec(status: str, started: str | None) -> dict:
        return {"steps": [{"name": F.COUNTS, "status": status, "started": started}]}

    assert F.counts_stopped_half_way(rec("started", None))
    assert F.counts_stopped_half_way(rec("failed", "2026-10-02T00:00:01Z"))
    # finished, never reached, or failed before it was launched (no hash to give it)
    for status, started in (("ok", "t"), (F.NOT_RUN, None), ("failed", None)):
        assert not F.counts_stopped_half_way(rec(status, started))
    assert not F.counts_stopped_half_way(None) and not F.counts_stopped_half_way({"steps": []})


def test_counts_again_goes_with_the_continuation_only(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for flags in (["--open-only"], ["--write-sealed-once"], ["--verify-rerun"], ["--dry-run"], []):
        with pytest.raises(SystemExit):
            freeze(*flags, F.COUNTS_AGAIN)
    assert f"{F.COUNTS_AGAIN} goes with --continue-after-sealed" in capsys.readouterr().err
    assert not F.RECORD.exists() and not F.RUN_LOCK.exists()
    assert freeze("--continue-after-sealed", F.COUNTS_AGAIN, "--dry-run") == 0


def test_a_terminal_that_has_gone_away_does_not_stop_the_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Gone:
        def write(self, text: str) -> int:
            raise BrokenPipeError

        def flush(self) -> None:
            raise BrokenPipeError

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", Gone())
        status = freeze("--write-sealed-once")
    rec = record()
    assert status == 0 and rec["status"] == "complete"
    assert rec["tables"]["sealed"][F.SEALED_TEST] == sha(sealed_folder() / F.SEALED_TEST)


# --------------------------------------------------------------------------------------------
# Checks after a step
# --------------------------------------------------------------------------------------------


def test_a_changed_availability_list_stops_the_run_and_is_put_back(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = F.STRINGS.read_bytes()
    knobs(change_strings=True)
    assert freeze("--write-sealed-once") == 1
    assert Path("fake/strings_written").exists()  # the list was written again, with other bytes
    assert F.STRINGS.read_bytes() == before
    problem = step(F.STRING_LIST)["problem"]
    assert (
        "availability_strings.csv, which must keep its bytes" in problem and "put back" in problem
    )
    assert [e["status"] for e in record()["steps"]][:3] == ["ok", "failed", F.NOT_RUN]
    assert not F.OPEN_TABLES[0].exists() and not sealed_folder().exists()
    assert not F.SEALED_MARK.exists()
    assert f"FAILED at [{F.STRING_LIST}]" in capsys.readouterr().out
    # the list as checked: the run goes through
    knobs()
    assert freeze("--write-sealed-once") == 0
    assert F.STRINGS.read_bytes() == before and step(F.STRING_LIST)["status"] == "ok"


def test_the_flags_of_the_counts_only_code_are_one_constant(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(F, "COUNTS_FLAGS", ())
    assert freeze("--write-sealed-once") == 0
    assert "--gate-observable" not in step(F.COUNTS)["command"]
    listed = record()["counts"]["gate1"]["eligible_list"]
    assert listed["thresholds"]["observable"] == {"count": None, "need": 250, "met": None}
    assert listed["thresholds"]["statements"]["met"] is True and listed["passes"] is None


@pytest.mark.parametrize(
    ("value", "noted"),
    [(90, False), (">105", False), ("<5", True), ("withheld", True)],
)
def test_a_scoreable_count_that_gives_power_no_number_is_noted(
    repo: Path, capsys: pytest.CaptureFixture[str], value: object, noted: bool
) -> None:
    knobs(scoreable_episodes=value)
    assert freeze("--write-sealed-once") == 0
    out = capsys.readouterr().out
    assert f"e3_eligible_test.scoreable_episodes: {value}" in out
    assert (f"note: scoreable_episodes is {value}: the power step needs" in out) == noted
    assert "note: scoreable_statements" not in out
    # power is run as it stands: it reads the two counts from the counts file itself
    assert json.loads((F.OUT / "power.json").read_text()) == {
        "arguments": ["-m", "analysis.coling.power"]
    }


def test_a_list_that_would_change_stops_the_run_and_is_put_back(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lists = [F.SAMPLES / f"sample_{name}.csv" for name in F.FIRST_DRAW]
    before = [path.read_bytes() for path in lists]
    put(F.OUT / "audit" / "manifest.json", '{"draws": 0}')
    knobs(change_list=True)
    assert freeze("--open-only") == 1
    assert [path.read_bytes() for path in lists] == before
    assert (F.OUT / "audit" / "manifest.json").read_text() == '{"draws": 0}'
    assert "sample_pilot.csv, which must keep its bytes" in step(F.SAMPLE_LISTS)["problem"]
    assert step(F.DATASET)["status"] == F.NOT_RUN
    assert f"FAILED at [{F.SAMPLE_LISTS}]" in capsys.readouterr().out


def test_a_list_changed_by_a_step_that_fails_is_put_back_too(repo: Path) -> None:
    pilot = F.SAMPLES / "sample_pilot.csv"
    before = pilot.read_bytes()
    knobs(change_list="and fail")
    assert freeze("--open-only") == 1
    assert pilot.read_bytes() == before
    problem = step(F.SAMPLE_LISTS)["problem"]
    assert problem.startswith("exit status 1; the step changed ") and "put back" in problem


@pytest.mark.parametrize("name", F.FIRST_DRAW)
def test_each_of_the_four_lists_is_compared(repo: Path, name: str) -> None:
    lists = [F.SAMPLES / f"sample_{n}.csv" for n in F.FIRST_DRAW]
    before = [path.read_bytes() for path in lists]
    # the made-up step changes the first list, or the last: every list is on the fixed side
    knobs(change_list="the last" if name == F.FIRST_DRAW[-1] else True)
    wanted = lists[-1] if name == F.FIRST_DRAW[-1] else lists[0]
    assert freeze("--open-only") == 1
    assert f"{wanted.name}, which must keep its bytes" in step(F.SAMPLE_LISTS)["problem"]
    assert [path.read_bytes() for path in lists] == before
    fixed = next(s for s in F.steps("x") if s.name == F.SAMPLE_LISTS).fixed
    assert (F.SAMPLES / f"sample_{name}.csv").as_posix() in fixed and len(fixed) == 4


def test_counts_of_another_sealed_file_fail_the_step(repo: Path) -> None:
    knobs(counted_file="5" * 64)
    assert freeze("--write-sealed-once") == 1
    assert step(F.COUNTS)["problem"] == (
        "the counts file names another sealed file than the one the build printed"
    )
    assert step(F.POWER)["status"] == F.NOT_RUN and record()["status"] == "failed"
    # the counts file is there, so the counts-only code is not run again
    assert freeze("--continue-after-sealed", F.COUNTS_AGAIN) == 1


def test_a_list_that_is_not_on_disk_stops_the_run(repo: Path) -> None:
    (F.SAMPLES / "sample_reserve.csv").unlink()
    assert freeze("--open-only") == 1
    assert "not on disk" in step(F.SAMPLE_LISTS)["problem"]
    assert step(F.SAMPLE_LISTS)["started"] is None


def test_the_dataset_builder_must_have_read_the_lists(repo: Path) -> None:
    knobs(lists_missing=True)
    assert freeze("--open-only") == 1
    problem = step(F.DATASET)["problem"]
    assert "first-draw lists not read: pilot" in problem
    assert "subsets not final: reference_check" in problem


@pytest.mark.parametrize(("changed", "status"), [(0, 0), (3, 1)])
def test_changed_rule_readings_stop_the_run(repo: Path, changed: int, status: int) -> None:
    knobs(changed_readings=changed)
    assert freeze("--open-only") == status
    entry = step(F.FORM_CHECK)
    assert entry["exit_status"] == 1  # stale outputs alone are expected after a new build
    assert entry.get("problem") == (
        "3 rule readings changed on pairs shared with the old golden file" if changed else None
    )


def test_a_form_check_that_stops_on_an_error_is_not_taken_for_stale_outputs(repo: Path) -> None:
    knobs(fail=F.FORM_CHECK)
    assert freeze("--open-only") == 1
    entry = step(F.FORM_CHECK)
    assert entry["exit_status"] == 1  # the status of stale outputs, and of a traceback
    assert entry["problem"] == "the check stopped before it compared the outputs"
    assert step(F.FORMS)["status"] == F.NOT_RUN


def test_a_builder_that_gives_other_bytes_the_second_time_fails(repo: Path) -> None:
    knobs(drift=True)
    assert freeze("--write-sealed-once") == 1
    assert "does not give the same bytes twice" in step(F.SEALED_BUILD)["problem"]
    # the sealed hashes are in the record all the same: they were printed
    assert record()["tables"]["sealed"][F.SEALED_TEST] == sha(sealed_folder() / F.SEALED_TEST)


def test_a_sealed_build_with_other_gate_counts_fails(repo: Path) -> None:
    knobs(sealed_episodes=121)
    assert freeze("--write-sealed-once") == 1
    assert step(F.SEALED_BUILD)["problem"] == (
        "the Gate 1 counts of this build are not those of the open build"
    )
    assert step(F.COUNTS)["status"] == F.NOT_RUN and not F.SEALED_COUNTS.exists()
    assert "  shortage episodes 121 (need >= 100)" in step(F.SEALED_BUILD)["lines"]
    # the build is used up all the same, and there is nothing to go on from
    assert freeze("--write-sealed-once") == 1 and freeze("--continue-after-sealed") == 1


def test_a_report_without_gate_counts_stops_before_the_sealed_build(repo: Path) -> None:
    put(Path("fake/step.py"), FAKE.replace("(need >= 100)", "(at least 100)"))
    assert freeze("--write-sealed-once") == 1
    assert "four Gate 1 counts" in step(F.OPEN_BUILD)["problem"]
    assert step(F.SEALED_BUILD)["status"] == F.NOT_RUN and not sealed_folder().exists()


def test_gate_counts_that_miss_a_threshold_are_reported(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    knobs(post_cutoff=149)
    assert freeze("--write-sealed-once") == 0
    builder = record()["counts"]["gate1"]["builder_gate_set"]
    assert builder["passes"] is False
    assert builder["thresholds"]["post_cutoff"] == {"count": 149, "need": 150, "met": False}
    assert "builder's gate set: NOT met" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("value", "need", "met"),
    [
        (600, 600, True),
        (599, 600, False),
        ("<5", 100, False),
        (">155", 150, True),
        (">148", 150, None),
        (">149", 150, True),
        ("withheld", 150, None),
        (None, 150, None),
        (True, 1, None),
    ],
)
def test_meets(value: object, need: int, met: bool | None) -> None:
    assert F.meets(value, need) is met


def test_count_lines_show_counts_and_hashes_only() -> None:
    nested = {
        "about": "text 2024-02-01",
        "inputs": {"sealed": {"file": "outcomes_test.csv.gz", "sha256": "a" * 64}},
        "e3": {"eligible": 650, "scoreable": "<5", "other": ">10", "slice": "withheld"},
        "models": ["grok-4.20"],
        "flag": True,
        "share": 0.5,
    }
    assert F.count_lines(nested) == [
        f"inputs.sealed.sha256: {'a' * 64}",
        "e3.eligible: 650",
        "e3.scoreable: <5",
        "e3.other: >10",
        "e3.slice: withheld",
    ]


# --------------------------------------------------------------------------------------------
# Going on after the sealed build
# --------------------------------------------------------------------------------------------


def test_a_failure_before_the_sealed_build_leaves_it_unused(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (F.FORM_CHECK, F.FORMS, F.SAMPLE_LISTS, F.DATASET):
        knobs(fail=name)
        assert freeze("--write-sealed-once") == 1
        assert not sealed_folder().exists() and not F.sealed_started(record())
        assert freeze("--continue-after-sealed") == 1  # there is nothing to go on from
    knobs()
    assert freeze("--write-sealed-once") == 0


@pytest.mark.parametrize("failing", [F.COUNTS, F.POWER])
def test_continue_after_a_failed_step_builds_nothing_again(
    repo: Path, capsys: pytest.CaptureFixture[str], failing: str
) -> None:
    knobs(fail=failing)
    assert freeze("--write-sealed-once") == 1
    first = record()
    sealed_bytes = (sealed_folder() / F.SEALED_TEST).read_bytes()
    knobs(sealed_extra="a build that must not happen")
    ran: list[str] = []

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        ran.append(command[2])
        return F.run_command(command, environ)

    flags = ["--continue-after-sealed", *([F.COUNTS_AGAIN] if failing == F.COUNTS else [])]
    assert freeze(*flags, rt=replace(runtime(), run=run)) == 0
    assert F.OPEN_BUILD not in ran and F.SEALED_BUILD not in ran
    kept = {F.OPEN_BUILD, F.SEALED_BUILD} | ({F.COUNTS} if failing == F.POWER else set())
    assert ran == [name for name in ORDER if name not in kept]
    assert (sealed_folder() / F.SEALED_TEST).read_bytes() == sealed_bytes
    rec = record()
    assert (rec["mode"], rec["status"]) == (F.FREEZE, "complete")
    assert rec["inputs"]["counts_again"] is (failing == F.COUNTS)
    earlier = rec["inputs"]["earlier_runs"]
    assert [run["status"] for run in earlier] == ["failed"]
    assert earlier[0]["started"] == first["inputs"]["started"] and earlier[0]["commit"] == "0123abc"
    assert "Written again by --continue-after-sealed. Earlier runs: started " in (
        F.RECORD_MD.read_text()
    )
    assert ("run a second time" in F.RECORD_MD.read_text()) == (failing == F.COUNTS)
    assert rec["tables"]["sealed"] == first["tables"]["sealed"]
    assert step(F.SEALED_BUILD) == next(e for e in first["steps"] if e["name"] == F.SEALED_BUILD)
    assert rec["counts"]["gate1"]["builder_gate_set"]["passes"] is True


def test_continue_keeps_the_sealed_counts_and_takes_up_a_changed_guide(repo: Path) -> None:
    assert freeze("--write-sealed-once") == 0
    first = record()
    put(F.GUIDE, F.GUIDE.read_text() + "\nA sentence added after the freeze.\n")
    knobs(draws=2, pending=["D1"])
    ran: list[str] = []

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        ran.append(command[2])
        return F.run_command(command, environ)

    assert freeze("--continue-after-sealed", rt=replace(runtime(), run=run)) == 0
    assert F.COUNTS not in ran and F.SEALED_BUILD not in ran and F.DATASET in ran
    rec = record()
    assert (
        rec["annotation"]["guide"]["sha256"]
        == sha(F.GUIDE)
        != first["annotation"]["guide"]["sha256"]
    )
    assert rec["prompts"]["templates"]["literal-v1"]["pending"] == ["D1"]
    assert step(F.COUNTS) == next(e for e in first["steps"] if e["name"] == F.COUNTS)
    assert rec["tables"]["sealed"] == first["tables"]["sealed"]
    assert rec["counts"]["gate1"]["eligible_list"] == first["counts"]["gate1"]["eligible_list"]


def test_continue_stops_when_the_eligible_list_is_no_longer_the_counted_one(repo: Path) -> None:
    assert freeze("--write-sealed-once") == 0
    put(F.GUIDE, F.GUIDE.read_text() + "\n## Appendix A\n\nOne more example.\n")
    assert freeze("--continue-after-sealed") == 1
    assert "no longer the one the sealed counts were taken on" in step(F.DATASET)["problem"]
    assert "decision for the owner" in step(F.DATASET)["problem"]
    assert record()["status"] == "failed" and step(F.COUNTS)["status"] == "ok"


def test_continue_needs_the_open_tables_of_the_freeze_run(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--write-sealed-once") == 0
    before = F.RECORD.read_bytes()
    F.OPEN_TABLES[0].write_bytes(b"another table")
    assert freeze("--continue-after-sealed") == 1
    assert "events.csv.gz on disk is not the table of the freeze run" in capsys.readouterr().out
    assert F.RECORD.read_bytes() == before


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("corpus.py", "corpus.py is not the file the sealed build ran"),
        ("manifest.py", "manifest.py is not the file the sealed build ran"),
    ],
)
def test_continue_needs_the_builder_of_the_sealed_build(
    repo: Path, capsys: pytest.CaptureFixture[str], name: str, said: str
) -> None:
    knobs(fail=F.POWER)
    assert freeze("--write-sealed-once") == 1
    assert record()["carried"]["built_with"] == {n: sha(F.HERE / n) for n in F.BUILD_CODE}
    before = F.RECORD.read_bytes()
    put(F.HERE / name, "# changed after the sealed build\n")
    knobs()
    assert freeze("--continue-after-sealed") == 1
    assert f"refused: {said}" in capsys.readouterr().out
    assert F.RECORD.read_bytes() == before


def test_continue_needs_the_capture_set_of_the_sealed_build(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--write-sealed-once") == 0
    # the manifest and the plan are changed together, so the plan's own check passes
    put(F.MANIFEST, F.MANIFEST.read_text() + "20260927000000.csv,20260927000000,1,00\n")
    put(F.PLAN, plan_text())
    assert F.check_pins(F.stated_pins(F.PLAN.read_text())) == []
    assert freeze("--continue-after-sealed") == 1
    out = capsys.readouterr().out
    assert "capture_manifest.csv does not have the hash the plan stated at the freeze run" in out


@pytest.mark.parametrize("name", ["dataset.py", "sealed_counts.py", "forms.py"])
def test_continue_fails_when_the_code_behind_the_sealed_counts_changed(
    repo: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    assert freeze("--write-sealed-once") == 0
    put(F.HERE / name, "# changed after the counts were taken\n")
    assert F.counts_drift(F.read_json(F.SEALED_COUNTS)) == [name]
    assert freeze("--continue-after-sealed") == 1
    assert f"FAILED: changed since the sealed counts were taken: {name}" in capsys.readouterr().out
    rec = record()
    assert rec["status"] == "failed" and "decision for the owner" in rec["problems"][0]
    assert all(e["status"] == "ok" for e in rec["steps"])
    assert f"changed since the sealed counts were taken: {name}" in F.RECORD_MD.read_text()


def test_counts_drift_names_changed_inputs(repo: Path) -> None:
    assert F.counts_drift(None) == [] and F.after_steps([]) == []
    assert freeze("--write-sealed-once") == 0
    counts = F.read_json(F.SEALED_COUNTS)
    assert F.counts_drift(counts) == []
    put(F.ELIGIBLE, "statement_group_id\ns9\n")
    put(F.MANIFEST, "another manifest\n")
    assert F.counts_drift(counts) == ["eligible_e3.csv", "capture_manifest.csv"]


def test_continue_needs_a_freeze_record(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--continue-after-sealed") == 1
    assert freeze("--open-only") == 0
    assert freeze("--continue-after-sealed") == 1
    assert capsys.readouterr().out.count("not the record of a freeze run whose sealed build") == 2
    assert record()["mode"] == F.OPEN_ONLY


# --------------------------------------------------------------------------------------------
# The one rerun
# --------------------------------------------------------------------------------------------


def test_verify_rerun_agrees_and_runs_once(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--write-sealed-once") == 0
    first = record()
    ran: list[str] = []

    def run(command: list[str], environ: dict[str, str]) -> F.Finished:
        ran.append(command[2])
        return F.run_command(command, environ)

    capsys.readouterr()
    assert freeze("--verify-rerun", rt=replace(runtime(), run=run)) == 0
    assert ran == [F.MANIFEST_CHECK, F.SEALED_BUILD]
    shown = capsys.readouterr().out
    assert "both sealed hashes and both open tables of the freeze run" in shown
    assert SECRET not in shown
    rec = record()
    rerun = rec.pop("verify_rerun")
    assert rec == first  # nothing else in the record changed
    assert rerun["matches"] is True and rerun["sealed"] == first["tables"]["sealed"]
    assert rerun["started"] < rerun["finished"]
    assert [e["status"] for e in rerun["steps"]] == ["ok", "ok"]
    assert "both sealed hashes and both open tables as recorded" in F.RECORD_MD.read_text()
    assert SECRET not in F.RECORD.read_text()
    # once only
    assert freeze("--verify-rerun") == 1
    assert "refused: the one rerun was started on" in capsys.readouterr().out
    # and it stays in the record when the run goes on after it
    assert freeze("--continue-after-sealed") == 0
    assert record()["verify_rerun"] == rerun


def test_verify_rerun_reports_a_difference(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--write-sealed-once") == 0
    first = record()
    knobs(sealed_extra="other outcomes")
    assert freeze("--verify-rerun") == 1
    assert "THE RERUN DOES NOT CONFIRM the freeze run" in capsys.readouterr().out
    rec = record()
    assert rec["verify_rerun"]["matches"] is False
    assert rec["verify_rerun"]["sealed"] != first["tables"]["sealed"]
    assert rec["tables"] == first["tables"]  # the freeze run's hashes stay as they were
    assert "A DIFFERENCE" in F.RECORD_MD.read_text()


def test_verify_rerun_sees_other_open_tables(repo: Path) -> None:
    assert freeze("--write-sealed-once") == 0
    knobs(drift=True)
    assert freeze("--verify-rerun") == 1
    rerun = record()["verify_rerun"]
    assert rerun["matches"] is False
    assert "does not give the same bytes twice" in rerun["steps"][1]["problem"]


def test_a_capture_set_that_is_not_the_manifest_s_does_not_use_up_the_rerun(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--write-sealed-once") == 0
    before = F.RECORD.read_bytes(), (sealed_folder() / F.SEALED_TEST).read_bytes()
    knobs(fail=F.MANIFEST_CHECK, sealed_extra="must not be written")
    assert freeze("--verify-rerun") == 1
    assert (
        "refused: the capture set is not the manifest's (exit status 1)" in capsys.readouterr().out
    )
    assert (F.RECORD.read_bytes(), (sealed_folder() / F.SEALED_TEST).read_bytes()) == before
    knobs()
    assert freeze("--verify-rerun") == 0


def test_a_rerun_that_crashes_is_still_the_one_rerun(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--write-sealed-once") == 0
    knobs(fail=F.SEALED_BUILD)
    assert freeze("--verify-rerun") == 1
    shown = capsys.readouterr().out
    assert "THE RERUN DOES NOT CONFIRM" in shown and SECRET not in shown
    rerun = record()["verify_rerun"]
    assert rerun["matches"] is False and rerun["steps"][1]["problem"] == "exit status 1"
    knobs()
    assert freeze("--verify-rerun") == 1
    assert "the one rerun was started on" in capsys.readouterr().out


def test_a_rerun_that_is_killed_is_still_the_one_rerun(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert freeze("--write-sealed-once") == 0
    first = record()
    with pytest.raises(KeyboardInterrupt):
        freeze("--verify-rerun", rt=killed_at(F.SEALED_BUILD))
    rec = record()
    rerun = rec.pop("verify_rerun")
    assert rec == first and rerun["matches"] is None and rerun["finished"] is None
    assert "started 2026-10-02T00:00:" in F.RECORD_MD.read_text()
    assert "not finished" in F.RECORD_MD.read_text() and not F.RUN_LOCK.exists()
    assert freeze("--verify-rerun") == 1
    assert "refused: the one rerun was started on 2026-10-02T00:00:" in capsys.readouterr().out


def test_verify_rerun_refusals(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert freeze("--verify-rerun") == 1  # no record
    assert freeze("--open-only") == 0
    assert freeze("--verify-rerun") == 1  # a rehearsal
    assert capsys.readouterr().out.count("not the record of a complete freeze run") == 2
    assert not sealed_folder().exists()
    assert freeze("--write-sealed-once") == 0
    before = F.RECORD.read_bytes(), (sealed_folder() / F.SEALED_TEST).read_bytes()
    knobs(sealed_extra="must not be written")
    put(F.HERE / "corpus.py", "# another builder\n")
    assert freeze("--verify-rerun") == 1
    assert "refused: corpus.py is not the file the sealed build ran" in capsys.readouterr().out
    put(F.HERE / "corpus.py", "# corpus.py\n")
    assert freeze("--verify-rerun", rt=runtime(dirty=lambda paths: ["?? f"])) == 1
    assert freeze("--verify-rerun", rt=runtime(env={"X_API_KEY": "k"})) == 1
    assert (F.RECORD.read_bytes(), (sealed_folder() / F.SEALED_TEST).read_bytes()) == before


# --------------------------------------------------------------------------------------------
# The plan, the files and the sealed folder
# --------------------------------------------------------------------------------------------


def test_stated_pins_follow_the_words_of_section_17(repo: Path) -> None:
    text = F.PLAN.read_text()
    assert F.stated_pins(text) == {name: sha(path)[:16] for name, (path, _) in F.PINNED.items()}
    assert F.plan_section(text, 17).startswith("## 17. Registration record")
    assert "Amendments" not in F.plan_section(text, 17) and "Before" not in F.plan_section(text, 17)
    assert F.plan_section(text, 18) == ""
    # a hash in the next list item or paragraph is not taken for this file's
    assert (
        F.hash_after("- `rules.py`: to come.\n- `forms.py`: `" + "a" * 16 + "`", r"`rules\.py`")
        is None
    )
    assert F.hash_after("`uv.lock`, hash\n  `" + "b" * 16 + "` on", r"`uv\.lock`") == "b" * 16
    assert F.stated_pins("no section") == dict.fromkeys(F.PINNED)


def test_the_study_plan_states_the_four_hashes() -> None:
    plan = Path(__file__).resolve().parent / "plan" / "PLAN.md"
    pins = F.stated_pins(plan.read_text(encoding="utf-8"))
    assert set(pins) == set(F.PINNED)
    assert all(isinstance(value, str) and len(value) == 16 for value in pins.values()), pins


def test_the_study_plan_lists_the_code_that_the_record_hashes() -> None:
    plan = Path(__file__).resolve().parent / "plan" / "PLAN.md"
    section = F.plan_section(plan.read_text(encoding="utf-8"), 17)
    block = section.split("**Code (hashed at registration).**")[1].split("\n**")[0]
    assert tuple(dict.fromkeys(re.findall(r"`(\w+\.py)`", block))) == F.CODE
    at_f1 = section.split("**At F1:**")[1]
    assert all(f"`{name}`" in at_f1 for name in F.CODE_OTHER)
    assert not set(F.CODE) & set(F.CODE_OTHER) and set(F.BUILD_CODE) <= set(F.CODE)
    inputs = F.hashed_inputs()
    assert {(F.HERE / name).as_posix() for name in (*F.CODE, *F.CODE_OTHER)} <= set(inputs)
    assert len(inputs) == len(set(inputs)) == len(F.CODE) + len(F.CODE_OTHER) + 5


def test_nothing_in_a_sealed_folder_is_opened(repo: Path) -> None:
    hidden = put(sealed_folder() / "outcomes_test.csv.gz", "x")
    for read in (F.sha256_file, F.content_sha256, F.data_rows, F.readable):
        with pytest.raises(SystemExit, match="never opens the sealed folder"):
            read(hidden)
    assert F.read_json(F.OUT / "missing.json") is None
    assert F.sha256_file(F.OUT / "missing.csv") is None
    names = [n for s in F.steps("x") for n in s.writes]
    assert set(F.step_outputs(F.steps("x"))) == {n for n in names if "sealed/" not in n}
    source = inspect.getsource(F)
    assert source.count("external_data/sealed/") == 3  # the docstring and the two names


def test_registered_hashes_name_what_section_17_must_hold(repo: Path) -> None:
    assert freeze("--write-sealed-once") == 0
    labels = F.registered_hashes(record())
    assert {f"code {name}" for name in F.CODE} <= set(labels)
    assert "code power.py" in labels and "code freeze.py" in labels
    assert "code read.py" not in labels  # hashed at F1
    for wanted in (
        "table events.csv.gz (gzip file)",
        "table outcomes_train.csv.gz (decompressed content)",
        "eligible list (file)",
        "secondary list stale (ids)",
        "sample list literal",
        "sample list outcome_audit_train",
        "guide",
        "MODELS.md",
        "template literal-v1",
        "lock file",
        "capture manifest",
        "availability-string list",
    ):
        assert isinstance(labels[wanted], str) and len(labels[wanted]) == 64, wanted
    assert not any("outcomes_test" in label or "uncensored" in label for label in labels)
    assert not set(labels.values()) & set(record()["tables"]["sealed"].values())
    disk = {**F.snapshot(), "environment": F.environment(), "prompts": record()["prompts"]}
    assert F.registered_hashes(disk) == labels


def test_later_lists_are_recorded_when_they_are_on_disk(repo: Path) -> None:
    put(F.SAMPLES_LATER / "sample_dev_prompt.csv", "event_id\ne1\n")
    assert "later_dev_prompt" in F.sample_lists()
    F.OUTCOME_SAMPLE.unlink()
    assert F.sample_lists()["outcome_audit_train"] == {
        "file": F.OUTCOME_SAMPLE.as_posix(),
        "sha256": None,
        "rows": None,
    }


# --------------------------------------------------------------------------------------------
# Against the real modules: what this module reads from them
# --------------------------------------------------------------------------------------------


def test_the_builder_prints_what_the_freeze_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The corpus builder on a synthetic capture set, written to a temporary folder only."""
    from analysis.coling import corpus as C
    from analysis.coling import test_corpus as TC

    caps, out, hidden = tmp_path / "caps", tmp_path / "out", tmp_path / "hidden"
    caps.mkdir()
    for stamp, rows in TC.gate_captures().items():
        TC.write_capture(caps, stamp, rows)
    C.open_build(caps, out, cutoff=F.CUTOFF, check=None)
    opened = capsys.readouterr().out.splitlines()
    args = ["--captures", str(caps), "--out", str(out), "--sealed", str(hidden)]
    assert C.main([*args, "--cutoff", F.CUTOFF], check=None) == 0
    built = capsys.readouterr().out.splitlines()

    values: dict = {}
    assert F.after_open_build(opened, values) == []
    assert F.after_sealed_build(built, values) == []
    assert values["open"] == {p.name: sha(out / p.name) for p in F.OPEN_TABLES}
    assert values["sealed"] == {Path(n).name: sha(hidden / Path(n).name) for n in F.SEALED_TABLES}
    counts = C.gate_counts(C.build_corpus(caps), F.CUTOFF)
    assert F.gate_counts(values["gate_lines"]) == {
        "statements": counts["distinct_statements"],
        "observable": counts["observable31_B_distinct"],
        "episodes": counts["episodes"],
        "post_cutoff": counts["after_cutoff_observable31_B_distinct"],
    }
    assert len(values["gate_lines"]) == 8 and F.GATE_NEEDS == C.GATE_THRESHOLDS
    assert "cutoff" in inspect.signature(C.open_build).parameters
    assert F.CAPTURES == C.CAPTURES_DIR and F.OUT == C.OUT_DIR and F.STRINGS == C.STRINGS_PATH
    assert C.CUTOFF.date().isoformat() == F.CUTOFF == C.cutoff_day(F.CUTOFF).date().isoformat()
    # the availability list: its own command, the default paths, and the same bytes each time
    written = inspect.signature(C.write_availability_strings).parameters
    assert (written["captures"].default, written["path"].default) == (F.CAPTURES, F.STRINGS)
    C.write_availability_strings(caps, out / "strings.csv")
    first = (out / "strings.csv").read_bytes()
    C.write_availability_strings(caps, out / "strings.csv")
    assert (out / "strings.csv").read_bytes() == first and first.startswith(b"string,")


def test_the_command_lines_the_steps_rely_on() -> None:
    from analysis.coling import audit_outcomes as AO
    from analysis.coling import audit_sample as S
    from analysis.coling import dataset as D
    from analysis.coling import forms
    from analysis.coling import manifest as M
    from analysis.coling import sealed_counts as SC

    by_name = {s.name: s for s in F.steps("0123456789abcdef")}
    # the counts-only code: flags, the output file, and where its file holds the gate counts
    values = {"sealed": {F.SEALED_TEST: "a" * 64}, "eligible": "b" * 64}
    args = SC.arguments(F.filled(by_name[F.COUNTS].command, values)[3:])
    assert (args.expect_sha256, args.expect_eligible_sha256) == ("a" * 64, "b" * 64)
    assert args.out == F.SEALED_COUNTS and args.gate_observable is True
    assert args.eligible == F.ELIGIBLE and args.sealed.name == F.SEALED_TEST
    for section, key in (*F.GATE_ON_THE_LIST.values(), F.SCOREABLE):
        assert key in SC.SECTION_KEYS[section], (section, key)
    assert "sealed_outcomes" in SC.FILE_INPUTS and SC.SEALED_FOLDER == F.SEALED_FOLDER
    assert (
        set(F.COUNTED_FILES) <= set(SC.FILE_INPUTS) and "code_sha256" in SC.SECTION_KEYS["inputs"]
    )
    assert all((F.HERE / name).name == Path(path).name for name, path in SC.CODE.items())
    assert tuple(F.COUNTED_FILES.values()) == (SC.ELIGIBLE, SC.EVENTS, SC.MANIFEST)
    assert all(F._MASK.fullmatch(mask) for mask in (f"<{SC.MASK_BELOW}", ">12", SC.WITHHELD))
    assert F.COUNTS_FLAGS == (SC.OBSERVABLE_FLAG,)
    assert {section for section, _ in F.GATE_ON_THE_LIST.values()} == {
        "e3_eligible_test",
        SC.OPTIONAL_KEY,
    }
    assert all(key in SC.SECTION_KEYS[section] for section, key in F.FOR_POWER)
    # one cutoff month in both parts of the gate record, and no cutoff argument to disagree on
    assert SC.CUTOFF_MONTH_ENDS[SC.GATE_MODEL].isoformat() == F.CUTOFF
    with pytest.raises(SystemExit, match="refused: unknown argument"):
        SC.arguments(["--cutoff", F.CUTOFF])
    # the sampler: the four lists, held fixed, where this module looks for them
    drawn = S.parser().parse_args(by_name[F.SAMPLE_LISTS].command[3:])
    assert drawn.command == "draw" and tuple(drawn.fixed) == S.FIRST_SAMPLES == F.FIRST_DRAW
    assert drawn.replace == [] and drawn.out / S.SAMPLES_DIR == F.SAMPLES
    assert drawn.out / S.LATER_DIR == F.SAMPLES_LATER and drawn.guide == F.GUIDE
    assert S.guide_version("**Version v1 draft, 1 October 2026.**") == "v1 draft"
    assert F.guide_version("**Version v1 draft, 1 October 2026.**") == "v1 draft"
    assert (
        F.guide_version("**Version v1, 2 October 2026.**")
        == S.guide_version("**Version v1,")
        == "v1"
    )
    assert AO.file_names("train")["sample"] == F.OUTCOME_SAMPLE.name
    # the dataset builder and the form classifier: files and the line that is read
    assert (D.COUNTS, D.ELIGIBLE, D.SAMPLES) == (F.DATASET_COUNTS, F.ELIGIBLE, F.SAMPLES)
    assert D.FIRST_DRAW == F.FIRST_DRAW and D.STATEMENTS.as_posix() in by_name[F.DATASET].writes
    source = inspect.getsource(forms.main)
    assert "readings changed on shared pairs: " in source
    assert '"up to date"' in source and '"differs from a fresh run: "' in source
    assert all(
        re.search(F.FORM_VERDICT, said) for said in ("up to date", "differs from a fresh run: x")
    )
    assert {forms.COUNTS.as_posix(), forms.GOLDEN.as_posix()} == set(by_name[F.FORMS].writes)
    # the manifest check and its pin
    assert M.MANIFEST == F.MANIFEST and M.SHORT == F.SHORT
    source = inspect.getsource(M.main)
    assert '"--check"' in source and '"--pin"' in source


def test_the_pins_command_and_the_power_outputs() -> None:
    from analysis.coling import power
    from analysis.coling import read as R

    pins = R.template_pins()
    values: dict = {}
    assert F.after_pins(json.dumps(pins, indent=2).splitlines(), values) == []
    assert all(
        {"sha256", "matches_pin", "pending"} <= set(pin) for pin in pins["templates"].values()
    )
    assert R._parser().parse_args(["--print-pins"]).print_pins is True
    assert F.after_pins(["not json"], {}) != []
    by_name = {s.name: s for s in F.steps("x")}
    assert {power.DEV_LOSSES.as_posix(), power.POWER_REPORT.as_posix()} == set(
        by_name[F.POWER].writes
    )
    assert power.SEALED_COUNTS == F.SEALED_COUNTS
    # power takes the two counts of FOR_POWER from the counts file: an integer, or a bound
    # ``>N`` as ``N + 1``; it stops at a count that is withheld or masked as small
    block = {key: 60 for _, key in F.FOR_POWER}
    assert power.registered_scoreable({"e3_eligible_test": block})[:2] == (60, 60)
    bound = dict(zip(block, (">55", ">6"), strict=True))
    assert power.registered_scoreable({"e3_eligible_test": bound})[:2] == (56, 7)
    for masked in ("<5", "withheld"):
        with pytest.raises(ValueError, match="no scoreable number"):
            power.registered_scoreable({"e3_eligible_test": {**block, F.FOR_POWER[1][1]: masked}})
