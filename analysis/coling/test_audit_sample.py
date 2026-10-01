"""Tests for the samples, sheets and validator of the literal task (``audit_sample.py``).

Everything runs on small made-up inputs: a short guide with the allocation table and an
Appendix A, statement records written by hand for the drawing rules, and an events table of
invented notices (one wording per form class, dated before and after 2023-01-01) for the sheets
and the commands. No capture file, no outcome table and nothing sealed is read. Covered: the
seeded order; the guide's table, exclusion list and version, and that the constants of the
code are those the real guide states; the display row (and that the
dataset builder picks the same one); strata, periods and the frame; the fixed test item of the
harness; the first draw (quotas, order of samples, train-only samples, the test share, caps per
template, episode and text, shortfall, rare strata first, exclusions, a kept sample, input
order); the later draw; the sheets (columns, blanks, guarded cells, order, item ids, the item
file as the harness loads and renders it, the key); the validator (every check of the guide's
section 3.12, by row and for the sheet, the warnings, the sitting times, a sheet saved by a
spreadsheet, a file that is not UTF-8 or not comma-separated); the commands end to end with
their manifest and their refusals (an exclusion that matches nothing, a list on disk that would
change, a sheet filled in place); and, when they exist, the files under
``analysis/coling/out/audit``.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_audit_sample.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import forms as F
from analysis.coling import read

REAL_GUIDE = Path("analysis/coling/plan/AUDIT_GUIDE.md")
REAL_OUT = Path("analysis/coling/out/audit")

ROWS = (
    ("month and year", "`month_year`"),
    ("month with no year", "`month_no_year`"),
    ("part of a month", "`part_of_month`"),
    ("quarter, half or year", "`quarter`, `half_year`, `year`"),
    ("range", "`range`"),
    ("relative", "`relative`"),
    ("exact day", "`exact_day`"),
    ("TBD or unknown", "`tbd`"),
    ("vague or undated", "`vague`, `no_date`"),
    ("silent", "`silent`"),
    (
        "distractor date",
        "`distractor`; `month_year`, `month_no_year`, `part_of_month`, `quarter`, `half_year`, "
        "`year`, `range`, `relative`, `exact_day`, `tbd`, `vague`, `no_date`, `silent` with a "
        "distractor date",
    ),
    ("discontinuation", "`discontinuation`"),
)
# the layout of the real guide: the vague and undated rows apart, and two distractor rows
DATED_CLASSES = (
    "`month_year`, `month_no_year`, `part_of_month`, `quarter`, `half_year`, `year`, `range`, "
    "`relative`, `exact_day`"
)
SPLIT_ROWS = (
    *ROWS[:8],
    ("vague", "`vague`"),
    ("undated", "`no_date`"),
    ("silent", "`silent`"),
    ("distractor only", "`distractor`; `tbd`, `vague`, `no_date`, `silent` with a distractor date"),
    ("dated target beside a distractor date", f"{DATED_CLASSES} with a distractor date"),
    ("discontinuation", "`discontinuation`"),
)
NAMES = (
    "month_year",
    "month_no_year",
    "part_of_month",
    "quarter",
    "range",
    "relative",
    "exact_day",
    "tbd",
    "vague",
    "silent",
    "distractor",
    "discontinuation",
)
SPLIT_NAMES = (
    *NAMES[:8],
    "vague",
    "no_date",
    "silent",
    "distractor",
    "dated_distractor",
    "discontinuation",
)
DATED = NAMES[:7]
EVERY = dict.fromkeys(NAMES, 1)
EVERY_DATED = dict.fromkeys(DATED, 1)

# one wording per stratum; {y} is the year after the statement's, so that no period is stale
TEXTS = {
    "month_year": "Backordered. Next release April {y}.",
    "month_no_year": "Backordered, next shipment in November.",
    "part_of_month": "Next release late August {y}.",
    "quarter": "Estimated recovery: Q4 {y}.",
    "range": "Additional lots in the March/April {y} timeframe.",
    "relative": "Estimated shortage duration: 60 days.",
    "exact_day": "Expected availability Oct 1, {y}.",
    "tbd": "Unavailable. Estimated recovery TBD.",
    "vague": "Will remain on backorder for few months.",
    "silent": "On backorder.",
    "distractor": "Remaining inventory estimated to last until April {y}.",
    "discontinuation": "To be discontinued on or near March {y}.",
}
WORDS = (
    "amber",
    "birch",
    "cedar",
    "dune",
    "elm",
    "fern",
    "grove",
    "heath",
    "iris",
    "juniper",
    "kelp",
    "larch",
    "moss",
    "nettle",
    "oak",
    "pine",
    "quartz",
    "reed",
    "sage",
    "thyme",
)
TRAIN_DAYS = ("2019-03-01", "2020-03-02", "2021-03-03", "2022-03-04")  # fit, fit, dev, dev
TEST_DAYS = ("2023-03-05", "2024-03-06")


# --------------------------------------------------------------------------------------------
# Made-up inputs
# --------------------------------------------------------------------------------------------


def guide_text(
    pilot: dict[str, int] | None = None,
    check: dict[str, int] | None = None,
    reserve: dict[str, int] | None = None,
    literal: dict[str, int] | None = None,
    appendix: str = "",
    split: bool = False,
    section: str = "",
) -> str:
    """A short guide: version line, the allocation table (a zero quota is an empty cell) and
    Appendix A. With ``split`` the table has the rows of the real guide; ``section`` is put
    before the appendix (a section 3 or 7 with quoted phrases)."""
    quotas = [pilot or {}, check or {}, reserve or {}, literal or {}]
    table = zip(SPLIT_ROWS, SPLIT_NAMES, strict=True) if split else zip(ROWS, NAMES, strict=True)
    lines = [
        "# Guide",
        "",
        "**Version v9 test, 1 January 2000.** A made-up guide.",
        "",
        "| Stratum | Classifier classes | Pilot | Check set | Reserve | Literal sample |",
        "|---|---|---|---|---|---|",
    ]
    for (label, classes), name in table:
        cells = " | ".join(str(q.get(name) or "") for q in quotas)
        lines.append(f"| {label} | {classes} | {cells} |")
    totals = " | ".join(f"**{sum(q.values())}**" for q in quotas)
    lines += [
        f"| **Total** | | {totals} |",
        "",
        section,
        "",
        "## Appendix A. Statements excluded from every sample",
        "",
        appendix,
        "",
        "## Appendix B. Something else",
        "",
        "| Generic | Company | Statement date |",
        "|---|---|---|",
        "| Not An Exclusion | Nobody | 2020-01-01 |",
        "",
    ]
    return "\n".join(lines)


def allocation(**quotas: dict[str, int]) -> S.Allocation:
    return S.guide_allocation(guide_text(**quotas))


def split_allocation(**quotas: dict[str, int]) -> S.Allocation:
    """The allocation of a made-up guide whose table has the rows of the real one."""
    return S.guide_allocation(guide_text(**quotas, split=True))


def record(n: int, stratum: str = "month_year", period: str = "train", **changes: Any) -> dict:
    """One row of the statement table, with a template, an episode and a text of its own."""
    row = {
        "id": f"S{n:05d}",
        "event_id": f"E{n:05d}",
        "thread_id": f"T{n:05d}",
        "event_date": "2020-03-01" if period == "train" else "2024-03-01",
        "split": "fit" if period == "train" else "test",
        "period": period,
        "form": stratum,
        "stratum": stratum,
        "stale": False,
        "in_frame": True,
        "at_risk_B": True,
        "text": f"text {n}",
        "wording": f"wording {n}",
        "notice": f"notice {n}",
        "template": f"template {n}",
        "episode": f"episode {n}",
        "n_presentations": 1,
    }
    return row | changes


def records(counts: dict[str, tuple[int, int]], **changes: Any) -> list[dict]:
    """``counts[stratum]`` = (train statements, test statements)."""
    out: list[dict] = []
    for stratum, (train, test) in counts.items():
        for period, k in (("train", train), ("test", test)):
            out += [record(len(out) + i, stratum, period, **changes) for i in range(k)]
    return out


def event(n: int, text: str, day: str = "2020-03-02", **changes: str) -> dict[str, str]:
    """One presentation event with the fields the sampler reads, and two it must never use."""
    row = {
        "event_id": f"E{n:05d}",
        "statement_group_id": f"S{n:05d}",
        "thread_id": f"T{n:05d}",
        "generic_id": f"g{n:05d}",
        "episode_id": f"P{n:05d}",
        "listing": "shortage",
        "event_date": day,
        "type_of_update": "revised",
        "generic_name": f"Examplamine {n} Injection",
        "company_name": "Acme Pharma, Inc.",
        "presentation": f"10 mg vial (NDC 0000-{n:04d}-01)",
        "status_at_statement": "current",
        "availability_class": "limited",
        "availability_text": text,
        "related_text": "",
        "statement_text": text,
        "reason_for_shortage": "Other",
        "therapeutic_category": "Oncology",
        "initial_posting_date": "01/15/2019",
        "outcome_type": "recovered",
        "upper_date": "2099-01-01",
    }
    return row | changes


def frame(rows: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, dtype=str)


def small_corpus(train: int = 8, test: int = 4) -> pd.DataFrame:
    """``train`` statements dated before 2023 and ``test`` dated after it for every stratum,
    each of another drug and with a wording of its own."""
    rows: list[dict[str, str]] = []
    for stratum in NAMES:
        days = [TRAIN_DAYS[i % 4] for i in range(train)] + [TEST_DAYS[i % 2] for i in range(test)]
        for i, day in enumerate(days):
            text = TEXTS[stratum].format(y=int(day[:4]) + 1) + f" Ask the {WORDS[i]} desk."
            rows.append(event(len(rows), text, day))
    return frame(rows)


def write_inputs(folder: Path, guide: str, events: pd.DataFrame) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    guide_path, events_path = folder / "guide.md", folder / "events.csv"
    guide_path.write_text(guide, encoding="utf-8")
    events.to_csv(events_path, index=False)
    return guide_path, events_path


SMALL = {
    "pilot": EVERY,
    "check": EVERY_DATED,
    "reserve": EVERY_DATED,
    "literal": dict.fromkeys(NAMES, 3),
}


UNMATCHED = "--allow-unmatched"  # the made-up corpus does not hold the harness's fixed test item


def drawn_folder(tmp_path: Path, name: str = "out", train: int = 8) -> tuple[Path, list[str]]:
    """A folder with the first draw of the small corpus and the sheets of every task; and the
    arguments that name its inputs."""
    guide, events = write_inputs(tmp_path / "in", guide_text(**SMALL), small_corpus(train))
    out = tmp_path / name
    inputs = ["--events", str(events), "--guide", str(guide), "--out", str(out)]
    assert S.main(["draw", *inputs, UNMATCHED, "--sheets", *S.FIRST_SAMPLES]) == 0
    return out, inputs


GOOD = {
    "statement_type": "next_delivery",
    "start": "2020-04-01",
    "end": "2020-04-30",
    "abstain": "0",
    "abstain_reason": "",
    "certainty": "asserted",
    "quote": "",
    "distractor_roles": "",
    "distractor_quotes": "",
    "hard": "0",
    "note": "",
}
ABSTAIN = GOOD | {
    "statement_type": "recovery",
    "start": "",
    "end": "",
    "abstain": "1",
    "abstain_reason": "tbd",
    "certainty": "undetermined",
}
SHOWN_ROW = {
    "item_id": "I0000000001",
    "drug": "Examplamine Injection",
    "company": "Acme Pharma, Inc.",
    "presentation": "10 mg vial",
    "therapeutic_category": "Oncology",
    "initial_posting_date": "2019-01-15",
    "type_of_update": "Revised",
    "date_of_update": "2020-03-02",
    "availability_information": "Backordered. Next release April 2020.",
    "related_information": "5 month expiry (1/2022 expiry) dating available by request.",
    "reason_for_shortage": "Other",
}


def fill(blank: str, labels: Any = None, times: tuple[str, str] = ("09:00", "09:20")) -> str:
    """The blank sheet with every row labelled (``labels`` maps a row to its entered cells) and
    the sitting times written in."""
    meta, rows = S.parse_sheet(blank)
    meta = [
        (k, times[0] if k == "sitting_start" else times[1] if k == "sitting_end" else v)
        for k, v in meta
    ]
    filled = [row | (labels(row) if labels else GOOD) for row in rows]
    return S.sheet_text(S.SHEET_COLUMNS, filled, meta)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------------
# Seeded order and small helpers
# --------------------------------------------------------------------------------------------


def test_seeded_order_ignores_input_order_and_keeps_places() -> None:
    ids = [f"S{n}" for n in range(40)]
    order = S.shuffled(ids, "a draw")
    mixed = ids[:]
    random.Random(1).shuffle(mixed)
    assert S.shuffled(mixed, "a draw") == order
    assert S.shuffled([*ids, *ids], "a draw") == order
    assert order != sorted(ids) and sorted(order) == sorted(ids)
    assert S.shuffled(ids, "another draw") != order
    assert S.shuffled(ids, "a draw", seed=1) != order
    assert [i for i in order if i != "S7"] == S.shuffled([i for i in ids if i != "S7"], "a draw")


def test_draw_key_is_the_rule_of_the_plan() -> None:
    expected = hashlib.sha256(b"20261001\x1fpilot/tbd/train\x1fS1").hexdigest()
    assert S.draw_key("pilot/tbd/train", "S1") == expected
    assert S.SEED == 20261001


def test_masked_template_masks_months_and_numbers_only() -> None:
    one = S.masked_template("Next release April 2020 (NDC 0143-9284-10).")
    two = S.masked_template("next release  Sept. 2021 (NDC 55111-527-01)")
    assert one == two == "next release <mon> <n> (ndc <n>-<n>-<n>)"
    assert S.masked_template("Maybe in March") == "maybe in <mon>"
    assert S.masked_template("Market withdrawal") == "market withdrawal"  # "mar" inside a word
    assert S.masked_template("Estimated recovery: Q4 2021") == "estimated recovery: q<n> <n>"


@pytest.mark.parametrize(
    ("quota", "share"), [(12, 4), (10, 3), (8, 3), (6, 2), (3, 1), (1, 0), (2, 1), (0, 0)]
)
def test_a_third_of_a_quota_rounded(quota: int, share: int) -> None:
    assert S.from_test_period(quota) == share


def test_dates_of_the_posting_cell() -> None:
    assert S.iso_or_text("01/15/2019") == "2019-01-15"
    assert S.iso_or_text("2019-01-15") == "2019-01-15"
    assert S.iso_or_text(" not  a date ") == "not a date"
    assert S.iso_or_text("") == ""


# --------------------------------------------------------------------------------------------
# The guide
# --------------------------------------------------------------------------------------------


def test_allocation_table_is_read() -> None:
    alloc = allocation(pilot=EVERY, check=EVERY_DATED, literal={"month_year": 12, "tbd": 5})
    assert alloc.names == NAMES
    assert alloc.quotas["pilot"] == EVERY
    assert alloc.quotas["check"] == {n: int(n in DATED) for n in NAMES}
    assert alloc.quotas["reserve"] == dict.fromkeys(NAMES, 0)
    assert alloc.quotas["literal"]["month_year"] == 12 and alloc.quotas["literal"]["tbd"] == 5
    assert alloc.by_class["half_year"] == alloc.by_class["year"] == "quarter"
    assert alloc.by_class["no_date"] == "vague"
    assert sorted(alloc.by_class) == sorted(F.FORM_NAMES)


def test_stratum_of_a_statement() -> None:
    alloc = allocation()
    assert alloc.stratum_of("month_year", 0) == "month_year"
    assert alloc.stratum_of("month_year", 1) == "distractor"
    assert alloc.stratum_of("tbd", 2) == "distractor"
    assert alloc.stratum_of("year", 0) == "quarter"
    assert alloc.stratum_of("discontinuation", 3) == "discontinuation"
    assert alloc.stratum_of("distractor", 0) == "distractor"


def test_cell_of_classes_names_own_classes_and_those_with_a_distractor_date() -> None:
    assert S.row_classes("`quarter`, `half_year`, `year`") == (("quarter", "half_year", "year"), ())
    assert S.row_classes("`distractor`; `tbd`, `vague` with a distractor date") == (
        ("distractor",),
        ("tbd", "vague"),
    )
    assert S.row_classes("`range`, `relative` With  a Distractor date") == (
        (),
        ("range", "relative"),
    )
    assert S.row_classes("`tbd` with a distractor date; `distractor`") == (
        ("distractor",),
        ("tbd",),
    )
    assert S.row_classes("no class at all") == ((), ())


def test_rows_of_the_real_layout_split_by_distractor_date() -> None:
    """The vague and undated rows apart; a statement with a distractor date goes to the
    distractor-only row when its class has no dated target, to the other row when it has one."""
    alloc = split_allocation(
        pilot=dict.fromkeys(SPLIT_NAMES, 1), literal={"vague": 3, "no_date": 5}
    )
    assert alloc.names == SPLIT_NAMES
    assert [s.label for s in alloc.strata[8:10]] == ["vague", "undated"]
    assert alloc.quotas["pilot"] == dict.fromkeys(SPLIT_NAMES, 1)
    assert (alloc.quotas["literal"]["vague"], alloc.quotas["literal"]["no_date"]) == (3, 5)
    assert sorted(alloc.by_class) == sorted(F.FORM_NAMES)
    assert alloc.by_class["vague"] == "vague" and alloc.by_class["no_date"] == "no_date"
    assert S.DATED_DISTRACTOR == "dated_distractor" not in alloc.by_class.values()
    beside = alloc.by_class_with_distractor
    assert sorted(beside) == sorted(set(F.FORM_NAMES) - set(S.OWN_ROW))
    assert {c for c, st in beside.items() if st == "dated_distractor"} == set(F.DATED_FORMS)
    assert {c for c, st in beside.items() if st == "distractor"} == {
        "tbd",
        "vague",
        "no_date",
        "silent",
    }
    for form in ("vague", "no_date", "tbd", "silent"):
        assert alloc.stratum_of(form, 0) == form
        assert alloc.stratum_of(form, 1) == "distractor"
    for form in F.DATED_FORMS:
        assert alloc.stratum_of(form, 0) == alloc.by_class[form] != "dated_distractor"
        assert alloc.stratum_of(form, 2) == "dated_distractor"
    assert alloc.stratum_of("year", 0) == "quarter"
    assert alloc.stratum_of("distractor", 0) == alloc.stratum_of("distractor", 4) == "distractor"
    assert alloc.stratum_of("discontinuation", 3) == "discontinuation"
    # the strata that the later draw and the check sets call dated own a dated class
    dated = [s.name for s in alloc.strata if set(s.classes) & set(F.DATED_FORMS)]
    assert dated == list(DATED)


def test_allocation_table_must_be_whole() -> None:
    good = guide_text(pilot=EVERY)
    with pytest.raises(ValueError, match="no allocation table"):
        S.guide_allocation("# A guide with no table\n")
    with pytest.raises(ValueError, match="totals row"):
        S.guide_allocation(good.replace("| **Total** | | **12** |", "| **Total** | | **13** |"))
    with pytest.raises(ValueError, match="missing \\['range'\\]"):
        S.guide_allocation(good.replace("| range | `range` | 1 |  |  |  |\n", ""))
    with pytest.raises(ValueError, match=r"classes named are not .* unknown or repeated"):
        S.guide_allocation(good.replace("`half_year`", "`range`"))
    with pytest.raises(ValueError, match="two rows give the stratum 'range'"):
        S.guide_allocation(good.replace("`relative`", "`range`"))
    with pytest.raises(ValueError, match="sample columns"):
        S.guide_allocation(good.replace("| Reserve |", "| Spare |"))
    with pytest.raises(ValueError, match="no classifier class"):
        S.guide_allocation(good.replace("`silent`", "silent"))


def test_classes_with_a_distractor_date_must_be_whole_too() -> None:
    good = guide_text(pilot=dict.fromkeys(SPLIT_NAMES, 1), split=True)
    assert S.guide_allocation(good).names == SPLIT_NAMES
    mark = "named with a distractor date are not the classifier's inventory"
    with pytest.raises(ValueError, match=f"{mark} \\(missing \\['silent'\\]"):
        S.guide_allocation(good.replace("`no_date`, `silent` with", "`no_date` with"))
    with pytest.raises(ValueError, match=f"{mark} .*unknown or repeated \\['tbd'\\]"):
        S.guide_allocation(good.replace("`exact_day` with", "`exact_day`, `tbd` with"))
    # a discontinuation or a distractor statement keeps its row: neither is named that way
    for own in S.OWN_ROW:
        with pytest.raises(ValueError, match=f"{mark} .*unknown or repeated \\['{own}'\\]"):
            S.guide_allocation(good.replace("`exact_day` with", f"`exact_day`, `{own}` with"))
    # the wording of the first draft of the guide is not read as a rule
    old = "`distractor`, and any class above with a distractor date"
    with pytest.raises(ValueError, match="allocation table"):
        S.guide_allocation(good.replace(SPLIT_ROWS[11][1], old))
    two = good.replace("`distractor`; `tbd`", "`tbd`").replace(
        "| discontinuation | `discontinuation` |",
        "| discontinuation | `discontinuation`, `distractor` |",
    )
    with pytest.raises(ValueError, match="two rows give the stratum 'dated_distractor'"):
        S.guide_allocation(two)


def test_exclusions_are_the_three_column_rows_of_appendix_a() -> None:
    appendix = "\n".join(
        [
            "| Generic | Company | Statement date |",
            "|---|---|---|",
            "| Alpha Tablets, USP | Acme  Pharma, Inc. | 2019-10-09 and 2019-12-10 |",
            '| Beta Injection | Bolt | 2020-03-31: "Estimated availability Dec-2020" |',
            "",
            "| Example | `event_id` |",
            "|---|---|",
            "| 1 Alpha | `E67ea1febd54f` |",
        ]
    )
    found = S.guide_exclusions(guide_text(appendix=appendix))
    assert found == [
        ("alpha tablets, usp", "acme pharma, inc", "2019-10-09"),
        ("alpha tablets, usp", "acme pharma, inc", "2019-12-10"),
        ("beta injection", "bolt", "2020-03-31"),
    ]
    assert S.guide_exclusions("# no appendix\n") == []


def test_guide_version_and_stamp() -> None:
    text = guide_text()
    assert S.guide_version(text) == "v9 test"
    assert S.guide_stamp(text) == f"v9 test sha256 {hashlib.sha256(text.encode()).hexdigest()[:16]}"
    assert S.guide_version("no version line") == "unknown"
    for line, version in (
        ("**Version v1 draft, 1 October 2026.** The pilot", "v1 draft"),
        ("**Version v1, 2 October 2026.** Frozen", "v1"),
        ("**Version v1.1, 3 October 2026.** Revised once more", "v1.1"),
        ("**Version v1.1 draft, 3 October 2026.**", "v1.1 draft"),
        ("**Version v1.** Frozen", "v1"),
        ("**Version v1.10.2.** Frozen", "v1.10.2"),
    ):
        assert S.guide_version(f"# Guide\n\n{line}\n") == version, line


def test_the_real_guide_gives_the_sizes_of_the_decisions() -> None:
    text = REAL_GUIDE.read_text(encoding="utf-8")
    alloc = S.guide_allocation(text)
    sums = {sample: sum(q.values()) for sample, q in alloc.quotas.items()}
    assert sums == {"pilot": 20, "check": 20, "reserve": 20, "literal": 120}
    dated = [s.name for s in alloc.strata if set(s.classes) & set(F.DATED_FORMS)]
    for sample in ("check", "reserve"):
        assert all(q == 0 for st, q in alloc.quotas[sample].items() if st not in dated)
        assert all(q > 0 for st, q in alloc.quotas[sample].items() if st in dated)
    assert all(q > 0 for q in alloc.quotas["pilot"].values())
    assert all(q > 0 for q in alloc.quotas["literal"].values())
    # the rows as the owner set them on 1 October: vague and undated apart, two distractor rows
    assert alloc.names == SPLIT_NAMES
    wanted = {"vague": (1, 3), "no_date": (1, 5), "distractor": (1, 6), "dated_distractor": (1, 6)}
    for name, sizes in wanted.items():
        assert (alloc.quotas["pilot"][name], alloc.quotas["literal"][name]) == sizes, name
    assert alloc.by_class_with_distractor == split_allocation().by_class_with_distractor
    assert sums["literal"] - alloc.quotas["literal"]["month_year"] == 108  # the E2 test items
    recipients = {st for names in S.SHORTFALL_TO.values() for st in names}
    recipients |= {st for names in S.SHORTFALL_FIRST.values() for st in names}
    assert (recipients | set(S.SHORTFALL_FIRST) | set(S.PAIR_SEEDS_LATER)) <= set(alloc.names)
    listed = S.guide_exclusions(text)
    assert len(listed) > 20
    assert all(date.fromisoformat(day) < date(2023, 1, 1) for _, _, day in listed)
    item = read.CANARY_ITEM
    assert any(
        (g, day) == (C.norm_text(item.generic_name), item.date_of_update) for g, _, day in listed
    )
    assert S.guide_version(text).startswith("v1")


def test_the_constants_are_the_real_guides() -> None:
    """The caps, the test share, the shortfall order and the 60-month warning are written in
    the guide (sections 3.2 and 3.12); the code must not drift from the registered text."""
    text = " ".join(REAL_GUIDE.read_text(encoding="utf-8").split())
    caps = re.search(
        r"At most (\d+) items per masked template .*? and (\d+) per shortage episode", text
    )
    assert caps and (int(caps[1]), int(caps[2])) == (S.MAX_PER_TEMPLATE, S.MAX_PER_EPISODE)
    assert "takes one third of its quota (rounded) from statements dated 2023-01-01" in text
    assert S.TEST_SHARE == (1, 3)
    assert "What the vague stratum lacks goes to the undated stratum first" in text
    assert S.SHORTFALL_FIRST == {"vague": ("no_date",)}
    assert "the shortfall goes to the TBD, distractor-only and silent strata in turn" in text
    assert S.SHORTFALL_TO["literal"] == ("tbd", "distractor", "silent")
    assert "in the pilot and the check sets it goes to the month-and-year stratum" in text
    assert {S.SHORTFALL_TO[name] for name in S.TRAIN_ONLY} == {("month_year",)}
    assert "A `distractor` statement is in the distractor-only row whatever it carries" in text
    assert "a `discontinuation` statement stays in its own row" in text
    assert S.OWN_ROW == ("distractor", "discontinuation")
    assert f"the row that owns none is `{S.DATED_DISTRACTOR}`" in text
    assert "ends in *with a distractor date*" in text
    assert S.DISTRACTOR_MARK == "with a distractor date"
    words = {"three": 3}
    phrase = re.search(
        r"word for word and punctuation aside, a phrase of (\w+) or more words quoted in "
        r"section (\d+) or in section (\d+)",
        text,
    )
    assert phrase and words[phrase[1]] == S.MIN_PHRASE_WORDS
    assert (phrase[2], phrase[3]) == S.PHRASE_SECTIONS
    assert S.phrase_key("Estimated recovery: TBD") == S.phrase_key("Estimated recovery TBD")
    far = re.search(r"a date lies more than (\d+) months from the Date of update", text)
    assert far and int(far[1]) == S.FAR_MONTHS
    assert f"Every draw uses seed {S.SEED}" in text
    # the later lists (sections 7.1 and 10)
    pool = re.search(r"the in-context pool, (\d+) fit-split statements", text)
    assert pool and int(pool[1]) == S.LATER["incontext_pool"].size
    assert S.LATER["incontext_pool"].splits == ("fit",)
    dev = re.search(r"(\d+) dev prompt items, dev-split statements", text)
    assert dev and int(dev[1]) == S.LATER["dev_prompt"].size
    assert S.LATER["dev_prompt"].splits == ("dev",)
    seeds = re.search(r"(\d+) pair seeds for the minimal-pair generator", text)
    assert seeds and int(seeds[1]) == S.LATER["pair_seeds"].size
    shares = re.search(r"(\d+) of month and year and (\d+) of each other stratum", text)
    assert shares and int(shares[1]) == S.PAIR_SEED_SHARE["month_year"]
    assert int(shares[2]) == S.PAIR_SEED_REST
    assert "the seeds of the relative form are statements dated 2023-01-01 or later" in text
    assert S.PAIR_SEEDS_LATER == ("relative",)
    assert "`draw_rank`" in text and "`period`" in text and "samples_later/" in text


def test_the_real_guide_quotes_its_phrases_in_sections_3_and_7() -> None:
    text = REAL_GUIDE.read_text(encoding="utf-8")
    phrases = S.guide_phrases(text)
    assert len(phrases) > 80
    assert all(S.phrase_words(phrase) >= S.MIN_PHRASE_WORDS for phrase in phrases)
    for quoted in (
        "Check wholesalers for inventory",  # section 3.6
        "Product will be made available as it is released",  # section 3.7
        "Unavailable. Estimated recovery TBD.",  # worked example 11
        "Backordered. Next release expected October 2020.",  # section 7.3
        # worked example 1: each of the two fields of the table cell
        "Next Delivery and Estimated Recovery: June 2021",
        "Shortage per Manufacturer: Manufacturing Delay",
        "Partial shipments on allocation through February 2021",  # worked example 8
    ):
        assert C.norm_text(quoted) in phrases, quoted
    assert "on backorder" not in phrases and "mar 21" not in phrases  # fewer than three words
    assert not any(" || " in phrase for phrase in phrases)  # a phrase is one quotation
    # the twins of worked examples at other drugs: one field, or two fields that are each quoted
    rows = [
        event(1, "Unavailable. Estimated recovery TBD."),  # example 11
        event(
            2,
            "Next Delivery and Estimated Recovery: June 2021 || Shortage per Manufacturer: "
            "Manufacturing Delay",  # example 1, as the table quotes its two fields
        ),
        event(3, "Backordered. Next release October 2020. || Check wholesalers for inventory"),
        event(4, "Backordered. Next release October 2021. || Check wholesalers for inventory"),
        event(5, "Backordered. Next release October 2020. || Call customer service"),
    ]
    assert S.phrase_statements(frame(rows), phrases) == {"S00001", "S00002", "S00003"}
    # a phrase quoted only outside sections 3 and 7 (here section 6.6) is not read
    assert "Estimated shortage duration is until Q1 2020" in text
    assert not any("estimated shortage duration is until q1 2020" in phrase for phrase in phrases)


# --------------------------------------------------------------------------------------------
# Display rows and the statement table
# --------------------------------------------------------------------------------------------


def test_display_row_is_the_seeded_at_risk_member() -> None:
    text = "Backordered. Next release April 2021."
    rows = [
        event(n, text, statement_group_id="S1", availability_class=c, status_at_statement=s)
        for n, (c, s) in enumerate(
            [
                ("available", "current"),
                ("limited", "current"),
                ("limited", "current"),
                ("unavailable", "current"),
                ("limited", "resolved"),
            ]
        )
    ]
    rows += [event(9, text, statement_group_id="S2", availability_class="available")]
    rows += [event(8, text, statement_group_id="S2", listing="discontinuation")]
    shown = S.display_events(frame(rows)).set_index("statement_group_id")
    at_risk = ["E00001", "E00002", "E00003"]
    assert shown.loc["S1", "event_id"] == min(at_risk, key=lambda e: S.draw_key("display/S1", e))
    assert shown.loc["S1", "n_presentations"] == 5
    assert shown.loc["S2", "event_id"] == "E00008"  # none at risk under B: the smallest id
    assert shown.loc["S2", "n_presentations"] == 2
    mixed = frame(random.Random(3).sample(rows, len(rows)))
    assert S.display_events(mixed).equals(S.display_events(frame(rows)))


def test_display_row_does_not_move_with_the_first_member() -> None:
    """Over many statements the seeded member is not always the first or the last one."""
    rows = [
        event(10 * g + k, "On backorder.", statement_group_id=f"S{g}")
        for g in range(30)
        for k in range(4)
    ]
    shown = S.display_events(frame(rows))
    places = Counter(int(e[1:]) % 10 for e in shown["event_id"])
    assert set(places) == {0, 1, 2, 3}


def test_display_row_is_the_dataset_builders() -> None:
    dataset = pytest.importorskip("analysis.coling.dataset")
    rows = [
        event(10 * g + k, "On backorder.", statement_group_id=f"S{g}", availability_class=c)
        for g in range(12)
        for k, c in enumerate(("available", "limited", "unavailable", "limited"))
    ]
    events = frame(rows)
    for column in dataset.EVENT_FIELDS:
        if column not in events.columns:
            events[column] = ""
    theirs = dataset.display_rows(dataset.member_flags(events))["event_id"]
    ours = S.display_events(events).set_index("statement_group_id")["event_id"]
    assert ours.to_dict() == theirs.to_dict()


def test_statement_table_strata_periods_and_frame() -> None:
    alloc = allocation()
    rows = [
        event(1, "Backordered. Next release April 2021.", "2020-03-02"),
        event(2, "Backordered. Next release April 2021. (expiry 6/30/2021)", "2020-03-02"),
        event(3, "Backordered. Next release April 2024.", "2023-01-01"),
        event(4, "Backordered. Next release April 2023.", "2022-12-31"),
        event(5, "On backorder.", "2021-01-01", status_at_statement="resolved"),
        event(6, "On backorder.", "2020-12-31", listing="discontinuation"),
        event(7, "On backorder.", "2020-06-01", availability_class="available", episode_id=""),
        event(8, "Next release April 2020.", "2020-06-01"),
        event(9, "To be discontinued March 2021. (expiry 6/30/2021)", "2020-06-01"),
    ]
    table = {s["id"]: s for s in S.statement_table(frame(rows), alloc)}
    assert [table[f"S{n:05d}"]["stratum"] for n in (1, 2, 5, 9)] == [
        "month_year",
        "distractor",
        "silent",
        "discontinuation",
    ]
    assert table["S00002"]["form"] == "month_year"
    assert [table[f"S{n:05d}"]["period"] for n in (1, 3, 4)] == ["train", "test", "train"]
    assert [table[f"S{n:05d}"]["split"] for n in (1, 3, 4, 5, 6)] == [
        "fit",
        "test",
        "dev",
        "dev",
        "fit",
    ]
    assert [table[f"S{n:05d}"]["in_frame"] for n in (1, 5, 6, 7)] == [True, False, False, True]
    assert [table[f"S{n:05d}"]["at_risk_B"] for n in (1, 7)] == [True, False]
    assert table["S00008"]["stale"] and not table["S00001"]["stale"]
    assert table["S00007"]["episode"] == "generic:g00007"
    assert table["S00001"]["episode"] == "P00001"
    assert table["S00001"]["template"] == "backordered. next release <mon> <n>"
    assert table["S00001"]["text"].split("\x1f") == [
        "g00001",
        "acme pharma, inc",
        "backordered. next release april 2021",
    ]
    assert table["S00001"]["wording"] == "backordered. next release april 2021"
    assert table["S00001"]["notice"].split("\x1f") == [
        "g00001",
        "acme pharma, inc",
        "2020-03-02",
        "next_delivery",
        "2021-04-01",
        "2021-04-30",
    ]
    assert table["S00005"]["notice"].split("\x1f")[3:] == ["none", "", ""]


def test_a_notice_is_the_drug_the_company_the_day_and_what_is_stated() -> None:
    """Two presentations of one drug that say the same on the same day have one notice, whatever
    the spelling; another period, another day, another company or another drug is another."""
    alloc = allocation()
    one = {"generic_id": "g1", "generic_name": "Examplamine Injection"}
    rows = [
        event(1, "Cannot support monthly demand. Estimated shortage duration: 90 days.", **one),
        event(2, "Cannot supoort monthly demand.  Estimated shortage duration: 90 days", **one),
        event(3, "Cannot support monthly demand. Estimated shortage duration: 60 days.", **one),
        event(4, "Estimated shortage duration: 90 days.", "2020-03-03", **one),
        event(5, "Estimated shortage duration: 90 days.", **one, company_name="Bolt"),
        event(6, "Estimated shortage duration: 90 days."),
    ]
    table = {s["id"]: s for s in S.statement_table(frame(rows), alloc)}
    notice = {n: table[f"S{n:05d}"]["notice"] for n in range(1, 7)}
    assert notice[1] == notice[2] and table["S00001"]["wording"] != table["S00002"]["wording"]
    assert len({notice[n] for n in (1, 3, 4, 5, 6)}) == 5
    twins = S.labelled_twins(list(table.values()), ["S00001"])
    assert twins == {"same_wording": set(), "same_notice": {"S00002"}}


def test_no_outcome_field_is_read() -> None:
    """The sampler keeps only its named first-sight fields: a table with other columns, whatever
    they hold, gives the same statements, and a missing field stops it."""
    events = small_corpus(3, 1)
    alloc = allocation()
    assert not {"outcome_type", "upper_date"} & set(S.EVENT_FIELDS)
    assert not [f for f in S.EVENT_FIELDS if any(w in f for w in ("outcome", "lower", "upper"))]
    changed = events.assign(outcome_type="discontinued", upper_date="", period="x", status="y")
    assert S.statement_table(changed, alloc) == S.statement_table(events, alloc)
    assert S.events_fields_sha256(changed) == S.events_fields_sha256(events)
    assert S.events_fields_sha256(events.iloc[::-1]) == S.events_fields_sha256(events)
    assert S.events_fields_sha256(events.drop(index=0)) != S.events_fields_sha256(events)
    with pytest.raises(ValueError, match="lacks \\['thread_id'\\]"):
        S.statement_table(events.drop(columns="thread_id"), alloc)


# --------------------------------------------------------------------------------------------
# Exclusions: Appendix A and the harness's fixed test item
# --------------------------------------------------------------------------------------------


def test_excluded_statements_by_date_and_by_text() -> None:
    same = {"generic_name": "Alpha Tablets, USP", "generic_id": "alpha"}
    rows = [
        event(1, "Next release April 2020.", "2020-03-02", **same),
        event(2, "Next release April 2020.", "2020-03-20", **same),  # the text, another day
        event(3, "Next release May 2020.", "2020-03-20", **same),  # another text
        event(4, "Next release April 2020.", "2020-03-02", **same, company_name="Bolt"),
        event(5, "Other words.", "2020-03-02", **same),  # the day, another text
        event(6, "Next release April 2020.", "2020-03-02"),  # another drug
    ]
    keys = [
        ("alpha tablets, usp", "acme pharma, inc", "2020-03-02"),
        ("gone", "nobody", "2020-01-01"),
    ]
    excluded, unmatched = S.excluded_statements(frame(rows), keys)
    assert excluded == {"S00001", "S00002", "S00005"}
    assert unmatched == 1
    assert S.excluded_statements(frame(rows), []) == (set(), 0)


QUOTING = """## 3. Task A

Cues: "Estimated Recovery", "Product will be made available as it
  is released" and \u201cNext release October 2020\u201d. A short one: "Mar 21".

- a bullet with "on allocation through X" and
  "Anticipated availability - April 2021";
- another with "TBD".

```
- Availability information: "Backordered. Next release May 2020."
- Related information: "Check wholesalers for inventory"
```

| # | Text (Availability; Related) | Why |
|---|---|---|
| 1 | "Next Delivery: June 2021"; "Shortage per Manufacturer: Delay" | both fields |
| 2 | "Low inventory"; "Partial shipments through February 2021" | a bare label |
| 3 | "Recovery May 2020", "Back in stock soon" | two phrases, not one entry |

### 3.2 A subsection

Still section 3: "Will remain on backorder for few months".

## 4. Pilot

Not read: "This phrase of section four".

## 7. Task C

| Factor | Edited entry |
|---|---|
| certainty | "Backordered. Next release expected October 2020." |

## 8. Statistics

Not read: "This phrase of section eight".
"""


def test_guide_phrases_are_the_quotes_of_sections_3_and_7() -> None:
    phrases = S.guide_phrases(guide_text(section=QUOTING))
    assert phrases == {
        "product will be made available as it is released",  # wrapped over two lines
        "next release october 2020",  # curly quotation marks
        "on allocation through x",
        "anticipated availability - april 2021",  # the dash is not a word, the rest is three
        "backordered. next release may 2020",
        "check wholesalers for inventory",
        "next delivery: june 2021",
        "shortage per manufacturer: delay",
        "partial shipments through february 2021",
        "recovery may 2020",
        "back in stock soon",
        "will remain on backorder for few months",
        "backordered. next release expected october 2020",
    }
    assert S.guide_phrases(guide_text()) == set()  # a guide without these sections
    assert S.guide_section(QUOTING, "3").startswith("## 3. Task A")
    assert "### 3.2" in S.guide_section(QUOTING, "3") and "## 4." not in S.guide_section(
        QUOTING, "3"
    )
    assert S.guide_section(QUOTING, "8").endswith('section eight".\n')
    assert S.guide_section(QUOTING, "9") == ""
    assert [S.phrase_words(t) for t in ("mar 21", "a - b", "a-b c d", "(1/2022 expiry)")] == [
        2,
        2,
        3,
        2,
    ]


def test_an_odd_number_of_quotation_marks_stops_the_reading() -> None:
    broken = QUOTING.replace('"Estimated Recovery"', '"Estimated Recovery')
    with pytest.raises(ValueError, match="section 3: an odd number of quotation marks in 'Cues"):
        S.guide_phrases(guide_text(section=broken))
    row = QUOTING.replace('"Recovery May 2020", ', '"Recovery May 2020, ')
    with pytest.raises(ValueError, match=r"section 3: an odd number of quotation marks in '\| 3 "):
        S.guide_phrases(guide_text(section=row))
    elsewhere = QUOTING.replace('"This phrase of section four"', '"This phrase')
    assert S.guide_phrases(guide_text(section=elsewhere))  # section 4 is not read


def test_statements_equal_to_a_phrase_whatever_the_drug() -> None:
    phrases = S.guide_phrases(guide_text(section=QUOTING))
    rows = [
        event(1, "Check wholesalers for inventory."),  # equal, up to case and the full stop
        event(2, "CHECK  wholesalers for inventory", company_name="Bolt"),  # another company
        event(3, "Check wholesalers for inventory", "2024-05-06"),  # another date and period
        event(4, "On backorder. Check wholesalers for inventory."),  # contains it: stays
        event(5, "Check wholesalers"),  # a part of it: stays
        event(6, "Mar 21"),  # a quoted phrase of two words: stays
        # two fields, each of them a quoted phrase (the entry block; a table cell with both)
        event(7, "Backordered. Next release May 2020. || Check wholesalers for inventory"),
        event(8, "Next Delivery: June 2021 || Shortage per Manufacturer: Delay."),
        event(9, "Partial shipments through February 2021"),
        # two fields of which only one is quoted: stays
        event(10, "Low inventory || Partial shipments through February 2021"),
        event(11, "This phrase of section four"),
        event(12, "Backordered. Next release June 2020. || Check wholesalers for inventory"),
        event(13, "Check wholesalers for inventory || TBD"),
        # the words of a phrase with other punctuation: equal; with another word or order: stays
        event(14, "Next Delivery - June 2021."),
        event(15, "Backordered, next release: May 2020 || Check wholesalers, for inventory"),
        event(16, "Next Delivery: July 2021"),
        event(17, "June 2021: Next Delivery"),
        event(18, "Checkwholesalers for inventory"),
    ]
    assert S.phrase_statements(frame(rows), phrases) == {"S00001", "S00002", "S00003"} | {
        "S00007",
        "S00008",
        "S00009",
        "S00014",
        "S00015",
    }
    assert S.phrase_key("  Estimated recovery: TBD. ") == "estimated recovery tbd"
    assert S.phrase_key("Available by 4/5/19 (Dec-2020)") == "available by 4 5 19 dec 2020"
    assert S.phrase_key("") == S.phrase_key(" - ") == ""
    assert S.phrase_statements(frame(rows), []) == set()
    # every presentation of a statement has its text: the statement is named once
    twice = [*rows, event(12, "Check wholesalers for inventory", statement_group_id="S00001")]
    assert S.phrase_statements(frame(twice), phrases) >= {"S00001"}


def test_items_that_contain_a_quoted_phrase_are_counted() -> None:
    phrases = {"check wholesalers for inventory", "next release october 2020"}
    table = [
        record(1, wording="backordered. next release october 2020"),
        record(2, wording="backordered. next release november 2020"),
        record(3, wording="on backorder || check wholesalers for inventory"),
        record(4, wording="check wholesalers for inventory. next release october 2020"),
        record(5, wording=""),
        record(6, wording="next release: october 2020"),  # the words, with a colon
        record(7, wording="next release october 20201"),  # another number: not the phrase
        record(8, wording="recheck wholesalers for inventory"),  # another word
    ]
    ids = [s["id"] for s in table]
    assert S.containing_a_phrase(table, ids, phrases) == 4  # an item with two phrases counts once
    assert S.containing_a_phrase(table, ids[1:2], phrases) == 0
    assert S.containing_a_phrase(table, ids, set()) == 0
    assert S.containing_a_phrase(table, [], phrases) == 0


def test_phrase_rule_is_counted_by_stratum_and_period() -> None:
    table = records({"silent": (5, 3), "tbd": (2, 0)})
    table.append(record(90, "silent", in_frame=False))
    silent = [s["id"] for s in table if s["stratum"] == "silent" and s["in_frame"]]
    listed = {silent[0], silent[1]}
    worded = {silent[1], silent[2], silent[5], "S00090"}  # one is in Appendix A already
    rows = S.phrase_counts(table, listed, worded)
    assert rows == [
        {
            "stratum": "silent",
            "period": "test",
            "frame": 3,
            "appendix_a": 0,
            "equal_to_a_phrase": 1,
            "removed": 1,
        },
        {
            "stratum": "silent",
            "period": "train",
            "frame": 5,
            "appendix_a": 2,
            "equal_to_a_phrase": 2,
            "removed": 1,
        },
        {
            "stratum": "tbd",
            "period": "train",
            "frame": 2,
            "appendix_a": 0,
            "equal_to_a_phrase": 0,
            "removed": 0,
        },
    ]
    assert tuple(rows[0]) == S.PHRASE_COLUMNS


def test_the_fixed_test_item_of_the_harness_is_found() -> None:
    item = read.CANARY_ITEM
    real = {"generic_name": item.generic_name, "generic_id": "anagrelide"}
    rows = [
        event(1, "Expected recovery April 2020", item.date_of_update, **real),
        event(2, "Expected recovery April 2020", "2020-02-11", **real),  # the text, earlier
        event(3, "On backorder", item.date_of_update, **real),  # the day, not the item's text
        event(4, "Expected recovery April 2020", item.date_of_update),  # another drug
        event(5, "On backorder", item.date_of_update, **real, company_name="Bolt"),  # other maker
    ]
    keys = S.canary_keys(frame(rows))
    assert keys == {(C.norm_text(item.generic_name), "acme pharma, inc", item.date_of_update)}
    excluded, unmatched = S.excluded_statements(frame(rows), keys)
    assert excluded == {"S00001", "S00002", "S00003"} and unmatched == 0
    assert S.canary_keys(frame(rows[3:])) == set()


# --------------------------------------------------------------------------------------------
# The first draw
# --------------------------------------------------------------------------------------------


def test_first_draw_fills_every_quota_and_keeps_samples_apart() -> None:
    alloc = allocation(**SMALL)
    table = records(dict.fromkeys(NAMES, (10, 5)))
    by_id = {s["id"]: s for s in table}
    drawn = S.draw_first(table, alloc)
    assert list(drawn.lists) == list(S.FIRST_SAMPLES)
    assert {k: len(v) for k, v in drawn.lists.items()} == {
        "pilot": 12,
        "check": 7,
        "reserve": 7,
        "literal": 36,
    }
    everything = [i for ids in drawn.lists.values() for i in ids]
    assert len(set(everything)) == len(everything)
    for sample, ids in drawn.lists.items():
        assert ids == sorted(ids)
        assert Counter(by_id[i]["stratum"] for i in ids) == {
            st: q for st, q in alloc.quotas[sample].items() if q
        }
    for sample in S.TRAIN_ONLY:
        assert {by_id[i]["period"] for i in drawn.lists[sample]} == {"train"}
    literal = Counter((by_id[i]["stratum"], by_id[i]["period"]) for i in drawn.lists["literal"])
    assert all(literal[st, "train"] == 2 and literal[st, "test"] == 1 for st in NAMES)
    rows = {(r["sample"], r["stratum"], r["period"]): r for r in drawn.strata}
    assert rows["pilot", "tbd", "train"] == {
        "sample": "pilot",
        "stratum": "tbd",
        "period": "train",
        "pool": 10,
        "available": 10,
        "quota": 1,
        "drawn": 1,
    }
    assert (
        rows["check", "tbd", "train"]["pool"] == 9 and rows["check", "tbd", "train"]["quota"] == 0
    )
    assert rows["literal", "range", "train"]["pool"] == 7  # after pilot, check and reserve
    assert rows["literal", "range", "test"] == {
        "sample": "literal",
        "stratum": "range",
        "period": "test",
        "pool": 5,
        "available": 5,
        "quota": 1,
        "drawn": 1,
    }
    assert ("pilot", "tbd", "test") not in rows


def test_first_draw_takes_the_top_of_the_seeded_order() -> None:
    alloc = allocation(pilot={"tbd": 3}, check={"range": 2})
    table = records({"tbd": (9, 4), "range": (6, 0)})
    drawn = S.draw_first(table, alloc)
    tbd = [s["id"] for s in table if s["stratum"] == "tbd" and s["period"] == "train"]
    assert drawn.lists["pilot"] == sorted(S.shuffled(tbd, "pilot/tbd/train")[:3])
    ranges = [s["id"] for s in table if s["stratum"] == "range"]
    assert drawn.lists["check"] == sorted(S.shuffled(ranges, "check/range/train")[:2])


def test_first_draw_ignores_input_order_and_untaken_statements() -> None:
    alloc = allocation(**SMALL)
    table = records(dict.fromkeys(NAMES, (10, 5)))
    drawn = S.draw_first(table, alloc)
    mixed = random.Random(5).sample(table, len(table))
    assert S.draw_first(mixed, alloc).lists == drawn.lists
    assert S.draw_first(mixed, alloc).strata == drawn.strata
    taken = {i for ids in drawn.lists.values() for i in ids}
    spare = next(s for s in table if s["id"] not in taken and s["stratum"] == "silent")
    without = [s for s in table if s is not spare]
    assert S.draw_first(without, alloc).lists == drawn.lists


def test_frame_and_exclusions_limit_the_first_draw() -> None:
    alloc = allocation(pilot={"tbd": 2}, literal={"tbd": 3})
    table = records({"tbd": (6, 3)})
    out = [record(100 + n, "tbd", in_frame=False) for n in range(60)]
    drawn = S.draw_first([*table, *out], alloc)
    assert not {s["id"] for s in out} & {i for ids in drawn.lists.values() for i in ids}
    barred = set(drawn.lists["pilot"]) | set(drawn.lists["literal"][:1])
    again = S.draw_first(table, alloc, excluded=barred)
    assert not barred & {i for ids in again.lists.values() for i in ids}
    assert len(again.lists["pilot"]) == 2 and len(again.lists["literal"]) == 3


def test_literal_periods_make_up_for_each_other() -> None:
    alloc = allocation(literal={"relative": 9, "range": 9, "quarter": 9, "tbd": 9})
    table = records({"relative": (2, 20), "range": (20, 1), "quarter": (20, 20), "tbd": (3, 2)})
    by_id = {s["id"]: s for s in table}
    drawn = S.draw_first(table, alloc)
    got = Counter((by_id[i]["stratum"], by_id[i]["period"]) for i in drawn.lists["literal"])
    assert (got["quarter", "train"], got["quarter", "test"]) == (6, 3)
    assert (got["relative", "train"], got["relative", "test"]) == (2, 7)
    assert (got["range", "train"], got["range", "test"]) == (8, 1)
    assert (got["tbd", "train"], got["tbd", "test"]) == (3, 2)  # all it has
    rows = {(r["stratum"], r["period"]): r for r in drawn.strata if r["sample"] == "literal"}
    assert (rows["relative", "train"]["quota"], rows["relative", "test"]["quota"]) == (6, 3)
    assert (rows["relative", "train"]["drawn"], rows["relative", "test"]["drawn"]) == (2, 7)


def test_cap_per_template_runs_over_all_samples() -> None:
    alloc = allocation(pilot={"tbd": 1}, check={"range": 1}, literal={"tbd": 4, "range": 4})
    one = [record(n, "tbd", template="the same wording") for n in range(8)]
    other = [record(20 + n, "range", template="the same wording") for n in range(8)]
    drawn = S.draw_first([*one, *other], alloc)
    assert sum(len(ids) for ids in drawn.lists.values()) == S.MAX_PER_TEMPLATE == 2
    assert len(drawn.lists["pilot"]) == 1 and len(drawn.lists["check"]) == 1
    assert drawn.lists["literal"] == []
    literal = {(r["stratum"], r["period"]): r for r in drawn.strata if r["sample"] == "literal"}
    assert literal["tbd", "train"]["pool"] == 7 and literal["tbd", "train"]["available"] == 0


def test_cap_per_episode_and_one_item_per_text() -> None:
    alloc = allocation(pilot={"tbd": 5}, literal={"tbd": 5})
    episode = [record(n, "tbd", episode="one episode") for n in range(8)]
    drawn = S.draw_first(episode, alloc)
    assert sum(len(ids) for ids in drawn.lists.values()) == S.MAX_PER_EPISODE == 3
    assert len(drawn.lists["pilot"]) == 3
    text = [record(n, "tbd", text="g\x1fc\x1fthe same text") for n in range(8)]
    drawn = S.draw_first(text, alloc)
    assert sum(len(ids) for ids in drawn.lists.values()) == 1


def test_capacity_counts_what_the_caps_allow() -> None:
    pool = [record(n, template="t") for n in range(5)] + [record(9)]
    used, caps = S.Used(), S.Caps()
    assert S.capacity(pool, used, caps) == 3
    assert (used, caps) == (S.Used(), S.Caps())  # nothing was claimed
    assert S.take(pool, 2, used, caps) == ["S00000", "S00001"]
    assert S.capacity(pool, used, caps) == 1
    assert S.take(pool, 5, used, caps) == ["S00009"]


def test_shortfall_goes_to_month_and_year_in_the_small_samples() -> None:
    alloc = allocation(pilot={"relative": 3, "month_year": 1}, check={"relative": 2, "range": 1})
    table = records({"relative": (2, 9), "month_year": (9, 0), "range": (9, 0)})
    by_id = {s["id"]: s for s in table}
    drawn = S.draw_first(table, alloc)
    assert Counter(by_id[i]["stratum"] for i in drawn.lists["pilot"]) == {
        "relative": 2,
        "month_year": 2,
    }
    assert Counter(by_id[i]["stratum"] for i in drawn.lists["check"]) == {
        "month_year": 2,
        "range": 1,
    }
    rows = {(r["sample"], r["stratum"]): r for r in drawn.strata}
    assert (rows["pilot", "relative"]["quota"], rows["pilot", "relative"]["drawn"]) == (3, 2)
    assert (rows["pilot", "month_year"]["quota"], rows["pilot", "month_year"]["drawn"]) == (1, 2)


def test_shortfall_of_the_literal_sample_goes_round_three_strata() -> None:
    alloc = allocation(literal={"relative": 9, "tbd": 3, "distractor": 3, "silent": 3})
    table = records({"relative": (1, 1), "tbd": (20, 20), "distractor": (20, 20), "silent": (3, 1)})
    by_id = {s["id"]: s for s in table}
    drawn = S.draw_first(table, alloc)
    got = Counter(by_id[i]["stratum"] for i in drawn.lists["literal"])
    # 7 missing: tbd, distractor, silent in turn; silent has one more, and the others go on
    assert got == {"relative": 2, "tbd": 6, "distractor": 6, "silent": 4}
    assert len(drawn.lists["literal"]) == 18
    nothing = S.draw_first(records({"relative": (1, 1)}), alloc)
    assert len(nothing.lists["literal"]) == 2  # no recipient has anything: the loop ends


def test_what_the_vague_stratum_lacks_goes_to_the_undated_one_first() -> None:
    def by(table: list[dict]) -> dict[str, dict]:
        return {s["id"]: s for s in table}

    # the pilot: one vague statement for a quota of two; the undated stratum takes the other
    alloc = split_allocation(pilot={"vague": 2, "no_date": 1, "month_year": 1})
    table = records({"vague": (1, 4), "no_date": (6, 0), "month_year": (6, 0)})
    drawn = S.draw_first(table, alloc)
    assert Counter(by(table)[i]["stratum"] for i in drawn.lists["pilot"]) == {
        "vague": 1,
        "no_date": 2,
        "month_year": 1,
    }
    rows = {(r["sample"], r["stratum"]): r for r in drawn.strata}
    assert (rows["pilot", "vague"]["quota"], rows["pilot", "vague"]["drawn"]) == (2, 1)
    assert (rows["pilot", "no_date"]["quota"], rows["pilot", "no_date"]["drawn"]) == (1, 2)
    # the undated stratum gives what it has; the rest goes on to the month-and-year stratum
    table = records({"vague": (0, 4), "no_date": (2, 0), "month_year": (6, 0)})
    drawn = S.draw_first(table, alloc)
    assert Counter(by(table)[i]["stratum"] for i in drawn.lists["pilot"]) == {
        "no_date": 2,
        "month_year": 2,
    }
    # the literal sample: undated first, in both periods, then TBD, distractor only and silent
    alloc = split_allocation(literal={"vague": 3, "no_date": 3, "tbd": 3, "relative": 3})
    table = records(
        {
            "vague": (1, 0),
            "no_date": (20, 20),
            "tbd": (20, 20),
            "relative": (1, 0),
            "silent": (9, 9),
        }
    )
    table += [record(900 + n, "distractor", "train" if n % 2 else "test") for n in range(18)]
    drawn = S.draw_first(table, alloc)
    got = Counter(by(table)[i]["stratum"] for i in drawn.lists["literal"])
    # vague lacks two (undated takes both); relative lacks two (TBD, then distractor only)
    assert got == {"vague": 1, "no_date": 5, "tbd": 4, "relative": 1, "distractor": 1}
    assert len(drawn.lists["literal"]) == 12
    periods = Counter(
        by(table)[i]["period"]
        for i in drawn.lists["literal"]
        if by(table)[i]["stratum"] == "no_date"
    )
    assert periods == {"train": 3, "test": 2}  # one third of five, rounded, from the later period
    # with the two rows in one stratum, as in the made-up guide, there is nothing to pass on
    assert "no_date" not in allocation().names
    one = S.draw_first(records({"vague": (1, 0), "tbd": (9, 9)}), allocation(literal={"vague": 3}))
    assert len(one.lists["literal"]) == 3  # the general recipients take the two


def test_rare_strata_are_served_first() -> None:
    """A stratum with few statements draws before a large one that shares its episode."""
    alloc = allocation(pilot={"month_year": 4, "relative": 1})
    large = [record(n, "month_year", episode="shared") for n in range(6)]
    rare = record(50, "relative", episode="shared")
    drawn = S.draw_first([*large, rare], alloc)
    assert rare["id"] in drawn.lists["pilot"]
    assert len(drawn.lists["pilot"]) == S.MAX_PER_EPISODE


def test_a_kept_sample_is_not_drawn_again_and_counts_against_the_caps() -> None:
    alloc = allocation(pilot={"tbd": 2}, check={"range": 2}, literal={"tbd": 2})
    table = records({"tbd": (8, 4), "range": (6, 0)})
    table += [record(90 + n, "range", template="kept wording") for n in range(3)]
    first = S.draw_first(table, alloc)
    kept = ["S00007", "S00090", "S00091"]  # not what the draw would take
    assert sorted(kept) != first.lists["pilot"]
    again = S.draw_first(table, alloc, fixed={"pilot": kept})
    assert again.lists["pilot"] == sorted(kept)
    assert not set(kept) & (set(again.lists["check"]) | set(again.lists["literal"]))
    assert "S00092" not in again.lists["check"]  # its template is used up by the kept sample
    assert [r for r in again.strata if r["sample"] == "pilot"] == []
    with pytest.raises(ValueError, match="not in the events table"):
        S.draw_first(table, alloc, fixed={"pilot": ["S99999"]})


# --------------------------------------------------------------------------------------------
# The later draw
# --------------------------------------------------------------------------------------------


def later_table() -> list[dict]:
    table: list[dict] = []
    for stratum in NAMES:
        for split, period, k in (("fit", "train", 14), ("dev", "train", 12), ("test", "test", 4)):
            table += [record(len(table) + i, stratum, period, split=split) for i in range(k)]
    return table


def test_later_draw_respects_splits_frames_and_earlier_samples() -> None:
    alloc = allocation(**SMALL)
    table = later_table()
    by_id = {s["id"]: s for s in table}
    first = S.draw_first(table, alloc)
    earlier = {i for ids in first.lists.values() for i in ids}
    audited = {s["id"] for s in table if s["split"] == "fit" and s["stratum"] == "range"}
    audited = set(sorted(audited - earlier)[:5])
    appendix = {s["id"] for s in table if s["split"] == "dev" and s["stratum"] == "tbd"}
    appendix = set(sorted(appendix - earlier)[:3])
    drawn = S.draw_later(table, alloc, appendix, earlier | audited)
    assert list(drawn.lists) == ["incontext_pool", "dev_prompt", "pair_seeds"]
    everything = [i for ids in drawn.lists.values() for i in ids]
    assert len(set(everything)) == len(everything)
    assert not set(everything) & (earlier | audited | appendix)
    pool = [by_id[i] for i in drawn.lists["incontext_pool"]]
    assert len(pool) == S.LATER["incontext_pool"].size
    assert {s["split"] for s in pool} == {"fit"}
    assert {s["form"] for s in pool} == set(DATED)  # the made-up table has no half or year
    counts = Counter(s["form"] for s in pool)
    left = [s for s in table if s["split"] == "fit" and s["id"] not in earlier | audited]
    assert counts["range"] == sum(s["form"] == "range" for s in left) < min(counts.values()) + 2
    others = [k for form, k in counts.items() if form != "range"]
    assert max(others) - min(others) <= 1  # in turn over the forms, a small one giving all it has
    dev = [by_id[i] for i in drawn.lists["dev_prompt"]]
    assert len(dev) == S.LATER["dev_prompt"].size and {s["split"] for s in dev} == {"dev"}
    assert {s["stratum"] for s in dev} == set(NAMES)
    seeds = [by_id[i] for i in drawn.lists["pair_seeds"]]
    assert {s["stratum"] for s in seeds} <= set(DATED)
    # relative seeds are statements dated 2023-01-01 or later; every other seed is train-period
    assert {s["period"] for s in seeds if s["stratum"] == "relative"} == {"test"}
    assert {s["period"] for s in seeds if s["stratum"] != "relative"} == {"train"}
    later = {s["id"] for s in table if s["stratum"] == "relative" and s["period"] == "test"}
    assert {s["id"] for s in seeds if s["stratum"] == "relative"} == later - earlier
    rows = {(r["sample"], r["stratum"]): r for r in drawn.strata}
    assert rows["pair_seeds", "relative"]["period"] == "test"
    assert rows["pair_seeds", "relative"]["pool"] == len(later - earlier)
    assert rows["pair_seeds", "range"]["period"] == "fit+dev"
    assert {
        s["period"]
        for name in ("incontext_pool", "dev_prompt")
        for s in map(by_id.get, drawn.lists[name])
    } == {"train"}
    for name, ids in drawn.lists.items():
        assert ids == sorted(ids)
        assert sorted(drawn.ranks[name].values()) == list(range(1, len(ids) + 1))
        assert set(drawn.ranks[name]) == set(ids)
    # the rank is the order of the draw: the first round takes one statement of every form
    first_round = [i for i, rank in drawn.ranks["incontext_pool"].items() if rank <= len(DATED)]
    assert {by_id[i]["form"] for i in first_round} == set(DATED)
    mixed = random.Random(2).sample(table, len(table))
    again = S.draw_later(mixed, alloc, appendix, earlier | audited)
    assert (again.lists, again.ranks) == (drawn.lists, drawn.ranks)


def test_in_turn_serves_the_smallest_stratum_first() -> None:
    cands = {
        "large": [record(n) for n in range(5)],
        "small": [record(10 + n) for n in range(2)],
        "middle": [record(20 + n) for n in range(3)],
    }
    got = S.in_turn(cands, 4, S.Used(), S.Caps())
    assert got == ["S00010", "S00020", "S00000", "S00011"]
    assert len(S.in_turn(cands, 99, S.Used(), S.Caps())) == 10  # it stops when all are taken
    assert S.in_turn(cands, 0, S.Used(), S.Caps()) == []


def test_later_draw_leaves_out_stale_unframed_and_repeated_texts() -> None:
    alloc = allocation()
    good = [record(n, "month_year", split="fit") for n in range(4)]
    stale = [record(10 + n, "month_year", split="fit", stale=True) for n in range(4)]
    undated = [record(20 + n, "tbd", split="fit") for n in range(4)]
    safe = [record(30 + n, "range", split="fit", at_risk_B=False) for n in range(4)]
    outside = [record(40 + n, "range", split="fit", in_frame=False) for n in range(4)]
    echo = record(50, "month_year", split="fit", text="text 60")  # the text of an earlier item
    earlier = record(60, "month_year", split="fit")
    table = [*good, *stale, *undated, *safe, *outside, echo, earlier]
    drawn = S.draw_later(table, alloc, [], [earlier["id"]])
    assert drawn.lists["incontext_pool"] == [s["id"] for s in good]
    assert drawn.lists["dev_prompt"] == []
    # seeds may be statements that are not at risk under B, but never stale or outside the frame
    assert drawn.lists["pair_seeds"] == [s["id"] for s in safe]


def test_statements_that_read_like_a_labelled_item() -> None:
    item = record(1, wording="next release may 2021", notice="g1/acme/2021-03-01/may")
    silent = record(2, "silent", wording="", notice="g2/acme/2021-03-01/none")
    table = [
        item,
        silent,
        record(3, wording="next release may 2021"),  # the item's text on another drug
        record(4, notice="g1/acme/2021-03-01/may"),  # the item's notice in another spelling
        record(5, wording="next release may 2021", notice="g1/acme/2021-03-01/may"),
        record(6, wording=""),  # an empty text is no wording
        record(7, wording="next release june 2021", notice="g1/acme/2021-03-01/june"),
        record(8, "silent", wording="check the desk", notice="g2/acme/2021-03-01/none"),
    ]
    twins = S.labelled_twins(table, ["S00001", "S00002", "S99999"])
    assert twins == {"same_wording": {"S00003", "S00005"}, "same_notice": {"S00004", "S00008"}}
    # the wording is compared word for word, punctuation aside, as a quoted phrase is
    spelt = [*table, record(9, wording="next release: may 2021."), record(10, wording=" - ")]
    assert S.labelled_twins(spelt, ["S00001", "S00002"])["same_wording"] == {
        "S00003",
        "S00005",
        "S00009",
    }
    assert S.labelled_twins(table, []) == {"same_wording": set(), "same_notice": set()}
    assert S.labelled_twins(table, ["S00007"]) == {"same_wording": set(), "same_notice": set()}


def test_later_draw_leaves_out_what_reads_like_a_labelled_item() -> None:
    alloc = allocation()
    labelled = record(1, split="fit", wording="next release may 2021", notice="n1")
    audited = record(2, split="fit", wording="next release june 2021", notice="n2")
    same_text = record(3, split="fit", wording="next release may 2021")
    same_notice = record(4, split="fit", notice="n1", text="text of the twin")
    echo = record(5, split="fit", text="text of the twin")  # the twin's text at another date
    of_audited = [
        record(6, split="fit", wording="next release june 2021"),
        record(7, split="fit", notice="n2"),
    ]
    free = [record(10 + n, split="fit") for n in range(3)]
    table = [labelled, audited, same_text, same_notice, echo, *of_audited, *free]
    earlier = [labelled["id"], audited["id"]]
    drawn = S.draw_later(table, alloc, [], earlier, labelled=[labelled["id"]])
    # the item's twins and the text of a twin are left out; an audited statement has no twin
    assert drawn.lists["incontext_pool"] == sorted(s["id"] for s in [*of_audited, *free])
    assert drawn.notes == {
        "frame_statements_left_out_same_wording": 1,
        "frame_statements_left_out_same_notice": 1,
    }
    # with no labelled item named, only the statements themselves are left out
    plain = S.draw_later(table, alloc, [], earlier)
    assert {same_text["id"], same_notice["id"]} <= set(plain.lists["incontext_pool"])
    assert not set(plain.lists["incontext_pool"]) & set(earlier)
    assert plain.notes == dict.fromkeys(drawn.notes, 0)
    # a twin outside the frame is left out and not counted
    outside = [*table, record(20, split="fit", wording="next release may 2021", in_frame=False)]
    assert S.draw_later(outside, alloc, [], earlier, labelled=[labelled["id"]]).notes == drawn.notes


def test_later_draw_caps_and_seed_quotas() -> None:
    alloc = allocation()
    spec = S.LATER["pair_seeds"]
    assert S.PAIR_SEED_SHARE["month_year"] + S.PAIR_SEED_REST * (len(DATED) - 1) == spec.size
    table: list[dict] = []
    for stratum in DATED:
        rare = stratum == "relative"  # six later statements; its train-period ones are not seeds
        table += [
            record(len(table) + i, stratum, "test", split="late" if i % 2 else "test")
            if rare
            else record(len(table) + i, stratum, split="dev")
            for i in range(6 if rare else 60)
        ]
    table += [record(len(table) + i, "relative", split="dev", at_risk_B=False) for i in range(9)]
    table += [record(len(table) + i, "range", "test", split="test") for i in range(9)]
    by_id = {s["id"]: s for s in table}
    drawn = S.draw_later(table, alloc, [], [])
    seeds = drawn.lists["pair_seeds"]
    assert not set(seeds) & set(drawn.lists["dev_prompt"])
    assert {by_id[i]["period"] for i in seeds if by_id[i]["stratum"] == "relative"} == {"test"}
    assert {by_id[i]["period"] for i in seeds if by_id[i]["stratum"] != "relative"} == {"train"}
    got = Counter(by_id[i]["stratum"] for i in seeds)
    assert got["relative"] == 6  # all it has; month and year takes the seven that are missing
    assert got["month_year"] == S.PAIR_SEED_SHARE["month_year"] + S.PAIR_SEED_REST - got["relative"]
    assert all(got[st] == S.PAIR_SEED_REST for st in DATED if st not in ("relative", "month_year"))
    assert len(seeds) == spec.size
    same = [record(n, "month_year", split="fit", template="one wording") for n in range(9)]
    same += [record(20 + n, "range", split="fit", episode="one episode") for n in range(9)]
    drawn = S.draw_later(same, alloc, [], [])
    assert len(drawn.lists["incontext_pool"]) == 2  # one per template, one per episode
    assert len(drawn.lists["pair_seeds"]) == 1 + 3  # one more of the template, three of the episode


# --------------------------------------------------------------------------------------------
# Sheets, item files and keys
# --------------------------------------------------------------------------------------------


def sheet_inputs() -> tuple[pd.DataFrame, list[dict], str]:
    rows = [
        event(1, "Backordered. Next release April 2021.", "2020-03-02"),
        event(2, "On backorder.", "2020-03-02", related_text="  Check   wholesalers\nfor stock. "),
        event(
            3,
            "=SUM(A1) is not a formula",
            "2021-05-06",
            presentation="-10 mg",
            reason_for_shortage="",
        ),
        event(4, "Estimated recovery: Q4 2024.", "2023-05-06", initial_posting_date="about 2019"),
        event(
            5, "On backorder.", "2020-03-02", statement_group_id="S00001", presentation="20 mg vial"
        ),
    ]
    events = frame(rows)
    guide = guide_text()
    return events, S.statement_table(events, S.guide_allocation(guide)), guide


def test_sheets_show_the_entry_block_and_nothing_else() -> None:
    events, table, guide = sheet_inputs()
    built = S.build_sheets(
        "literal", ["S00001", "S00002", "S00003", "S00004"], events, table, guide
    )
    assert sorted(built.files) == ["literal_A1.csv", "literal_A2.csv", "literal_items.jsonl"]
    assert built.n_items == 4
    meta, rows = S.parse_sheet(built.files["literal_A1.csv"])
    assert dict(meta)["sheet"] == "literal" and dict(meta)["annotator"] == "A1"
    assert dict(meta)["guide"] == S.guide_stamp(guide) and dict(meta)["seed"] == "20261001"
    assert dict(meta)["items"] == "4"
    assert dict(meta)["sitting_start"] == dict(meta)["sitting_end"] == ""
    assert [k for k, _ in meta][-2:] == ["sitting_start", "sitting_end"]
    assert dict(meta)["values of certainty"] == "asserted | estimated | undetermined | no_statement"
    header = next(
        line
        for line in csv.reader(io.StringIO(built.files["literal_A1.csv"]))
        if line[0] == "item_id"
    )
    assert tuple(header) == S.SHEET_COLUMNS == (*S.SHOWN, *S.ENTERED)
    hidden = ("status", "capture", "outcome", "stratum", "sample", "event_id", "group", "thread")
    assert not [c for c in header if any(word in c for word in hidden)]
    assert "form" not in header and "period" not in header and "split" not in header
    assert all(row[c] == "" for row in rows for c in S.ENTERED)
    by_item = {row["item_id"]: row for row in rows}
    one = by_item[S.item_id("S00001")]
    shown = S.display_events(events).set_index("statement_group_id").loc["S00001"]
    assert one["presentation"] == shown["presentation"]
    assert one["initial_posting_date"] == "2019-01-15" and one["date_of_update"] == "2020-03-02"
    assert one["type_of_update"] == "Revised" and one["therapeutic_category"] == "Oncology"
    two = by_item[S.item_id("S00002")]
    assert two["related_information"] == "Check wholesalers for stock."
    three = by_item[S.item_id("S00003")]
    assert three["availability_information"] == "'=SUM(A1) is not a formula"
    assert three["presentation"] == "'-10 mg" and three["reason_for_shortage"] == S.BLANK
    assert three["related_information"] == S.BLANK
    assert by_item[S.item_id("S00004")]["initial_posting_date"] == "about 2019"
    text = built.files["literal_A1.csv"]
    assert "recovered" not in text and "2099-01-01" not in text and "current" not in text.lower()


def test_sheet_ids_and_orders() -> None:
    events, table, guide = sheet_inputs()
    ids = [f"S{n:05d}" for n in range(1, 5)]
    built = S.build_sheets("literal", ids, events, table, guide)
    orders = [
        [r["item_id"] for r in S.parse_sheet(built.files[f"literal_{a}.csv"])[1]]
        for a in S.ANNOTATORS
    ]
    assert sorted(orders[0]) == sorted(orders[1]) == sorted(S.item_id(i) for i in ids)
    assert orders[0] == S.shuffled(orders[0], "literal/order/A1")
    assert orders[1] == S.shuffled(orders[0], "literal/order/A2")
    assert S.item_id("S00001") == "I" + S.draw_key("item", "S00001")[:10]
    assert not any(i[1:] in shown for i in ids for shown in orders[0])
    again = S.build_sheets("literal", ids[::-1], events.iloc[::-1], table[::-1], guide)
    assert again.files == built.files and again.key == built.key


def test_item_file_is_what_the_harness_loads_and_renders(tmp_path: Path) -> None:
    events, table, guide = sheet_inputs()
    built = S.build_sheets("literal", [f"S{n:05d}" for n in range(1, 5)], events, table, guide)
    path = tmp_path / "literal_items.jsonl"
    path.write_text(built.files["literal_items.jsonl"], encoding="utf-8")
    raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert all(set(item) == {"item_id", *S.ITEM_FIELDS} for item in raw)
    assert [item["item_id"] for item in raw] == sorted(item["item_id"] for item in raw)
    items = {item.item_id: item for item in read.load_items(path)}
    rows = {r["item_id"]: r for r in S.parse_sheet(built.files["literal_A2.csv"])[1]}
    assert set(items) == set(rows)
    assert all(item.stated_end is None and item.form is None for item in items.values())
    quoted = ("availability_information", "related_information", "reason_for_shortage")
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
    assert tuple(labels) == S.SHOWN[1:]
    for item_id, item in items.items():
        cells = {c: S.unguarded(v) for c, v in rows[item_id].items()}
        lines = ["Entry"]
        for column, label in labels.items():
            cell = cells[column]
            if column in quoted and cell != S.BLANK:
                cell = f'"{cell}"'
            lines.append(f"- {label}: {cell}")
        prompt = read.render_prompt(read.TEMPLATES["literal-v1"], item)
        assert "\n".join(lines) in prompt
    assert read.ENTRY_BLOCK.count("\n- ") == len(labels)
    assert "Status" not in read.ENTRY_BLOCK


def test_key_links_items_to_statements_and_small_samples_are_train_only() -> None:
    events, table, guide = sheet_inputs()
    built = S.build_sheets("literal", ["S00001", "S00004"], events, table, guide)
    key = list(csv.DictReader(io.StringIO(built.key)))
    assert tuple(key[0]) == S.KEY_COLUMNS
    by_statement = {k["statement_group_id"]: k for k in key}
    assert by_statement["S00001"]["item_id"] == S.item_id("S00001")
    assert by_statement["S00001"] | {"event_id": ""} == {
        "item_id": S.item_id("S00001"),
        "statement_group_id": "S00001",
        "event_id": "",
        "thread_id": by_statement["S00001"]["thread_id"],
        "sample": "literal",
        "stratum": "month_year",
        "form": "month_year",
        "period": "train",
        "split": "fit",
        "n_presentations": "2",
    }
    assert (
        by_statement["S00004"]["period"] == "test"
        and by_statement["S00004"]["stratum"] == "quarter"
    )
    for task in S.TRAIN_ONLY:
        with pytest.raises(ValueError, match="dated 2023-01-01 or later"):
            S.build_sheets(task, ["S00001", "S00004"], events, table, guide)
        assert S.build_sheets(task, ["S00001", "S00002"], events, table, guide).n_items == 2
    with pytest.raises(ValueError, match="not in the events table"):
        S.build_sheets("pilot", ["S77777"], events, table, guide)


def test_guarded_cells() -> None:
    for text in ("=1+1", "+1", "-1", "@x"):
        assert S.guarded(text) == "'" + text and S.unguarded(S.guarded(text)) == text
    for text in ("", "plain", "'quoted'", "1-2", "'"):
        assert S.guarded(text) == text and S.unguarded(text) == text


def test_sheet_survives_a_spreadsheet() -> None:
    """A sheet saved by a spreadsheet: a byte-order mark, CRLF, minimal quoting, padded rows,
    comment lines spread over cells, an empty line; and a ``#`` inside an entry stays there."""
    rows = [
        SHOWN_ROW | GOOD | {"note": "see lot #4"},
        SHOWN_ROW | ABSTAIN | {"item_id": "I0000000002", "drug": "# not a comment"},
    ]
    meta = [
        ("sheet", "pilot"),
        ("annotator", "A1"),
        ("sitting_start", "9:00"),
        ("sitting_end", "9:30"),
    ]
    ours = S.sheet_text(S.SHEET_COLUMNS, rows, meta)
    assert all(line.startswith('"') and line.endswith('"') for line in ours.splitlines())
    table = list(csv.reader(io.StringIO(ours)))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    for line in table:
        if line[0].startswith("# sitting"):
            key, _, value = line[0].partition(":")
            line = [key + ":", value.strip()]
        writer.writerow([*line, *([""] * (len(S.SHEET_COLUMNS) + 2 - len(line)))])
        if line[0] == "item_id":
            writer.writerow([])
    theirs = chr(0xFEFF) + buf.getvalue()
    assert S.parse_sheet(theirs) == S.parse_sheet(ours)
    parsed_meta, parsed = S.parse_sheet(theirs)
    assert parsed_meta == meta
    assert [r["item_id"] for r in parsed] == ["I0000000001", "I0000000002"]
    assert parsed[0]["note"] == "see lot #4" and parsed[1]["drug"] == "# not a comment"
    checked = S.validate_sheet(parsed_meta, parsed, S.parse_sheet(ours)[1])
    assert checked.ok and checked.minutes == 30 and len(checked.labels) == 2


# --------------------------------------------------------------------------------------------
# Labels and the checks of the guide's section 3.12
# --------------------------------------------------------------------------------------------


def label_of(**changes: str) -> tuple[S.Label | None, list[str], list[str]]:
    return S.read_label(SHOWN_ROW | GOOD | changes)


def test_a_good_row_is_read() -> None:
    label, errors, warnings = label_of(quote="Next release April 2020", hard="1", note="why")
    assert errors == [] and warnings == []
    assert label is not None
    assert (label.start, label.end) == (date(2020, 4, 1), date(2020, 4, 30))
    assert label.interval == (date(2020, 4, 1), date(2020, 4, 30))
    assert label.anchor == date(2020, 3, 2) and not label.abstain and label.hard
    assert not label.stale
    assert label.offsets() == {
        "start_offset_m": 1,
        "start_offset_d": 30,
        "end_offset_m": 1,
        "end_offset_d": 59,
    }
    assert label.entered() == GOOD | {
        "quote": "Next release April 2020",
        "hard": "1",
        "note": "why",
    }
    one_day, errors, _ = label_of(start="2020-10-01", end="2020-10-01")
    assert errors == [] and one_day is not None and one_day.start == one_day.end
    abstaining, errors, _ = S.read_label(SHOWN_ROW | ABSTAIN)
    assert errors == [] and abstaining is not None
    assert abstaining.abstain and abstaining.interval is None and not abstaining.stale
    assert set(abstaining.offsets().values()) == {None}
    assert abstaining.entered() == ABSTAIN


def test_month_shorthand_and_calendar() -> None:
    label, errors, _ = label_of(start="2020-02", end="2020-02")
    assert errors == [] and label is not None
    assert (label.start, label.end) == (date(2020, 2, 1), date(2020, 2, 29))
    assert label.entered()["start"] == "2020-02-01" and label.entered()["end"] == "2020-02-29"
    assert S.parse_day("2021-02", end=True) == date(2021, 2, 28)
    assert S.parse_day("2021-12", end=True) == date(2021, 12, 31)
    assert S.parse_day("2021-12", end=False) == date(2021, 12, 1)
    assert S.month_end(2024, 2) == date(2024, 2, 29)
    for bad, why in (
        ("2020-02-30", "not a calendar date"),
        ("2020-13", "not a calendar month"),
        ("2020-00", "not a calendar month"),
        ("04/2020", "is not YYYY-MM-DD or YYYY-MM"),
        ("April 2020", "is not YYYY-MM-DD or YYYY-MM"),
        ("2020-4-1", "is not YYYY-MM-DD or YYYY-MM"),
    ):
        with pytest.raises(ValueError, match=why):
            S.parse_day(bad, end=False)


def test_month_offsets_are_calendar_months() -> None:
    anchor = date(2021, 11, 17)
    assert S.month_offset(date(2021, 10, 1), anchor) == -1
    assert S.month_offset(date(2022, 3, 31), anchor) == 4
    assert S.month_offset(date(2021, 11, 30), anchor) == 0
    assert S.month_offset(date(2019, 11, 1), date(2021, 9, 23)) == -22


def test_stale_is_an_end_before_the_anchor() -> None:
    stale, errors, _ = label_of(start="2020-02", end="2020-03-01")
    assert errors == [] and stale is not None and stale.stale
    same_day, _, _ = label_of(start="2020-02", end="2020-03-02")
    assert same_day is not None and not same_day.stale


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"abstain": "1"}, "abstain is 1 but a date is given"),
        ({"start": ""}, "abstain is 0 but start or end is missing"),
        ({"end": ""}, "abstain is 0 but start or end is missing"),
        ({"start": "", "end": ""}, "abstain is 0 but start or end is missing"),
        ({"start": "2020-05-01"}, "start is after end"),
        ({"end": "2020-04-31"}, "end: 2020-04-31 is not a calendar date"),
        ({"start": "4/1/2020"}, "start: '4/1/2020' is not YYYY-MM-DD or YYYY-MM"),
        ({"statement_type": "none"}, "statement_type none and certainty no_statement go together"),
        (
            {"certainty": "no_statement"},
            "statement_type none and certainty no_statement go together",
        ),
        (
            {"statement_type": "none", "certainty": "no_statement"},
            "statement_type is none but the row does not abstain",
        ),
        ({"certainty": "undetermined"}, "certainty is undetermined but an interval is given"),
        ({"abstain_reason": "tbd"}, "abstain_reason is given but the row does not abstain"),
        ({"distractor_roles": "expiry"}, "1 distractor roles but 0 distractor quotes"),
        (
            {"distractor_roles": "expiry", "distractor_quotes": "(1/2022 expiry); dating"},
            "1 distractor roles but 2 distractor quotes",
        ),
        ({"hard": "1"}, "hard is 1 but note is empty"),
        ({"statement_type": "delivery"}, "statement_type 'delivery' is not one of"),
        ({"statement_type": ""}, "statement_type is missing"),
        ({"abstain": "yes"}, "abstain 'yes' is not one of 0, 1"),
        ({"abstain": ""}, "abstain is missing"),
        ({"certainty": "firm"}, "certainty 'firm' is not one of"),
        ({"certainty": ""}, "certainty is missing"),
        ({"hard": "x"}, "hard 'x' is not one of 0, 1"),
        ({"distractor_roles": "expiry; typo"}, "distractor role 'typo' is not one of"),
        ({"date_of_update": "03/02/2020"}, "date_of_update '03/02/2020' is not an ISO date"),
    ],
)
def test_a_wrong_row_is_rejected(changes: dict[str, str], error: str) -> None:
    label, errors, _ = label_of(**changes)
    assert label is None
    assert any(error in e for e in errors), errors


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"abstain_reason": ""}, "abstain_reason is missing"),
        ({"abstain_reason": "unknown"}, "abstain_reason 'unknown' is not one of"),
        ({"certainty": "estimated"}, "abstain_reason tbd needs certainty undetermined"),
        ({"abstain_reason": "no_date", "certainty": "estimated"}, "abstain_reason no_date needs"),
        ({"abstain_reason": "vague"}, "abstain_reason vague needs certainty estimated"),
        (
            {"abstain_reason": "no_statement"},
            "abstain_reason no_statement needs certainty no_statement",
        ),
        (
            {"abstain_reason": "no_statement", "certainty": "no_statement"},
            "statement_type none and certainty no_statement go together",
        ),
        ({"statement_type": "none"}, "statement_type none and certainty no_statement go together"),
        ({"start": "2020-04"}, "abstain is 1 but a date is given"),
    ],
)
def test_a_wrong_abstention_is_rejected(changes: dict[str, str], error: str) -> None:
    label, errors, _ = S.read_label(SHOWN_ROW | ABSTAIN | changes)
    assert label is None
    assert any(error in e for e in errors), errors


@pytest.mark.parametrize(
    "changes",
    [
        {"abstain_reason": "no_date"},
        {"abstain_reason": "vague", "certainty": "estimated"},
        {"statement_type": "none", "abstain_reason": "no_statement", "certainty": "no_statement"},
        {"statement_type": "next_delivery"},
        {"hard": "", "note": "a note without the flag"},
        {"distractor_roles": "Expiry", "distractor_quotes": "(1/2022 expiry)"},
    ],
)
def test_every_kind_of_abstention_is_accepted(changes: dict[str, str]) -> None:
    label, errors, _ = S.read_label(SHOWN_ROW | ABSTAIN | changes)
    assert errors == [] and label is not None and label.abstain


def test_an_empty_row_is_reported_as_not_filled() -> None:
    blank = dict.fromkeys(S.ENTERED, "")
    assert S.read_label(SHOWN_ROW | blank) == (None, ["the row is not filled"], [])


def test_distractor_lists() -> None:
    label, errors, warnings = label_of(
        distractor_roles="expiry; other",
        distractor_quotes="(1/2022 expiry); 5 month expiry",
    )
    assert errors == [] and warnings == [] and label is not None
    assert label.distractor_roles == ("expiry", "other")
    assert label.distractor_quotes == ("(1/2022 expiry)", "5 month expiry")
    assert label.entered()["distractor_roles"] == "expiry; other"
    assert label.entered()["distractor_quotes"] == "(1/2022 expiry) | 5 month expiry"
    assert S.split_list("lots due; then more | (1/2022 expiry)") == [
        "lots due; then more",
        "(1/2022 expiry)",
    ]
    assert S.split_list("a; b;; c ;") == ["a", "b", "c"]
    assert S.split_list("") == []
    # the bar typed with the backslash that the guide's table source shows before it
    assert S.split_list("lots due; then more \\| (1/2022 expiry)") == [
        "lots due; then more",
        "(1/2022 expiry)",
    ]


def test_warnings_do_not_reject_a_row() -> None:
    label, errors, warnings = label_of(quote="Next release May 2020")
    assert label is not None and errors == []
    assert warnings == ["quote 'Next release May 2020' is not in the entry"]
    label, errors, warnings = label_of(start="2025-04", end="2025-04", quote="next  RELEASE april")
    assert label is not None and errors == []
    assert warnings == [
        "start is more than 60 months from the Date of update",
        "end is more than 60 months from the Date of update",
    ]
    _, _, warnings = label_of(start="2025-03-01", end="2025-03-31")
    assert warnings == []  # 60 months exactly
    _, _, warnings = label_of(distractor_roles="expiry", distractor_quotes="expiry 2022")
    assert warnings == ["distractor quote 'expiry 2022' is not in the entry"]


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("09:05", 545), ("9:05", 545), ("14:30:59", 870), ("2:30 pm", 870), ("12:10 AM", 10)],
)
def test_clock_times(text: str, minutes: int) -> None:
    assert S.clock(text) == minutes


@pytest.mark.parametrize("text", ["", "9", "9.30", "24:00", "10:60", "half past nine"])
def test_clock_rejects(text: str) -> None:
    assert S.clock(text) is None


def test_sitting_times_in_the_header() -> None:
    one = [("sitting_start", "09:00"), ("sitting_end", "09:20")]
    assert S.sittings(one) == (20, [])
    two = [*one, ("sitting_start", "14:00"), ("sitting_end", "14:45")]
    assert S.sittings(two) == (65, [])
    assert S.sittings([("sitting_start", ""), ("sitting_end", "")])[0] is None
    assert "give one sitting_start" in S.sittings([("sitting_start", "09:00")])[1][0]
    assert "not after" in S.sittings([("sitting_start", "10:00"), ("sitting_end", "09:00")])[1][0]
    minutes, errors = S.sittings([("sitting_start", "nine"), ("sitting_end", "09:20")])
    assert minutes is None and errors == ["header: sitting_start 'nine' is not a time (HH:MM)"]


def sheet_of(rows: list[dict[str, str]], times: tuple[str, str] = ("09:00", "09:20")) -> S.Checked:
    meta = [("sitting_start", times[0]), ("sitting_end", times[1])]
    blank = [SHOWN_ROW | {"item_id": f"I000000000{n}"} for n in (1, 2, 3)]
    return S.validate_sheet(meta, rows, blank)


def test_a_filled_sheet_passes_and_errors_come_by_row() -> None:
    rows = [SHOWN_ROW | GOOD | {"item_id": f"I000000000{n}"} for n in (1, 2, 3)]
    good = sheet_of(rows)
    assert good.ok and good.minutes == 20 and sorted(good.labels) == [r["item_id"] for r in rows]
    rows[1] = rows[1] | {"start": "2020-05-01"}
    rows[2] = rows[2] | {"certainty": "", "hard": "1"}
    bad = sheet_of(rows)
    assert bad.errors == [
        "row 2 (I0000000002): start is after end",
        "row 3 (I0000000003): certainty is missing",
    ]
    assert sorted(bad.labels) == ["I0000000001"] and not bad.ok
    rows[2] = rows[2] | {"certainty": "asserted"}
    assert sheet_of(rows).errors == [
        "row 2 (I0000000002): start is after end",
        "row 3 (I0000000003): hard is 1 but note is empty",
    ]


def test_the_sheet_as_a_whole_is_checked_against_its_blank() -> None:
    rows = [SHOWN_ROW | GOOD | {"item_id": f"I000000000{n}"} for n in (1, 2, 3)]
    assert sheet_of(rows[:2]).errors == ["sheet: item I0000000003 of the blank sheet is missing"]
    added = [*rows, SHOWN_ROW | GOOD | {"item_id": "I0000000009"}]
    assert sheet_of(added).errors == ["row 4 (I0000000009): this item is not in the blank sheet"]
    twice = sheet_of([*rows, rows[0]])
    assert twice.errors == [
        "row 1 (I0000000001): item_id is missing or repeated",
        "row 4 (I0000000001): item_id is missing or repeated",
    ]
    changed = [rows[0] | {"date_of_update": "2020-03-03", "drug": "Other"}, *rows[1:]]
    assert sheet_of(changed).errors == [
        "row 1 (I0000000001): shown cells changed (drug, date_of_update); "
        "import every column as text and do not edit shown cells"
    ]
    assert sheet_of(rows, times=("", "")).errors == [
        "header: give one sitting_start and one sitting_end (HH:MM) for each sitting"
    ]
    assert sheet_of([]).errors == ["sheet: the sheet has no rows"]
    short = [{k: v for k, v in r.items() if k != "certainty"} for r in rows]
    assert sheet_of(short).errors == ["sheet: columns missing: certainty"]
    unfilled = [rows[0], SHOWN_ROW | {"item_id": "I0000000002"}, rows[2]]
    assert sheet_of(unfilled).errors == ["row 2 (I0000000002): the row is not filled"]
    without_blank = S.validate_sheet([("sitting_start", "9:00"), ("sitting_end", "9:10")], added)
    assert without_blank.ok and len(without_blank.labels) == 4


def test_a_guard_lost_or_kept_by_the_spreadsheet_is_not_a_change() -> None:
    shown = SHOWN_ROW | {"presentation": "'-10 mg"}
    meta = [("sitting_start", "09:00"), ("sitting_end", "09:20")]
    for cell in ("'-10 mg", "-10 mg"):
        checked = S.validate_sheet(meta, [shown | GOOD | {"presentation": cell}], [shown])
        assert checked.ok, checked.errors
    checked = S.validate_sheet(meta, [shown | GOOD | {"presentation": "10 mg"}], [shown])
    assert "shown cells changed (presentation)" in checked.errors[0]


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


def test_made_up_corpus_has_the_forms_it_claims() -> None:
    alloc = allocation()
    table = S.statement_table(small_corpus(), alloc)
    assert len(table) == 12 * len(NAMES)
    assert Counter(s["stratum"] for s in table) == dict.fromkeys(NAMES, 12)
    assert Counter(s["period"] for s in table) == {"train": 8 * len(NAMES), "test": 4 * len(NAMES)}
    assert Counter(s["split"] for s in table)["dev"] == 4 * len(NAMES)
    assert len({s["template"] for s in table}) == len(table)
    assert not any(s["stale"] for s in table)


def test_draw_command_writes_lists_sheets_and_manifest(tmp_path: Path, capsys: Any) -> None:
    out, _ = drawn_folder(tmp_path)
    printed = capsys.readouterr().out
    assert "pilot: 12 statements, sha256 " in printed and "literal: 36 statements" in printed
    assert "appendix_a_rows: 0" in printed
    assert "warning: pilot has" not in printed and "the guide's table" not in printed
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == S.SEED
    samples = manifest["samples"]
    assert {k: samples[k]["n"] for k in S.FIRST_SAMPLES} == {
        "pilot": 12,
        "check": 7,
        "reserve": 7,
        "literal": 36,
    }
    assert samples["caps"] == {"per_template": 2, "per_episode": 3} and samples["fixed"] == []
    assert samples["inputs"]["guide"].startswith("v9 test sha256 ")
    assert samples["inputs"]["rules_sha256"] == F.RULES_SHA256[:16]
    assert samples["inputs"]["events_fields_sha256"] == S.events_fields_sha256(small_corpus())
    seen: set[str] = set()
    for name in S.FIRST_SAMPLES:
        path = out / samples[name]["file"]
        assert path == out / "samples" / f"sample_{name}.csv"
        assert sha(path) == samples[name]["sha256"]
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        assert tuple(rows[0]) == S.SAMPLE_COLUMNS  # ids only: no stratum, no form, no outcome
        ids = [r["statement_group_id"] for r in rows]
        assert ids == sorted(ids) == S.read_list(path)
        assert samples[name]["statements_sha256"] == S.ids_sha256(ids)
        assert (
            samples[name]["statements_sha256"]
            == hashlib.sha256("".join(f"{i}\n" for i in ids).encode()).hexdigest()
        )
        assert not seen & set(ids)
        seen |= set(ids)
    assert sha(out / "samples" / "strata.csv") == samples["strata"]["sha256"]
    strata = list(csv.DictReader((out / "samples" / "strata.csv").open(encoding="utf-8")))
    assert tuple(strata[0]) == S.STRATA_COLUMNS
    for task in S.FIRST_SAMPLES:
        entry = manifest["sheets"][task]
        assert entry["items"] == samples[task]["n"]
        assert sorted(entry["files"]) == [f"{task}_A1.csv", f"{task}_A2.csv", f"{task}_items.jsonl"]
        assert all(sha(out / name) == digest for name, digest in entry["files"].items())
        assert sha(out / "keys" / f"{task}_key.csv") == entry["key_sha256"]
        key = list(csv.DictReader((out / "keys" / f"{task}_key.csv").open(encoding="utf-8")))
        assert sorted(k["statement_group_id"] for k in key) == S.read_list(
            out / "samples" / f"sample_{task}.csv"
        )
        if task in S.TRAIN_ONLY:
            assert {k["period"] for k in key} == {"train"}
    literal = list(csv.DictReader((out / "keys" / "literal_key.csv").open(encoding="utf-8")))
    assert Counter(k["period"] for k in literal) == {"train": 24, "test": 12}


def test_draw_command_is_deterministic(tmp_path: Path) -> None:
    one, _ = drawn_folder(tmp_path, "one")
    two, _ = drawn_folder(tmp_path, "two")
    names = sorted(p.relative_to(one).as_posix() for p in one.rglob("*") if p.is_file())
    assert names == sorted(p.relative_to(two).as_posix() for p in two.rglob("*") if p.is_file())
    assert len(names) == 1 + 5 + 4 * 3 + 4
    for name in names:
        if name == "manifest.json":
            continue
        assert (one / name).read_bytes() == (two / name).read_bytes(), name
    first = json.loads((one / "manifest.json").read_text(encoding="utf-8"))
    second = json.loads((two / "manifest.json").read_text(encoding="utf-8"))
    assert first == second


def test_appendix_a_and_a_kept_pilot(tmp_path: Path) -> None:
    out, inputs = drawn_folder(tmp_path)
    pilot = S.read_list(out / "samples" / "sample_pilot.csv")
    events = small_corpus().set_index("statement_group_id")
    named = events.loc[pilot[0]]
    appendix = "\n".join(
        [
            "| Generic | Company | Statement date |",
            "|---|---|---|",
            f"| {named['generic_name']} | {named['company_name']} | {named['event_date']} |",
            "| Unknown Drug | Nobody | 2020-01-01 |",
        ]
    )
    guide = Path(inputs[3])
    guide.write_text(guide_text(**SMALL, appendix=appendix), encoding="utf-8")
    kept = tmp_path / "kept"
    (kept / "samples").mkdir(parents=True)
    (kept / "samples" / "sample_pilot.csv").write_bytes(
        (out / "samples" / "sample_pilot.csv").read_bytes()
    )
    assert S.main(["draw", *inputs[:4], "--out", str(kept), "--fixed", "pilot", UNMATCHED]) == 0
    manifest = json.loads((kept / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["samples"]["fixed"] == ["pilot"]
    assert manifest["samples"]["exclusions"] == {
        "appendix_a_rows": 2,
        "appendix_a_rows_matching_no_event": 1,
        "fixed_test_item_statements": 0,
        "fixed_test_item_in_appendix_a": False,
        "excluded_statements": 1,
        "guide_phrases": 0,
        "statements_equal_to_a_guide_phrase": 0,
        "excluded_statements_with_guide_phrases": 1,
    }
    assert S.read_list(kept / "samples" / "sample_pilot.csv") == pilot
    for name in ("check", "reserve", "literal"):
        assert pilot[0] not in S.read_list(kept / "samples" / f"sample_{name}.csv")
    with pytest.raises(SystemExit, match="the exclusions are incomplete"):
        S.main(["draw", *inputs[:4], "--out", str(tmp_path / "stopped"), "--fixed", "pilot"])
    fresh = tmp_path / "fresh"
    assert S.main(["draw", *inputs[:4], "--out", str(fresh), UNMATCHED]) == 0
    redrawn = S.read_list(fresh / "samples" / "sample_pilot.csv")
    assert pilot[0] not in redrawn and len(redrawn) == len(pilot)
    assert not list(fresh.glob("*.csv"))  # no --sheets: no sheet is written


def test_sheets_command_needs_the_recorded_list(tmp_path: Path) -> None:
    out, inputs = drawn_folder(tmp_path)
    before = (out / "check_A1.csv").read_text(encoding="utf-8")
    guide = Path(inputs[3])
    guide.write_text(
        guide.read_text(encoding="utf-8").replace("v9 test", "v10 test"), encoding="utf-8"
    )
    assert S.main(["sheets", "--task", "check", *inputs]) == 0
    after = (out / "check_A1.csv").read_text(encoding="utf-8")
    assert after != before and "# guide: v10 test sha256" in after
    assert S.parse_sheet(after)[1] == S.parse_sheet(before)[1]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sheets"]["check"]["guide"].startswith("v10 test")
    assert manifest["sheets"]["pilot"]["guide"].startswith("v9 test")  # left as it was
    assert sha(out / "check_A1.csv") == manifest["sheets"]["check"]["files"]["check_A1.csv"]
    events = Path(inputs[1])
    table = events.read_text(encoding="utf-8")
    events.write_text(table.replace(",limited,", ",available,", 1), encoding="utf-8")
    with pytest.raises(SystemExit, match="not the one the samples were drawn on"):
        S.main(["sheets", "--task", "check", *inputs])
    events.write_text(table.replace(",recovered,", ",discontinued,"), encoding="utf-8")
    assert S.main(["sheets", "--task", "check", *inputs]) == 0  # a field the sampler never reads
    assert (out / "check_A1.csv").read_text(encoding="utf-8") == after
    events.write_text(table, encoding="utf-8")
    path = out / "samples" / "sample_check.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("\n", "\n\n", 1), encoding="utf-8")
    with pytest.raises(SystemExit, match="is not the list the manifest records"):
        S.main(["sheets", "--task", "check", *inputs])
    path.unlink()
    with pytest.raises(SystemExit, match="run the draw command first"):
        S.main(["sheets", "--task", "check", *inputs])


def test_validate_command(tmp_path: Path, capsys: Any) -> None:
    out, _ = drawn_folder(tmp_path)
    blank = (out / "pilot_A1.csv").read_text(encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    good = work / "pilot_A1.csv"
    good.write_text(fill(blank), encoding="utf-8")
    capsys.readouterr()
    assert S.main(["validate", str(good), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "12 rows, 12 valid, 0 errors, 0 warnings; sittings: 20 minutes" in printed
    unfilled = work / "unfilled.csv"
    unfilled.write_text(blank, encoding="utf-8")
    assert S.main(["validate", str(unfilled), "--out", str(out)]) == 1
    printed = capsys.readouterr().out
    assert printed.count("the row is not filled") == 12 and "error: header: give one" in printed
    meta, rows = S.parse_sheet(fill(blank))
    short = work / "short.csv"
    short.write_text(S.sheet_text(S.SHEET_COLUMNS, rows[1:], meta), encoding="utf-8")
    assert S.main(["validate", str(short), "--out", str(out)]) == 1
    assert "of the blank sheet is missing" in capsys.readouterr().out
    # the blank is found by the sheet's own header; elsewhere there is none, and that is said
    assert S.main(["validate", str(short), "--out", str(tmp_path / "elsewhere")]) == 0
    assert "warning: sheet: no blank sheet to compare with" in capsys.readouterr().out
    elsewhere = ["--out", str(tmp_path / "elsewhere"), "--blank", str(unfilled)]
    assert S.main(["validate", str(short), *elsewhere]) == 1
    assert "of the blank sheet is missing" in capsys.readouterr().out
    in_place = out / "pilot_A1.csv"
    in_place.write_text(fill(blank), encoding="utf-8")
    assert S.main(["validate", str(in_place), "--out", str(out)]) == 0
    assert "no blank sheet to compare with" in capsys.readouterr().out


def test_later_draw_command(tmp_path: Path, capsys: Any) -> None:
    out, inputs = drawn_folder(tmp_path, train=16)
    with pytest.raises(SystemExit, match="run the draw command first"):
        S.main(
            ["draw-later", *inputs[:4], "--out", str(tmp_path / "empty"), "--outcome-sample", "x"]
        )
    first = {name: S.read_list(out / "samples" / f"sample_{name}.csv") for name in S.FIRST_SAMPLES}
    taken = {i for ids in first.values() for i in ids}
    events = small_corpus(16)
    free = events[~events["statement_group_id"].isin(taken) & (events["event_date"] < "2023")]
    audited = free.head(6)
    sample = tmp_path / "audit" / "outcome_train_sample.csv"
    sample.parent.mkdir()
    audited[list(S.SAMPLE_COLUMNS)].to_csv(sample, index=False)
    status = sample.with_name("outcome_train_manifest.json")
    status.write_text(json.dumps({"status": "draft"}), encoding="utf-8")
    later = ["draw-later", *inputs, UNMATCHED, "--outcome-sample", str(sample)]
    with pytest.raises(SystemExit, match="is a draft draw"):
        S.main(later)
    assert S.main([*later, "--draft"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["samples_later"]["status"] == "draft"
    status.write_text(json.dumps({"status": "final"}), encoding="utf-8")
    capsys.readouterr()
    assert S.main(later) == 0
    assert "pair_seeds: " in capsys.readouterr().out
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["samples_later"]
    assert entry["status"] == "final"
    assert entry["inputs"]["outcome_sample_sha256"] == sha(sample)
    assert "samples" in manifest and "sheets" in manifest  # the other sections are kept
    barred = taken | set(audited["statement_group_id"])
    seen: set[str] = set()
    for name in S.LATER:
        path = out / entry[name]["file"]
        assert path == out / "samples_later" / f"sample_{name}.csv"
        assert sha(path) == entry[name]["sha256"]
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        assert tuple(rows[0]) == S.LATER_COLUMNS
        ids = [r["statement_group_id"] for r in rows]
        assert ids == sorted(ids) and not set(ids) & barred and not set(ids) & seen
        assert sorted(int(r["draw_rank"]) for r in rows) == list(range(1, len(rows) + 1))
        seen |= set(ids)
    dates = events.set_index("statement_group_id")["event_date"]
    for name in S.LATER:
        for row in csv.DictReader((out / entry[name]["file"]).open(encoding="utf-8")):
            later = dates[row["statement_group_id"]] >= "2023-01-01"
            assert row["period"] == ("test" if later else "train")
    seeds = list(csv.DictReader((out / entry["pair_seeds"]["file"]).open(encoding="utf-8")))
    forms = events.set_index("statement_group_id")["statement_text"].map(
        lambda text: text.startswith("Estimated shortage duration")
    )
    relative = [r for r in seeds if forms[r["statement_group_id"]]]
    assert relative and {r["period"] for r in relative} == {"test"}
    assert {r["period"] for r in seeds if not forms[r["statement_group_id"]]} == {"train"}
    assert entry["exclusions"]["guide_phrases"] == 0
    pool = S.read_list(out / "samples_later" / "sample_incontext_pool.csv")
    assert pool and all(dates[i] < "2021-01-01" for i in pool)
    dev = S.read_list(out / "samples_later" / "sample_dev_prompt.csv")
    assert dev and all("2021-01-01" <= dates[i] < "2023-01-01" for i in dev)
    assert not list((out / "samples").glob("*incontext*"))
    overlap = tmp_path / "audit" / "overlap_sample.csv"
    events[events["statement_group_id"].isin(first["pilot"])][list(S.SAMPLE_COLUMNS)].to_csv(
        overlap, index=False
    )
    with pytest.raises(SystemExit, match="holds statements of the first draw"):
        S.main(["draw-later", *inputs, "--outcome-sample", str(overlap)])


def test_draw_command_leaves_out_statements_equal_to_a_guide_phrase(
    tmp_path: Path, capsys: Any
) -> None:
    """Thirty silent statements of other drugs say only what the guide quotes: a draw under a
    guide without the quote can take them, a draw under the guide with it cannot."""
    wording = "Check wholesalers for inventory"
    twins = [event(9000 + n, f"{wording}.", TRAIN_DAYS[n % 4]) for n in range(30)]
    twins += [event(9100 + n, wording.upper(), TEST_DAYS[n % 2]) for n in range(5)]
    events = pd.concat([small_corpus(), frame(twins)], ignore_index=True)
    equal = {row["statement_group_id"] for row in twins}
    quoting = guide_text(**SMALL, section=QUOTING)
    silent = {"pilot": {"silent": 2}, "literal": {"silent": 6}}
    drawn: dict[str, set[str]] = {}
    for name, guide in (
        ("without", guide_text(**silent)),
        ("with", guide_text(**silent, section=QUOTING)),
    ):
        guide_path, events_path = write_inputs(tmp_path / name, guide, events)
        out = tmp_path / name / "out"
        inputs = ["--events", str(events_path), "--guide", str(guide_path), "--out", str(out)]
        capsys.readouterr()
        assert S.main(["draw", *inputs, UNMATCHED]) == 0
        drawn[name] = {
            i for s in S.FIRST_SAMPLES for i in S.read_list(out / "samples" / f"sample_{s}.csv")
        }
    printed = capsys.readouterr().out
    assert drawn["without"] & equal and not drawn["with"] & equal
    assert len(drawn["with"]) == len(drawn["without"]) == 8
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    notes = manifest["samples"]["exclusions"]
    assert notes["guide_phrases"] == len(S.guide_phrases(quoting)) == 13
    assert notes["statements_equal_to_a_guide_phrase"] == 35
    assert notes["excluded_statements"] == 0
    assert notes["excluded_statements_with_guide_phrases"] == 35
    rule = {(r["stratum"], r["period"]): r for r in manifest["samples"]["phrase_rule"]}
    assert rule["silent", "train"] == {
        "stratum": "silent",
        "period": "train",
        "frame": 38,
        "appendix_a": 0,
        "equal_to_a_phrase": 30,
        "removed": 30,
    }
    assert rule["silent", "test"]["removed"] == 5 and rule["tbd", "train"]["removed"] == 0
    assert len(rule) == 2 * len(NAMES)
    assert "guide phrases: frame statements whose whole text equals one (2 cells)" in printed
    assert "statements_equal_to_a_guide_phrase: 35" in printed
    # the later draw leaves them out as well
    sample = tmp_path / "audit" / "outcome_train_sample.csv"
    sample.parent.mkdir()
    sample.write_text(",".join(S.SAMPLE_COLUMNS) + "\n", encoding="utf-8")
    assert S.main(["draw-later", *inputs, UNMATCHED, "--outcome-sample", str(sample)]) == 0
    later = {
        i for name in S.LATER for i in S.read_list(out / "samples_later" / f"sample_{name}.csv")
    }
    assert later and not later & equal
    entry = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["samples_later"]
    assert entry["exclusions"]["statements_equal_to_a_guide_phrase"] == 35


def test_draw_command_counts_the_items_that_contain_a_guide_phrase(
    tmp_path: Path, capsys: Any
) -> None:
    """The made-up vague statements hold a phrase the guide quotes among other words: they are
    drawn, and the draw says how many items of each sample contain a quoted phrase."""
    guide, events = write_inputs(tmp_path, guide_text(**SMALL, section=QUOTING), small_corpus())
    out = tmp_path / "out"
    inputs = ["--events", str(events), "--guide", str(guide), "--out", str(out)]
    assert S.main(["draw", *inputs, UNMATCHED]) == 0
    printed = capsys.readouterr().out
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["samples"]["exclusions"]["statements_equal_to_a_guide_phrase"] == 0
    assert manifest["samples"]["items_containing_a_guide_phrase"] == {
        "pilot": 1,
        "check": 0,
        "reserve": 0,
        "literal": 3,
    }
    assert "pilot: 1 of its items contain a phrase the guide quotes" in printed
    assert "literal: 3 of its items contain a phrase the guide quotes" in printed
    # a draw that keeps every list counts the same items
    assert S.main(["draw", *inputs, UNMATCHED, "--fixed", *S.FIRST_SAMPLES]) == 0
    again = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["samples"]
    assert (
        again["items_containing_a_guide_phrase"]
        == (manifest["samples"]["items_containing_a_guide_phrase"])
    )


def test_later_draw_command_leaves_out_what_reads_like_a_labelled_item(
    tmp_path: Path, capsys: Any
) -> None:
    """After the first draw, the events table gains three statements: the text of a labelled
    item on another drug, the item's notice in another spelling on another presentation, and the
    text of a statement of the outcome-audit sample, which nobody labels. Only the last can be
    on a later list."""
    out, inputs = drawn_folder(tmp_path, train=16)
    events = small_corpus(16)
    first = {
        i for name in S.FIRST_SAMPLES for i in S.read_list(out / "samples" / f"sample_{name}.csv")
    }
    early = events[
        events["statement_text"].str.startswith("Backordered. Next release")
        & (events["event_date"] < "2021-01-01")
    ]
    item = early[early["statement_group_id"].isin(first)].iloc[0]
    spare = early[~early["statement_group_id"].isin(first)].iloc[0]
    same_drug = {"generic_id": item["generic_id"], "generic_name": item["generic_name"]}
    twins = [
        event(9001, item["statement_text"], "2019-06-01"),
        event(9002, item["statement_text"].replace("Ask", "Aks"), item["event_date"], **same_drug),
        event(9003, spare["statement_text"], "2019-06-01"),
    ]
    grown = tmp_path / "grown.csv"
    pd.concat([events, frame(twins)], ignore_index=True).to_csv(grown, index=False)
    sample = tmp_path / "audit" / "outcome_train_sample.csv"
    sample.parent.mkdir()
    audited = ",".join(spare[c] for c in S.SAMPLE_COLUMNS)
    sample.write_text(",".join(S.SAMPLE_COLUMNS) + f"\n{audited}\n", encoding="utf-8")
    capsys.readouterr()
    later = ["draw-later", "--events", str(grown), *inputs[2:], UNMATCHED]
    assert S.main([*later, "--outcome-sample", str(sample)]) == 0
    printed = capsys.readouterr().out
    drawn = {
        i for name in S.LATER for i in S.read_list(out / "samples_later" / f"sample_{name}.csv")
    }
    assert "S09003" in drawn and not drawn & {"S09001", "S09002"} and not drawn & first
    assert spare["statement_group_id"] not in drawn
    notes = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["samples_later"]
    assert notes["exclusions"]["frame_statements_left_out_same_wording"] == 1
    assert notes["exclusions"]["frame_statements_left_out_same_notice"] == 1
    assert "frame_statements_left_out_same_wording: 1" in printed


def test_later_draw_does_not_replace_a_list_on_disk_unasked(tmp_path: Path) -> None:
    """A repeated later draw writes the same bytes. When the outcome-audit sample has changed so
    that a list would hold other statements, the command stops and writes nothing; ``--replace``
    takes the new lists."""
    out, inputs = drawn_folder(tmp_path, train=16)
    sample = tmp_path / "audit" / "outcome_train_sample.csv"
    sample.parent.mkdir()
    sample.write_text(",".join(S.SAMPLE_COLUMNS) + "\n", encoding="utf-8")
    later = ["draw-later", *inputs, UNMATCHED, "--outcome-sample", str(sample)]
    assert S.main(later) == 0
    files = [*sorted((out / "samples_later").glob("*.csv")), out / "manifest.json"]
    before = {path: path.read_bytes() for path in files}
    assert S.main(later) == 0
    assert {path: path.read_bytes() for path in files} == before
    # the same statements in another order of the draw are another list
    seeds = out / "samples_later" / "sample_pair_seeds.csv"
    rows = S.read_csv(seeds)
    rows[0]["draw_rank"], rows[1]["draw_rank"] = rows[1]["draw_rank"], rows[0]["draw_rank"]
    seeds.write_text(S.plain_csv(S.LATER_COLUMNS, rows), encoding="utf-8")
    with pytest.raises(SystemExit, match="would change the list on disk of: pair_seeds"):
        S.main(later)
    seeds.write_bytes(before[seeds])
    assert S.main(later) == 0
    assert {path: path.read_bytes() for path in files} == before
    # an item of the in-context pool is audited after all: the pool would lose it
    pool = S.read_csv(out / "samples_later" / "sample_incontext_pool.csv")
    taken = ",".join(pool[0][c] for c in S.SAMPLE_COLUMNS)
    sample.write_text(",".join(S.SAMPLE_COLUMNS) + f"\n{taken}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="would change the list on disk of: incontext_pool"):
        S.main(later)
    assert {path: path.read_bytes() for path in files} == before
    assert S.main([*later, "--replace"]) == 0
    after = S.read_list(out / "samples_later" / "sample_incontext_pool.csv")
    assert pool[0]["statement_group_id"] not in after
    assert (out / "manifest.json").read_bytes() != before[out / "manifest.json"]


def test_sheets_command_reads_no_exclusion(tmp_path: Path) -> None:
    """A guide revised after the draw can quote other phrases, or hold a stray quotation mark:
    the sheets of the lists on disk are written all the same, and the draw says what is wrong."""
    out, inputs = drawn_folder(tmp_path)
    before = S.parse_sheet((out / "check_A1.csv").read_text(encoding="utf-8"))[1]
    guide = Path(inputs[3])
    stray = '## 3. Task A\n\nA cue: "Estimated Recovery and no closing mark.\n'
    guide.write_text(guide_text(**SMALL, section=stray), encoding="utf-8")
    assert S.main(["sheets", "--task", "check", *inputs]) == 0
    assert S.parse_sheet((out / "check_A1.csv").read_text(encoding="utf-8"))[1] == before
    with pytest.raises(ValueError, match="an odd number of quotation marks"):
        S.main(["draw", *inputs, UNMATCHED])


def test_files_are_written_under_the_folder_only(tmp_path: Path) -> None:
    assert S.write_text(tmp_path, "a/b.txt", "x") == hashlib.sha256(b"x").hexdigest()
    assert (tmp_path / "a" / "b.txt").read_text(encoding="utf-8") == "x"
    with pytest.raises(ValueError, match="is outside"):
        S.write_text(tmp_path / "a", "../c.txt", "x")
    assert S.ids_sha256(["S2", "S1", "S3"]) == S.ids_sha256(["S1", "S2", "S3"])
    assert S.ids_sha256(["S1", "S2"]) == hashlib.sha256(b"S1\nS2\n").hexdigest()
    S.update_manifest(tmp_path, "one", {"k": 1})
    S.update_manifest(tmp_path, "two", {"k": 2})
    S.update_manifest(tmp_path, "one", {"k": 3})
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["one"] == {"k": 3} and manifest["two"] == {"k": 2} and manifest["seed"] == S.SEED
    )


def test_draw_command_says_when_a_sample_is_short(tmp_path: Path, capsys: Any) -> None:
    """Two statements per stratum cannot fill a pilot, a check set and a reserve of one each."""
    guide, events = write_inputs(tmp_path / "in", guide_text(**SMALL), small_corpus(2, 4))
    out = tmp_path / "out"
    inputs = ["--events", str(events), "--guide", str(guide), "--out", str(out)]
    capsys.readouterr()
    assert S.main(["draw", *inputs, UNMATCHED]) == 0
    printed = capsys.readouterr().out
    assert "warning: pilot has" not in printed and "warning: check has" not in printed
    assert "warning: reserve has 0 statements, the guide's table 7" in printed
    assert S.read_list(out / "samples" / "sample_reserve.csv") == []


def canary_event(n: int = 9000) -> dict[str, str]:
    """The statement the harness builds its fixed test item on, as an event of the corpus."""
    item = read.CANARY_ITEM
    return event(
        n,
        "Expected recovery April 2020",
        item.date_of_update,
        generic_name=item.generic_name,
        generic_id="anagrelide",
        company_name="Teva Pharmaceuticals",
    )


def test_draw_stops_when_an_exclusion_matches_nothing(tmp_path: Path, capsys: Any) -> None:
    item = read.CANARY_ITEM
    known = f"| {item.generic_name} | Teva Pharmaceuticals | {item.date_of_update} |"
    table = ["| Generic | Company | Statement date |", "|---|---|---|", known]
    unknown = "| Unknown Drug | Nobody | 2020-01-01 |"
    events = pd.concat([small_corpus(), frame([canary_event()])], ignore_index=True)
    guide, with_item = write_inputs(tmp_path / "in", guide_text(**SMALL), events)
    _, without_item = write_inputs(tmp_path / "bare", guide_text(**SMALL), small_corpus())
    out = tmp_path / "out"
    draw = ["draw", "--guide", str(guide), "--out", str(out), "--events"]

    # the corpus does not hold the fixed test item of the harness
    with pytest.raises(SystemExit, match="the exclusions are incomplete"):
        S.main([*draw, str(without_item)])
    assert "error: the fixed test item of the harness" in capsys.readouterr().out
    assert not out.exists()  # nothing was written

    # a row of Appendix A that names no event
    guide.write_text(guide_text(**SMALL, appendix="\n".join([*table, unknown])), encoding="utf-8")
    with pytest.raises(SystemExit, match="pass --allow-unmatched to draw anyway"):
        S.main([*draw, str(with_item)])
    printed = capsys.readouterr().out
    assert "error: Appendix A row matches no event: unknown drug, nobody, 2020-01-01" in printed
    assert "fixed test item" not in printed and not out.exists()
    assert S.main([*draw, str(with_item), UNMATCHED]) == 0
    assert "warning: Appendix A row matches no event" in capsys.readouterr().out

    # complete exclusions need no flag, and the manifest says the item is listed
    guide.write_text(guide_text(**SMALL, appendix="\n".join(table)), encoding="utf-8")
    assert S.main([*draw, str(with_item), "--replace", *S.FIRST_SAMPLES]) == 0
    printed = capsys.readouterr().out
    assert "error:" not in printed and "warning:" not in printed
    notes = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["samples"]["exclusions"]
    assert notes["appendix_a_rows_matching_no_event"] == 0
    assert notes["fixed_test_item_statements"] == 1 and notes["fixed_test_item_in_appendix_a"]
    drawn = {
        i for name in S.FIRST_SAMPLES for i in S.read_list(out / "samples" / f"sample_{name}.csv")
    }
    assert "S09000" not in drawn

    # the later draw has the same check
    sample = tmp_path / "audit" / "outcome_train_sample.csv"
    sample.parent.mkdir()
    sample.write_text(",".join(S.SAMPLE_COLUMNS) + "\n", encoding="utf-8")
    later = [
        "draw-later",
        "--guide",
        str(guide),
        "--out",
        str(out),
        "--outcome-sample",
        str(sample),
    ]
    with pytest.raises(SystemExit, match="the exclusions are incomplete"):
        S.main([*later, "--events", str(without_item)])
    assert not (out / "samples_later").exists()


def test_draw_does_not_replace_a_list_on_disk_unasked(tmp_path: Path, capsys: Any) -> None:
    out, inputs = drawn_folder(tmp_path)
    draw = ["draw", *inputs, UNMATCHED]

    def state() -> dict[str, bytes]:
        return {
            p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()
        }

    before = state()
    assert S.main(draw) == 0 and state() == before  # the same inputs: the same bytes, no flag

    # the guide now excludes a statement of the pilot: the pilot would hold another one
    pilot = S.read_list(out / "samples" / "sample_pilot.csv")
    named = small_corpus().set_index("statement_group_id").loc[pilot[0]]
    row = f"| {named['generic_name']} | {named['company_name']} | {named['event_date']} |"
    appendix = "\n".join(["| Generic | Company | Statement date |", "|---|---|---|", row])
    Path(inputs[3]).write_text(guide_text(**SMALL, appendix=appendix), encoding="utf-8")
    capsys.readouterr()
    with pytest.raises(SystemExit, match="would change the list on disk of: pilot") as stop:
        S.main(draw)
    assert "Nothing was written" in str(stop.value) and "--fixed pilot" in str(stop.value)
    assert state() == before

    # kept: the pilot stays, and the lists drawn around it do not move either
    assert S.main([*draw, "--fixed", "pilot"]) == 0
    assert S.read_list(out / "samples" / "sample_pilot.csv") == pilot
    for name in S.FIRST_SAMPLES:
        assert (out / "samples" / f"sample_{name}.csv").read_bytes() == before[
            f"samples/sample_{name}.csv"
        ]

    # replaced: only when the sample is named
    with pytest.raises(SystemExit, match="would change the list on disk of: pilot"):
        S.main([*draw, "--replace", "literal"])
    # ... and its sheets on disk, which are those of the old list, are written again with it
    kept = state()
    with pytest.raises(SystemExit, match="Add --sheets pilot") as stop:
        S.main([*draw, "--replace", *S.FIRST_SAMPLES])
    assert "Nothing was written" in str(stop.value) and state() == kept
    assert S.main([*draw, "--replace", *S.FIRST_SAMPLES, "--sheets", *S.FIRST_SAMPLES]) == 0
    redrawn = S.read_list(out / "samples" / "sample_pilot.csv")
    assert pilot[0] not in redrawn and len(redrawn) == len(pilot)
    shown = {r["item_id"] for r in S.read_sheet(out / "pilot_A1.csv")[1]}
    assert shown == {S.item_id(i) for i in redrawn}


def test_a_draw_that_keeps_every_list_keeps_the_stratum_table_too(
    tmp_path: Path, capsys: Any
) -> None:
    """The freeze run draws with all four lists kept: the lists and the table of what each
    stratum had when they were drawn must keep their bytes."""
    out, inputs = drawn_folder(tmp_path)
    draw = ["draw", *inputs, UNMATCHED]
    before = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    table = before["samples/strata.csv"]
    assert table.count(b"\n") > 1 + 4 * len(NAMES)  # the literal sample has a row per period
    for kept in (["pilot"], ["check", "literal"], list(S.FIRST_SAMPLES)):
        capsys.readouterr()
        assert S.main([*draw, "--fixed", *kept]) == 0
        printed = capsys.readouterr().out
        after = {
            p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()
        }
        assert sorted(after) == sorted(before)
        assert {n for n in before if after[n] != before[n]} == {"manifest.json"}, kept
        manifest = json.loads(after["manifest.json"])
        assert manifest["samples"]["fixed"] == sorted(kept)
        assert manifest["samples"]["strata"]["sha256"] == hashlib.sha256(table).hexdigest()
        assert manifest["sheets"] == json.loads(before["manifest.json"])["sheets"]
        assert all(f"  {name:15s} month_year" in printed for name in S.FIRST_SAMPLES)
        assert printed.count("(kept from disk)") == len(kept)
    # a kept list whose rows are not on disk has none in the table (a list copied alone)
    alone = tmp_path / "alone"
    (alone / "samples").mkdir(parents=True)
    (alone / "samples" / "sample_pilot.csv").write_bytes(before["samples/sample_pilot.csv"])
    assert S.main(["draw", *inputs[:4], "--out", str(alone), UNMATCHED, "--fixed", "pilot"]) == 0
    rows = S.read_csv(alone / "samples" / "strata.csv")
    assert {r["sample"] for r in rows} == {"check", "reserve", "literal"}


def test_a_sheet_filled_in_place_is_not_written_over(tmp_path: Path) -> None:
    out, inputs = drawn_folder(tmp_path)
    blank = (out / "pilot_A2.csv").read_text(encoding="utf-8")
    assert not S.holds_labels(out / "pilot_A2.csv") and not S.holds_labels(out / "absent.csv")
    meta, rows = S.parse_sheet(blank)
    one_cell = [rows[0] | {"statement_type": "none"}, *rows[1:]]
    timed = [(k, "09:00" if k == "sitting_start" else v) for k, v in meta]
    for text in (
        fill(blank),
        S.sheet_text(S.SHEET_COLUMNS, one_cell, meta),  # one label
        S.sheet_text(S.SHEET_COLUMNS, rows, timed),  # a sitting time and no label yet
    ):
        (out / "pilot_A2.csv").write_text(text, encoding="utf-8")
        assert S.holds_labels(out / "pilot_A2.csv")
        with pytest.raises(SystemExit, match=r"pilot_A2\.csv: the sheet holds labels"):
            S.main(["sheets", "--task", "check", "pilot", *inputs])
        manifest = (out / "manifest.json").read_bytes()
        with pytest.raises(SystemExit, match="Nothing was written"):
            S.main(["draw", *inputs, UNMATCHED, "--sheets", "pilot"])
        assert (out / "pilot_A2.csv").read_text(encoding="utf-8") == text
        assert (out / "manifest.json").read_bytes() == manifest
    # a draw that would replace a list stops before it writes the list
    literal = out / "samples" / "sample_literal.csv"
    listed = literal.read_bytes()
    named = small_corpus().set_index("statement_group_id").loc[S.read_list(literal)[0]]
    row = f"| {named['generic_name']} | {named['company_name']} | {named['event_date']} |"
    appendix = "\n".join(["| Generic | Company | Statement date |", "|---|---|---|", row])
    guide = Path(inputs[3])
    original = guide.read_text(encoding="utf-8")
    guide.write_text(guide_text(**SMALL, appendix=appendix), encoding="utf-8")
    with pytest.raises(SystemExit, match="Nothing was written"):
        S.main(["draw", *inputs, UNMATCHED, "--replace", "literal", "--sheets", "pilot"])
    assert literal.read_bytes() == listed
    guide.write_text(original, encoding="utf-8")
    (out / "pilot_A2.csv").write_bytes("café".encode("cp1252"))  # unreadable: left alone too
    with pytest.raises(SystemExit, match="the sheet holds labels"):
        S.main(["sheets", "--task", "pilot", *inputs])
    assert S.main(["sheets", "--task", "check", *inputs]) == 0  # the other task is not held up
    (out / "pilot_A2.csv").unlink()
    assert S.main(["sheets", "--task", "pilot", *inputs]) == 0
    assert (out / "pilot_A2.csv").read_text(encoding="utf-8") == blank


def test_a_file_a_spreadsheet_saved_in_another_format_is_one_clear_error(
    tmp_path: Path, capsys: Any
) -> None:
    shown = SHOWN_ROW | {"availability_information": "On backorder – next release April 2020."}
    meta = [("sheet", "pilot"), ("annotator", "A1"), ("sitting_start", "9:00")]
    text = S.sheet_text(S.SHEET_COLUMNS, [shown | GOOD], [*meta, ("sitting_end", "9:10")])
    legacy = tmp_path / "legacy.csv"
    legacy.write_bytes(text.encode("cp1252"))  # "CSV (Comma delimited)" of a spreadsheet
    checked = S.check_file(legacy, None, tmp_path)
    assert checked.errors == [S.NOT_UTF8] and not checked.labels
    assert S.main(["validate", str(legacy), "--out", str(tmp_path)]) == 1
    assert "error: sheet: the file is not UTF-8 text; save it again as CSV UTF-8" in (
        capsys.readouterr().out
    )
    good = tmp_path / "good.csv"
    good.write_text(text, encoding="utf-8")
    assert S.check_file(good, None, tmp_path).ok
    semicolons = tmp_path / "semicolons.csv"
    lines = [line.replace('","', '";"') for line in text.splitlines()]
    semicolons.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert (
        S.check_file(semicolons, None, tmp_path)
        .errors[0]
        .endswith("(the file looks semicolon-separated; save it comma-separated)")
    )


# --------------------------------------------------------------------------------------------
# The files on disk, when the draw has been run
# --------------------------------------------------------------------------------------------


def on_disk() -> dict[str, Any]:
    path = REAL_OUT / "manifest.json"
    if not path.is_file():
        pytest.skip("the draw has not been run: analysis/coling/out/audit/manifest.json is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def test_lists_on_disk_match_the_manifest_and_the_guide_table() -> None:
    manifest = on_disk()
    samples = manifest["samples"]
    alloc = S.guide_allocation(REAL_GUIDE.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for name in S.FIRST_SAMPLES:
        path = REAL_OUT / samples[name]["file"]
        assert sha(path) == samples[name]["sha256"]
        rows = S.read_csv(path)
        assert tuple(rows[0]) == S.SAMPLE_COLUMNS
        ids = [r["statement_group_id"] for r in rows]
        assert ids == sorted(set(ids)) and S.ids_sha256(ids) == samples[name]["statements_sha256"]
        assert len(ids) <= sum(alloc.quotas[name].values())
        assert not seen & set(ids)
        seen |= set(ids)
    assert sha(REAL_OUT / samples["strata"]["file"]) == samples["strata"]["sha256"]
    assert samples["exclusions"]["appendix_a_rows_matching_no_event"] == 0
    assert samples["exclusions"]["fixed_test_item_statements"] >= 1
    assert samples["exclusions"]["guide_phrases"] > 80
    assert samples["inputs"]["rules_sha256"] == F.RULES_SHA256[:16]
    strata = S.read_csv(REAL_OUT / samples["strata"]["file"])
    assert {r["stratum"] for r in strata} == set(alloc.names)
    rule = samples["phrase_rule"]
    assert {r["stratum"] for r in rule} == set(alloc.names)
    assert all(r["removed"] <= r["equal_to_a_phrase"] <= r["frame"] for r in rule)


def test_later_lists_on_disk_mark_the_period_of_every_statement() -> None:
    manifest = on_disk()
    if "samples_later" not in manifest:
        pytest.skip("the later draw has not been run")
    entry = manifest["samples_later"]
    first = {
        i
        for name in S.FIRST_SAMPLES
        for i in S.read_list(REAL_OUT / S.SAMPLES_DIR / f"sample_{name}.csv")
    }
    seen: set[str] = set()
    for name, spec in S.LATER.items():
        path = REAL_OUT / entry[name]["file"]
        assert sha(path) == entry[name]["sha256"]
        rows = S.read_csv(path)
        assert tuple(rows[0]) == S.LATER_COLUMNS and len(rows) <= spec.size
        ids = [r["statement_group_id"] for r in rows]
        assert not set(ids) & first and not set(ids) & seen
        seen |= set(ids)
        assert sorted(int(r["draw_rank"]) for r in rows) == list(range(1, len(rows) + 1))
        if name != "pair_seeds":
            assert {r["period"] for r in rows} == {"train"}
    strata = S.read_csv(REAL_OUT / entry["strata"]["file"])
    seeds = {r["stratum"]: r for r in strata if r["sample"] == "pair_seeds"}
    later = sum(r["period"] == "test" for r in S.read_csv(REAL_OUT / entry["pair_seeds"]["file"]))
    assert seeds["relative"]["period"] == "test" and int(seeds["relative"]["drawn"]) == later


def test_sheets_on_disk_are_blank_train_period_and_recorded() -> None:
    manifest = on_disk()
    for task, entry in manifest.get("sheets", {}).items():
        for name, digest in entry["files"].items():
            assert sha(REAL_OUT / name) == digest, name
        key = S.read_csv(REAL_OUT / S.KEYS_DIR / f"{task}_key.csv")
        assert sha(REAL_OUT / S.KEYS_DIR / f"{task}_key.csv") == entry["key_sha256"]
        listed = S.read_list(REAL_OUT / S.SAMPLES_DIR / f"sample_{task}.csv")
        assert sorted(k["statement_group_id"] for k in key) == listed
        if task in S.TRAIN_ONLY:
            assert {k["period"] for k in key} == {"train"}
        items = {i.item_id: i for i in read.load_items(REAL_OUT / f"{task}_items.jsonl")}
        assert set(items) == {k["item_id"] for k in key}
        for annotator in S.ANNOTATORS:
            meta, rows = S.read_sheet(REAL_OUT / f"{task}_{annotator}.csv")
            assert dict(meta)["sheet"] == task and dict(meta)["annotator"] == annotator
            assert tuple(rows[0]) == S.SHEET_COLUMNS
            assert {r["item_id"] for r in rows} == set(items)
            assert all(r[c] == "" for r in rows for c in S.ENTERED)
            if task in S.TRAIN_ONLY:
                assert all(r["date_of_update"] < "2023-01-01" for r in rows)
        orders = [
            [r["item_id"] for r in S.read_sheet(REAL_OUT / f"{task}_{a}.csv")[1]]
            for a in S.ANNOTATORS
        ]
        assert orders[0] != orders[1]
