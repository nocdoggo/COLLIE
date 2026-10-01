"""Tests for the registration check (``plan_check.py``) on small made-up plans and records.

The marker tests use short plan texts written here. The readiness tests work in the temporary
repository of ``test_freeze.py``: its made-up freeze run and its one rerun give a real record
and its Markdown rendering, and a plan that holds that rendering in section 17 is the plan that
is ready. Each test then breaks one thing. No test reads the study's sealed folder; one test
prints the worklist of the study's own draft and checks only that it finds markers, and one
reads the study's template pins.

Covered: the markers and tags found (kinds, lines, sections, the lead-in, the rule sentence, a
tag broken over two lines, a table row, a definition in the opening and a second one of the
same marker, a marker of no known kind or in other letters, ``TBD-at-F1``); the
worklist and its counts by kind and by section; a ready plan; and each reason for "not ready":
a marker or tag left, the draft paragraph, no record, a rehearsal's record, a failed run, a
rerun not run or not agreeing, a hash missing from section 17, a file changed since the freeze,
a pinned file changed together with the plan, a code file the record does not know, a Python
version missing from section 17, a path in a sealed folder, the note on hashes that nothing
vouches for, a list drawn after the freeze, a changed output, a sealed hash missing from
section 17 (with the sealed folder gone, to show that it is not read), sealed counts of
another sealed file or of code changed since, a stated hash that the file does not have, two
hashes stated for the rule reader, a guide that is still a draft, a prompt that waits for a
pilot sentence or does not match its pin.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_plan_check.py -q -p no:cacheprovider
"""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import pytest

from analysis.coling import freeze as F
from analysis.coling import plan_check as P
from analysis.coling import test_freeze as TF

STUDY_PLAN = Path(__file__).resolve().parent / "plan" / "PLAN.md"

DRAFT = """\
# A study plan

**DRAFT (2026-10-01). Not registered.** This file becomes the registration when:

- every **TBD-at-gate** and **TBD-at-registration** marker is replaced by its value;
- every **[owner to confirm]** tag is resolved.

Four markers are used:

- **TBD-at-gate**: depends on the frozen build.
- **TBD-at-registration**: a fact confirmed at its source.
- **TBD-at-F1**: fixed by amendment F1.
- **[owner to confirm]**: a provisional rule.

## 2. Data

### 2.3 Unit

**Size.** The corpus is large. The counts of events and of statements, by period,
are **TBD-at-gate**, from the freeze run. Another sentence follows.

- **At risk.** A statement is at risk when listed. The count is **TBD-at-gate**.
- A rule that is provisional. It stands unless changed. [owner to
  confirm]

## 9. Budget

| Model | Calls | Cost |
|---|---|---|
| alpha | 100 | **TBD-at-gate** |
| beta | 200 | $3 |

The evaluator (**TBD-at-F1**: file and hash) refuses a run. Two values here are
**TBD-at-gate** and the source is **TBD-at-registration**.

## 17. Registration record

**Models.** `MODELS.md`: its hash. **TBD-at-registration.**
"""


def pins_of(**changes: object):
    """A stand-in for the template pins as read now."""
    pin = {"sha256": "e" * 64, "pinned": "e" * 64, "matches_pin": True, "pending": []}
    return lambda: {"templates": {"literal-v1": {**pin, **changes}}}


@pytest.fixture
def ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary repository after a freeze run and its rerun, with a plan whose section 17
    holds the rendering of the record: the state in which the plan is ready."""
    TF.make_repo(tmp_path, monkeypatch)
    assert TF.freeze("--write-sealed-once") == 0
    assert TF.freeze("--verify-rerun") == 0
    write_plan()
    return tmp_path


def write_plan(opening: str = "Registered.", drop: str = "") -> None:
    """The plan of the temporary repository: the four stated hashes, then the record as
    rendered now; ``drop`` is taken out of section 17."""
    rendered = F.RECORD_MD.read_text(encoding="utf-8").replace("# Freeze record", "The record.")
    text = TF.plan_text().replace("Opening.", opening)
    section = F.plan_section(text, 17)
    TF.put(F.PLAN, text.replace(section, (section + rendered).replace(drop, "") + "\n"))


def check(capsys: pytest.CaptureFixture[str], pins=None) -> tuple[int, str]:
    capsys.readouterr()
    status = P.main([], pins_of=pins or pins_of())
    return status, capsys.readouterr().out


def failing(out: str) -> list[str]:
    return [line.split("  ", 1)[1].strip() for line in out.splitlines() if line.startswith("NOT")]


# --------------------------------------------------------------------------------------------
# Markers and tags
# --------------------------------------------------------------------------------------------


def test_every_marker_and_tag_is_found_with_its_place() -> None:
    found = P.find_markers(DRAFT)
    assert [(f.kind, f.line) for f in found] == [
        (P.GATE, 5),
        (P.REGISTRATION, 5),
        (P.OWNER, 6),
        (P.GATE, 10),
        (P.REGISTRATION, 11),
        (P.F1, 12),
        (P.OWNER, 13),
        (P.GATE, 20),
        (P.GATE, 22),
        (P.OWNER, 23),
        (P.GATE, 30),
        (P.F1, 33),
        (P.GATE, 34),
        (P.REGISTRATION, 34),
        (P.REGISTRATION, 38),
    ]
    assert [f.line for f in found if f.definition] == [10, 11, 12, 13]
    by_line = {(f.line, f.kind): f for f in found}
    size = by_line[20, P.GATE]
    assert (size.section, size.place) == ("2. Data", "2.3 Unit / Size")
    assert size.rule == (
        "The counts of events and of statements, by period, are **TBD-at-gate**, from the "
        "freeze run."
    )
    assert by_line[22, P.GATE].place == "2.3 Unit / At risk"
    assert by_line[22, P.GATE].rule == "The count is **TBD-at-gate**."
    # a tag that stands after its sentence, broken over two lines, takes the sentence with it
    tag = by_line[23, P.OWNER]
    assert tag.rule == "It stands unless changed. [owner to confirm]"
    assert tag.place == "2.3 Unit / At risk"
    row = by_line[30, P.GATE]
    assert (row.section, row.place, row.rule) == (
        "9. Budget",
        "9. Budget",
        "| alpha | 100 | **TBD-at-gate** |",
    )
    assert by_line[34, P.GATE].rule == by_line[34, P.REGISTRATION].rule
    assert by_line[34, P.GATE].rule.startswith("Two values here are **TBD-at-gate** and")
    last = by_line[38, P.REGISTRATION]
    assert last.place == "17. Registration record / Models"
    assert last.rule == "`MODELS.md`: its hash. **TBD-at-registration.**"
    opening = by_line[5, P.GATE]
    assert opening.section == P.OPENING and not opening.definition
    assert opening.rule.startswith("every **TBD-at-gate** and")


def test_what_is_left_leaves_out_f1_and_the_definitions() -> None:
    left = P.left(P.find_markers(DRAFT))
    assert [(f.kind, f.line) for f in left] == [
        (P.GATE, 5),
        (P.REGISTRATION, 5),
        (P.OWNER, 6),
        (P.GATE, 20),
        (P.GATE, 22),
        (P.OWNER, 23),
        (P.GATE, 30),
        (P.GATE, 34),
        (P.REGISTRATION, 34),
        (P.REGISTRATION, 38),
    ]
    # a definition is a list item of the opening only: the same words in a section count
    moved = DRAFT.replace("## 2. Data", "## 2. Data\n\n- **TBD-at-gate**: left here by mistake.")
    assert len(P.left(P.find_markers(moved))) == len(left) + 1
    assert P.left(P.find_markers("# T\n\nText with TBD-at-\ngate inside.\n"))[0].line == 3
    assert P.find_markers("# T\n\nNothing to fill. TBD at the gate.\n") == []


def test_a_marker_of_no_known_kind_and_one_in_other_letters_count() -> None:
    text = (
        "# T\n\n- **TBD-at-gate**: defined here.\n\n## 1. One\n\n"
        "The quota is TBD-at-pilot. The price is tbd-at-registration.\n"
        "A rule. [Owner to confirm] The file is tbd-at-f1.\n"
    )
    found = P.find_markers(text)
    assert [(f.kind, f.line, f.definition) for f in found] == [
        (P.GATE, 3, True),
        ("TBD-at-pilot", 7, False),
        (P.REGISTRATION, 7, False),
        (P.OWNER, 8, False),
        (P.F1, 8, False),
    ]
    assert [f.kind for f in P.left(found)] == ["TBD-at-pilot", P.REGISTRATION, P.OWNER]
    assert P.check_markers(text)[:3] == [
        "1 TBD-at-registration",
        "1 [owner to confirm]",
        "1 TBD-at-pilot",
    ]
    lines = P.worklist(found)
    assert lines[0] == "4 markers and tags, 3 of them to resolve"
    assert "TBD-at-pilot: 1 (not a marker of this plan: to resolve as one of the four)" in lines
    assert lines[-1].split() == ["0", "1", "1", "1", "1", "all"]


def test_only_the_first_definition_of_each_marker_is_left_out() -> None:
    opening = (
        "# T\n\nFour markers are used:\n\n"
        "- **TBD-at-gate**: depends on the build, unlike TBD-at-registration.\n"
        "- **TBD-at-registration**: a fact; unlike TBD-at-gate it does not depend on the data.\n"
        "- **TBD-at-F1**: fixed by F1.\n"
        "- **[owner to confirm]**: a provisional rule.\n"
        "- **TBD-at-gate**: a second item of the same kind.\n"
        "- **TBD-at-pilot**: not a marker of the plan.\n"
        "  - **TBD-at-registration**: indented, so no definition.\n"
        "- A price that is **TBD-at-registration**: with a colon after it.\n"
    )
    found = P.find_markers(opening)
    assert [f.line for f in found if f.definition] == [5, 6, 7, 8]
    assert [(f.kind, f.line) for f in P.left(found)] == [
        (P.REGISTRATION, 5),
        (P.GATE, 6),
        (P.GATE, 9),
        ("TBD-at-pilot", 10),
        (P.REGISTRATION, 11),
        (P.REGISTRATION, 12),
    ]
    # the same four items after the first heading define nothing
    moved = opening.replace("Four markers are used:", "## 1. One")
    assert not any(f.definition for f in P.find_markers(moved))


def test_a_marker_broken_by_an_empty_line_is_found_all_the_same() -> None:
    found = P.find_markers("# T\n\nThe count is TBD-at-\n\ngate, from the build.\n")
    assert [(f.kind, f.line) for f in found] == [(P.GATE, 3)] and found[0].rule


def test_worklist_groups_by_kind_and_counts_by_section() -> None:
    lines = P.worklist(P.find_markers(DRAFT))
    assert lines[0] == "11 markers and tags, 10 of them to resolve"
    heads = [line for line in lines if line and not line.startswith(" ")]
    assert [head.split(":")[0] for head in heads[1:5]] == list(P.KINDS)
    assert [int(head.split(": ")[1].split()[0]) for head in heads[1:5]] == [5, 3, 2, 1]
    assert "definitions of a marker in the opening, not counted: 4" in lines
    assert (
        "  line   23  [2.3 Unit / At risk]  It stands unless changed. [owner to confirm]" in lines
    )
    table = lines[lines.index("by section:") + 2 :]
    assert [(row.split()[:4], row.split(maxsplit=4)[4]) for row in table] == [
        (["1", "1", "1", "0"], P.OPENING),
        (["2", "0", "1", "0"], "2. Data"),
        (["2", "1", "0", "1"], "9. Budget"),
        (["0", "1", "0", "0"], "17. Registration record"),
        (["5", "3", "2", "1"], "all"),
    ]


def test_list_prints_the_worklist_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = TF.put(tmp_path / "PLAN.md", DRAFT)
    assert P.main(["--plan", str(plan), "--list"], pins_of=lambda: None) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"{plan.as_posix()}: 11 markers and tags, 10 of them to resolve")
    assert "TBD-at-gate: 5 (to fill before registration" in out
    assert "TBD-at-F1: 1 (may stay" in out


def test_a_missing_plan_is_an_error_of_the_command_line(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        P.main(["--plan", str(tmp_path / "MISSING.md"), "--list"], pins_of=lambda: None)


def test_list_works_on_the_study_draft(capsys: pytest.CaptureFixture[str]) -> None:
    assert P.main(["--plan", str(STUDY_PLAN), "--list"], pins_of=lambda: None) == 0
    out = capsys.readouterr().out
    assert "by section:" in out
    found = P.find_markers(STUDY_PLAN.read_text(encoding="utf-8"))
    assert len(found) >= 1 and all(f.rule and f.place and f.line > 0 for f in found)
    # the opening defines each of the four markers once, and the draft uses no other kind
    assert sorted(f.kind for f in found if f.definition) == sorted(P.KINDS)
    assert {f.kind for f in found} <= set(P.KINDS)


# --------------------------------------------------------------------------------------------
# Ready, and each way of not being ready
# --------------------------------------------------------------------------------------------


def test_a_plan_that_holds_the_record_is_ready(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(capsys)
    assert status == 0, out
    assert out.splitlines()[-1] == "ready to register: every check holds"
    assert sum(line.startswith("ok ") for line in out.splitlines()) == 8 and "NOT READY" not in out


def test_the_sealed_folder_is_not_read(ready: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.rmtree(TF.sealed_folder())
    assert check(capsys)[0] == 0
    assert not TF.sealed_folder().exists()


@pytest.mark.parametrize(
    ("added", "kinds"),
    [
        ("The count is **TBD-at-gate**.", ["1 TBD-at-gate"]),
        ("The price is **TBD-at-registration**.", ["1 TBD-at-registration"]),
        ("A rule. [owner to\nconfirm]", ["1 [owner to confirm]"]),
    ],
)
def test_a_marker_or_tag_left_is_not_ready(
    ready: Path, capsys: pytest.CaptureFixture[str], added: str, kinds: list[str]
) -> None:
    TF.put(
        F.PLAN, F.PLAN.read_text().replace("## 16. Before\n\nText.", f"## 16. Before\n\n{added}")
    )
    status, out = check(capsys)
    assert status == 1 and failing(out) == ["no marker and no owner tag is left"]
    assert f"    {kinds[0]}" in out and "    line 7 (16. Before): " in out
    assert out.splitlines()[-1] == "not ready to register: 1 of 8 checks fail"


def test_f1_markers_and_a_definition_may_stay(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_plan(opening="Registered.\n\n- **TBD-at-gate**: was filled from the frozen build.")
    text = F.PLAN.read_text().replace("Text.", "The evaluator is **TBD-at-F1**.")
    TF.put(F.PLAN, text)
    assert check(capsys)[0] == 0


def test_the_draft_paragraph_is_not_ready(ready: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_plan(opening="**DRAFT (2026-10-01). Not registered.** This file becomes the plan.")
    status, out = check(capsys)
    assert status == 1 and failing(out) == ["the draft paragraph is replaced"]


def test_no_record_is_not_ready(ready: Path, capsys: pytest.CaptureFixture[str]) -> None:
    F.RECORD.unlink()
    status, out = check(capsys)
    assert status == 1
    assert failing(out) == [
        "the freeze record is complete and its rerun agreed",
        "the record's hashes are in section 17 and on disk",
        "the sealed hashes are in section 17, and the counts are theirs",
    ]
    assert "there is no freeze record" in out and out.count("waits for the freeze record") == 2


def test_a_rehearsal_record_is_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    TF.make_repo(tmp_path, monkeypatch)
    assert TF.freeze("--open-only") == 0
    write_plan()
    status, out = check(capsys)
    assert status == 1
    assert "the record is of a run in mode open-only, not of the freeze" in out
    assert "sealed outcomes_test.csv.gz: the record has 'not run', not a sha256" in out
    assert "the one rerun has not confirmed the sealed hashes" in out
    assert "the record's hashes are in section 17 and on disk" not in failing(out)


def test_a_failed_run_is_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    TF.make_repo(tmp_path, monkeypatch)
    TF.knobs(fail=F.POWER)
    assert TF.freeze("--write-sealed-once") == 1
    status, out = check(capsys)
    assert status == 1 and "the record's status is failed, not complete" in out
    assert "guide: the record has no hash" in out


def test_the_rerun_must_have_run_and_agreed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    TF.make_repo(tmp_path, monkeypatch)
    assert TF.freeze("--write-sealed-once") == 0
    write_plan()
    status, out = check(capsys)
    assert status == 1 and failing(out) == ["the freeze record is complete and its rerun agreed"]
    TF.knobs(sealed_extra="other outcomes")
    assert TF.freeze("--verify-rerun") == 1
    status, out = check(capsys)
    assert status == 1 and "the one rerun has not confirmed the sealed hashes" in out


def test_a_hash_missing_from_section_17_is_named(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = TF.record()
    labels = F.registered_hashes(record)
    for label in ("code dataset.py", "table events.csv.gz (decompressed content)", "guide"):
        write_plan(drop=labels[label][:16])
        status, out = check(capsys)
        assert status == 1, label
        assert failing(out) == ["the record's hashes are in section 17 and on disk"]
        assert f"    {label}: {labels[label][:16]} is not in section 17" in out
    pin = labels["template literal-v1"]
    write_plan(drop=pin)
    assert f"template literal-v1: {pin[:16]} is not in section 17" in check(capsys)[1]
    # a hash that stands elsewhere in the plan, outside section 17, does not count
    write_plan(opening=f"Registered. `{labels['guide'][:16]}`", drop=labels["guide"][:16])
    assert "guide: " + labels["guide"][:16] + " is not in section 17" in check(capsys)[1]


def test_a_sealed_hash_missing_from_section_17_is_named(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    value = TF.record()["tables"]["sealed"][F.SEALED_TEST]
    write_plan(drop=value[:16])
    status, out = check(capsys)
    assert status == 1
    assert failing(out) == ["the sealed hashes are in section 17, and the counts are theirs"]
    assert f"sealed {F.SEALED_TEST}: {value[:16]} is not in section 17" in out


def test_counts_of_another_sealed_file_are_named(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    counts = json.loads(F.SEALED_COUNTS.read_text())
    recorded = TF.record()["tables"]["sealed"][F.SEALED_TEST]
    counts["inputs"]["sealed_outcomes"]["sha256"] = "5" * 64
    TF.put(F.SEALED_COUNTS, json.dumps(counts))
    out = check(capsys)[1]
    assert (
        f"sealed_counts.json: counts of the sealed file {'5' * 16}, not of the record's "
        f"{recorded[:16]}" in out
    )
    F.SEALED_COUNTS.unlink()
    assert "sealed_counts.json: counts of the sealed file None" in check(capsys)[1]


def test_code_changed_since_the_counts_were_taken_is_named(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    TF.put(F.HERE / "dataset.py", "# changed after the counts were taken\n")
    status, out = check(capsys)
    assert status == 1
    assert "    changed since the sealed counts were taken: dataset.py" in out
    assert "    code dataset.py: the record has " in out


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (F.HERE / "corpus.py", "code corpus.py"),
        (F.GUIDE, "guide"),
        (F.MODELS, "MODELS.md"),
        (F.SAMPLES / "sample_check.csv", "sample list check"),
        (F.OUTCOME_SAMPLE, "sample list outcome_audit_train"),
        (F.ELIGIBLE, "eligible list (file)"),
    ],
)
def test_a_file_changed_since_the_freeze_is_named(
    ready: Path, capsys: pytest.CaptureFixture[str], path: Path, label: str
) -> None:
    recorded = F.registered_hashes(TF.record())[label]
    TF.put(path, path.read_text() + "changed\n")
    status, out = check(capsys)
    assert status == 1
    assert "the record's hashes are in section 17 and on disk" in failing(out)
    now = F.sha256_file(path)
    assert f"    {label}: the record has {recorded[:16]}, the disk {now[:16]}" in out


def test_a_changed_table_is_named_as_file_and_as_content(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    table = F.OPEN_TABLES[0]
    recorded = TF.record()["tables"]["open"][table.name]
    table.write_bytes(gzip.compress(b"event_id\ne1\ne2\n", mtime=0))
    status, out = check(capsys)
    assert status == 1
    for kind, key in (("gzip file", "gzip_sha256"), ("decompressed content", "content_sha256")):
        assert f"table {table.name} ({kind}): the record has {recorded[key][:16]}, the disk " in out
    # the same content compressed otherwise: only the file differs
    table.write_bytes(gzip.compress(b"event_id\ne1\n", compresslevel=1, mtime=1))
    out = check(capsys)[1]
    assert f"table {table.name} (gzip file): the record has" in out
    assert f"table {table.name} (decompressed content)" not in out
    table.write_bytes(b"not a gzip file")
    assert f"table {table.name} (decompressed content): the record has " in check(capsys)[1]


def test_a_changed_pin_or_output_is_named(ready: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out = check(capsys, pins_of(sha256="9" * 64, pinned="9" * 64))
    assert status == 1
    assert f"template literal-v1: the record has {'e' * 16}, the disk {'9' * 16}" in out
    counts = json.loads(F.DATASET_COUNTS.read_text())
    counts["secondary_lists_test"]["tbd"]["ids_sha256"] = "7" * 64
    TF.put(F.DATASET_COUNTS, json.dumps(counts))
    status, out = check(capsys)
    assert status == 1
    assert f"secondary list tbd (ids): the record has {'b' * 16}, the disk {'7' * 16}" in out
    assert f"{F.DATASET_COUNTS.as_posix()}: written by the freeze as " in out
    (F.OUT / "power.json").unlink()
    assert f"{(F.OUT / 'power.json').as_posix()}: written by the freeze as" in check(capsys)[1]


def test_a_list_drawn_after_the_freeze_is_named_until_the_record_has_it(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    later = TF.put(F.SAMPLES_LATER / "sample_dev_prompt.csv", "event_id\ne8\n")
    status, out = check(capsys)
    assert status == 1
    assert (
        f"sample list later_dev_prompt: on disk ({TF.sha(later)[:16]}) and not in the record" in out
    )
    assert TF.freeze("--continue-after-sealed") == 0
    status, out = check(capsys)
    assert f"sample list later_dev_prompt: {TF.sha(later)[:16]} is not in section 17" in out
    write_plan()
    assert check(capsys)[0] == 0


def test_a_list_missing_from_the_record_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    TF.make_repo(tmp_path, monkeypatch)
    F.OUTCOME_SAMPLE.unlink()
    assert TF.freeze("--write-sealed-once") == 0
    assert TF.freeze("--verify-rerun") == 0
    write_plan()
    status, out = check(capsys)
    assert status == 1 and "sample list outcome_audit_train: the record has no hash" in out


def test_a_stated_hash_must_be_the_file_s(ready: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stated = F.stated_pins(F.PLAN.read_text())["uv.lock"]
    TF.put(F.LOCK, "another lock\n")
    status, out = check(capsys)
    assert status == 1 and failing(out) == [
        "the record's hashes are in section 17 and on disk",
        "the hashes the plan states are those of the files",
    ]
    assert f"uv.lock: the plan states {stated}, the file has {TF.sha(F.LOCK)[:16]}" in out
    assert f"lock file: the record has {stated}, the disk {TF.sha(F.LOCK)[:16]}" in out


@pytest.mark.parametrize(
    ("path", "label"),
    [(F.MANIFEST, "capture manifest"), (F.STRINGS, "availability-string list")],
)
def test_a_pinned_file_changed_with_the_plan_is_still_not_the_record_s(
    ready: Path, capsys: pytest.CaptureFixture[str], path: Path, label: str
) -> None:
    recorded = F.registered_hashes(TF.record())[label]
    TF.put(path, path.read_text() + "changed\n")
    write_plan()  # the plan now states the new hash, and holds the record as rendered
    status, out = check(capsys)
    assert status == 1 and "the hashes the plan states are those of the files" not in failing(out)
    assert f"    {label}: the record has {recorded[:16]}, the disk {TF.sha(path)[:16]}" in out


def test_a_code_file_the_record_does_not_know_is_named(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = TF.record()
    del record["code"]["power.py"]
    TF.put(F.RECORD, json.dumps(record))
    status, out = check(capsys)
    assert status == 1 and failing(out) == ["the record's hashes are in section 17 and on disk"]
    now = TF.sha(F.HERE / "power.py")[:16]
    assert f"    code power.py: on disk ({now}) and not in the record" in out


def test_the_python_of_the_record_is_in_section_17(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    python = TF.record()["environment"]["python"]
    write_plan(drop=f"Python {python}")
    status, out = check(capsys)
    assert status == 1 and failing(out) == ["the record's hashes are in section 17 and on disk"]
    assert f"    Python {python} (the record's) is not in section 17" in out


def test_hashes_in_section_17_that_nothing_vouches_for_are_noted(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "note: " not in check(capsys)[1]
    text = F.PLAN.read_text()
    stale, sheet = "0123456789abcdef", "1234abcd" * 8
    added = f"\n- `corpus.py` on 1 October: `{stale}`.\n- A submitted sheet: `{sheet}`.\n"
    TF.put(F.PLAN, text.replace("\n## Amendments", added + "\n## Amendments"))
    status, out = check(capsys)
    assert status == 0  # a note fails nothing: the checker cannot say whose hashes these are
    assert (
        "note: 2 hashes in section 17 are not in the freeze record or the template pins; "
        f"check them by hand: {stale}, {sheet}" in out
    )
    record, pins = TF.record(), pins_of()()
    section = F.plan_section(F.PLAN.read_text(), 17)
    assert P.unchecked_hashes(record, pins, section) == [stale, sheet]
    assert P.unchecked_hashes(None, None, f"`{stale}` and `{stale}`") == [stale]
    assert P.unchecked_hashes(None, pins, "`" + "e" * 16 + "` 2026-10-01 abcdef") == []
    assert P.unchecked_hashes(None, None, f"`{stale}`", stated=[stale, None]) == []


def test_a_path_in_a_sealed_folder_stops_the_check(ready: Path) -> None:
    hidden = TF.put(TF.sealed_folder() / "PLAN.md", TF.plan_text())
    for flag in ("--plan", "--record", "--guide"):
        with pytest.raises(SystemExit, match="never opens the sealed folder"):
            P.main([flag, str(hidden)], pins_of=pins_of())
    with pytest.raises(SystemExit, match="never opens the sealed folder"):
        P.main(["--plan", str(hidden), "--list"], pins_of=pins_of())
    # nor is a file that a record names there
    record = TF.record()
    record["outputs"][(TF.sealed_folder() / F.SEALED_TEST).as_posix()] = "0" * 64
    TF.put(F.RECORD, json.dumps(record))
    with pytest.raises(SystemExit, match="never opens the sealed folder"):
        P.main([], pins_of=pins_of())


def test_the_opening_and_section_17_state_one_hash_for_the_rule_reader(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stated = F.stated_pins(F.PLAN.read_text())["rules.py"]
    write_plan(opening=f"Registered. `rules.py` is frozen at sha256 prefix `{stated}`.")
    assert check(capsys)[0] == 0
    write_plan(opening=f"Registered. `rules.py` is frozen at sha256 prefix `{'0' * 16}`.")
    status, out = check(capsys)
    assert status == 1
    assert f"rules.py: the opening states {'0' * 16}, section 17 states {stated}" in out


@pytest.mark.parametrize(
    "line", ["**Version v1 draft, 1 October 2026.**", "**Version v2,**", "none"]
)
def test_the_guide_must_say_v1(ready: Path, capsys: pytest.CaptureFixture[str], line: str) -> None:
    TF.put(F.GUIDE, f"# Guide\n\n{line} Text.\n")
    status, out = check(capsys)
    assert status == 1 and "the guide is v1" in failing(out)
    assert "the guide's version line says" in out
    assert P.check_guide(F.HERE / "plan" / "missing.md") != []


def test_prompts_must_match_their_pins_and_wait_for_nothing(
    ready: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out = check(capsys, pins_of(pending=["D1", "D3"]))
    assert status == 1 and failing(out) == ["the prompts match their pins and wait for nothing"]
    assert "literal-v1: waits for the pilot sentences D1, D3" in out
    status, out = check(capsys, pins_of(matches_pin=False))
    assert status == 1 and "literal-v1: the template does not match its pin" in out
    status, out = check(capsys, lambda: None)
    assert status == 1 and "the template pins could not be read" in out
    assert "template literal-v1: the record has" in out  # the record's pin has nothing on disk


def test_the_study_pins_can_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(STUDY_PLAN.parents[3])
    pins = P.live_pins()
    assert len(pins["templates"]) == 5
    assert all(len(pin["sha256"]) == 64 for pin in pins["templates"].values())
