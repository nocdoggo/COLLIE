"""Tests for the reference-reading check (``audit_reference.py``, task E).

Four tests read the real guide and the registered files under ``analysis/coling/out``. All the
others run on made-up inputs in a temporary folder: an eligible list, an events table, an item
file, a counts file, a freeze record and the four first-draw lists, built by :func:`world` with
the hashes that register them. The eligible list, the events table, the items and the counts
file carry a poisoned outcome entry that no test may find in a frame or in an output. Nothing
sealed is read and no outcome is used anywhere.

Covered: the split and its determinism; the registered hashes and every refusal (a changed
list, counts file, item file, events table or first-draw list, a registered hash that is too
short, a record that is no complete freeze, a reader that is not the frozen one, a subset the
counts file does not record, a statement outside the test period or with no stated period, a
rule reading that is not the registered one or not that of the text shown, an item that is not
the row, the date or the stated end of the list, a statement of the first draw or its twin on a
sheet, a sheet filled in place, a path in a sealed folder or a link that leads into one); the sheets
(columns, entry block as the harness renders it, rule reading, orders, the items text, the
manifest); every rule and warning of the validator; the scorer on a hand-worked case
(agreement, kappa, the adjudication sheet and its checks, the result, the Wilson interval, the
confirmed list), its refusals (sheets or blanks that are not those of the sample, decisions
taken on other entries, a second sheet of an annotator or of ADJ, a sheet of ADJ that was begun
in place), the result that goes when a sheet is replaced and the unfilled adjudication sheet
that goes when the new pair reports nothing, and its exit statuses;
that no outcome column is read and that every write goes under the output folder; the constants
against the real guide; and the registered subset and the blank sheets under
``analysis/coling/out``, which hold no statement of the first draw and no minimal-pair seed.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_audit_reference.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analysis.coling import audit_reference as R
from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import dataset as D
from analysis.coling import forms as F
from analysis.coling import read, sheet_xlsx

REAL = Path("analysis/coling/out")
REAL_GUIDE = Path("analysis/coling/plan/AUDIT_GUIDE.md")
POISON = "POISON-OUTCOME"
GUIDE_TEXT = "# Guide\n\n**Version v1, 5 October 2026.** A guide made up for the tests.\n"
TEXTS = (  # availability and related information; {y} is the year after the statement's
    ("Unavailable", "Next release April {y}."),
    ("Estimated recovery: Q4 {y}", "Check wholesalers for inventory"),
    ("Limited supply; Recovery mid-February {y}", ""),
    ("Unavailable", "Additional lots will be available in the March - April {y} timeframe."),
    ("Unavailable", "Estimated recovery: {y}."),
    ("=Backordered. Next release May {y}.", ""),
    ("Next Delivery: TBD; Estimated Recovery: September {y}", "-Check wholesaler"),
)
SUBSETS = ("probe", "samples20", "paraphrase", "twobytwo", "reference_check")


# --------------------------------------------------------------------------------------------
# A made-up registered world
# --------------------------------------------------------------------------------------------


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def statement(n: int, marked: bool = True) -> dict[str, Any]:
    """A test-period statement with one or two presentations and its frozen rule reading."""
    year = 2023 + n % 3
    day = f"{year}-{1 + n % 12:02d}-{1 + n % 27:02d}"
    availability, related = (part.format(y=year + 1) for part in TEXTS[n % len(TEXTS)])
    reading = F.classify(C.statement_text(availability, related), day)
    members = ("a", "b") if n % 4 == 0 else ("a",)
    return {
        "statement_group_id": f"S{n:05d}",
        "members": [f"E{n:05d}{m}" for m in members],
        "event_id": f"E{n:05d}{members[-1]}",
        "event_date": day,
        "generic_name": f"Drug{n} Injection",
        "company_name": f"Maker {n % 9}",
        "presentation": "-10 mg vial" if n % 10 == 3 else f"{n} mg vial (NDC 0000-{n:04d}-01)",
        "availability_text": availability,
        "related_text": related,
        "reason_for_shortage": "" if n % 5 == 0 else "Demand increase for the drug",
        "form": reading.form,
        "stated_end": reading.end,
        "marked": marked,
    }


def labelled_statement(n: int) -> dict[str, Any]:
    """A train-period statement of the first draw."""
    return statement(n, marked=False) | {
        "statement_group_id": f"L{n:05d}",
        "members": [f"F{n:05d}a"],
        "event_id": f"F{n:05d}a",
        "event_date": f"2021-{1 + n % 12:02d}-10",
        "availability_text": "On backorder",
        "related_text": f"Next release in lot {n}; date TBD.",
    }


def event_rows(statements: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for s in statements:
        for event in s["members"]:
            rows.append(
                {
                    "event_id": event,
                    "statement_group_id": s["statement_group_id"],
                    "thread_id": "T" + event[1:],
                    "listing": "shortage",
                    "event_date": s["event_date"],
                    "status_at_statement": "current",
                    "availability_class": "unavailable",
                    "generic_name": s["generic_name"],
                    "company_name": s["company_name"],
                    "presentation": s["presentation"],
                    "availability_text": s["availability_text"],
                    "related_text": s["related_text"],
                    "statement_text": C.statement_text(s["availability_text"], s["related_text"]),
                    "outcome": POISON,
                    "upper_date": POISON,
                }
            )
    return rows


def eligible_rows(statements: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "statement_group_id": s["statement_group_id"],
            "event_id": s["event_id"],
            "thread_id": "T" + s["event_id"][1:],
            "episode_id": f"{s['generic_name']}@2022-01-01",
            "event_date": s["event_date"],
            "form": s["form"],
            "stated_end": s["stated_end"],
            **{name: "0" for name in SUBSETS[:-1]},
            "reference_check": str(int(s["marked"])),
            "outcome": POISON,
            "E_end": POISON,
        }
        for s in sorted(statements, key=lambda s: s["statement_group_id"])
    ]


def item_rows(statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": s["statement_group_id"],
            "generic_name": s["generic_name"],
            "company_name": s["company_name"],
            "presentation": s["presentation"],
            "therapeutic_category": "Oncology",
            "initial_posting_date": "2020-01-15",
            "date_of_update": s["event_date"],
            "type_of_update": "Revised",
            "availability_information": s["availability_text"],
            "related_information": s["related_text"],
            "reason_for_shortage": s["reason_for_shortage"],
            "stated_end": s["stated_end"],
            "form": "a month and year",
            "revision": "first",
            "display_event_id": s["event_id"],
            "split": "test",
            "outcome": POISON,
        }
        for s in sorted(statements, key=lambda s: s["statement_group_id"])
        if s["marked"]
    ]


def register(root: Path, final: bool = True, ids_sha256: str | None = None) -> None:
    """Write the counts file and the freeze record that register the files under ``root``."""
    listed = pd.read_csv(root / R.ELIGIBLE, dtype=str, keep_default_na=False)
    ids = list(listed.loc[listed["reference_check"] == "1", "statement_group_id"])
    counts = {
        "subsets": {
            "reference_check": {
                "final": final,
                "statements": len(ids),
                "ids_sha256": ids_sha256 or D.ids_sha256(ids),
            }
        },
        "outputs": {"items": {Path(R.ITEMS).name: {"sha256": sha(root / R.ITEMS)[:16]}}},
        "train": {"dated": {"E_end": {"yes": POISON}}},
    }
    (root / R.COUNTS).write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    record = {
        "mode": "freeze",
        "status": "complete",
        "tables": {
            "eligible_list": {"sha256": sha(root / R.ELIGIBLE)},
            "open": {R.EVENTS: {"gzip_sha256": sha(root / R.EVENTS)}},
        },
        "outputs": {f"analysis/coling/out/{R.COUNTS}": sha(root / R.COUNTS)},
        "sample_lists": {
            name: {"sha256": sha(root / R.SAMPLES / f"sample_{name}.csv")} for name in R.FIRST_DRAW
        },
        "code": {"rules.py": sha(Path(F.rules.__file__)), "forms.py": sha(Path(F.__file__))},
    }
    (root / R.FREEZE).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


Edit = Callable[[list[dict[str, Any]], dict[str, list[dict[str, Any]]]], None]


def world(
    tmp_path: Path,
    n: int = 100,
    final: bool = True,
    edit: Edit | None = None,
    reverse: bool = False,
) -> Path:
    """A folder with every registered file: ``n`` marked statements, 12 unmarked ones and two
    train-period statements in each first-draw list. ``edit`` changes the statements or the
    lists before anything is written; ``reverse`` writes the tables bottom up."""
    root = tmp_path / "out"
    statements = [statement(k) for k in range(1, n + 1)]
    statements += [statement(k, marked=False) for k in range(n + 1, n + 13)]
    first = {
        name: [labelled_statement(10 * k + j) for j in (1, 2)]
        for k, name in enumerate(R.FIRST_DRAW)
    }
    if edit is not None:
        edit(statements, first)
    drawn = {s["statement_group_id"]: s for group in first.values() for s in group}
    everything = statements + [s for i, s in drawn.items() if i[0] == "L"]
    (root / R.SAMPLES).mkdir(parents=True)
    (root / "items").mkdir()
    events, eligible = event_rows(everything), eligible_rows(statements)
    if reverse:
        events, eligible = events[::-1], eligible[::-1]
    pd.DataFrame(events).to_csv(root / R.EVENTS, index=False, compression="gzip")
    pd.DataFrame(eligible).to_csv(root / R.ELIGIBLE, index=False)
    lines = [json.dumps(item, sort_keys=True) for item in item_rows(statements)]
    (root / R.ITEMS).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    for name, group in first.items():
        rows = [
            {
                "event_id": s["event_id"],
                "statement_group_id": s["statement_group_id"],
                "thread_id": "T" + s["event_id"][1:],
            }
            for s in group
        ]
        (root / R.SAMPLES / f"sample_{name}.csv").write_text(
            S.plain_csv(S.SAMPLE_COLUMNS, rows), encoding="utf-8"
        )
    (tmp_path / "guide.md").write_text(GUIDE_TEXT, encoding="utf-8")
    register(root, final)
    return root


def run(root: Path, *command: str) -> int:
    """One command of the module on the made-up world."""
    arguments = [*command, "--root", str(root)]
    if command[0] == "sheets":
        arguments += ["--guide", str(root.parent / "guide.md")]
    return R.main(arguments)


def refused(root: Path, *command: str) -> str:
    """The message with which a command stops."""
    with pytest.raises(SystemExit) as stopped:
        run(root, *command)
    assert not isinstance(stopped.value.code, int), "the command ended with an exit status"
    return str(stopped.value.code)


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One world with its blank sheets written, shared by the tests that only read."""
    root = world(tmp_path_factory.mktemp("reference"))
    assert run(root, "sheets") == 0
    return root


def blank(root: Path, annotator: str) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    return S.read_sheet(root / R.OUT_NAME / f"reference_{annotator}.csv")


def fill(
    root: Path,
    annotator: str,
    marks: Mapping[str, Mapping[str, str]] | None = None,
    times: tuple[str, str] | None = ("09:00", "09:30"),
    name: str | None = None,
) -> Path:
    """A filled copy of an annotator's blank, kept outside the output folder: ``ok`` on every
    row but those in ``marks``, and one sitting."""
    meta, rows = blank(root, annotator)
    for row in rows:
        row |= {"verdict": "ok"} | dict((marks or {}).get(row["item_id"], {}))
    if times is not None:
        clock = dict(zip(S.SITTING_KEYS, times, strict=True))
        meta = [(key, clock.get(key, value)) for key, value in meta]
    path = root.parent / "filled" / (name or f"reference_{annotator}.csv")
    path.parent.mkdir(exist_ok=True)
    path.write_text(S.sheet_text(R.SHEET_COLUMNS, rows, meta), encoding="utf-8")
    return path


def split(root: Path) -> dict[str, list[str]]:
    """The item ids of A1 alone, of A2 alone and of both, sorted, as the two blanks give them."""
    ids = {a: {row["item_id"] for row in blank(root, a)[1]} for a in R.ANNOTATORS}
    return {
        "A1": sorted(ids["A1"] - ids["A2"]),
        "A2": sorted(ids["A2"] - ids["A1"]),
        "both": sorted(ids["A1"] & ids["A2"]),
    }


def statement_of(n: int = 100) -> dict[str, dict[str, Any]]:
    """The made-up statement behind each item id."""
    return {S.item_id(s["statement_group_id"]): s for s in map(statement, range(1, n + 1))}


# --------------------------------------------------------------------------------------------
# The split
# --------------------------------------------------------------------------------------------


def test_split_sizes() -> None:
    assert R.split_sizes(100) == {"A1": 45, "A2": 45, "both": 10}
    assert R.split_sizes(99) == {"A1": 45, "A2": 44, "both": 10}
    assert R.split_sizes(95) == {"A1": 43, "A2": 42, "both": 10}
    assert R.split_sizes(94) == {"A1": 43, "A2": 42, "both": 9}
    assert R.split_sizes(0) == {"A1": 0, "A2": 0, "both": 0}
    assert all(sum(R.split_sizes(n).values()) == n for n in range(0, 240))


def test_assignment_is_the_seeded_rule_and_ignores_the_input_order() -> None:
    ids = [f"S{n:05d}" for n in range(1, 101)]
    who = R.assignment(ids)
    assert who == R.assignment(ids[::-1]) == R.assignment([*ids, *ids[:7]])
    assert Counter(who.values()) == {"A1": 45, "A2": 45, "both": 10}
    order = sorted(
        ids,
        key=lambda i: hashlib.sha256(f"20261001\x1freference/assign\x1f{i}".encode()).hexdigest(),
    )
    assert [i for i in order if who[i] == "A1"] == order[:45]
    assert [i for i in order if who[i] == "A2"] == order[45:90]
    assert [i for i in order if who[i] == "both"] == order[90:]
    assert order[:45] != sorted(order[:45])  # a draw, not the first ids of the list


def test_sheets_hold_45_and_45_with_the_10_shared_in_orders_of_their_own(made: Path) -> None:
    parts = split(made)
    assert [len(parts[k]) for k in ("A1", "A2", "both")] == [45, 45, 10]
    orders = {a: [row["item_id"] for row in blank(made, a)[1]] for a in R.ANNOTATORS}
    assert len(orders["A1"]) == len(orders["A2"]) == 55
    for annotator, order in orders.items():
        assert order == S.shuffled(order, f"reference/order/{annotator}")
    shared = [[i for i in order if i in parts["both"]] for order in orders.values()]
    assert shared[0] != shared[1] and sorted(shared[0]) == sorted(shared[1])
    by_item = statement_of()
    who = R.assignment(s["statement_group_id"] for s in by_item.values())
    for name, items in parts.items():
        assert {who[by_item[i]["statement_group_id"]] for i in items} == {name}
    assert set(by_item) == set(orders["A1"]) | set(orders["A2"])
    assert not any(s["statement_group_id"][1:] in i for i, s in by_item.items())


def test_two_runs_and_another_row_order_write_the_same_bytes(tmp_path: Path, made: Path) -> None:
    out = made / R.OUT_NAME
    before = {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()}
    assert sorted(before) == [
        "reference_A1.csv",
        "reference_A1_items.txt",
        "reference_A2.csv",
        "reference_A2_items.txt",
        "reference_manifest.json",
    ]
    assert run(made, "sheets") == 0 and run(made, "sheets", "--check") == 0
    assert {path.name: path.read_bytes() for path in out.iterdir() if path.is_file()} == before
    other = world(tmp_path, reverse=True)
    assert run(other, "sheets") == 0
    sheets = [name for name in before if name != R.MANIFEST]
    assert all((other / R.OUT_NAME / name).read_bytes() == before[name] for name in sheets)
    # a freeze record written again with the same hashes (a later run) leaves all up to date
    record = json.loads((other / R.FREEZE).read_text(encoding="utf-8"))
    record |= {"earlier_runs": [{"finished": "2026-10-06T10:00:00Z"}]}
    (other / R.FREEZE).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    assert run(other, "sheets", "--check") == 0


def test_check_writes_nothing_and_names_what_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = world(tmp_path)
    assert run(root, "sheets", "--check") == 1
    assert not (root / R.OUT_NAME).exists()
    printed = capsys.readouterr().out
    assert "5 files are not up to date" in printed and "note:" not in printed
    assert run(root, "sheets") == 0
    # the command that writes the sheets says when they may go out, and who waits longer: the
    # annotators start once both task A sheets are in, ADJ only after the task A adjudication
    printed = capsys.readouterr().out
    assert f"note: {R.HAND_OUT}" in printed and "reference_A1.csv: 55 items, about 28" in printed
    assert "only after both task A sheets are submitted; ADJ opens none before" in R.HAND_OUT
    assert run(root, "sheets", "--check") == 0
    assert "up to date" in capsys.readouterr().out
    path = root / R.OUT_NAME / "reference_A2_items.txt"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert run(root, "sheets", "--check") == 1
    assert f"not up to date: {path}" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------
# The registered files and the refusals of ``sheets``
# --------------------------------------------------------------------------------------------


def nothing_written(root: Path) -> bool:
    return not (root / R.OUT_NAME).exists()


def test_a_changed_eligible_list_is_refused(tmp_path: Path) -> None:
    root = world(tmp_path)
    path = root / R.ELIGIBLE
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("S00001,", "S00001x,", 1), encoding="utf-8")
    message = refused(root, "sheets")
    assert "is not the registered file (the eligible list)" in message and nothing_written(root)
    # one more statement marked, in a list that is otherwise the registered one
    path.write_text(text, encoding="utf-8")
    assert run(root, "sheets", "--check") == 1
    rows = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows.loc[rows["statement_group_id"] == "S00105", "reference_check"] = "1"
    rows.to_csv(path, index=False)
    assert "is not the registered file (the eligible list)" in refused(root, "sheets")


@pytest.mark.parametrize(
    ("name", "what"),
    [
        (R.COUNTS, "the counts file of the dataset builder"),
        (R.ITEMS, "the item file of the subset"),
        (R.EVENTS, "the events table"),
        (f"{R.SAMPLES}/sample_literal.csv", "the literal list"),
        (f"{R.SAMPLES}/sample_pilot.csv", "the pilot list"),
    ],
)
def test_a_changed_registered_file_is_refused(tmp_path: Path, name: str, what: str) -> None:
    root = world(tmp_path)
    path = root / name
    path.write_bytes(path.read_bytes() + b"\n")
    message = refused(root, "sheets")
    assert f"is not the registered file ({what})" in message and "registered" in message
    assert nothing_written(root)


def test_a_missing_file_or_hash_is_refused(tmp_path: Path) -> None:
    root = world(tmp_path)
    (root / R.SAMPLES / "sample_reserve.csv").unlink()
    assert "sample_reserve.csv not found (the reserve list)" in refused(root, "sheets")
    root = world(tmp_path / "second")
    record = json.loads((root / R.FREEZE).read_text(encoding="utf-8"))
    del record["sample_lists"]["check"]
    (root / R.FREEZE).write_text(json.dumps(record), encoding="utf-8")
    assert "no registered sha256 for the check list" in refused(root, "sheets")
    (root / R.FREEZE).unlink()
    assert "the sample is checked against the freeze record" in refused(root, "sheets")
    assert nothing_written(root)


def test_a_registered_hash_is_compared_over_16_characters_or_more(tmp_path: Path) -> None:
    path = tmp_path / "file.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    digest = sha(path)
    assert R.require_registered(path, digest, "a file") == digest
    assert R.require_registered(path, digest[:16], "a file") == digest
    for short in (digest[:15], digest[:2], "", None, 16):
        with pytest.raises(SystemExit, match="no registered sha256 for a file"):
            R.require_registered(path, short, "a file")
    with pytest.raises(SystemExit, match=r"is not the registered file \(a file\)"):
        R.require_registered(path, digest[:15] + ("0" if digest[15] != "0" else "1"), "a file")
    # the same through the command: a record that names two characters of a list's hash
    root = world(tmp_path)
    record = json.loads((root / R.FREEZE).read_text(encoding="utf-8"))
    record["sample_lists"]["pilot"]["sha256"] = record["sample_lists"]["pilot"]["sha256"][:2]
    (root / R.FREEZE).write_text(json.dumps(record), encoding="utf-8")
    assert "no registered sha256 for the pilot list" in refused(root, "sheets")
    assert nothing_written(root)


@pytest.mark.parametrize("change", [{"status": "started"}, {"mode": "open-only"}])
def test_a_record_that_is_no_complete_freeze_is_refused(
    tmp_path: Path, change: dict[str, str]
) -> None:
    root = world(tmp_path)
    record = json.loads((root / R.FREEZE).read_text(encoding="utf-8")) | change
    (root / R.FREEZE).write_text(json.dumps(record), encoding="utf-8")
    assert "is not the record of a complete freeze run" in refused(root, "sheets")
    assert nothing_written(root)


def test_a_reader_that_is_not_the_frozen_one_is_refused(tmp_path: Path) -> None:
    root = world(tmp_path)
    record = json.loads((root / R.FREEZE).read_text(encoding="utf-8"))
    for name in ("rules.py", "forms.py"):
        changed = json.loads(json.dumps(record))
        changed["code"][name] = "0" * 64
        (root / R.FREEZE).write_text(json.dumps(changed), encoding="utf-8")
        assert f"is not the registered file (the frozen {name})" in refused(root, "sheets")
    assert sha(Path(F.rules.__file__)).startswith(F.RULES_SHA256) and nothing_written(root)


def test_the_reader_must_be_the_one_the_form_classifier_was_built_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a record that registers the rules.py on disk is not enough: its hash must begin with the
    # prefix that forms.py pins, which is the one the sheets name
    root = world(tmp_path)
    monkeypatch.setattr(F, "RULES_SHA256", "0" * 16)
    assert "rules.py is not the frozen file (0000000000000000)" in refused(root, "sheets")
    assert nothing_written(root)


def test_marked_statements_must_be_the_subset_of_the_counts_file(tmp_path: Path) -> None:
    root = world(tmp_path)
    register(root, ids_sha256=D.ids_sha256(["S00001"]))
    assert "are not the subset that" in refused(root, "sheets") and nothing_written(root)


def test_a_statement_outside_the_test_period_is_refused(tmp_path: Path) -> None:
    def late(statements: list[dict[str, Any]], _: Any) -> None:
        statements[4] |= {"event_date": "2026-01-02"}
        statements[5] |= {"event_date": "2022-12-31"}

    message = refused(world(tmp_path, edit=late), "sheets")
    assert "not dated in the test period: ['S00005', 'S00006']" in message


def test_the_rule_reading_must_be_the_registered_one(tmp_path: Path) -> None:
    def other_end(statements: list[dict[str, Any]], _: Any) -> None:
        assert statements[6]["stated_end"] == "2025-04-30"  # Next release April 2025.
        statements[6] |= {"stated_end": "2025-04-29"}

    message = refused(world(tmp_path, edit=other_end), "sheets")
    assert "S00007: the rule reader and the registered list disagree" in message
    assert "month_year ending 2025-04-30; the list, month_year ending 2025-04-29" in message

    def other_form(statements: list[dict[str, Any]], _: Any) -> None:
        statements[6] |= {"form": "quarter"}

    message = refused(world(tmp_path / "form", edit=other_form), "sheets")
    assert "the reader gives month_year ending 2025-04-30; the list, quarter" in message

    def stale(statements: list[dict[str, Any]], _: Any) -> None:
        statements[0] |= {"availability_text": "Unavailable", "form": "month_year"}
        statements[0] |= {"related_text": "Next release April 2023.", "stated_end": "2023-04-30"}
        statements[0] |= {"event_date": "2023-05-02"}

    message = refused(world(tmp_path / "stale", edit=stale), "sheets")
    assert "S00001: the rule reader and the registered list disagree" in message
    assert "ending 2023-04-30, stale" in message and nothing_written(tmp_path / "stale" / "out")

    def undated(statements: list[dict[str, Any]], _: Any) -> None:
        # a statement with no stated period, marked in a list that agrees with the reader
        reading = F.classify(C.statement_text("Unavailable", "Next release: TBD"), "2023-08-08")
        assert (reading.form, reading.end, reading.stale) == ("tbd", None, False)
        statements[6] |= {"availability_text": "Unavailable", "related_text": "Next release: TBD"}
        statements[6] |= {"form": "tbd", "stated_end": ""}

    message = refused(world(tmp_path / "undated", edit=undated), "sheets")
    assert "S00007: the rule reader and the registered list disagree" in message
    assert "the reader gives tbd ending nowhere; the list, tbd ending ." in message
    assert nothing_written(tmp_path / "undated" / "out")


def test_the_text_shown_must_give_the_reading(tmp_path: Path) -> None:
    root = world(tmp_path)
    path = root / R.ITEMS
    text = path.read_text(encoding="utf-8")
    assert text.count("Next release April 2024.") > 1
    path.write_text(text.replace("Next release April 2024.", "Next release 1 April 2024.", 1))
    register(root)
    message = refused(root, "sheets")
    assert "the text shown, read on its own, does not give the statement's rule reading" in message
    assert nothing_written(root)
    # the same period under another statement type is another reading too
    one = F.classify(C.statement_text("Unavailable", "Next release April 2024."), "2023-01-02")
    two = F.classify(
        C.statement_text("Unavailable", "Estimated recovery: April 2024."), "2023-01-02"
    )
    assert (one.start, one.end, one.stale) == (two.start, two.end, two.stale)
    assert (one.statement_type, two.statement_type) == ("next_delivery", "recovery")
    path.write_text(
        text.replace("Next release April 2024.", "Estimated recovery: April 2024.", 1),
        encoding="utf-8",
    )
    register(root)
    assert message == refused(root, "sheets") and nothing_written(root)


def test_the_item_file_must_hold_the_display_rows_of_the_list(tmp_path: Path) -> None:
    root = world(tmp_path)
    path = root / R.ITEMS
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"display_event_id": "E00004b"', '"display_event_id": "E00004a"'))
    register(root)
    assert "the item of S00004 is not the display row" in refused(root, "sheets")
    lines = text.splitlines(keepends=True)
    path.write_text("".join(lines[1:]), encoding="utf-8")
    register(root)
    assert "does not hold the items of the marked statements" in refused(root, "sheets")
    path.write_text(text.replace('"reason_for_shortage"', '"reason"', 1), encoding="utf-8")
    register(root)
    assert "an item lacks one of" in refused(root, "sheets")
    # an item with another Date of update or another stated end than the list gives
    item = json.loads(lines[6])
    assert (item["item_id"], item["date_of_update"], item["stated_end"]) == (
        "S00007",
        "2024-08-08",
        "2025-04-30",
    )
    for key, value in (("date_of_update", "2024-08-09"), ("stated_end", "2025-04-29")):
        changed = json.dumps(item | {key: value}, sort_keys=True) + "\n"
        path.write_text("".join([*lines[:6], changed, *lines[7:]]), encoding="utf-8")
        register(root)
        message = refused(root, "sheets")
        assert "the item of S00007 is not the display row, the date or the stated end" in message
    assert nothing_written(root)

    def stranger(statements: list[dict[str, Any]], _: Any) -> None:
        statements[2] |= {"event_id": "E00002a"}

    message = refused(world(tmp_path / "row", edit=stranger), "sheets")
    assert "S00003: its display row E00002a is not an event of this statement" in message


def as_first_draw(name: str, index: int) -> Edit:
    """Put a marked statement on a first-draw list."""

    def edit(statements: list[dict[str, Any]], first: dict[str, list[dict[str, Any]]]) -> None:
        first[name].append(statements[index])

    return edit


@pytest.mark.parametrize("name", R.FIRST_DRAW)
def test_a_statement_of_the_first_draw_in_a_final_subset_is_refused(
    tmp_path: Path, name: str
) -> None:
    root = world(tmp_path, edit=as_first_draw(name, 8))
    message = refused(root, "sheets")
    assert "1 marked statements are statements of the pilot, the check sets or the" in message
    assert "S00009" in message and "the files contradict each other" in message
    assert refused(root, "sheets", "--leave-off") == message and nothing_written(root)


def test_a_subset_that_is_not_final_leaves_such_statements_off_when_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def edit(statements: list[dict[str, Any]], first: dict[str, list[dict[str, Any]]]) -> None:
        first["literal"].append(statements[8])
        # the same notice of the same drug at another date as a pilot statement
        twin = first["pilot"][0]
        statements[20] |= {k: twin[k] for k in ("generic_name", "company_name")}
        twin |= {k: statements[20][k] for k in ("availability_text", "related_text")}

    root = world(tmp_path, final=False, edit=edit)
    message = refused(root, "sheets")
    assert "2 marked statements" in message and "S00009, S00021" in message
    assert "the subset is not final: --leave-off leaves them off the sheets" in message
    assert nothing_written(root)
    assert run(root, "sheets", "--leave-off") == 0
    assert "task E: 98 of 100 registered statements (2 left off)" in capsys.readouterr().out
    sample = json.loads((root / R.OUT_NAME / R.MANIFEST).read_text(encoding="utf-8"))["sample"]
    assert sample["left_off"] == ["S00009", "S00021"] and sample["final"] is False
    assert (sample["registered"], sample["statements"]) == (100, 98)
    assert sample["assigned"] == {"A1": 44, "A2": 44, "both": 10}
    shown = {row["item_id"] for a in R.ANNOTATORS for row in blank(root, a)[1]}
    assert len(shown) == 98 and not shown & {S.item_id("S00009"), S.item_id("S00021")}
    for annotator in R.ANNOTATORS:
        text = (root / R.OUT_NAME / f"reference_{annotator}_items.txt").read_text(encoding="utf-8")
        assert "Drug9 Injection" not in text and text.count("=== ") == 54
    # the scorer follows the manifest: 98 statements, 2 left off
    returned = [str(fill(root, a)) for a in R.ANNOTATORS]
    assert run(root, "score", "--a1", returned[0], "--a2", returned[1]) == 0
    scored = json.loads((root / R.OUT_NAME / R.RESULT).read_text(encoding="utf-8"))
    assert (scored["statements"], scored["registered"], scored["left_off"]) == (98, 100, 2)
    assert scored["subset_final"] is False and scored["reading_confirmed"]["n"] == 98


def test_a_twin_of_a_labelled_statement_counts_as_labelled() -> None:
    events = pd.DataFrame(
        event_rows(
            [
                labelled_statement(1),
                statement(2) | {"generic_name": "DRUG1  injection", "company_name": "maker 1"},
                statement(3),
            ]
        )
    )
    twin = events["statement_group_id"] == "S00002"
    events.loc[twin, "statement_text"] = "NEXT release in  lot 1; date tbd"
    assert R.labelled(events, ["L00001", "L99999"]) == {"L00001", "L99999", "S00002"}
    assert R.labelled(events, []) == set()


def test_a_sheet_that_holds_a_verdict_is_not_written_over(tmp_path: Path) -> None:
    root = world(tmp_path)
    assert run(root, "sheets") == 0
    path = root / R.OUT_NAME / "reference_A2.csv"
    original = path.read_bytes()
    meta, rows = S.read_sheet(path)
    rows[3]["verdict"] = "ok"
    path.write_text(S.sheet_text(R.SHEET_COLUMNS, rows, meta), encoding="utf-8")
    kept = path.read_bytes()
    message = refused(root, "sheets")
    assert "reference_A2.csv: the sheet holds a verdict or a sitting time" in message
    assert path.read_bytes() == kept != original
    # a sitting time alone, a note alone and a file that is no sheet count as filled too
    timed = [(k, "10:00" if k == "sitting_start" else v) for k, v in meta]
    rows[3]["verdict"] = ""
    for text in (
        S.sheet_text(R.SHEET_COLUMNS, rows, timed),
        S.sheet_text(R.SHEET_COLUMNS, [rows[0] | {"note": "?"}, *rows[1:]], meta),
    ):
        path.write_text(text, encoding="utf-8")
        assert R.holds_marks(path) and "filled in place" in refused(root, "sheets")
    path.write_bytes(b"\xff\xfe\x00no sheet")
    assert R.holds_marks(path) and "filled in place" in refused(root, "sheets")
    path.write_bytes(original)
    assert not R.holds_marks(path) and not R.holds_marks(path.with_name("absent.csv"))
    assert run(root, "sheets") == 0 and path.read_bytes() == original


def test_the_sealed_folder_is_never_a_root_an_output_or_a_sheet(tmp_path: Path) -> None:
    sealed = tmp_path / "sealed" / "out"
    for arguments in (
        ["sheets", "--root", str(sealed)],
        ["sheets", "--root", str(tmp_path), "--out", str(sealed)],
        ["validate", str(sealed / "reference_A1.csv")],
        ["score", "--a1", "a.csv", "--a2", "b.csv", "--out", str(sealed)],
    ):
        with pytest.raises(SystemExit, match="never touches the sealed folder"):
            R.main(arguments)


def test_a_link_that_leads_into_a_sealed_folder_is_refused(tmp_path: Path) -> None:
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "sheet.csv").write_text("no sheet\n", encoding="utf-8")
    file_link, folder_link = tmp_path / "linked.csv", tmp_path / "linked"
    file_link.symlink_to(sealed / "sheet.csv")
    folder_link.symlink_to(sealed, target_is_directory=True)
    for path in (file_link, folder_link, folder_link / "sheet.csv", folder_link / "absent.csv"):
        assert "sealed" not in path.parts  # nothing in the path as written names the folder
        with pytest.raises(SystemExit, match="never touches the sealed folder"):
            R.not_sealed(path)
    with pytest.raises(SystemExit, match="never touches the sealed folder"):
        R.main(["validate", str(file_link)])
    plain = tmp_path / "unsealed" / "sheet.csv"  # a name that only contains the word is open
    assert R.not_sealed(plain) == plain


def test_no_file_a_command_is_given_may_lie_in_the_sealed_folder(tmp_path: Path) -> None:
    root = world(tmp_path)
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    guide = sealed / "guide.md"
    guide.write_text(GUIDE_TEXT, encoding="utf-8")
    stop = "never touches the sealed folder"
    with pytest.raises(SystemExit, match=stop):
        R.main(["sheets", "--root", str(root), "--guide", str(guide)])
    assert nothing_written(root) and run(root, "sheets") == 0
    good = {a: fill(root, a) for a in R.ANNOTATORS}
    inside = {a: sealed / path.name for a, path in good.items()}
    for annotator, path in good.items():
        inside[annotator].write_bytes(path.read_bytes())
    blank_copy = sealed / "blank.csv"
    blank_copy.write_bytes((root / R.OUT_NAME / "reference_A1.csv").read_bytes())
    for arguments in (
        ["validate", str(inside["A1"])],
        ["validate", str(good["A1"]), "--blank", str(blank_copy)],
        ["score", "--a1", str(inside["A1"]), "--a2", str(good["A2"])],
        ["score", "--a1", str(good["A1"]), "--a2", str(inside["A2"])],
        ["score", "--a1", str(good["A1"]), "--a2", str(good["A2"]), "--adjudication", str(guide)],
    ):
        with pytest.raises(SystemExit, match=stop):
            run(root, *arguments)
    out = root / R.OUT_NAME
    assert sorted(path.name for path in out.iterdir()) == sorted(
        [
            *(f"reference_{a}{end}" for a in R.ANNOTATORS for end in (".csv", "_items.txt")),
            R.MANIFEST,
        ]
    )


# --------------------------------------------------------------------------------------------
# What a sheet shows
# --------------------------------------------------------------------------------------------


def test_sheet_columns_header_lines_and_blank_entered_cells(made: Path) -> None:
    text = (made / R.OUT_NAME / "reference_A1.csv").read_text(encoding="utf-8")
    table = list(csv.reader(io.StringIO(text)))
    header = next(line for line in table if line[0] == "item_id")
    assert tuple(header) == R.SHEET_COLUMNS == (*S.SHOWN, *R.RULE, *R.ENTERED)
    assert R.ENTERED == ("verdict", "codes", "true_end", "start_differs", "note")
    assert R.RULE == ("rule_statement_type", "rule_start", "rule_end", "rule_stale")
    hidden = ("status", "capture", "outcome", "stratum", "event_id", "group", "thread", "split")
    assert not [c for c in header if any(word in c for word in hidden)]
    assert "form" not in header and "stated_end" not in header and "assigned_to" not in header
    assert all(cell.startswith('"') for cell in text.splitlines())  # every cell is quoted
    meta, rows = blank(made, "A1")
    said = dict(meta)
    assert said["task"] == "E reference readings (AUDIT_GUIDE.md section 12.2)"
    assert (said["sheet"], said["annotator"], said["seed"]) == ("reference", "A1", "20261001")
    assert said["guide"] == S.guide_stamp(GUIDE_TEXT) and said["items"] == "55"
    assert said["rule reader"] == f"rules.py sha256 {F.RULES_SHA256}"
    assert said["values of verdict"].startswith("ok | error | cannot_tell")
    assert said["values of codes"].startswith("K1; K2; K3; K4")
    assert said["values of start_differs"].startswith("1 or 0")
    assert [said[f"code {code}"] for code in R.CODES] == list(R.CODES.values())
    assert [key for key, _ in meta][-2:] == ["sitting_start", "sitting_end"]
    assert said["sitting_start"] == said["sitting_end"] == ""
    assert all(row[c] == "" for row in rows for c in R.ENTERED)
    assert all(re.fullmatch(r"I[0-9a-f]{10}", row["item_id"]) for row in rows)


def test_rule_cells_are_the_frozen_reading_and_the_registered_end(made: Path) -> None:
    by_item = statement_of()
    types = Counter()
    for annotator in R.ANNOTATORS:
        for row in blank(made, annotator)[1]:
            s = by_item[row["item_id"]]
            reading = F.classify(
                C.statement_text(s["availability_text"], s["related_text"]), s["event_date"]
            )
            assert row["rule_statement_type"] == reading.statement_type
            assert (row["rule_start"], row["rule_end"]) == (reading.start, reading.end)
            assert row["rule_end"] == s["stated_end"] and row["rule_stale"] == "0"
            assert row["rule_start"] <= row["rule_end"] >= row["date_of_update"] == s["event_date"]
            types[row["rule_statement_type"]] += 1
    assert set(types) == {"recovery", "next_delivery"}
    # the reading comes from the statement's events, by the call of the dataset builder
    root = made
    record = R.frozen_record(root)
    rows, counts, _ = R.marked_rows(root, record)
    events, _ = R.load_events(root, record)
    items, _ = R.harness_items(root, counts, rows)
    mine = events[events["statement_group_id"].isin({r["statement_group_id"] for r in rows})]
    builder = F.statement_forms(mine).set_index("statement_group_id")
    readings = R.rule_readings(events, rows, items)
    for row in rows:
        gid = row["statement_group_id"]
        assert readings[gid] == {
            "rule_statement_type": builder.at[gid, "statement_type"],
            "rule_start": builder.at[gid, "start"],
            "rule_end": builder.at[gid, "end"],
            "rule_stale": "0",
        }


def test_shown_cells_are_the_entry_block_of_the_harness(made: Path) -> None:
    labels = {
        "drug": "Drug",
        "company": "Company",
        "presentation": "Presentation",
        "therapeutic_category": "Therapeutic category",
        "initial_posting_date": "Initial posting date",
        "type_of_update": "Type of update",
        "date_of_update": "Date of update",
        "availability_information": "Availability information",
        "related_information": "Related information",
        "reason_for_shortage": "Reason for shortage",
    }
    quoted = ("availability_information", "related_information", "reason_for_shortage")
    assert tuple(labels) == S.SHOWN[1:] == R.SHOWN[1 : len(S.SHOWN)]
    registered = {i.item_id: i for i in read.load_items(made / R.ITEMS)}
    seen = Counter()
    for annotator in R.ANNOTATORS:
        text = (made / R.OUT_NAME / f"reference_{annotator}_items.txt").read_text(encoding="utf-8")
        blocks = text.split("=== ")[1:]
        rows = blank(made, annotator)[1]
        assert len(blocks) == len(rows) == 55
        for n, (row, block) in enumerate(zip(rows, blocks, strict=True), start=1):
            cells = {c: S.unguarded(v) for c, v in row.items()}
            lines = ["Entry"]
            for column, label in labels.items():
                cell = cells[column]
                if column in quoted and cell != S.BLANK:
                    cell = f'"{cell}"'
                lines.append(f"- {label}: {cell}")
            entry = "\n".join(lines)
            item = registered[statement_of()[row["item_id"]]["statement_group_id"]]
            assert entry in read.render_prompt(read.TEMPLATES["literal-v1"], item)
            stale = "stale" if row["rule_stale"] == "1" else "not stale"
            reading = (
                f"Rule reading: {row['rule_statement_type']}, {row['rule_start']} to "
                f"{row['rule_end']}, {stale}"
            )
            assert block == f"{n} of 55: {row['item_id']} ===\n{entry}\n{reading}\n" + (
                "\n" if n < 55 else ""
            )
            seen.update(
                k for k in ("(blank)", "'-", "'=") if any(v.startswith(k) for v in row.values())
            )
    assert seen["(blank)"] and seen["'-"] and seen["'="]  # blanks and guarded cells were met
    assert read.ENTRY_BLOCK.count("\n- ") == len(labels) and "Status" not in read.ENTRY_BLOCK
    item = json.loads((made / R.ITEMS).read_text(encoding="utf-8").splitlines()[0])
    assert R.entry_block(item) == read.render_prompt(
        read.PromptTemplate("x", "literal", read.ENTRY_BLOCK), read.ReadItem.from_dict(item)
    )
    assert (
        R.rule_line(
            {
                "rule_statement_type": "recovery",
                "rule_start": "2021-06-01",
                "rule_end": "2021-06-30",
                "rule_stale": "0",
            }
        )
        == "Rule reading: recovery, 2021-06-01 to 2021-06-30, not stale"
    )


def test_manifest_records_inputs_sample_and_files(made: Path) -> None:
    out = made / R.OUT_NAME
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["seed"] == 20261001 and sorted(manifest) == [
        "about",
        "inputs",
        "sample",
        "seed",
        "sheets",
    ]
    inputs = manifest["inputs"]
    assert inputs["eligible_sha256"] == sha(made / R.ELIGIBLE)
    assert inputs["counts_sha256"] == sha(made / R.COUNTS)
    assert inputs["events_sha256"] == sha(made / R.EVENTS)
    assert inputs["items_sha256"] == sha(made / R.ITEMS)
    assert not [key for key in inputs if "freeze" in key]  # a later run rewrites the record
    assert inputs["rules.py_sha256"].startswith(F.RULES_SHA256)
    assert inputs["forms.py_sha256"] == sha(Path(F.__file__))
    assert inputs["first_draw_lists_sha256"] == {
        name: sha(made / R.SAMPLES / f"sample_{name}.csv") for name in R.FIRST_DRAW
    }
    sample = manifest["sample"]
    ids = [f"S{n:05d}" for n in range(1, 101)]
    assert sample["ids_sha256"] == D.ids_sha256(ids) and sample["left_off"] == []
    assert (sample["registered"], sample["statements"], sample["final"]) == (100, 100, True)
    assert sample["assigned"] == {"A1": 45, "A2": 45, "both": 10}
    assert sample["by_year"] == dict(
        sorted(Counter(statement(n)["event_date"][:4] for n in range(1, 101)).items())
    )
    assert sample["by_form"] == dict(Counter(statement(n)["form"] for n in range(1, 101)))
    who = R.assignment(ids)
    pairs = sorted((S.item_id(i), who[i]) for i in ids)
    digest = hashlib.sha256("".join(f"{i},{w}\n" for i, w in pairs).encode()).hexdigest()
    assert sample["assignment_sha256"] == digest
    sheets = manifest["sheets"]
    assert sheets["guide"] == S.guide_stamp(GUIDE_TEXT)
    assert sheets["items_per_sheet"] == {"A1": 55, "A2": 55}
    assert sheets["minutes_per_sheet"] == {"A1": [28, 18, 41], "A2": [28, 18, 41]}
    assert sheets["files"] == {name: sha(out / name) for name in sorted(sheets["files"])}
    assert len(sheets["files"]) == 4
    text = json.dumps(manifest)
    assert not re.search(r"I[0-9a-f]{10}", text)  # nothing names who checks which item


def test_blank_sheet_is_in_the_layout_the_workbook_script_reads(made: Path) -> None:
    for annotator in R.ANNOTATORS:
        path = made / R.OUT_NAME / f"reference_{annotator}.csv"
        sheet = sheet_xlsx.read_csv_sheet(path)
        assert sheet.quoted_comments and sheet.newline == "\n"
        assert sheet.header == list(R.SHEET_COLUMNS) and sheet.header_at == 17
        assert sheet_xlsx.write_csv_sheet(sheet).encode("utf-8") == path.read_bytes()
        assert sheet.header.index("verdict") == len(R.SHOWN)
        assert "statement_type" not in sheet.header and "verdict_B" not in sheet.header
        # no first column of another task's sheet is a column of this one, so the workbook
        # script takes ``verdict`` for the first column to fill as soon as it names it
        others = [name for name in sheet_xlsx.FIRST_ENTERED if name != "verdict"]
        assert not set(others) & set(sheet.header)
        if "verdict" in sheet_xlsx.FIRST_ENTERED:
            assert sheet_xlsx.first_entered(sheet.header) == len(R.SHOWN)
    # the same for the sheet of ADJ and its first column, ``decision``
    columns = [*R.ADJUDICATION_SHOWN, *R.ADJUDICATION_ENTERED]
    assert columns.index("decision") == len(R.ADJUDICATION_SHOWN)
    assert not {name for name in sheet_xlsx.FIRST_ENTERED if name != "decision"} & set(columns)
    if "decision" in sheet_xlsx.FIRST_ENTERED:
        assert sheet_xlsx.first_entered(columns) == len(R.ADJUDICATION_SHOWN)


# --------------------------------------------------------------------------------------------
# Validator
# --------------------------------------------------------------------------------------------


def a_row(**cells: str) -> dict[str, str]:
    """A row of a sheet as the validator reads it: one shown reading, and the given entries."""
    shown = dict.fromkeys(R.SHOWN, "x") | {
        "item_id": "I0000000001",
        "date_of_update": "2023-03-10",
        "rule_statement_type": "recovery",
        "rule_start": "2023-06-01",
        "rule_end": "2023-06-30",
        "rule_stale": "0",
    }
    return shown | dict.fromkeys(R.ENTERED, "") | cells


def test_a_good_row_is_read() -> None:
    mark, errors, warnings = R.read_mark(a_row(verdict="ok"))
    assert (errors, warnings) == ([], [])
    assert mark == {"verdict": "ok", "codes": "", "true_end": "", "start_differs": "0", "note": ""}
    mark, errors, warnings = R.read_mark(
        a_row(verdict="error", codes="K2, K1;K2", true_end="2023-07", note="July, not June")
    )
    assert (errors, warnings) == ([], [])
    assert mark == {
        "verdict": "error",
        "codes": "K1;K2",
        "true_end": "2023-07-31",
        "start_differs": "0",
        "note": "July, not June",
    }
    mark, errors, warnings = R.read_mark(a_row(verdict="error", codes="K3"))
    assert (errors, warnings) == ([], []) and mark is not None and mark["true_end"] == ""
    mark, errors, warnings = R.read_mark(a_row(verdict="ok", start_differs="1"))
    assert (errors, warnings) == ([], []) and mark is not None and mark["start_differs"] == "1"
    mark, errors, warnings = R.read_mark(a_row(verdict="cannot_tell", note="two targets"))
    assert (errors, warnings) == ([], []) and mark is not None and mark["verdict"] == "cannot_tell"
    mark, _, _ = R.read_mark(a_row(verdict="error", codes="K4 K1", true_end="2023-02-28"))
    assert mark is not None and (mark["codes"], mark["true_end"]) == ("K1;K4", "2023-02-28")
    assert R.code_list(" K1;K2 , K3\tK4 ") == ["K1", "K2", "K3", "K4"] and R.code_list(" ") == []


@pytest.mark.parametrize(
    ("cells", "error"),
    [
        ({}, "verdict is missing: it is not one of ok, error, cannot_tell"),
        ({"verdict": "OK"}, "verdict 'OK' is not one of ok, error, cannot_tell"),
        ({"verdict": "wrong"}, "verdict 'wrong' is not one of ok, error, cannot_tell"),
        ({"verdict": "error"}, "verdict is error but codes is empty"),
        ({"verdict": "ok", "codes": "K2"}, "codes is given but verdict is ok"),
        (
            {"verdict": "cannot_tell", "codes": "K1", "note": "n"},
            "codes is given but verdict is cannot_tell",
        ),
        ({"verdict": "error", "codes": "K5"}, "codes: unknown K5 (the codes are K1, K2, K3, K4)"),
        (
            {"verdict": "error", "codes": "K2; k1; O3"},
            "codes: unknown k1 O3 (the codes are K1, K2, K3, K4)",
        ),
        (
            {"verdict": "error", "codes": "K2", "true_end": "June 2023"},
            "true_end: 'June 2023' is not YYYY-MM-DD or YYYY-MM",
        ),
        (
            {"verdict": "error", "codes": "K2", "true_end": "2023-02-30"},
            "true_end: 2023-02-30 is not a calendar date",
        ),
        (
            {"verdict": "error", "codes": "K2", "true_end": "2023-13"},
            "true_end: 2023-13 is not a calendar month",
        ),
        (
            {"verdict": "error", "codes": "K2", "true_end": "30/06/2023"},
            "true_end: '30/06/2023' is not YYYY-MM-DD or YYYY-MM",
        ),
        ({"verdict": "ok", "true_end": "2023-06-30"}, "true_end is given but verdict is ok"),
        (
            {"verdict": "cannot_tell", "true_end": "2023-07", "note": "n"},
            "true_end is given but verdict is cannot_tell",
        ),
        ({"verdict": "ok", "start_differs": "2"}, "start_differs must be 1 or 0"),
        ({"verdict": "ok", "start_differs": "yes"}, "start_differs must be 1 or 0"),
        ({"verdict": "cannot_tell"}, "verdict is cannot_tell but note is empty: say why"),
    ],
)
def test_every_row_rule_of_the_validator(cells: dict[str, str], error: str) -> None:
    mark, errors, warnings = R.read_mark(a_row(**cells))
    assert mark is None and errors == [error] and warnings == []


def test_a_row_can_have_several_errors() -> None:
    mark, errors, _ = R.read_mark(
        a_row(verdict="cannot_tell", codes="K9", true_end="soon", start_differs="x")
    )
    assert mark is None and len(errors) == 6


@pytest.mark.parametrize(
    ("cells", "warning"),
    [
        (
            {"codes": "K2"},
            "error with no true_end: give the right last day, or K3 if there is no date",
        ),
        (
            {"codes": "K1"},
            "error with no true_end: give the right last day, or K3 if there is no date",
        ),
        (
            {"codes": "K3", "true_end": "2023-07"},
            "K3 says that the target gives no date, but true_end gives one",
        ),
        (
            {"codes": "K2", "true_end": "2023-06"},
            "K2 says that the last day is wrong, but true_end is the rule_end",
        ),
        (
            {"codes": "K4", "true_end": "2023-03-10"},
            "K4 is the code of a period that ends before the Date of update: true_end is not "
            "before it",
        ),
        (
            {"codes": "K2", "true_end": "2023-03-09"},
            "K4 is the code of a period that ends before the Date of update: true_end is "
            "before it without K4",
        ),
        (
            {"codes": "K2", "true_end": "2023-07", "start_differs": "1"},
            "start_differs is 1 but the verdict is not ok (it is for a right last day)",
        ),
    ],
)
def test_every_warning_of_the_validator(cells: dict[str, str], warning: str) -> None:
    mark, errors, warnings = R.read_mark(a_row(verdict="error", **cells))
    assert mark is not None and errors == [] and warnings == [warning]


def test_rows_that_raise_no_warning() -> None:
    for cells in (
        {"verdict": "error", "codes": "K4", "true_end": "2023-03-09"},
        {"verdict": "error", "codes": "K1;K4", "true_end": "2022-12"},
        {"verdict": "error", "codes": "K1;K3"},
        {"verdict": "error", "codes": "K1", "true_end": "2023-06-30"},
        {"verdict": "error", "codes": "K2", "true_end": "2023-03-10"},
        {"verdict": "ok", "start_differs": "0"},
    ):
        mark, errors, warnings = R.read_mark(a_row(**cells))
        assert mark is not None and (errors, warnings) == ([], []), cells
    _, _, warnings = R.read_mark(a_row(verdict="cannot_tell", note="n", start_differs="1"))
    assert warnings == ["start_differs is 1 but the verdict is not ok (it is for a right last day)"]
    row = a_row(verdict="error", codes="K2", true_end="2023-03-09") | {"date_of_update": "(blank)"}
    assert R.read_mark(row)[2] == []  # no anchor to compare with


def sheet(made: Path, annotator: str = "A1") -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    """A filled sheet in memory: every row ``ok``, one sitting of half an hour."""
    meta, rows = blank(made, annotator)
    clock = {"sitting_start": "09:00", "sitting_end": "09:30"}
    return [(k, clock.get(k, v)) for k, v in meta], [row | {"verdict": "ok"} for row in rows]


def test_a_filled_sheet_validates_against_its_blank(made: Path) -> None:
    meta, rows = sheet(made)
    checked = R.validate_sheet(meta, rows, blank(made, "A1")[1])
    assert checked.ok and checked.warnings == [] and checked.minutes == 30
    assert len(checked.marks) == 55 and set(checked.marks) == {row["item_id"] for row in rows}
    assert R.validate_sheet(meta, rows, None).ok


def test_sitting_times_are_required_as_in_task_a(made: Path) -> None:
    meta, rows = sheet(made)
    handed = blank(made, "A1")[1]
    untimed = [(k, "" if k in S.SITTING_KEYS else v) for k, v in meta]
    message = "header: give one sitting_start and one sitting_end (HH:MM) for each sitting"
    assert R.validate_sheet(untimed, rows, handed).errors == [message]
    half = [(k, "" if k == "sitting_end" else v) for k, v in meta]
    assert R.validate_sheet(half, rows, handed).errors == [message]
    odd = [(k, "half past nine" if k == "sitting_end" else v) for k, v in meta]
    assert R.validate_sheet(odd, rows, handed).errors == [
        "header: sitting_end 'half past nine' is not a time (HH:MM)"
    ]
    back = [(k, "08:59" if k == "sitting_end" else v) for k, v in meta]
    assert R.validate_sheet(back, rows, handed).errors == [
        "header: a sitting_end is not after its sitting_start"
    ]
    two = [*meta, ("sitting_start", "14:00"), ("sitting_end", "14:12")]
    assert R.validate_sheet(two, rows, handed).minutes == 42


def test_items_and_shown_cells_must_be_those_of_the_blank(made: Path) -> None:
    meta, rows = sheet(made)
    handed = blank(made, "A1")[1]
    first, second = rows[0]["item_id"], rows[1]["item_id"]
    assert R.validate_sheet(meta, rows[1:], handed).errors == [
        f"sheet: item {first} of the blank sheet is missing"
    ]
    stranger = rows[0] | {"item_id": "I0000000000"}
    assert R.validate_sheet(meta, [stranger, *rows[1:]], handed).errors == [
        "row 1 (I0000000000): this item is not in the blank sheet",
        f"sheet: item {first} of the blank sheet is missing",
    ]
    twice = R.validate_sheet(meta, [*rows, rows[1]], handed)
    assert twice.errors == [
        f"row 2 ({second}): item_id is missing or repeated",
        f"row 56 ({second}): item_id is missing or repeated",
    ]
    assert second not in twice.marks and len(twice.marks) == 54
    nameless = R.validate_sheet(meta, [rows[0] | {"item_id": ""}, *rows[1:]], handed)
    assert nameless.errors[0] == "row 1 (no item_id): item_id is missing or repeated"
    for column in (
        "rule_end",
        "rule_start",
        "rule_statement_type",
        "rule_stale",
        "drug",
        "date_of_update",
    ):
        changed = rows[0] | {column: rows[0][column] + "1"}
        errors = R.validate_sheet(meta, [changed, *rows[1:]], handed).errors
        assert len(errors) == 1 and f"shown cells changed ({column})" in errors[0], column
    both = rows[0] | {"company": "?", "rule_end": "2030-01-01"}
    errors = R.validate_sheet(meta, [both, *rows[1:]], handed).errors
    assert errors == [
        f"row 1 ({first}): shown cells changed (company, rule_end); "
        "import every column as text and do not edit shown cells"
    ]
    # a guarded cell may come back with or without its apostrophe
    guarded = next(n for n, row in enumerate(rows) if row["presentation"].startswith("'-"))
    bare = rows[guarded] | {"presentation": rows[guarded]["presentation"][1:]}
    assert R.validate_sheet(meta, [*rows[:guarded], bare, *rows[guarded + 1 :]], handed).ok
    # row errors are named by row and item
    wrong = rows[2] | {"verdict": "error"}
    errors = R.validate_sheet(meta, [*rows[:2], wrong, *rows[3:]], handed).errors
    assert errors == [f"row 3 ({rows[2]['item_id']}): verdict is error but codes is empty"]


def test_a_sheet_without_its_columns_or_rows_is_one_error(made: Path) -> None:
    meta, rows = sheet(made)
    short = [{k: v for k, v in row.items() if k not in ("codes", "rule_end")} for row in rows]
    assert R.validate_sheet(meta, short).errors == ["sheet: columns missing: rule_end, codes"]
    assert R.validate_sheet(meta, []).errors == ["sheet: the sheet has no rows"]
    line = ";".join(R.SHEET_COLUMNS)
    errors = R.validate_sheet(meta, [{line: ";".join("x" * len(R.SHEET_COLUMNS))}]).errors
    assert len(errors) == 1 and errors[0].endswith("save it comma-separated)")


def test_validate_command_finds_the_blank_and_refuses_the_blank_itself(
    made: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = fill(made, "A1", name="v_good.csv")
    assert run(made, "validate", str(good)) == 0
    assert (
        "55 rows, 55 valid, 0 errors, 0 warnings; sittings: 30 minutes" in capsys.readouterr().out
    )
    item = blank(made, "A1")[1][0]["item_id"]
    bad = fill(made, "A1", {item: {"verdict": "error"}}, name="v_bad.csv")
    assert run(made, "validate", str(bad)) == 1
    printed = capsys.readouterr().out
    assert f"error: row 1 ({item}): verdict is error but codes is empty" in printed
    assert "55 rows, 54 valid, 1 errors" in printed
    untimed = fill(made, "A1", times=None, name="v_untimed.csv")
    assert run(made, "validate", str(untimed)) == 1
    assert "give one sitting_start and one sitting_end" in capsys.readouterr().out
    # the blank of the other annotator, given by hand, does not hold these items
    assert (
        run(made, "validate", str(good), "--blank", str(made / R.OUT_NAME / "reference_A2.csv"))
        == 1
    )
    assert "this item is not in the blank sheet" in capsys.readouterr().out
    assert run(made, "validate", str(made / R.OUT_NAME / "reference_A1.csv")) == 1
    assert "this is the blank sheet itself; fill a copy kept elsewhere" in capsys.readouterr().out
    # with no blank to compare with, the sheet is checked on its own and the gap is named
    assert R.main(["validate", str(good), "--root", str(made.parent / "nowhere")]) == 0
    assert "no blank sheet to compare with" in capsys.readouterr().out
    # a sheet whose header names another task or no annotator takes no blank of this task
    meta, rows = S.read_sheet(good)
    for key, value in (("sheet", "pilot"), ("sheet", ""), ("annotator", "ADJ")):
        renamed = [(k, value if k == key else v) for k, v in meta]
        odd = good.with_name("v_renamed.csv")
        odd.write_text(S.sheet_text(R.SHEET_COLUMNS, rows, renamed), encoding="utf-8")
        assert run(made, "validate", str(odd)) == 0
        assert "no blank sheet to compare with" in capsys.readouterr().out, (key, value)
    # a sheet or a blank that is not there is one error, not a traceback
    assert run(made, "validate", str(good.with_name("absent.csv"))) == 1
    assert "absent.csv not found" in capsys.readouterr().out
    assert run(made, "validate", str(good), "--blank", str(good.with_name("no_blank.csv"))) == 1
    assert "no_blank.csv not found" in capsys.readouterr().out
    other = made.parent / "filled" / "v_latin.csv"
    other.write_bytes(good.read_text(encoding="utf-8").replace("Drug", "Drüg").encode("latin-1"))
    assert run(made, "validate", str(other)) == 1
    assert "the file is not UTF-8 text" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------
# Scorer
# --------------------------------------------------------------------------------------------


def test_wilson_interval_and_kappa() -> None:
    stats = pytest.importorskip("scipy.stats")
    assert R.wilson(96, 100) == [0.9016, 0.9843] and R.wilson(97, 100) == [0.9155, 0.9897]
    assert R.wilson(100, 100) == [0.963, 1.0] and R.wilson(0, 10) == [0.0, 0.2775]
    assert R.wilson(0, 0) is None
    for k, n in ((96, 100), (97, 100), (100, 100), (0, 10), (3, 7), (55, 98)):
        exact = stats.binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
        assert R.wilson(k, n) == pytest.approx([exact.low, exact.high], abs=6e-5)
    assert R.share(96, 100) == {"n": 96, "share": 0.96, "wilson95": [0.9016, 0.9843]}
    assert R.share(0, 0) == {"n": 0, "share": None, "wilson95": None}
    # a share is given to four places, as its interval is: 85 of the 99 left by one left off
    assert R.share(85, 99) == {"n": 85, "share": 0.8586, "wilson95": R.wilson(85, 99)}
    assert R.share(1, 3)["share"] == 0.3333 and R.share(2, 3)["share"] == 0.6667
    pairs = [("error", "ok"), ("error", "error"), *[("ok", "ok")] * 7]
    assert R.cohen_kappa(pairs) == round(14 / 23, 4) == 0.6087
    assert R.cohen_kappa([("ok", "ok")] * 4) is None and R.cohen_kappa([]) is None
    assert R.cohen_kappa([("ok", "error"), ("error", "ok")]) == -1.0


def worked(root: Path) -> dict[str, Any]:
    """The hand-worked case: what A1 and A2 enter, and what ADJ decides.

    A1 alone: an error K2, an error K1 and K4, a cannot_tell, and a start_differs on an ok row.
    A2 alone: an error K3. Shared: A1 error against A2 ok; both error K2; A1 cannot_tell
    against A2 ok; and a start_differs of A2 on a row both call ok. Seven items reach ADJ, who
    confirms three (K2, K3, K2), rejects three and leaves one unresolved.
    """
    parts = split(root)
    a1, a2, both = parts["A1"], parts["A2"], parts["both"]
    k2 = {"verdict": "error", "codes": "K2", "true_end": "2030-06"}
    return {
        "A1": {
            a1[0]: k2,
            a1[1]: {"verdict": "error", "codes": "K4; K1", "true_end": "2022-12-31", "note": "old"},
            a1[2]: {"verdict": "cannot_tell", "note": "two targets"},
            a1[3]: {"start_differs": "1"},
            both[0]: k2 | {"note": "July"},
            both[1]: k2,
            both[2]: {"verdict": "cannot_tell", "note": "unclear"},
        },
        "A2": {
            a2[0]: {"verdict": "error", "codes": "K3"},
            both[1]: {"verdict": "error", "codes": "K2", "true_end": "2030-06-30"},
            both[3]: {"start_differs": "1"},
        },
        "decisions": {
            a1[0]: {
                "decision": "confirmed",
                "confirmed_codes": "K2",
                "confirmed_true_end": "2030-06",
            },
            a1[1]: {"decision": "rejected", "adj_note": "the reading stands"},
            a1[2]: {"decision": "unresolved"},
            a2[0]: {"decision": "confirmed", "confirmed_codes": "K3"},
            both[0]: {"decision": "rejected"},
            both[1]: {
                "decision": "confirmed",
                "confirmed_codes": "K2 ",
                "confirmed_true_end": "2030-06-30",
            },
            both[2]: {"decision": "rejected"},
        },
        "confirmed": [a1[0], a2[0], both[1]],
        "unresolved": [a1[2]],
        "differ": sorted([both[0], both[2]]),
    }


def adjudicate(
    root: Path, decisions: Mapping[str, Mapping[str, str]], name: str = "adj.csv"
) -> Path:
    """A filled copy of the adjudication sheet, kept outside the output folder."""
    meta, rows = S.read_sheet(root / R.OUT_NAME / R.ADJUDICATION)
    for row in rows:
        row |= decisions.get(row["item_id"], {})
    path = root.parent / "filled" / name
    columns = (*R.ADJUDICATION_SHOWN, *R.ADJUDICATION_ENTERED)
    path.write_text(S.sheet_text(columns, rows, meta), encoding="utf-8")
    return path


def test_score_on_a_hand_worked_case(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = world(tmp_path)
    assert run(root, "sheets") == 0
    out = root / R.OUT_NAME
    case = worked(root)
    returned = {a: fill(root, a, case[a]) for a in R.ANNOTATORS}
    sheets = ("--a1", str(returned["A1"]), "--a2", str(returned["A2"]))
    capsys.readouterr()
    assert run(root, "score", *sheets) == 3
    printed = capsys.readouterr().out
    assert "A1: 55 items; ok 49, error 4, cannot_tell 2; seconds per item: 32.7" in printed
    assert "A2: 55 items; ok 53, error 2, cannot_tell 0; seconds per item: 32.7" in printed
    assert "shared items: the same verdict on 8 of 10" in printed
    assert "7 items to adjudicate" in printed and not (out / R.RESULT).exists()

    stats = json.loads((out / R.AGREEMENT).read_text(encoding="utf-8"))
    assert stats["statements"] == 100 and stats["task"] == R.TASK
    assert stats["reported"]["A1"] == {
        "items": 55,
        "ok": 49,
        "error": 4,
        "cannot_tell": 2,
        "codes": {"K1": 1, "K2": 3, "K3": 0, "K4": 1},
        "start_differs": 1,
    }
    assert stats["reported"]["A2"] == {
        "items": 55,
        "ok": 53,
        "error": 2,
        "cannot_tell": 0,
        "codes": {"K1": 0, "K2": 1, "K3": 1, "K4": 0},
        "start_differs": 1,
    }
    assert stats["shared"] == {
        "items": 10,
        "same_verdict": 8,
        "raw_agreement": 0.8,
        "with_cannot_tell": 1,
        "kappa_ok_error": 0.6087,  # 9 clear pairs: (8/9 - 58/81) / (1 - 58/81) = 14/23
        "items_that_differ": case["differ"],
    }
    assert stats["minutes"] == {"A1": 30, "A2": 30}
    assert stats["seconds_per_item"] == {"A1": 32.7, "A2": 32.7}
    assert stats["sheets_sha256"] == {a: sha(returned[a]) for a in R.ANNOTATORS}

    # the sheets as submitted, byte for byte, and the manifest's record of them
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    for annotator in R.ANNOTATORS:
        name = f"submitted/reference_{annotator}.csv"
        assert (out / name).read_bytes() == returned[annotator].read_bytes()
        assert manifest["submitted"]["files"][name] == sha(returned[annotator])
    assert manifest["submitted"]["replaced"] == []
    assert manifest["agreement"] == {R.AGREEMENT: sha(out / R.AGREEMENT)}
    assert manifest["adjudication"] == {R.ADJUDICATION: sha(out / R.ADJUDICATION)}

    # the adjudication sheet: one row per reported item, both entries where the item is shared
    meta, rows = S.read_sheet(out / R.ADJUDICATION)
    assert (
        dict(meta)["items"] == "7"
        and dict(meta)["values of decision"] == "confirmed | rejected | unresolved"
    )
    assert [row["item_id"] for row in rows] == sorted(case["decisions"])
    assert tuple(rows[0]) == (*R.ADJUDICATION_SHOWN, *R.ADJUDICATION_ENTERED)
    assert all(row[c] == "" for row in rows for c in R.ADJUDICATION_ENTERED)
    by_item = {row["item_id"]: row for row in rows}
    parts = split(root)
    shown = {row["item_id"]: row for a in R.ANNOTATORS for row in blank(root, a)[1]}
    for item, row in by_item.items():
        assert all(row[c] == shown[item][c] for c in R.SHOWN)
        assert bool(row["A1_verdict"]) == (item not in parts["A2"])
        assert bool(row["A2_verdict"]) == (item not in parts["A1"])
    one = by_item[parts["A1"][1]]
    assert [one[f"A1_{c}"] for c in R.ENTERED] == ["error", "K1;K4", "2022-12-31", "0", "old"]
    assert [one[f"A2_{c}"] for c in R.ENTERED] == [""] * 5
    two = by_item[parts["both"][0]]
    assert [two[f"A1_{c}"] for c in R.ENTERED] == ["error", "K2", "2030-06-30", "0", "July"]
    assert [two[f"A2_{c}"] for c in R.ENTERED] == ["ok", "", "", "0", ""]
    three = by_item[parts["both"][1]]
    assert three["A1_true_end"] == three["A2_true_end"] == "2030-06-30"
    assert by_item[parts["A2"][0]]["A2_codes"] == "K3" and parts["both"][3] not in by_item

    # a second run before ADJ has decided writes the same sheet and waits again
    before = (out / R.ADJUDICATION).read_bytes()
    assert run(root, "score", *sheets) == 3 and (out / R.ADJUDICATION).read_bytes() == before

    filled = adjudicate(root, case["decisions"])
    capsys.readouterr()
    assert run(root, "score", *sheets, "--adjudication", str(filled)) == 0
    printed = capsys.readouterr().out
    assert "without_confirmed_error: 97 of 100 (0.97; Wilson 95% 0.9155 to 0.9897)" in printed
    assert "reading_confirmed: 96 of 100 (0.96; Wilson 95% 0.9016 to 0.9843)" in printed
    assert "confirmed errors 3, rejected 3, unresolved 1" in printed
    assert (out / R.ADJUDICATION).read_bytes() == before  # the blank one is left as it was

    scored = json.loads((out / R.RESULT).read_text(encoding="utf-8"))
    statements = statement_of()
    assert scored["status"] == "scored" and scored["task"] == R.TASK
    assert (scored["statements"], scored["registered"], scored["left_off"]) == (100, 100, 0)
    assert scored["subset_final"] is True and scored["sent_to_adjudication"] == 7
    assert (scored["confirmed_errors"], scored["rejected"], scored["unresolved"]) == (3, 3, 1)
    assert scored["without_confirmed_error"] == {
        "n": 97,
        "share": 0.97,
        "wilson95": [0.9155, 0.9897],
    }
    assert scored["reading_confirmed"] == {"n": 96, "share": 0.96, "wilson95": [0.9016, 0.9843]}
    assert scored["codes"] == {"K1": 0, "K2": 2, "K3": 1, "K4": 0}
    assert scored["start_differs"] == 2
    assert scored["unresolved_items"] == case["unresolved"]
    assert [e["item_id"] for e in scored["errors"]] == sorted(case["confirmed"])
    for error in scored["errors"]:
        s = statements[error["item_id"]]
        assert (error["statement_group_id"], error["form"]) == (s["statement_group_id"], s["form"])
    by_error = {e["item_id"]: e for e in scored["errors"]}
    assert by_error[parts["A1"][0]]["codes"] == ["K2"]
    assert by_error[parts["A1"][0]]["true_end"] == "2030-06-30"
    assert (by_error[parts["A2"][0]]["codes"], by_error[parts["A2"][0]]["true_end"]) == (["K3"], "")

    # the tables by form class and by year, counted here from the made-up statements
    for key, table in (("form", scored["by_form"]), ("year", scored["by_year"])):
        value = (lambda s: s["form"]) if key == "form" else (lambda s: s["event_date"][:4])
        total = Counter(value(s) for s in statements.values())
        wrong = Counter(value(statements[i]) for i in case["confirmed"])
        open_ = Counter(value(statements[i]) for i in case["unresolved"])
        assert table == {
            name: {
                "statements": total[name],
                "confirmed_errors": wrong[name],
                "unresolved": open_[name],
                "reading_confirmed": total[name] - wrong[name] - open_[name],
            }
            for name in table
        }
        assert set(table) == set(total) and sum(t["statements"] for t in table.values()) == 100
    assert sorted(scored["by_year"]) == ["2023", "2024", "2025"]

    # the confirmed list, for E7: every statement but the three errors and the unresolved one
    left = {statements[i]["statement_group_id"] for i in (*case["confirmed"], *case["unresolved"])}
    wanted = sorted({s["statement_group_id"] for s in statements.values()} - left)
    assert scored["confirmed_statement_ids"] == wanted and len(wanted) == 96
    listed = S.read_csv(out / R.CONFIRMED)
    assert [row["statement_group_id"] for row in listed] == wanted
    assert all(tuple(row) == ("statement_group_id",) for row in listed)

    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["result"] == {
        R.CONFIRMED: sha(out / R.CONFIRMED),
        R.RESULT: sha(out / R.RESULT),
    }
    assert scored["adjudication_sha256"] == sha(filled)
    assert manifest["submitted"]["files"][f"submitted/{R.ADJUDICATION}"] == sha(filled)
    assert len(manifest["submitted"]["files"]) == 3
    assert (out / "submitted" / R.ADJUDICATION).read_bytes() == filled.read_bytes()
    assert scored["sheets_sha256"] == {a: sha(returned[a]) for a in R.ANNOTATORS}


def test_score_without_a_reported_item_needs_no_adjudication(tmp_path: Path) -> None:
    root = world(tmp_path)
    assert run(root, "sheets") == 0
    returned = [str(fill(root, a)) for a in R.ANNOTATORS]
    assert run(root, "score", "--a1", returned[0], "--a2", returned[1]) == 0
    out = root / R.OUT_NAME
    scored = json.loads((out / R.RESULT).read_text(encoding="utf-8"))
    assert scored["without_confirmed_error"] == {"n": 100, "share": 1.0, "wilson95": [0.963, 1.0]}
    assert scored["reading_confirmed"] == scored["without_confirmed_error"]
    assert scored["sent_to_adjudication"] == 0 and scored["errors"] == []
    assert len(scored["confirmed_statement_ids"]) == 100 and "adjudication_sha256" not in scored
    assert not (out / R.ADJUDICATION).exists()
    stats = json.loads((out / R.AGREEMENT).read_text(encoding="utf-8"))
    assert stats["shared"]["raw_agreement"] == 1.0 and stats["shared"]["kappa_ok_error"] is None


def scored_once(tmp_path: Path) -> tuple[Path, dict[str, Any], tuple[str, ...]]:
    """A world whose sheets were returned and scored up to the adjudication sheet."""
    root = world(tmp_path)
    assert run(root, "sheets") == 0
    case = worked(root)
    returned = {a: fill(root, a, case[a]) for a in R.ANNOTATORS}
    sheets = ("--a1", str(returned["A1"]), "--a2", str(returned["A2"]))
    assert run(root, "score", *sheets) == 3
    return root, case, sheets


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"decision": ""}, "no decision"),
        ({"decision": "maybe"}, "decision must be one of confirmed, rejected, unresolved"),
        (
            {"decision": "confirmed", "confirmed_codes": ""},
            "a confirmed error needs confirmed_codes from K1 to K4",
        ),
        (
            {"decision": "confirmed", "confirmed_codes": "K7"},
            "a confirmed error needs confirmed_codes from K1 to K4",
        ),
        (
            {"decision": "rejected", "confirmed_codes": "K2"},
            "confirmed_codes or confirmed_true_end without confirmed",
        ),
        (
            {"decision": "unresolved", "confirmed_true_end": "2030-06"},
            "confirmed_codes or confirmed_true_end without confirmed",
        ),
        (
            {"decision": "confirmed", "confirmed_codes": "K2", "confirmed_true_end": "June"},
            "confirmed_true_end: 'June' is not YYYY-MM-DD or YYYY-MM",
        ),
    ],
)
def test_every_rule_of_the_adjudication_sheet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, str], problem: str
) -> None:
    root, case, sheets = scored_once(tmp_path)
    item = sorted(case["decisions"])[0]
    blank_cells = dict.fromkeys(R.ADJUDICATION_ENTERED, "")
    filled = adjudicate(root, case["decisions"] | {item: blank_cells | change})
    capsys.readouterr()
    assert run(root, "score", *sheets, "--adjudication", str(filled)) == 2
    printed = capsys.readouterr().out
    assert f"error: adjudication: {item}: {problem}" in printed
    assert "the adjudication sheet does not validate; no result was written" in printed
    assert not (root / R.OUT_NAME / R.RESULT).exists()
    assert not (root / R.OUT_NAME / "submitted" / R.ADJUDICATION).exists()


def test_adjudication_rows_must_be_those_that_were_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    wanted = S.read_sheet(root / R.OUT_NAME / R.ADJUDICATION)[1]
    done = [row | case["decisions"][row["item_id"]] for row in wanted]
    decisions, problems = R.check_adjudication(wanted, done)
    assert problems == [] and len(decisions) == 7
    first = sorted(case["decisions"])[0]
    assert decisions[first]["decision"] == case["decisions"][first]["decision"]
    assert R.check_adjudication(wanted, done[1:])[1] == [f"{first}: no decision"]
    extra = done[0] | {"item_id": "I0000000000"}
    assert R.check_adjudication(wanted, [*done, extra])[1] == [
        "I0000000000: not sent to adjudication"
    ]
    assert R.check_adjudication(wanted, [*done, done[2]])[1] == ["an item is listed more than once"]
    assert R.check_adjudication([], []) == ({}, [])
    # the decision of a confirmed error is read with its codes sorted and its date in full
    item = split(root)["both"][1]
    assert decisions[item] == {
        "decision": "confirmed",
        "confirmed_codes": "K2",
        "confirmed_true_end": "2030-06-30",
        "adj_note": "",
    }
    # the decisions on one pair of sheets do not fit another pair
    first_decisions = adjudicate(root, case["decisions"], name="first.csv")
    late = {split(root)["A1"][7]: {"verdict": "cannot_tell", "note": "n"}}
    other = ("--a1", str(fill(root, "A1", late, name="other.csv")), *sheets[2:])
    assert run(root, "score", *other, "--replace") == 3
    capsys.readouterr()
    assert run(root, "score", *other, "--adjudication", str(first_decisions)) == 2
    printed = capsys.readouterr().out
    assert f"error: adjudication: {split(root)['A1'][7]}: no decision" in printed
    assert f"error: adjudication: {split(root)['A1'][0]}: not sent to adjudication" in printed


def test_an_adjudication_sheet_filled_in_place_is_not_written_over(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    path = root / R.OUT_NAME / R.ADJUDICATION
    in_place = adjudicate(root, case["decisions"]).read_bytes()
    path.write_bytes(in_place)
    capsys.readouterr()
    assert run(root, "score", *sheets) == 2
    assert "holds decisions (it was filled in place)" in capsys.readouterr().out
    assert path.read_bytes() == in_place and R.decisions_entered(path)
    assert run(root, "score", *sheets, "--adjudication", str(path)) == 0
    assert path.read_bytes() == in_place
    assert not R.decisions_entered(path.with_name("absent.csv"))


def test_any_entry_of_adj_counts_as_filled_in_place(tmp_path: Path) -> None:
    root, _, sheets = scored_once(tmp_path)
    path = root / R.OUT_NAME / R.ADJUDICATION
    meta, rows = S.read_sheet(path)
    columns = (*R.ADJUDICATION_SHOWN, *R.ADJUDICATION_ENTERED)
    assert not R.decisions_entered(path)
    # codes, a date or a note with no decision beside them: ADJ has begun, nothing is written over
    for column, entry in zip(R.ADJUDICATION_ENTERED[1:], ("K2", "2030-06", "see A1"), strict=True):
        begun = [*rows[:-1], rows[-1] | {column: entry}]
        path.write_text(S.sheet_text(columns, begun, meta), encoding="utf-8")
        kept = path.read_bytes()
        assert R.decisions_entered(path), column
        assert run(root, "score", *sheets) == 2 and path.read_bytes() == kept


def test_an_adjudication_sheet_for_other_sheets_goes_when_no_item_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, _ = scored_once(tmp_path)
    out = root / R.OUT_NAME
    waiting = (out / R.ADJUDICATION).read_bytes()
    assert "adjudication" in json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    clean = {a: fill(root, a, name=f"clean_{a}.csv") for a in R.ANNOTATORS}
    sheets = ("--a1", str(clean["A1"]), "--a2", str(clean["A2"]))
    # without --replace nothing is taken and the sheet that waits for ADJ stays
    assert run(root, "score", *sheets) == 2 and (out / R.ADJUDICATION).read_bytes() == waiting
    # a sheet that ADJ has begun to fill is not removed either: the command stops first
    begun = adjudicate(root, {sorted(case["decisions"])[0]: {"decision": "rejected"}}).read_bytes()
    (out / R.ADJUDICATION).write_bytes(begun)
    assert run(root, "score", *sheets, "--replace") == 2
    assert (out / R.ADJUDICATION).read_bytes() == begun and not (out / R.RESULT).exists()
    (out / R.ADJUDICATION).write_bytes(waiting)
    # the pair that takes the place of the first reports no item: the result is written at
    # once, and the sheet that asked ADJ about the first pair goes, with its manifest entry
    capsys.readouterr()
    assert run(root, "score", *sheets, "--replace") == 0
    printed = capsys.readouterr().out
    assert f"removed {R.ADJUDICATION}: it was written for other sheets" in printed
    assert not (out / R.ADJUDICATION).exists()
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert "adjudication" not in manifest and sorted(manifest["result"]) == [R.CONFIRMED, R.RESULT]
    assert [entry["file"] for entry in manifest["submitted"]["replaced"]] == [
        "submitted/reference_A1.csv",
        "submitted/reference_A2.csv",
    ]
    scored = json.loads((out / R.RESULT).read_text(encoding="utf-8"))
    assert scored["sent_to_adjudication"] == 0 and "adjudication_sha256" not in scored
    assert scored["reading_confirmed"]["n"] == 100
    # the same sheets again: nothing is removed a second time and the result is the same
    result = (out / R.RESULT).read_bytes()
    capsys.readouterr()
    assert run(root, "score", *sheets) == 0 and "removed" not in capsys.readouterr().out
    assert (out / R.RESULT).read_bytes() == result


def test_score_refuses_sheets_that_do_not_validate_or_do_not_belong(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = world(tmp_path)
    assert run(root, "sheets") == 0
    out = root / R.OUT_NAME
    good = {a: str(fill(root, a)) for a in R.ANNOTATORS}
    item = blank(root, "A2")[1][0]["item_id"]
    bad = str(fill(root, "A2", {item: {"verdict": "error"}}, name="bad.csv"))
    capsys.readouterr()
    assert run(root, "score", "--a1", good["A1"], "--a2", bad) == 2
    printed = capsys.readouterr().out
    assert (
        "verdict is error but codes is empty" in printed and "the sheets were not scored" in printed
    )
    assert "reference_A1.csv: 55 rows, 55 valid, 0 errors" in printed  # both sheets are reported
    assert run(root, "score", "--a1", good["A1"], "--a2", good["A2"] + ".absent") == 2
    assert ".absent not found" in capsys.readouterr().out
    # the sheets the wrong way round
    assert run(root, "score", "--a1", good["A2"], "--a2", good["A1"]) == 2
    assert "this item is not in the blank sheet" in capsys.readouterr().out
    # a sheet whose header names the other annotator, on this annotator's items
    meta, rows = S.read_sheet(Path(good["A1"]))
    renamed = root.parent / "filled" / "renamed.csv"
    swapped = [(k, "A2" if k == "annotator" else v) for k, v in meta]
    renamed.write_text(S.sheet_text(R.SHEET_COLUMNS, rows, swapped), encoding="utf-8")
    assert run(root, "score", "--a1", str(renamed), "--a2", good["A2"]) == 2
    assert "sheet: this is not the reference sheet of A1" in capsys.readouterr().out
    # the blank itself, filled in place
    assert run(root, "score", "--a1", str(out / "reference_A1.csv"), "--a2", good["A2"]) == 2
    assert "this is the blank sheet itself" in capsys.readouterr().out
    # a blank that is not the one the manifest records
    path = out / "reference_A2.csv"
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    assert run(root, "score", "--a1", good["A1"], "--a2", good["A2"]) == 2
    assert (
        "reference_A2.csv is missing or is not the sheet the manifest records"
        in capsys.readouterr().out
    )
    path.write_bytes(original)
    for name in (R.AGREEMENT, R.RESULT, R.ADJUDICATION, "submitted"):
        assert not (out / name).exists(), name
    assert run(root, "score", "--a1", good["A1"], "--a2", good["A2"]) == 0


def test_score_refuses_blanks_that_do_not_hold_the_items_of_the_sample(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # a blank that the manifest records, and a sheet that is a filled copy of it, but one item
    # of the annotator is on neither: the sheets are not those of the registered assignment
    root = world(tmp_path)
    assert run(root, "sheets") == 0
    out = root / R.OUT_NAME
    good = {a: fill(root, a) for a in R.ANNOTATORS}
    gone = split(root)["A1"][0]
    for path in (out / "reference_A1.csv", good["A1"]):
        meta, rows = S.read_sheet(path)
        kept = [row for row in rows if row["item_id"] != gone]
        assert len(kept) == 54
        path.write_text(S.sheet_text(R.SHEET_COLUMNS, kept, meta), encoding="utf-8")
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    manifest["sheets"]["files"]["reference_A1.csv"] = sha(out / "reference_A1.csv")
    (out / R.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert run(root, "validate", str(good["A1"])) == 0  # the sheet is a copy of that blank
    capsys.readouterr()
    assert run(root, "score", "--a1", str(good["A1"]), "--a2", str(good["A2"])) == 2
    printed = capsys.readouterr().out
    assert "error: sheet: its items are not those of this annotator" in printed
    assert "the sheets were not scored" in printed
    assert not (out / R.AGREEMENT).exists() and not (out / "submitted").exists()


def test_score_needs_the_sheets_and_the_registered_sample(tmp_path: Path) -> None:
    root = world(tmp_path)
    assert "run the sheets command first" in refused(
        root, "score", "--a1", "a.csv", "--a2", "b.csv"
    )
    assert run(root, "sheets") == 0
    returned = [str(fill(root, a)) for a in R.ANNOTATORS]
    path = root / R.ELIGIBLE
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    message = refused(root, "score", "--a1", returned[0], "--a2", returned[1])
    assert "is not the registered file (the eligible list)" in message
    # another registered sample than the one of the sheets
    rows = pd.read_csv(io.BytesIO(original), dtype=str, keep_default_na=False)
    rows.loc[rows["statement_group_id"].isin(["S00001", "S00105"]), "reference_check"] = ["0", "1"]
    rows.to_csv(path, index=False)
    register(root)
    message = refused(root, "score", "--a1", returned[0], "--a2", returned[1])
    assert "the registered sample is not the one the sheets were written on" in message
    assert not (root / R.OUT_NAME / R.AGREEMENT).exists()


def test_a_second_submission_needs_replace_and_is_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    out = root / R.OUT_NAME
    first = sha(out / "submitted" / "reference_A1.csv")
    again = fill(root, "A1", name="again.csv")
    capsys.readouterr()
    assert run(root, "score", "--a1", str(again), *sheets[2:]) == 2
    assert "holds another submitted sheet; --replace takes this one" in capsys.readouterr().out
    assert sha(out / "submitted" / "reference_A1.csv") == first
    stats = json.loads((out / R.AGREEMENT).read_text(encoding="utf-8"))
    assert stats["reported"]["A1"]["error"] == 4  # the agreement of the first sheets stands
    assert run(root, "score", "--a1", str(again), *sheets[2:], "--replace") == 3
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["submitted"]["replaced"] == [
        {"file": "submitted/reference_A1.csv", "sha256": first}
    ]
    assert manifest["submitted"]["files"]["submitted/reference_A1.csv"] == sha(again)
    stats = json.loads((out / R.AGREEMENT).read_text(encoding="utf-8"))
    assert stats["reported"]["A1"]["error"] == 0 and len(case["decisions"]) == 7


def test_a_result_scored_on_a_replaced_sheet_is_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    out = root / R.OUT_NAME
    first_sheet = sha(out / "submitted" / "reference_A1.csv")
    decided = adjudicate(root, case["decisions"])
    assert run(root, "score", *sheets, "--adjudication", str(decided)) == 0
    result, listed = (out / R.RESULT).read_bytes(), (out / R.CONFIRMED).read_bytes()
    # the same sheets again without ADJ's sheet: the command waits and the result stands
    capsys.readouterr()
    assert run(root, "score", *sheets) == 3
    assert "they were scored on other sheets" not in capsys.readouterr().out
    assert (out / R.RESULT).read_bytes() == result and (out / R.CONFIRMED).read_bytes() == listed
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert "result" in manifest
    # and the manifest still names all three submitted sheets, ADJ's among them
    assert manifest["submitted"]["files"] == {
        f"submitted/{name}": sha(out / "submitted" / name)
        for name in ("reference_A1.csv", "reference_A2.csv", R.ADJUDICATION)
    }
    assert manifest["submitted"]["files"][f"submitted/{R.ADJUDICATION}"] == sha(decided)
    # another sheet of A1: refused without --replace, and the result stands
    late = split(root)["A1"][7]
    marks = case["A1"] | {late: {"verdict": "cannot_tell", "note": "n"}}
    other = ("--a1", str(fill(root, "A1", marks, name="other.csv")), *sheets[2:])
    assert run(root, "score", *other) == 2
    assert (out / R.RESULT).read_bytes() == result and (out / R.CONFIRMED).read_bytes() == listed
    # with --replace the result of the earlier pair goes, with its list and its manifest entry
    capsys.readouterr()
    assert run(root, "score", *other, "--replace") == 3
    printed = capsys.readouterr().out
    assert (
        f"removed {R.RESULT}, {R.CONFIRMED}: they were scored on other sheets than these" in printed
    )
    assert "8 items to adjudicate" in printed
    assert not (out / R.RESULT).exists() and not (out / R.CONFIRMED).exists()
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert "result" not in manifest and sorted(manifest) == [
        "about",
        "adjudication",
        "agreement",
        "inputs",
        "sample",
        "seed",
        "sheets",
        "submitted",
    ]
    assert manifest["submitted"]["replaced"] == [
        {"file": "submitted/reference_A1.csv", "sha256": first_sheet}
    ]
    # ADJ decides again on the sheet of this pair; the earlier sheet of ADJ gives way when asked
    again = adjudicate(
        root, case["decisions"] | {late: {"decision": "unresolved"}}, name="adj2.csv"
    )
    capsys.readouterr()
    assert run(root, "score", *other, "--adjudication", str(again)) == 2
    assert (
        f"{R.ADJUDICATION} holds another submitted sheet; --replace takes this one"
        in capsys.readouterr().out
    )
    assert not (out / R.RESULT).exists()
    assert (out / "submitted" / R.ADJUDICATION).read_bytes() == decided.read_bytes()
    assert run(root, "score", *other, "--adjudication", str(again), "--replace") == 0
    scored = json.loads((out / R.RESULT).read_text(encoding="utf-8"))
    assert (scored["confirmed_errors"], scored["rejected"], scored["unresolved"]) == (3, 3, 2)
    assert scored["reading_confirmed"]["n"] == 95 and scored["sent_to_adjudication"] == 8
    assert scored["sheets_sha256"]["A1"] == sha(Path(other[1]))
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["submitted"]["replaced"] == [
        {"file": "submitted/reference_A1.csv", "sha256": first_sheet},
        {"file": f"submitted/{R.ADJUDICATION}", "sha256": sha(decided)},
    ]
    assert manifest["result"] == {
        R.CONFIRMED: sha(out / R.CONFIRMED),
        R.RESULT: sha(out / R.RESULT),
    }


def test_a_second_sheet_of_adj_needs_replace_and_is_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    out = root / R.OUT_NAME
    first = adjudicate(root, case["decisions"], name="adj_first.csv")
    assert run(root, "score", *sheets, "--adjudication", str(first)) == 0
    result = (out / R.RESULT).read_bytes()
    open_item = case["unresolved"][0]
    changed = case["decisions"] | {open_item: {"decision": "rejected"}}
    second = adjudicate(root, changed, name="adj_second.csv")
    capsys.readouterr()
    assert run(root, "score", *sheets, "--adjudication", str(second)) == 2
    assert (
        f"{R.ADJUDICATION} holds another submitted sheet; --replace takes this one"
        in capsys.readouterr().out
    )
    assert (out / R.RESULT).read_bytes() == result
    assert (out / "submitted" / R.ADJUDICATION).read_bytes() == first.read_bytes()
    # the sheet that was submitted may be given again, and changes nothing
    assert run(root, "score", *sheets, "--adjudication", str(first)) == 0
    assert (out / R.RESULT).read_bytes() == result
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["submitted"]["replaced"] == []
    assert run(root, "score", *sheets, "--adjudication", str(second), "--replace") == 0
    scored = json.loads((out / R.RESULT).read_text(encoding="utf-8"))
    assert (scored["unresolved"], scored["rejected"]) == (0, 4)
    assert scored["reading_confirmed"]["n"] == 97 and scored["adjudication_sha256"] == sha(second)
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    name = f"submitted/{R.ADJUDICATION}"
    assert manifest["submitted"]["replaced"] == [{"file": name, "sha256": sha(first)}]
    assert manifest["submitted"]["files"][name] == sha(second)
    assert (out / name).read_bytes() == second.read_bytes()


def test_adj_must_have_decided_on_the_entries_of_these_sheets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    out = root / R.OUT_NAME
    wanted = S.read_sheet(out / R.ADJUDICATION)[1]
    done = [row | case["decisions"][row["item_id"]] for row in wanted]
    assert R.check_adjudication(wanted, done)[1] == []
    hint = "; fill a copy of the sheet as it was written, with every column as text"
    item = split(root)["A1"][0]  # A1 alone: error K2 with true_end 2030-06-30
    at = next(n for n, row in enumerate(done) if row["item_id"] == item)
    for column, value in (
        ("rule_end", "2031-01-31"),
        ("drug", "Another drug"),
        ("A1_true_end", "2030-07-31"),
        ("A1_verdict", "cannot_tell"),
        ("A2_verdict", "ok"),  # A2 did not check this item
        ("A1_note", "a note A1 did not write"),
    ):
        other = [*done[:at], done[at] | {column: value}, *done[at + 1 :]]
        assert R.check_adjudication(wanted, other)[1] == [
            f"{item}: the cells shown to ADJ are not those of these sheets ({column}){hint}"
        ], column
    both = [*done[:at], done[at] | {"company": "?", "A1_codes": "K3"}, *done[at + 1 :]]
    assert R.check_adjudication(wanted, both)[1] == [
        f"{item}: the cells shown to ADJ are not those of these sheets (company, A1_codes){hint}"
    ]
    # a guard, the spacing and the line breaks of a cell are not differences
    spaced = split(root)["A1"][2]  # A1's note there is "two targets"
    loose = [row | {c: S.unguarded(row[c]) for c in R.SHOWN} for row in done]
    at = next(n for n, row in enumerate(loose) if row["item_id"] == spaced)
    assert wanted[at]["A1_note"] == "two targets"
    loose[at] |= {"A1_note": " two\r\n  targets "}
    assert R.check_adjudication(wanted, loose)[1] == []
    assert R.as_shown("'-10 mg vial") == R.as_shown("-10 mg vial") == "-10 mg vial"
    assert R.as_shown(" two\r\n  targets ") == "two targets" and R.as_shown(None) == ""
    assert R.as_shown("'quoted") == "'quoted"

    # through the command: decisions taken on the first pair, another true_end from A1 since
    first = adjudicate(root, case["decisions"], name="first.csv")
    marks = case["A1"] | {item: case["A1"][item] | {"true_end": "2030-07"}}
    other_sheets = ("--a1", str(fill(root, "A1", marks, name="other.csv")), *sheets[2:])
    assert run(root, "score", *other_sheets, "--replace") == 3
    assert [r["item_id"] for r in S.read_sheet(out / R.ADJUDICATION)[1]] == sorted(
        case["decisions"]
    )
    capsys.readouterr()
    assert run(root, "score", *other_sheets, "--adjudication", str(first)) == 2
    printed = capsys.readouterr().out
    assert (
        f"error: adjudication: {item}: the cells shown to ADJ are not those of these sheets "
        f"(A1_true_end){hint}" in printed
    )
    assert printed.count("error: adjudication:") == 1 and not (out / R.RESULT).exists()
    assert not (out / "submitted" / R.ADJUDICATION).exists()


def test_a_sheet_of_adj_that_cannot_be_read_is_one_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, case, sheets = scored_once(tmp_path)
    absent = root.parent / "filled" / "no_such_adjudication.csv"
    capsys.readouterr()
    assert run(root, "score", *sheets, "--adjudication", str(absent)) == 2
    assert f"error: adjudication: {absent} not found" in capsys.readouterr().out
    latin = adjudicate(root, case["decisions"], name="latin.csv")
    latin.write_bytes(latin.read_text(encoding="utf-8").replace("Drug", "Drüg").encode("latin-1"))
    assert run(root, "score", *sheets, "--adjudication", str(latin)) == 2
    assert "error: adjudication: sheet: the file is not UTF-8 text" in capsys.readouterr().out
    assert not (root / R.OUT_NAME / R.RESULT).exists()
    assert not (root / R.OUT_NAME / "submitted" / R.ADJUDICATION).exists()


def test_pure_scoring_functions_on_a_small_sample() -> None:
    rows = [
        {"statement_group_id": f"S{n}", "event_date": f"202{3 + n % 2}-05-01", "form": form}
        for n, form in enumerate(["month_year"] * 6 + ["quarter"] * 3 + ["range"])
    ]
    sample = R.on_sheets(rows, {"subsets": {"reference_check": {"final": True}}}, ["S9"])
    assert sample.registered == 10 and sample.left_off == ("S9",) and len(sample.rows) == 9
    assert Counter(r["assigned_to"] for r in sample.rows) == {"A1": 4, "A2": 4, "both": 1}
    assert not R.on_sheets(rows, {}).final
    ok = {"verdict": "ok", "codes": "", "true_end": "", "start_differs": "0", "note": ""}
    sheets = {
        a: R.Checked({i: dict(ok) for i in sample.of(a)}, [], [], 20 if a == "A1" else None, [], [])
        for a in R.ANNOTATORS
    }
    shared = next(r["item_id"] for r in sample.rows if r["assigned_to"] == "both")
    own = next(r["item_id"] for r in sample.rows if r["assigned_to"] == "A2")
    sheets["A1"].marks[shared] |= {"verdict": "error", "codes": "K1"}
    sheets["A2"].marks[shared] |= {"verdict": "cannot_tell", "note": "n", "start_differs": "1"}
    sheets["A2"].marks[own] |= {"verdict": "error", "codes": "K2;K4", "true_end": "2020-01-31"}
    stats = R.agreement(sample, sheets)
    assert stats["shared"] == {
        "items": 1,
        "same_verdict": 0,
        "raw_agreement": 0.0,
        "with_cannot_tell": 1,
        "kappa_ok_error": None,
        "items_that_differ": [shared],
    }
    assert stats["seconds_per_item"] == {"A1": 240.0, "A2": None}
    shown = {
        r["item_id"]: dict.fromkeys(R.SHOWN, "s") | {"item_id": r["item_id"]} for r in sample.rows
    }
    wanted = R.adjudication_rows(sample, sheets, shown)
    assert [w["item_id"] for w in wanted] == sorted([shared, own])
    decisions = {
        shared: {"decision": "unresolved", "confirmed_codes": "", "confirmed_true_end": ""},
        own: {
            "decision": "confirmed",
            "confirmed_codes": "K2;K4",
            "confirmed_true_end": "2020-01-31",
        },
    }
    scored = R.result(sample, sheets, decisions)
    assert scored["without_confirmed_error"] == R.share(8, 9)
    assert scored["reading_confirmed"] == R.share(7, 9)
    assert scored["codes"] == {"K1": 0, "K2": 1, "K3": 0, "K4": 1} and scored["start_differs"] == 1
    assert scored["unresolved_items"] == [shared] and len(scored["confirmed_statement_ids"]) == 7
    assert sum(t["confirmed_errors"] for t in scored["by_form"].values()) == 1
    assert sum(t["unresolved"] for t in scored["by_year"].values()) == 1
    assert R.minutes_for(55) == [28, 18, 41] and R.minutes_for(0) == [0, 0, 0]


def test_two_cannot_tell_agree_and_stay_out_of_kappa() -> None:
    rows = [
        {"statement_group_id": f"S{n:02d}", "event_date": "2024-05-01", "form": "month_year"}
        for n in range(30)
    ]
    sample = R.on_sheets(rows, {})
    ok = {"verdict": "ok", "codes": "", "true_end": "", "start_differs": "0", "note": ""}
    sheets = {
        a: R.Checked({i: dict(ok) for i in sample.of(a)}, [], [], None, [], [])
        for a in R.ANNOTATORS
    }
    one, two, three = sorted(r["item_id"] for r in sample.rows if r["assigned_to"] == "both")
    for annotator in R.ANNOTATORS:
        sheets[annotator].marks[one] |= {"verdict": "cannot_tell", "note": "n"}
    sheets["A1"].marks[three] |= {"verdict": "error", "codes": "K2"}
    assert R.agreement(sample, sheets)["shared"] == {
        "items": 3,
        "same_verdict": 2,  # two cannot_tell are the same verdict
        "raw_agreement": 0.6667,
        "with_cannot_tell": 1,
        "kappa_ok_error": 0.0,  # (ok, ok) and (error, ok): agreement 1/2, chance 1/2
        "items_that_differ": [three],
    }
    shown = {
        r["item_id"]: dict.fromkeys(R.SHOWN, "s") | {"item_id": r["item_id"]} for r in sample.rows
    }
    wanted = R.adjudication_rows(sample, sheets, shown)
    assert [w["item_id"] for w in wanted] == [one, three] and two not in (one, three)
    assert [(w["A1_verdict"], w["A2_verdict"]) for w in wanted] == [
        ("cannot_tell", "cannot_tell"),
        ("error", "ok"),
    ]


# --------------------------------------------------------------------------------------------
# No outcome
# --------------------------------------------------------------------------------------------


def test_no_outcome_column_is_read_or_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = world(tmp_path)
    # the poison is in the three inputs that could carry an outcome
    assert POISON.encode() in (root / R.ELIGIBLE).read_bytes()
    assert POISON.encode() in pd.read_csv(root / R.EVENTS, dtype=str).to_csv().encode()
    assert POISON in (root / R.ITEMS).read_text(encoding="utf-8")
    calls: list[tuple[str, tuple[str, ...]]] = []
    frames: list[pd.DataFrame] = []
    plain = pd.read_csv

    def watched(path: Any, *args: Any, **kwargs: Any) -> pd.DataFrame:
        frame = plain(path, *args, **kwargs)
        calls.append((Path(str(path)).name, tuple(kwargs.get("usecols") or ())))
        frames.append(frame)
        return frame

    monkeypatch.setattr(pd, "read_csv", watched)
    assert run(root, "sheets") == 0
    case = worked(root)
    returned = {a: fill(root, a, case[a]) for a in R.ANNOTATORS}
    sheets = ("--a1", str(returned["A1"]), "--a2", str(returned["A2"]))
    assert run(root, "validate", str(returned["A1"])) == 0
    assert run(root, "score", *sheets) == 3
    filled = adjudicate(root, case["decisions"])
    assert run(root, "score", *sheets, "--adjudication", str(filled)) == 0
    monkeypatch.undo()

    read_files = Counter(name for name, _ in calls)
    assert set(read_files) == {
        "eligible_e3.csv",
        "events.csv.gz",
        *(f"sample_{n}.csv" for n in R.FIRST_DRAW),
    }
    assert read_files["events.csv.gz"] == 1  # the scorer does not open the events table
    poisoned = {"outcome", "upper_date", "E_end"}
    for name, columns in calls:
        assert columns, f"{name} was read whole"
        assert not poisoned & set(columns) and not set(columns) & set(D.OUTCOME_COLUMNS)
    assert {columns for name, columns in calls if name == "eligible_e3.csv"} == {R.ELIGIBLE_FIELDS}
    assert {columns for name, columns in calls if name == "events.csv.gz"} == {R.EVENT_FIELDS}
    for frame in frames:
        assert not poisoned & set(frame.columns)
        assert not frame.isin([POISON]).any().any()
    # nothing the module wrote holds the poison or a column of outcomes
    written = [path for path in (root / R.OUT_NAME).rglob("*") if path.is_file()]
    assert len(written) == 12
    outcome_names = {*D.OUTCOME_COLUMNS, *poisoned}
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert POISON not in text, path
        if path.suffix == ".csv":
            header = next(
                line for line in csv.reader(io.StringIO(text)) if not line[0].startswith("#")
            )
            assert not outcome_names & set(header) and not any("outcome" in c for c in header)
    scored = json.loads((root / R.OUT_NAME / R.RESULT).read_text(encoding="utf-8"))
    assert not [key for key in scored if "outcome" in key or key in outcome_names]


def test_outcome_columns_are_refused_by_name_and_items_keep_only_their_keys(made: Path) -> None:
    for column in ("outcome", "E_end", "upper_date", "scoreable", "ttr_mid_days"):
        assert column in D.OUTCOME_COLUMNS
        with pytest.raises(ValueError, match="outcome columns are never read"):
            R.read_columns(made / R.ELIGIBLE, ("statement_group_id", column))
    frame = R.read_columns(made / R.ELIGIBLE, R.ELIGIBLE_FIELDS)
    assert tuple(frame.columns) == R.ELIGIBLE_FIELDS and len(frame) == 112
    with pytest.raises(SystemExit, match="eligible_e3"):
        R.read_columns(made / R.ELIGIBLE, ("statement_group_id", "no_such_column"))
    record = R.frozen_record(made)
    rows, counts, _ = R.marked_rows(made, record)
    assert POISON in (made / R.COUNTS).read_text(encoding="utf-8")
    assert sorted(counts) == ["outputs", "subsets"] and POISON not in json.dumps(counts)
    assert list(counts["subsets"]) == ["reference_check"] and list(counts["outputs"]) == ["items"]
    items, _ = R.harness_items(made, counts, rows)
    assert all(tuple(sorted(item)) == tuple(sorted(R.ITEM_KEYS)) for item in items.values())
    assert not set(R.ITEM_KEYS) & set(D.OUTCOME_COLUMNS) and "outcome" not in R.ITEM_KEYS
    assert not set(R.EVENT_FIELDS) & set(D.OUTCOME_COLUMNS)
    assert not {*R.SHEET_COLUMNS, *R.ADJUDICATION_SHOWN, *R.ADJUDICATION_ENTERED} & set(
        D.OUTCOME_COLUMNS
    )
    source = Path(R.__file__).read_text(encoding="utf-8")
    assert "outcomes_" not in source and "statements.csv" not in source
    assert "external_data/sealed" not in source


# --------------------------------------------------------------------------------------------
# The real guide, the registered subset and the blank sheets on disk
# --------------------------------------------------------------------------------------------


def test_constants_are_those_of_the_real_guide() -> None:
    guide = REAL_GUIDE.read_text(encoding="utf-8")
    section = guide.split("### 12.2 Task E")[1].split("\n## ")[0]
    codes = dict(re.findall(r"^\s*\| (K\d) \| (.+?) \|$", section, flags=re.M))
    assert codes == R.CODES
    assert "45 to A1, 45 to A2, 10 checked by both" in section
    assert R.split_sizes(100) == {"A1": 45, "A2": 45, "both": 10}
    assert "`ok` when all four hold; `cannot_tell`" in section and "Otherwise `error`" in section
    assert R.VERDICTS == ("ok", "error", "cannot_tell")
    rate, low, high = R.SECONDS_PER_ITEM
    assert f"| E. Reference readings | 55 | {rate} s ({low} to {high}) |" in guide
    layout = guide.split("**Task E: `reference_<A1|A2>.csv`**")[1].split("\n## ")[0]
    cells = [line.split("|")[1] for line in layout.splitlines() if line.startswith("| `")]
    names = [name for cell in cells for name in re.findall(r"`(\w+)`", cell)]
    assert names[0] == "item_id" and tuple(names[1:]) == (*R.RULE, *R.ENTERED)
    assert "the entry-block columns of task A" in layout and R.SHOWN[:11] == S.SHOWN
    assert "`# sitting_start:` and `# sitting_end:`" in guide
    assert R.SEED == 20261001 and S.guide_version(guide) == "v1"


registered = pytest.mark.skipif(
    not (REAL / R.FREEZE).is_file(), reason="the corpus freeze has not been run in this checkout"
)


@registered
def test_the_registered_subset() -> None:
    record = R.frozen_record(REAL)
    rows, counts, source = R.marked_rows(REAL, record)
    ids = {row["statement_group_id"] for row in rows}
    assert len(rows) == len(ids) == 100
    assert all("2023-01-01" <= row["event_date"] <= "2025-12-31" for row in rows)
    assert counts["subsets"]["reference_check"]["final"] is True
    assert source["eligible_sha256"] == record["tables"]["eligible_list"]["sha256"]
    first, lists = R.first_draw(REAL, record)
    assert len(first) == 180 and not first & ids and sorted(lists) == sorted(R.FIRST_DRAW)
    literal = pd.read_csv(REAL / R.SAMPLES / "sample_literal.csv", dtype=str)
    assert len(literal) == 120 and not set(literal["statement_group_id"]) & ids
    events, _ = R.load_events(REAL, record)
    assert not R.labelled(events, first) & ids
    R.frozen_reader(record)
    sample = R.on_sheets(rows, counts)
    assert sample.final and sample.left_off == () and sample.registered == 100
    assert Counter(row["assigned_to"] for row in sample.rows) == {"A1": 45, "A2": 45, "both": 10}
    items, _ = R.harness_items(REAL, counts, rows)
    readings = R.rule_readings(events, sample.rows, items)
    for row in sample.rows:
        reading = readings[row["statement_group_id"]]
        assert reading["rule_end"] == row["stated_end"] and reading["rule_stale"] == "0"
        assert reading["rule_statement_type"] in ("recovery", "next_delivery")
        assert reading["rule_start"] <= reading["rule_end"] >= row["event_date"]
        assert row["form"] in F.DATED_FORMS
    # every registered item is shown as the harness renders it, and with the registered end
    files = R.build_files(sample, items, readings, REAL_GUIDE.read_text(encoding="utf-8"))
    harness = {item.item_id: item for item in read.load_items(REAL / R.ITEMS)}
    of_item = {row["item_id"]: row for row in sample.rows}
    quoted = ("availability_information", "related_information", "reason_for_shortage")
    for annotator in R.ANNOTATORS:
        _, shown = S.parse_sheet(files[f"reference_{annotator}.csv"])
        text = files[f"reference_{annotator}_items.txt"]
        assert len(shown) == 55 and text.count("\nEntry\n") == 55
        for row in shown:
            registered_row = of_item[row["item_id"]]
            item = harness[registered_row["statement_group_id"]]
            cells = {c: S.unguarded(v) for c, v in row.items()}
            lines = [
                f'"{cells[c]}"' if c in quoted and cells[c] != S.BLANK else cells[c]
                for c in S.SHOWN[1:]
            ]
            block = read.render_prompt(read.TEMPLATES["literal-v1"], item).split("Entry\n", 1)[1]
            entry = block.splitlines()[: len(lines)]
            assert lines == [line.split(": ", 1)[1] for line in entry]
            assert f"=== {row['item_id']} ===\nEntry\n" not in text  # the id line counts the items
            assert f": {row['item_id']} ===\n" + "\n".join(["Entry", *entry]) + "\nRule" in text
            assert row["rule_end"] == item.stated_end == registered_row["stated_end"]
            assert row["date_of_update"] == registered_row["event_date"]


@registered
def test_the_blank_sheets_on_disk_are_what_the_module_writes() -> None:
    out = REAL / R.OUT_NAME
    if not (out / R.MANIFEST).is_file():
        pytest.skip("the task E sheets have not been written")
    assert R.main(["sheets", "--check"]) == 0
    manifest = json.loads((out / R.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["sample"]["statements"] == 100 and manifest["sample"]["left_off"] == []
    assert manifest["sample"]["assigned"] == {"A1": 45, "A2": 45, "both": 10}
    assert manifest["sheets"]["guide"] == S.guide_stamp(REAL_GUIDE.read_text(encoding="utf-8"))
    for name, digest in manifest["sheets"]["files"].items():
        assert sha(out / name) == digest
    # the statements A1 and A2 label, or audit as the seed of a minimal pair (guide, section 2,
    # rule 1): the four lists of the first draw and, when it is drawn, the list of pair seeds
    lists = [REAL / R.SAMPLES / f"sample_{name}.csv" for name in R.FIRST_DRAW]
    seeds = REAL / "audit" / "samples_later" / "sample_pair_seeds.csv"
    lists += [seeds] if seeds.is_file() else []
    hidden: set[str] = set()
    for path in lists:
        listed = pd.read_csv(path, dtype=str, usecols=["statement_group_id"])
        hidden |= {S.item_id(i) for i in listed["statement_group_id"]}
    assert len(hidden) >= 180
    on_sheet: dict[str, set[str]] = {}
    for annotator in R.ANNOTATORS:
        meta, rows = S.read_sheet(out / f"reference_{annotator}.csv")
        assert len(rows) == 55 and dict(meta)["annotator"] == annotator
        assert tuple(rows[0]) == R.SHEET_COLUMNS
        assert all("2023-01-01" <= row["date_of_update"] <= "2025-12-31" for row in rows)
        assert all(
            row["rule_stale"] == "0" and row["rule_end"] >= row["date_of_update"] for row in rows
        )
        if not R.holds_marks(out / f"reference_{annotator}.csv"):
            assert all(row[c] == "" for row in rows for c in R.ENTERED)
        on_sheet[annotator] = {row["item_id"] for row in rows}
    shown = on_sheet["A1"] | on_sheet["A2"]
    assert len(shown) == 100 and not shown & hidden
    assert len(on_sheet["A1"] & on_sheet["A2"]) == 10  # all else is on one sheet only
    for annotator, other in (("A1", "A2"), ("A2", "A1")):
        text = (out / f"reference_{annotator}_items.txt").read_text(encoding="utf-8")
        assert set(re.findall(r"I[0-9a-f]{10}", text)) == on_sheet[annotator]
        assert not any(i in text for i in on_sheet[other] - on_sheet[annotator])
    eligible = pd.read_csv(
        REAL / R.ELIGIBLE, dtype=str, usecols=["statement_group_id", "reference_check"]
    )
    marked = eligible.loc[eligible["reference_check"] == "1", "statement_group_id"]
    assert shown == {S.item_id(i) for i in marked}


def watch_writes(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every path written through ``Path.write_bytes`` or ``Path.write_text`` from now on."""
    written: list[Path] = []
    plain_bytes, plain_text = Path.write_bytes, Path.write_text

    def write_bytes(self: Path, data: bytes) -> int:
        written.append(self.resolve())
        return plain_bytes(self, data)

    def write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        written.append(self.resolve())
        return plain_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", write_bytes)
    monkeypatch.setattr(Path, "write_text", write_text)
    return written


def test_every_command_writes_under_the_output_folder_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = world(tmp_path)
    inputs = {p: sha(p) for p in root.rglob("*") if p.is_file()}
    assert run(root, "sheets") == 0
    case = worked(root)
    returned = {a: fill(root, a, case[a]) for a in R.ANNOTATORS}
    sheets = ("--a1", str(returned["A1"]), "--a2", str(returned["A2"]))
    written = watch_writes(monkeypatch)
    assert run(root, "sheets") == 0 and run(root, "sheets", "--check") == 0
    assert run(root, "validate", str(returned["A1"])) == 0
    assert run(root, "score", *sheets) == 3
    monkeypatch.undo()
    filled = adjudicate(root, case["decisions"])
    later = watch_writes(monkeypatch)
    assert run(root, "score", *sheets, "--adjudication", str(filled)) == 0
    monkeypatch.undo()
    out = (root / R.OUT_NAME).resolve()
    assert (len(written), len(later)) == (10, 7)
    assert all(path.is_relative_to(out) for path in (*written, *later))
    assert {p: sha(p) for p in inputs} == inputs  # no registered file was touched
    assert sorted(p.name for p in (tmp_path / "out").iterdir() if p.is_dir()) == [
        "audit",
        "audit_reference",
        "items",
    ]


@registered
def test_on_the_registered_files_sheets_writes_its_five_files_and_no_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read_by_the_module = [
        REAL / R.FREEZE,
        REAL / R.ELIGIBLE,
        REAL / R.COUNTS,
        REAL / R.EVENTS,
        REAL / R.ITEMS,
        *(REAL / R.SAMPLES / f"sample_{name}.csv" for name in R.FIRST_DRAW),
        *(p for p in (REAL / R.OUT_NAME).glob("*") if p.is_file()),
    ]
    before = {p: sha(p) for p in read_by_the_module}
    out = tmp_path / "audit_reference"
    written = watch_writes(monkeypatch)
    assert R.main(["sheets", "--out", str(out)]) == 0
    monkeypatch.undo()
    assert sorted(p.name for p in out.iterdir()) == [
        "reference_A1.csv",
        "reference_A1_items.txt",
        "reference_A2.csv",
        "reference_A2_items.txt",
        "reference_manifest.json",
    ]
    assert len(written) == 5 and all(path.is_relative_to(out.resolve()) for path in written)
    assert {p: sha(p) for p in before} == before
