"""Tests for the secondary scorer (``secondary_scores.py``).

No test reads the study's sealed folder, opens a network connection or reads a key (the guard of
``test_evaluate.py`` is applied to every test). The command tests run on one synthetic study in
a temporary folder, built the way the evaluator's tests build theirs and from the same parts:

* capture files made into the open tables, the eligible list, the counts file and the item files
  by ``corpus.build_corpus`` and ``dataset.build``; the test-period outcome rows are written to a
  file that stands in for the sealed one. Besides dated statements the test split holds TBD,
  silent and stale-at-issue ones, presentations that read "Limited Availability" before they
  are available, and presentations that leave the list without a resolution;
* a plan made by ``launch.make_plan`` with three paraphrase templates entered in the harness
  for the length of the module, and every run of the phases ``dev``, ``confirmatory`` and
  ``rest`` whose item file exists, read by the harness's own reader around a scripted client
  (masked, shifted and sampled runs included), so the stored rows and manifests are the
  harness's;
* scripted answers that are a fixed function of the model, the condition, the statement and the
  sample (``answer``), with planted effects: one secondary model whose condition (b) follows the
  outcome and whose literal reading is the rule reading; a primary whose reading of a stale
  period under (a) is always above one half; cells of the 2x2 that move the probabilities by a
  known amount. A few answers fail to parse;
* the dev command, the baselines command and the confirmatory command of the evaluator, whose
  result file the secondary scorer needs.

Covered: every statistic on a case worked by hand; the contrasts of the secondary models
against a computation made here from the scripted answers and the synthetic outcomes; every
section of the result file; every refusal, with the sealed file left unread; the order in which
the files are read; a run stored in several parts; no statement in any output; the train-period
descriptives, which take no sealed path.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_secondary_scores.py -q -p no:cacheprovider
"""

from __future__ import annotations

import builtins
import csv
import io
import itertools
import json
import os
import re
import shutil
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager, redirect_stdout
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from analysis.coling import corpus as C
from analysis.coling import dataset as D
from analysis.coling import evaluate as ev
from analysis.coling import launch as lp
from analysis.coling import predictors as P
from analysis.coling import read as rd
from analysis.coling import sealed_counts as S
from analysis.coling import secondary_scores as sc
from analysis.coling import test_evaluate as TE

LLAMA, DEEPSEEK = rd.PRIMARIES
INFORMED = "qwen-2.5-7b"
"""The secondary model with planted effects: (b) follows the outcome, (c) is the rule reading."""
NOISY = "gemma-3-27b"
"""A secondary model some of whose answers fail to parse."""
PARAPHRASES = tuple(f"predictive-track-p{n}" for n in (1, 2, 3))
"""The three paraphrases of ``predictive-track-v1`` that the harness holds."""
SIZES = {"probe": 120, "samples20": 60, "paraphrase": 50, "twobytwo": 80, "reference_check": 20}
CELL_OF = {(True, 0): "mask", (False, lp.SHIFT_YEARS): "shift", (True, lp.SHIFT_YEARS): "both"}
CELL_NAMES = dict(zip(("mask", "shift", "both"), sc.CELLS, strict=True))
CELL_SHIFT = {"mask": (0.10, 20), "shift": (-0.05, 0), "both": (0.20, 40)}
"""What each cell of the 2x2 adds to the two probabilities and to the median of condition (b)."""
SLIP_DRAWS = 20
BARE: dict[str, str] = {}
"""The statement of the 20-sample subset none of whose samples the second primary parses."""


# --------------------------------------------------------------------------------------------
# Guards for every test
# --------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def sealed_off(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    TE.guard(monkeypatch, tmp_path_factory.mktemp("nowhere"))


def test_the_harness_holds_the_three_paraphrases_this_file_scores() -> None:
    """The launcher plans the paraphrase runs only when the harness holds exactly three
    paraphrases of ``predictive-track-v1``, each with its pin."""
    held = sorted(name for name in rd.TEMPLATES if name.startswith("predictive-track-p"))
    assert tuple(held) == PARAPHRASES
    for name in PARAPHRASES:
        assert rd.TEMPLATES[name].needs_track and rd.TEMPLATES[name].kind == "predictive"
        assert rd.FROZEN_SHA256[name] == rd.TEMPLATES[name].sha256


# --------------------------------------------------------------------------------------------
# The synthetic corpus
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """One presentation: its statement, the capture from which it reads Available, the one from
    which it reads Limited Availability, and the one from which it is no longer listed."""

    generic: str
    company: str
    day: str
    text: str
    back: date | None
    posted: str
    reason: str
    limited: date | None = None
    gone: date | None = None


def kind_of(split: str, drug: int, n: int) -> str:
    """What the n-th statement of a drug says: a month, a quarter, TBD, nothing about timing
    (test split only), or a month that has passed (some test drugs)."""
    if split == "test" and n % 9 == 5:
        return "silent"
    if split == "test" and drug % 3 == 0 and n == 2:
        return "stale"
    every = {"fit": 6, "dev": 8, "test": 9}.get(split, 0)
    if every and (n % every == every - 1 or (split == "test" and n % every == 2)):
        return "tbd"
    return "quarter" if n % 7 == 3 else "month"


def layout() -> list[Line]:
    """The statements, as in the evaluator's tests (dated the 15th of a month, giving the month
    two months on, back ``k`` months after that month's first day): 10 drugs in the fit split,
    8 in dev, 24 in the test split and one in the late split."""
    rng = np.random.default_rng(20261001)
    out: list[Line] = []

    def add(split: str, drug: int, months: Sequence[str]) -> None:
        company = TE.COMPANIES[int(rng.integers(len(TE.COMPANIES)))]
        posted = f"0{int(rng.integers(1, 9))}/05/{int(rng.integers(2016, 2020))}"
        lean = rng.dirichlet([2.0, 1.5, 2.0, 1.5, 0.8, 0.8])
        for n, month in enumerate(months):
            stated = TE.month_start(month, 2)
            past = TE.month_start(month, -2)
            k = TE.K_VALUES[int(rng.choice(len(TE.K_VALUES), p=lean))]
            text = {
                "tbd": "Estimated recovery: TBD",
                "silent": "On backorder",
                "stale": f"Estimated recovery: {TE.MONTHS[past.month - 1]} {past.year}",
                "quarter": f"Estimated recovery: Q{(stated.month - 1) // 3 + 1} {stated.year}",
                "month": f"Estimated recovery: {TE.MONTHS[stated.month - 1]} {stated.year}",
            }[kind_of(split, drug, n)]
            reason = TE.REASONS[int(rng.integers(len(TE.REASONS)))]
            out.append(
                Line(
                    f"{split.capitalize()}drug {drug:02d}",
                    company,
                    f"{month}-15",
                    text,
                    None if k is None else TE.month_start(month, 2 + k),
                    posted,
                    reason,
                    TE.month_start(month, 1 + k) if k and n % 4 == 1 else None,
                    TE.month_start(month, 5) if k is None and n % 2 == 0 else None,
                )
            )

    for g in range(10):
        add("fit", g, TE.span("2019-12", 13))
    for g in range(8):
        add("dev", g, TE.span("2021-01", 17))
    for g in range(24):
        add("test", g, TE.span("2023-01", 28)[g % 3 :: 3])
    add("late", 0, ["2026-01", "2026-02"])
    return out


def capture_rows(day: date, lines: Sequence[Line]) -> list[list[str]]:
    """The listing on one capture day: every presentation whose statement is dated by then and
    which has not left the list."""
    rows = []
    for index, line in enumerate(lines):
        stated = date.fromisoformat(line.day)
        if stated > day or (line.gone is not None and day >= line.gone):
            continue
        supply = "Unavailable"
        if line.back is not None and day >= line.back:
            supply = "Available"
        elif line.limited is not None and day >= line.limited:
            supply = "Limited Availability"
        rows.append(
            [
                line.generic,
                line.company,
                "800-000-0000",
                TE.presentation(index),
                "Revised",
                stated.strftime("%m/%d/%Y"),
                supply,
                line.text,
                "",
                line.reason,
                "Anesthesia" if index % 2 else "Oncology",
                "Current",
                "",
                "",
                line.posted,
            ]
        )
    return rows


# --------------------------------------------------------------------------------------------
# The scripted answers
# --------------------------------------------------------------------------------------------


def clip(p: float) -> float:
    return round(min(1.0, max(0.0, p)), 4)


def list_answer(model: str, kind: str, row: dict[str, str]) -> dict[str, Any]:
    """The scripted reading of a TBD, silent or stale statement by a primary."""
    item, which, day = row["statement_group_id"], row["analysis_set"], row["event_date"]
    truth = {"yes": 1.0, "no": 0.0}
    if kind == "c":
        if which == "stale":
            if model == LLAMA or TE.unit(item, "lc") < 0.7:
                return TE.literal("recovery", row["stated_start"], row["stated_end"])
            return TE.literal("recovery", "", "")
        if model == DEEPSEEK and TE.unit(item, "lc") < 0.3:
            start = date.fromisoformat(day) + timedelta(days=30)
            return TE.literal("recovery", start.isoformat(), (start + timedelta(30)).isoformat())
        return TE.literal("recovery", "", "")
    if model == LLAMA and which == "stale":
        return TE.forecast(0.9, 0.95, 30) if kind == "a" else TE.forecast(0.2, 0.5, 200)
    if model == LLAMA and kind == "b":
        return TE.forecast(
            0.2 + 0.6 * truth.get(row["E_90"], 0.5), 0.2 + 0.6 * truth.get(row["E_180"], 0.5), 120
        )
    if model == LLAMA:
        return TE.forecast(0.6, 0.8, 100)
    p = 0.3 + 0.4 * TE.unit(item, f"l{kind}")
    return TE.forecast(p, min(1.0, p + 0.2), 150)


def answer(model: str, kind: str, row: dict[str, str], sample: int = 0) -> dict[str, Any]:
    """The scripted reading of one statement (``row``: its cells in the statement table with the
    synthetic outcome cells). ``kind`` is a condition (a, b, c, probe), ``samples``, a cell of
    the 2x2 (``mask``, ``shift``, ``both``) or a paraphrase template."""
    item = row["statement_group_id"]
    if row["analysis_set"] != "dated":
        return list_answer(model, kind, row)
    end = D.days_between(row["event_date"], row["stated_end"])
    truth = {"yes": 1.0, "no": 0.0}
    if kind == "samples":
        return TE.forecast(0.4, 0.6, 40 + int(250 * TE.unit(item, f"{model}-s{sample}")))
    if kind in CELL_SHIFT or kind in PARAPHRASES:
        plain = TE.answer(model, "b", row)
        if kind in CELL_SHIFT:
            more, days = CELL_SHIFT[kind]
        else:
            more, days = 0.2 * (TE.unit(item, f"{model}-{kind}") - 0.5), PARAPHRASES.index(kind)
        median = plain["days_to_recovery"]["q50"] + days
        return TE.forecast(
            clip(plain["p_by_horizon_a"] + more), clip(plain["p_by_horizon_b"] + more), median
        )
    if model in rd.PRIMARIES:
        return TE.answer(model, kind, row)
    if kind == "probe":
        return TE.forecast(0.5, 0.5, 3.0 + rd.STUDY_MODELS.index(model))
    if model == INFORMED:
        if kind == "c":
            return TE.literal("recovery", row["stated_start"], row["stated_end"])
        if kind == "a":
            return TE.forecast(0.9, 0.95, end)
        p_a = 0.2 + 0.6 * truth.get(row["E_end"], 0.5) + 0.1 * (TE.unit(item, "q1") - 0.5)
        p_b = 0.2 + 0.6 * truth.get(row["E_end90"], 0.5) + 0.1 * (TE.unit(item, "q2") - 0.5)
        return TE.forecast(p_a, p_b, end + 30)
    if kind == "c":
        draw = TE.unit(item, f"{model}-literal")
        if draw < 0.15:
            later = (date.fromisoformat(row["stated_end"]) + timedelta(days=31)).isoformat()
            return TE.literal("recovery", row["stated_start"], later)
        if draw < 0.21:
            return TE.literal("recovery", "", "")
        if draw < 0.25:
            return TE.literal("depletion", row["stated_start"], row["stated_end"])
        return TE.literal("next_delivery", row["stated_start"], row["stated_end"])
    level = 0.25 + 0.05 * rd.STUDY_MODELS.index(model)
    p_a = level + 0.2 * (TE.unit(item, f"{model}-{kind}1") - 0.5)
    p_b = level + 0.2 + 0.2 * (TE.unit(item, f"{model}-{kind}2") - 0.5)
    return TE.forecast(p_a, p_b, 100 + 10 * rd.STUDY_MODELS.index(model))


def fails(model: str, kind: str, item: str, sample: int = 0) -> int:
    """How many attempts of this reading come back unparsable: 2 (failed), 1 (repaired), 0."""
    if kind == "samples":
        if model == DEEPSEEK and item == BARE.get("item"):
            return 2
        return 2 if TE.unit(item, f"{model}-fail-s{sample}") < 0.05 else 0
    if model in rd.PRIMARIES and kind in ("a", "b", "c", "probe"):
        return TE.fails(model, kind, item)
    planned = {
        (NOISY, "b"): 0.08,
        (NOISY, "c"): 0.06,
        (LLAMA, "mask"): 0.05,
        (LLAMA, PARAPHRASES[0]): 0.05,
    }
    share = planned.get((model, kind), 0.0)
    draw = TE.unit(item, f"{model}-fail-{kind}")
    return 2 if draw < share / 2 else 1 if draw < share else 0


def kind_of_run(run: dict) -> str:
    """The kind of scripted answer a run of the plan gets (see ``answer``)."""
    if run["line"] == sc.SAMPLES_LINE:
        return "samples"
    if run["line"] == sc.CELLS_LINE:
        return CELL_OF[(run["mask_names"], run["shift_years"])]
    if run["line"] == sc.PARAPHRASE_LINE:
        return run["template"]
    return run["line"].rsplit("-", 1)[1]


class ScriptedSDK:
    """Stands in for the SDK client inside the real ``read.RouteCheckedClient``: it echoes the
    model it was asked for, names the pinned provider, and answers with ``reply(prompt)``."""

    def __init__(self, reply: Callable[[str], str], provider: str | None) -> None:
        self.reply, self.provider = reply, provider
        self.chat = self.completions = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        text = self.reply(kwargs["messages"][-1]["content"])
        return SimpleNamespace(
            model=kwargs["model"],
            provider=self.provider,
            openrouter_metadata=None,
            usage=SimpleNamespace(prompt_tokens=500, completion_tokens=60, total_tokens=560),
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        )


def make_run(
    plan: dict, run: dict, known: pd.DataFrame, local: Path, kind: str | None = None
) -> None:
    """One run of the plan, read by the harness's reader around a scripted client and written
    by ``read.write_run`` with the fields the harness's command line adds to the manifest. The
    scripted client is told which item and sample is being read, so that it can answer a
    prompt whose names are masked. ``kind`` names the scripted answer of a run whose cells no
    longer say which one it gets."""
    model, out_dir = run["model"], Path(plan["options"]["out_root"]) / run["run"]
    every = rd.load_items(Path(run["items"]))
    shard = rd.parse_shard(run["shard"])
    items = [i for i in every if shard is None or rd.shard_of(i.item_id, shard[1]) == shard[0]]
    items = items[: run["limit"]]
    track = None
    if run["track"]:
        track = rd.load_track_record(Path(plan["tracks"][run["track"]]["path"]))
    route, kind, now = rd.ROUTES[model], kind or kind_of_run(run), {"item": "", "sample": 0}

    def reply(prompt: str) -> str:
        attempt = int("Your previous reply was:" in prompt)
        if attempt < fails(model, kind, now["item"], now["sample"]):
            return TE.GARBAGE
        return json.dumps(answer(model, kind, known.loc[now["item"]].to_dict(), now["sample"]))

    pinned = rd.provider_object(route) is not None
    sdk = ScriptedSDK(reply, route.provider.split("/")[0] if pinned else None)
    client = rd.RouteCheckedClient(
        rd.route_endpoint(model), rd.served_as(model), route=route, sdk=sdk
    )
    endpoint, transport = rd.build_transport(
        model,
        spend_log=out_dir / "spend_log.jsonl",
        spend_cap_usd=1000.0,
        max_physical_calls=10**7,
        inner=client,
    )
    reader = rd.Reader(
        model=model,
        template=rd.TEMPLATES[run["template"]],
        endpoint=endpoint,
        transport=transport,
        cache=rd.ReadCache(local / "cache"),
        decoding=rd.decoding_for(run["temperature"]),
        track=track,
        masker=rd.NameMasker() if run["mask_names"] else None,
        shift_years=run["shift_years"],
        route=route,
    )
    rows = []
    for item in items:
        for sample in range(run["samples"]):
            now.update(item=item.item_id, sample=sample)
            rows.append(reader.read(item, sample))
    meta = {
        "run_name": run["run"],
        "status": "complete",
        "items_sha256": TE.file_sha(Path(run["items"])),
        "items_in_file": len(every),
        "limit": run["limit"],
        "samples": run["samples"],
        "spend_cap_usd": run["cap_usd"],
        "shard": run["shard"],
        "temperature": run["temperature"],
        "mask_names": run["mask_names"],
        "shift_years": run["shift_years"],
    }
    rd.write_run(
        rows,
        reader,
        out_dir=out_dir,
        local_dir=local / run["run"],
        meta=meta,
        items=items,
        samples=run["samples"],
    )


# --------------------------------------------------------------------------------------------
# The synthetic study
# --------------------------------------------------------------------------------------------


def build_study(root: Path) -> SimpleNamespace:
    """The synthetic study on disk (see the module docstring), with what the tests need to
    work out the expected numbers on their own."""
    captures, out, vault, local = root / "captures", root / "out", root / "sealed", root / "local"
    items_dir, runs = out / "items", out / "read"
    for folder in (captures, vault, items_dir, runs, local):
        folder.mkdir(parents=True)
    lines = layout()
    manifest = []
    for day in TE.CAPTURE_DAYS:
        buffer = io.StringIO()
        csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            capture_rows(day, lines)
        )
        data = ("\r\n" + TE.HEADER + "\r\n" + buffer.getvalue()).encode("utf-8")
        stamp = day.strftime("%Y%m%d") + "000000"
        (captures / f"{stamp}.csv").write_bytes(data)
        manifest.append(
            {
                "file": f"{stamp}.csv",
                "timestamp": stamp,
                "bytes": str(len(data)),
                "sha256": S.sha256(data),
            }
        )
    pd.DataFrame(manifest).to_csv(out / "capture_manifest.csv", index=False, lineterminator="\n")
    corpus = C.build_corpus(captures)
    train = corpus.outcomes[corpus.outcomes["period"] == "train"]
    patch = pytest.MonkeyPatch()
    patch.setattr(D, "SUBSETS", tuple(replace(s, size=SIZES[s.name]) for s in D.SUBSETS))
    try:
        built = D.build(
            D.Inputs(
                events=D.as_text(corpus.events),
                outcomes=D.require_train(D.as_text(train)),
                days=tuple(sorted({d.date() for d in corpus.captures.dates})),
                examples=(),
                source={"events": "synthetic captures"},
            )
        )
    finally:
        patch.undo()
    paths = SimpleNamespace(
        statements=out / D.STATEMENTS.name,
        eligible=out / D.ELIGIBLE.name,
        counts=out / D.COUNTS.name,
        events=out / "events.csv.gz",
        sealed=vault / "outcomes_test.csv.gz",
        runs=runs,
        selections=out,
        confirmatory=out / "confirmatory.json",
    )
    paths.statements.write_bytes(built.statements_gz)
    paths.eligible.write_text(built.eligible_csv, encoding="utf-8")
    paths.counts.write_text(built.report_text, encoding="utf-8")
    C.write_gz(corpus.events, paths.events)
    C.write_gz(corpus.outcomes[corpus.outcomes["period"] == "test"], paths.sealed)
    for name, text in built.item_text.items():
        (items_dir / name).write_text(text, encoding="utf-8")
    (items_dir / "track_fit.json").write_text(json.dumps(TE.TRACK, indent=1))
    both = TE.TRACK | {"split": "fit+dev", "through": "2022-12-31"}
    (items_dir / "track_fit_dev.json").write_text(json.dumps(both, indent=1))

    # what the scripted client knows about each statement, the synthetic outcomes included
    table = built.table
    population = sc.at_risk_in_the_test_split(table)
    sealed_rows = D.read_table(paths.sealed)
    filled = D.attach_outcomes(population, sealed_rows)
    known = pd.concat([table[table["period"] == "train"], filled]).set_index(
        "statement_group_id", drop=False
    )
    listed = table[D.true(table["e3_eligible"])].sort_values("statement_group_id")
    eligible = built.eligible
    BARE["item"] = sorted(eligible.loc[eligible["samples20"] == 1, "statement_group_id"])[0]

    options = lp.default_options(items_dir)
    options |= {"out_root": str(runs), "local_root": str(local)}
    plan = lp.make_plan(options)
    lp.plan_path(runs).parent.mkdir(parents=True)
    lp.plan_path(runs).write_text(lp.plan_text(plan), encoding="utf-8")
    for run in lp.select(plan, ["dev", "confirmatory", "rest"]):
        if plan["lists"][run["list"]]["on_disk"]:
            make_run(plan, run, known, local)
    return SimpleNamespace(
        root=root,
        paths=paths,
        plan=plan,
        table=table,
        eligible=eligible,
        listed=listed.reset_index(drop=True),
        population=population,
        filled=filled.set_index("statement_group_id", drop=False),
        known=known,
        sealed_rows=sealed_rows,
        lines=lines,
        sealed_sha=TE.file_sha(paths.sealed),
        eligible_sha=TE.file_sha(paths.eligible),
    )


@pytest.fixture(scope="module")
def study(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    patch = pytest.MonkeyPatch()
    TE.guard(patch, tmp_path_factory.mktemp("nowhere"))
    # the number of draws behind a Turnbull interval is a constant of the scorer, and no option
    # of a command: the tests on the synthetic study take fewer, for the length of the module
    patch.setattr(sc, "SLIP_DRAWS", SLIP_DRAWS)
    try:
        built = build_study(tmp_path_factory.mktemp("study"))
        with redirect_stdout(io.StringIO()):
            for model in rd.PRIMARIES:
                out = built.paths.selections / ev.SELECTION_NAME.format(model=model)
                dev = TE.options(built, "statements", "counts", "out-root")
                assert ev.main(["dev", "--model", model, "--out", str(out), *dev]) == 0
            built.selection_shas = TE.selection_args(built.paths.selections)
            record = tmp_path_factory.mktemp("freeze") / "baselines.json"
            assert ev.main(["baselines", "--out", str(record), *TE.options(built, *TE.OPEN)]) == 0
            built.baselines_sha = json.loads(record.read_text())["predictions_sha256"]
            confirm = ["confirmatory", "--out", str(built.paths.confirmatory)]
            assert ev.main([*confirm, *TE.options(built)]) == 0
        yield built
    finally:
        patch.undo()


def options(study: SimpleNamespace, **replace: Any) -> list[str]:
    """The options of the ``score`` command on the synthetic study, with the values of
    ``replace`` in place of the study's (None leaves an option out; a list gives the option
    once for each value)."""
    values: dict[str, Any] = {
        "statements": study.paths.statements,
        "eligible": study.paths.eligible,
        "events": study.paths.events,
        "counts": study.paths.counts,
        "out-root": study.paths.runs,
        "selections": study.paths.selections,
        "sealed": study.paths.sealed,
        "confirmatory": study.paths.confirmatory,
        "expect-sha256": study.sealed_sha,
        "expect-eligible-sha256": study.eligible_sha,
        "expect-baselines-sha256": study.baselines_sha,
        "expect-selection-sha256": study.selection_shas,
    }
    values.update({key.replace("_", "-"): value for key, value in replace.items()})
    return [
        str(part)
        for name, value in values.items()
        if value is not None
        for one in (value if isinstance(value, list) else [value])
        for part in (f"--{name}", one)
    ]


def scored(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], **replace: Any
) -> tuple[dict[str, Any], str]:
    """Run the ``score`` command on the synthetic study: the record and the printout."""
    out = TE.fresh(tmp_path)
    capsys.readouterr()
    assert sc.main(["score", "--out", str(out), *options(study, **replace)]) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    return json.loads(out.read_text()), printed.out


def refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], **replace: Any
) -> str:
    """The reason of a refusal of the ``score`` command: one sentence as the exit status,
    nothing printed, nothing written, and no other error travelling with it."""
    out = TE.fresh(tmp_path, "refused")
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        sc.main(["score", "--out", str(out), *options(study, **replace)])
    assert isinstance(stop.value.code, str) and stop.value.code.startswith("refused: ")
    assert "Traceback" not in stop.value.code and "\n" not in stop.value.code
    assert stop.value.__cause__ is None and stop.value.__context__ is None
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == ""
    assert list(out.parent.iterdir()) == []
    return stop.value.code


@pytest.fixture(scope="module")
def base(study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """One ``score`` run on the untouched synthetic study, for the tests that only read it."""
    out = tmp_path_factory.mktemp("base") / "secondary.json"
    patch, printed = pytest.MonkeyPatch(), io.StringIO()
    TE.guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        with redirect_stdout(printed):
            assert sc.main(["score", "--out", str(out), *options(study)]) == 0
    finally:
        patch.undo()
    return SimpleNamespace(
        report=json.loads(out.read_text()), text=out.read_text(), printed=printed.getvalue()
    )


def test_the_layout_gives_a_study_of_the_planned_shape(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    sets = study.population["analysis_set"].value_counts().to_dict()
    assert sets["tbd"] >= 20 and sets["silent"] >= 20 and sets["stale"] >= 5
    assert len(study.listed) == sets["dated"] > 120
    assert sorted(base.report["sections"]) == sorted(sc.SECTIONS)


# --------------------------------------------------------------------------------------------
# What the tests work out on their own from the scripted answers and the synthetic outcomes
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fit(study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """The refit of the model-free predictors with their predictions on the eligible list, and
    the two horizon events of every statement of the test-split population (1, 0 or missing)."""
    patch = pytest.MonkeyPatch()
    TE.guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        frame = P.prepare(study.table)
        ids = list(study.listed["statement_group_id"])
        probe_ids = sorted(study.eligible.loc[study.eligible["probe"] == 1, "statement_group_id"])
        fitted, free, _, _ = ev.free_predictions(frame, ids, probe_ids)
    finally:
        patch.undo()
    events, filled = {"yes": 1.0, "no": 0.0}, study.filled
    dated = filled["analysis_set"] == "dated"
    y = pd.DataFrame(
        {
            "y_a": filled["E_end"].map(events).where(dated, filled["E_90"].map(events)),
            "y_b": filled["E_end90"].map(events).where(dated, filled["E_180"].map(events)),
            "episode": filled["episode_id"],
        }
    )
    y["scoreable"] = y["y_a"].notna() & y["y_b"].notna()
    return SimpleNamespace(
        frame=frame, ids=ids, probe_ids=probe_ids, fitted=fitted, free=free, y=y, base=free[ev.BASE]
    )


def given(
    study: SimpleNamespace, model: str, kind: str, ids: Sequence[str], base: pd.DataFrame
) -> tuple[pd.DataFrame, pd.Series]:
    """The scripted predictions of a predictive reading on ``ids``, with the output of ``base``
    where the reading fails twice, and which statements were parsed."""
    values, parsed = [], []
    for item in ids:
        parsed.append(fails(model, kind, item) < 2)
        if not parsed[-1]:
            values.append(base.loc[item, list(P.PREDICTION_COLUMNS)].tolist())
            continue
        reading = answer(model, kind, study.known.loc[item].to_dict())
        days = reading["days_to_recovery"]
        values.append(
            [
                reading["p_by_horizon_a"],
                reading["p_by_horizon_b"],
                *(days[k] for k in P.QUANTILE_KEYS),
            ]
        )
    frame = pd.DataFrame(values, index=list(ids), columns=list(P.PREDICTION_COLUMNS), dtype=float)
    return frame, pd.Series(parsed, index=list(ids))


def read_days(study: SimpleNamespace, model: str, ids: Sequence[str]) -> pd.Series:
    """The end of the scripted literal reading of each statement in days from its date; missing
    where the reading fails twice, abstains or gives the period of another statement type."""
    days = []
    for item in ids:
        row = study.known.loc[item].to_dict()
        reading = answer(model, "c", row)
        stated = isinstance(reading["interval"], dict) and reading["statement_type"] in (
            "recovery",
            "next_delivery",
        )
        if fails(model, "c", item) == 2 or not stated:
            days.append(float("nan"))
        else:
            days.append(float(D.days_between(row["event_date"], reading["interval"]["end"])))
    return pd.Series(days, index=list(ids), dtype=float)


def brier(pred: pd.DataFrame, y: pd.DataFrame) -> pd.Series:
    return ((pred["p_a"] - y["y_a"]) ** 2 + (pred["p_b"] - y["y_b"]) ** 2) / 2


def by_hand(difference: pd.Series, episodes: pd.Series) -> tuple[float, list[float]]:
    """The mean of paired differences and its 95% percentile interval over the registered
    bootstrap draws of the episodes, from the episode sums."""
    sums = difference.groupby(episodes).sum().sort_index()
    sizes = difference.groupby(episodes).size().sort_index()
    taken = P.cluster_draws(len(sums), ev.DRAWS, ev.SEED).astype(float)
    means = (taken @ sums.to_numpy()) / (taken @ sizes.to_numpy().astype(float))
    low, high = np.quantile(means, [0.025, 0.975])
    return float(difference.mean()), [float(low), float(high)]


def near(got: Any, wanted: Any, tolerance: float = 2e-6) -> bool:
    """Whether two numbers, or two lists of numbers and nulls, agree to the six decimals of a
    result file."""
    if isinstance(wanted, list | tuple):
        return len(got) == len(wanted) and all(
            near(a, b, tolerance) for a, b in zip(got, wanted, strict=True)
        )
    if got is None or wanted is None:
        return got is None and wanted is None
    return abs(float(got) - float(wanted)) <= tolerance


def as_parsed_only(
    got: dict, count: Any, counted: np.ndarray, unparsed: np.ndarray, delta: float | None = None
) -> None:
    """Hold the record of a contrast on the statements both readings parsed, and the count
    beside it, to the rules: with one to four readings not parsed, or as few parsed, nothing
    but the number not parsed is written; with a few counted statements left out or left,
    the counts alone; else the contrast, whose estimate is ``delta``."""
    not_parsed, left_out = int(unparsed.sum()), int((counted & unparsed).sum())
    kept = int((counted & ~unparsed).sum())
    if 0 < not_parsed < sc.MIN_SHOWN or 0 < len(unparsed) - not_parsed < sc.MIN_SHOWN:
        assert got == {"not_both_parsed": not_parsed, "withheld": True} and count is None
        return
    assert (got["not_both_parsed"], got["left_out"], got["statements"]) == (
        not_parsed,
        left_out,
        kept,
    )
    assert count == left_out
    if 0 < left_out < sc.MIN_SHOWN or 0 < kept < sc.MIN_SHOWN:
        assert got["withheld"] is True and "delta" not in got
    elif delta is not None and got.get("evaluable"):
        assert near(got["delta"], delta)


BARE_PART = {"mean": None, "ci95": None, "withheld": True}
"""A part of selective prediction of which nothing that depends on an outcome is written."""


def held_parts(point: dict, read: np.ndarray, scoreable: np.ndarray) -> str:
    """Hold the two parts of a point of selective prediction to the rules and say which one
    applies: ``bare`` (a part of one to four statements: not even how many of them are
    scoreable), ``withheld`` (a part with one to four scoreable statements), ``scenarios
    withheld`` (a part with one to four statements that are not scoreable) or ``shown``."""
    sizes = {
        name: (int(part.sum()), int((part & scoreable).sum()), int((part & ~scoreable).sum()))
        for name, part in (("read", read), ("abstained_on", ~read))
    }

    def few(position: int) -> bool:
        return any(0 < size[position] < sc.MIN_SHOWN for size in sizes.values())

    kind = (
        "bare" if few(0) else "withheld" if few(1) else "scenarios withheld" if few(2) else "shown"
    )
    for name, (statements, counted, _) in sizes.items():
        record = point[f"primary_brier_{name}"]
        bounds = record["bounds_all_statements"]
        if kind == "bare":
            assert record == BARE_PART | {
                "bounds_all_statements": {"statements": statements, "withheld": True}
            }, name
            continue
        assert record["statements"] == counted and bounds["statements"] == statements, name
        if kind == "withheld":
            assert record["mean"] is None and record["ci95"] is None and record["withheld"]
        if kind != "shown":
            assert not set(sc.FILLS) & set(bounds), name
    return kind


def typed(**columns: Any) -> pd.DataFrame:
    """A small typed frame, as ``predictors.prepare`` gives it, from the columns named."""
    size = len(next(iter(columns.values())))
    frame = pd.DataFrame(columns, index=[f"S{k}" for k in range(size)])
    if "y_a" in frame and "y_b" in frame:
        frame["scoreable"] = frame["y_a"].notna() & frame["y_b"].notna()
    return frame


def forecasts(index: Sequence[str], p_a: Sequence[float], p_b: Sequence[float], q: Any = 100):
    """Predictions with the given probabilities and one value (or one per statement) for every
    quantile."""
    frame = pd.DataFrame({"p_a": list(p_a), "p_b": list(p_b)}, index=list(index), dtype=float)
    for key in P.QUANTILE_KEYS:
        frame[key] = q
    return frame.astype(float)


# --------------------------------------------------------------------------------------------
# Every statistic on a case worked by hand
# --------------------------------------------------------------------------------------------


def test_a_mean_with_its_interval_and_the_rule_that_withholds_it() -> None:
    values, clusters = [1.0, 0.0, 1.0, 1.0], ["a", "a", "b", "c"]
    record = sc.mean_record(values, clusters, 500, 7)
    assert record["statements"] == 4 and record["episodes"] == 3 and record["mean"] == 0.75
    assert record["ci95"] == P.interval(P.bootstrap_means(values, clusters, 500, 7)[:, 0], 0.95)
    assert record["ci95"][0] <= 0.75 <= record["ci95"][1]
    # a 95% percentile interval over the registered draws of the episodes, from the episode
    # sums: 60 values in 9 episodes of unlike means tell the levels and the seeds apart
    rng = np.random.default_rng(5)
    episodes = [f"e{k % 9}" for k in range(60)]
    spread = rng.random(60) + np.array([int(name[1:]) for name in episodes]) / 5
    wide = sc.mean_record(spread, episodes, 2000, 7)
    sums = pd.Series(spread).groupby(episodes).sum().sort_index().to_numpy()
    sizes = pd.Series(spread).groupby(episodes).size().sort_index().to_numpy().astype(float)

    def ends(seed: int, level: float) -> list[float]:
        taken = P.cluster_draws(9, 2000, seed).astype(float)
        means = (taken @ sums) / (taken @ sizes)
        return [float(end) for end in np.quantile(means, [(1 - level) / 2, (1 + level) / 2])]

    assert near(wide["ci95"], ends(7, 0.95), 1e-12)
    assert not near(wide["ci95"], ends(7, 0.90), 1e-4)
    assert not near(wide["ci95"], ends(8, 0.95), 1e-4)
    assert ends(7, 0.95)[0] < ends(7, 0.90)[0] < ends(7, 0.90)[1] < ends(7, 0.95)[1]
    # one cluster has no resampling distribution
    alone = sc.mean_record([0.2, 0.4], ["a", "a"], 500, 7)
    assert near(alone["mean"], 0.3) and alone["ci95"] is None
    # under the least number of statements the value is withheld, and the counts stay
    few = sc.mean_record(values, clusters, 500, 7, least=5)
    assert few == {"statements": 4, "episodes": 3, "mean": None, "ci95": None, "withheld": True}
    assert sc.mean_record([*values, 1.0], [*clusters, "c"], 500, 7, least=5)["mean"] == 0.8
    none = sc.mean_record([], [], 500, 7)
    assert none["mean"] is None and none["withheld"] is False and none["statements"] == 0


def test_stale_value_uptake_is_the_share_above_one_half() -> None:
    index = [f"S{k}" for k in range(5)]
    pred = forecasts(index, [0.6, 0.5, 0.9, 0.2, 0.51], [0.9] * 5)
    parsed = pd.Series([True, True, False, True, True], index=index)
    record = sc.uptake(pred, parsed, ["a", "a", "b", "c", "c"], 300, 1)
    # 0.6, 0.9 and 0.51 are above one half; exactly one half is not
    assert near(record["share_above_one_half"]["mean"], 3 / 5)
    assert record["share_above_one_half"]["statements"] == 5
    assert near(record["share_above_one_half_among_parsed"]["mean"], 2 / 4)
    assert record["share_above_one_half_among_parsed"]["statements"] == 4
    assert record["not_parsed"] == 1
    assert sc.UPTAKE_ABOVE == 0.5


def test_selective_prediction_is_one_point_per_reader() -> None:
    rows = typed(
        episode_id=["a", "a", "b", "b", "c", "c", "d", "d", "e", "e", "f", "f"],
        y_a=[1.0, 0.0, 1.0, np.nan, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0],
        y_b=[1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0],
    )
    pred = forecasts(rows.index, [0.5] * 12, [1.0] * 12)
    days = pd.Series([10.0, np.nan, 5.0, np.nan, np.nan, 3.0, 4.0, np.nan, 2.0, 1.0, np.nan, 9.0])
    days.index = rows.index
    record = sc.selective(rows, pred, days, 300, 1)
    assert record["statements"] == 12 and record["abstained"] == 5
    assert near(record["abstention_rate"], 5 / 12)
    # the loss of a statement: ((0.5 - y_a)^2 + (1 - y_b)^2) / 2 = 0.125, or 0.625 when y_b is 0
    loss = np.array(
        [0.125, 0.625, 0.125, np.nan, 0.125, 0.125, 0.125, 0.625, 0.625, 0.125, 0.125, 0.125]
    )
    read = days.notna().to_numpy()
    scoreable = rows["scoreable"].to_numpy()
    assert record["primary_brier_read"]["statements"] == int((read & scoreable).sum()) == 7
    # four scoreable statements abstained on: fewer than five, so their mean is withheld, and
    # the mean of the statements read with it: the loss on all less the one would give the other
    assert record["primary_brier_abstained_on"]["statements"] == 4
    for part in ("read", "abstained_on"):
        assert record[f"primary_brier_{part}"]["mean"] is None
        assert record[f"primary_brier_{part}"]["ci95"] is None
        assert record[f"primary_brier_{part}"]["withheld"] is True
    assert record["primary_brier_all"]["statements"] == 11
    assert near(record["primary_brier_all"]["mean"], np.nanmean(loss))
    assert "withheld" not in record["primary_brier_all"]
    # with a fifth scoreable statement abstained on, both parts are given
    rows.loc["S3", "y_a"] = 1.0
    rows["scoreable"] = rows["y_a"].notna() & rows["y_b"].notna()
    loss[3] = 0.125
    record = sc.selective(rows, pred, days, 300, 1)
    scoreable = rows["scoreable"].to_numpy()
    assert record["primary_brier_abstained_on"]["statements"] == 5
    assert near(record["primary_brier_read"]["mean"], loss[read & scoreable].mean())
    assert near(record["primary_brier_abstained_on"]["mean"], loss[~read & scoreable].mean())
    assert near(record["primary_brier_all"]["mean"], loss.mean())


def sample_rows(item: str, medians: Sequence[int | None]) -> dict[tuple[str, int], dict]:
    return {
        (item, k): {
            "item_id": item,
            "sample": k,
            "reading": None
            if m is None
            else {
                "days_to_recovery": {"q50": m},
                "p_by_horizon_a": 0.4,
                "p_by_horizon_b": 0.3 if m == 30 else 0.4 if m == 20 else 0.6,
            },
        }
        for k, m in enumerate(medians)
    }


def test_sampled_quantiles_are_the_harness_ranks_of_the_sampled_medians() -> None:
    order = np.random.default_rng(3).permutation(np.arange(1, 21)).tolist()
    stored = {
        **sample_rows("A", order),
        **sample_rows("B", [None] * 17 + [30, 10, 20]),
        **sample_rows("C", [None] * 20),
    }
    base = forecasts(["A", "B", "C"], [0.1] * 3, [0.2] * 3, q=[7.0, 8.0, 9.0])
    table, counts, some = sc.sampled_table(stored, ["A", "B", "C"], base)
    assert some.to_dict() == {"A": True, "B": True, "C": False}
    # of 20 sampled medians: the 2nd, 10th, 16th, 18th and 19th smallest
    assert table.loc["A"].tolist() == [2.0, 10.0, 16.0, 18.0, 19.0]
    # of 3: ranks ceil(0.1 * 3) = 1, ceil(1.5) = 2, ceil(2.4) = 3, 3, 3
    assert table.loc["B"].tolist() == [10.0, 20.0, 30.0, 30.0, 30.0]
    # none parsed: the base-rate quantiles, counted
    assert table.loc["C"].tolist() == [9.0] * 5
    assert list(table.columns) == list(P.QUANTILE_KEYS)
    # a statement with a sample left out is counted, the one with none parsed among them; one
    # sampled answer (the median of 30) puts P(E_end90) below P(E_end), and the two that give
    # both events the same probability (the medians of 20) are not counted
    equal = [row for row in stored.values() if row["reading"] is not None]
    assert sum(r["reading"]["p_by_horizon_b"] == r["reading"]["p_by_horizon_a"] for r in equal) == 2
    assert counts == {
        "statements": 3,
        "samples_per_statement": 20,
        "samples_parsed": 23,
        "statements_with_a_sample_left_out": 2,
        "statements_with_no_parsed_sample": 1,
        "p_b_below_p_a": 1,
    }


def test_sampled_against_verbalised_quantiles_on_a_case_worked_by_hand() -> None:
    rows = typed(
        episode_id=["a", "a", "b", "c", "d", "d"],
        ttr_kind=["interval", "interval", "at_cap", "right_censored", "interval", "interval"],
        ttr_lower=[0.0, 40.0, 365.0, 100.0, 95.0, 95.0],
        ttr_upper=[20.0, 60.0, 365.0, np.nan, 105.0, 105.0],
        ttr_mid=[10.0, 50.0, 365.0, np.nan, 100.0, 100.0],
    )
    ids = list(rows.index)
    # the last two statements are met exactly by both: they add to the count and to no loss
    exact = [[90, 100, 100, 110, 100]] * 2
    sampled = pd.DataFrame(
        [
            [0, 20, 30, 40, 50],
            [30, 40, 60, 70, 80],
            [300, 365, 365, 365, 365],
            [50, 60, 70, 80, 90],
            *exact,
        ],
        columns=list(P.QUANTILE_KEYS),
        index=ids,
        dtype=float,
    )
    assert list(sampled.columns) == ["q10", "q50", "q80", "q90", "q95"]
    verbal = forecasts(ids, [0.5] * 6, [0.5] * 6)
    verbal[list(P.QUANTILE_KEYS)] = [
        [5, 10, 20, 15, 30],
        [35, 90, 95, 99, 100],
        [1, 165, 300, 320, 365],
        [0, 1, 2, 3, 4],
        *exact,
    ]
    prepared = SimpleNamespace(
        sampled={"m": sampled},
        sampled_counts={"m": {"statements": 6}},
        sampled_parsed={"m": pd.Series(True, index=ids)},
        study=SimpleNamespace(
            predictions={"m:a": verbal},
            parsed={"m:a": pd.Series([True, True, False, True, True, True], index=ids)},
            first=pd.DataFrame({"event_date": ["2023-03-01"] * 2 + ["2023-09-01"] * 4}, index=ids),
        ),
    )
    more = SimpleNamespace(ids={"samples": ids}, records={"m": {sc.SAMPLES_LINE: {"runs": 1}}})
    out = sc.sampled_quantiles(prepared, rows, more, {}, 200, 5)["m"]
    assert (
        out["statements"] == 6 and out["verbalised_not_parsed"] == 1 and out["run"] == {"runs": 1}
    )
    assert out["item_set_fixed_by_the_probe"] == {}
    assert out["probe_excludes_the_statements_before_the_cutoff"] is False
    assert "after_the_cutoff" not in out
    # a primary whose probe beat the base rate: the statements after its cutoff apart, and
    # withheld here, where they are four and the others two
    switched = {"switched": True, "evaluable": False, "reason": "a small slice"}
    sets = {"m": (None, switched | {"cutoff_month_end": "2023-06-30"})}
    again = sc.sampled_quantiles(prepared, rows, more, sets, 200, 5)["m"]
    assert again["item_set_fixed_by_the_probe"] == switched
    assert again["probe_excludes_the_statements_before_the_cutoff"] is True
    assert again["after_the_cutoff"] == {"statements": 4, "withheld": True}
    assert again["pinball"] == out["pinball"] and again["coverage_80"] == out["coverage_80"]
    half = out["pinball"]["0.50"]
    # targets 10, 50, 365, 100 and 100 (the censored one is left out); sampled medians 20, 40,
    # 365, 100, 100: 0.5 * (10 + 10 + 0 + 0 + 0) / 5; verbalised medians 10, 90, 165, 100, 100:
    # 0.5 * (0 + 40 + 200 + 0 + 0) / 5
    assert half["sampled"]["statements"] == 5 and half["sampled"]["left_out_right_censored"] == 1
    assert near(half["sampled"]["loss"], 2.0) and near(half["verbalised"]["loss"], 24.0)
    assert near(half["verbalised_minus_sampled"]["delta"], 22.0)
    assert half["verbalised_minus_sampled"]["statements"] == 5
    # section 4: again where the verbalised answer was parsed and a sample was. One answer of
    # the six was not parsed: the counts of the record would say whether that statement has a
    # target, so it is withheld with them
    assert half["not_parsed_by_both"] is None
    assert half["verbalised_minus_sampled_both_parsed"] == {"not_both_parsed": 1, "withheld": True}
    # at 0.95 with the q95: sampled 50, 80, 365 against 10, 50, 365: 0.05 * (40 + 30) / 5
    assert near(out["pinball"]["0.95"]["sampled"]["loss"], 0.05 * 70 / 5)
    # and verbalised 30, 100, 365: 0.05 * (20 + 50) / 5
    assert near(out["pinball"]["0.95"]["verbalised"]["loss"], 0.05 * 70 / 5)
    assert near(out["pinball"]["0.80"]["sampled"]["loss"], (0.2 * 20 + 0.2 * 10 + 0) / 5)
    # coverage of [q10, q90]: brackets (0, 20], (40, 60], 365, (100, cap] and (95, 105] twice
    # sampled [0, 40] holds the first, [30, 70] the second, [300, 365] the third; [50, 80] lies
    # below the fourth; [90, 110] holds the last two: five inside, one outside
    assert out["coverage_80"]["sampled"] == {
        "inside": 5,
        "outside": 1,
        "bracket_straddles_the_interval": 0,
        "coverage": 5 / 6,
    }
    # verbalised [5, 15] straddles (0, 20]; [35, 99] holds the second; [1, 320] and [0, 3] miss
    assert out["coverage_80"]["verbalised"]["inside"] == 3
    assert out["coverage_80"]["verbalised"]["outside"] == 2
    assert out["coverage_80"]["verbalised"]["bracket_straddles_the_interval"] == 1
    # on four statements, three of them with a target, nothing but counts is written: a loss
    # or a coverage over so few would say where they ended
    few = sc.sampled_scores(rows.iloc[:4], sampled, verbal, pd.Series(True, index=ids), 200, 5)
    assert "coverage_80" not in few and numbers(written(few)) == []
    assert few["pinball"]["0.50"]["sampled"] == {
        "statements": 3,
        "left_out_right_censored": 1,
        "withheld": True,
    }
    assert few["pinball"]["0.50"]["verbalised_minus_sampled"] == {
        "statements": 3,
        "episodes": 2,
        "withheld": True,
    }


CELL_LEVELS = (0.8, 0.6, 0.9, 0.5)
"""The probability each cell of the hand-worked 2x2 gives to both events, in the order of the
reference cell and ``CELLS``."""


def four_cells(
    first_event: Sequence[float] = (1.0, 1.0, 1.0, 1.0, 1.0, np.nan),
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.Series]]:
    """Statements in episodes of two whose second event is yes, with the first events given,
    and the four cells of the 2x2, each with one probability for both events; the first cell
    after the reference fails to parse on the fifth statement."""
    count = len(first_event)
    rows = typed(
        episode_id=[chr(ord("a") + k // 2) for k in range(count)],
        y_a=list(first_event),
        y_b=[1.0] * count,
    )
    ids = list(rows.index)
    names = (sc.REFERENCE_CELL, *sc.CELLS)
    levels = dict(zip(names, CELL_LEVELS, strict=True))
    medians = dict(zip(names, (100, 120, 100, 140), strict=True))
    predictions = {
        name: forecasts(ids, [levels[name]] * count, [levels[name]] * count, medians[name])
        for name in names
    }
    parsed = {name: pd.Series(True, index=ids) for name in names}
    parsed[names[1]] = pd.Series([k != 4 for k in range(count)], index=ids)
    return rows, predictions, parsed


def two_by_two(rows: pd.DataFrame, predictions: dict, parsed: dict) -> dict:
    """``name_date_2x2`` of one model ``m`` on the cells of ``four_cells``."""
    prepared = SimpleNamespace(
        cells={"m": {name: predictions[name] for name in sc.CELLS}},
        cells_parsed={"m": {name: parsed[name] for name in sc.CELLS}},
        cells_runs={"m": {name: {"p_b_below_p_a": 0} for name in sc.CELLS}},
        study=SimpleNamespace(
            predictions={"m:b": predictions[sc.REFERENCE_CELL]},
            parsed={"m:b": parsed[sc.REFERENCE_CELL]},
        ),
    )
    more = SimpleNamespace(ids={"twobytwo": list(rows.index)})
    return sc.name_date_2x2(prepared, rows, more, {}, 200, 5)["m"]


def test_the_scenarios_of_an_effect_of_the_2x2_on_a_case_worked_by_hand() -> None:
    """The two scenarios beside an effect are the effect of the cells' scenario means: a main
    effect is half the sum of two cells less half the sum of the two others, the interaction
    the whole of it. Seven scoreable statements and five that are not, so they are given."""
    rows, predictions, parsed = four_cells([1.0] * 7 + [np.nan] * 5)
    effects = two_by_two(rows, predictions, parsed)["effects_on_primary_loss"]

    def mean(p: float, fill: float) -> float:
        """The mean loss of a cell with the five undetermined events set to ``fill``."""
        return (7 * (1 - p) ** 2 + 5 * ((p - fill) ** 2 + (1 - p) ** 2) / 2) / 12

    for fill, value in (("undetermined_as_yes", 1.0), ("undetermined_as_no", 0.0)):
        real, masked, shifted, both = (mean(p, value) for p in CELL_LEVELS)
        wanted = {
            "names_masked": (masked + both) / 2 - (real + shifted) / 2,
            "dates_shifted": (shifted + both) / 2 - (real + masked) / 2,
            "interaction": (both - shifted) - (masked - real),
        }
        for name, effect in wanted.items():
            bounds = effects[name]["bounds"]
            assert near(bounds[fill], effect), (name, fill)
            assert bounds["statements"] == 12 and bounds["with_a_horizon_event_undetermined"] == 5
    # with every event set to yes the losses are those on the scoreable statements
    assert near(effects["names_masked"]["bounds"]["undetermined_as_yes"], 0.18)
    assert near(effects["names_masked"]["delta"], 0.18)
    assert near(effects["interaction"]["bounds"]["undetermined_as_yes"], 0.12)


def test_the_figures_on_losses_over_three_scoreable_statements_in_two_episodes() -> None:
    """Three scoreable statements in two episodes: a contrast over them is evaluable, and every
    mean loss, every change of a loss, every effect of the 2x2 and every spread across prompts
    is withheld all the same, with its scenarios. What uses no outcome stays."""
    rows, predictions, parsed = four_cells([1.0] * 3 + [np.nan] * 5)
    scoreable = rows[rows["scoreable"]]
    assert len(scoreable) == 3 and scoreable["episode_id"].nunique() == ev.MIN_EPISODES == 2
    pair = (sc.REFERENCE_CELL, next(iter(sc.CELLS)))
    assert ev.scored(rows, predictions, *pair, draws=200, seed=5)["evaluable"] is True
    _, _, means, moved = sc.changes(rows, predictions, parsed, sc.REFERENCE_CELL, 200, 5)
    for entry in means.values():
        assert entry["mean"] is None and entry["withheld"] is True and entry["statements"] == 3
        assert entry["bounds_all_statements"]["withheld"] is True
    for entry in moved.values():
        change = entry["primary_loss"]
        assert change["withheld"] is True and "delta" not in change and change["statements"] == 3
        assert change["bounds"]["withheld"] is True and not set(sc.FILLS) & set(change["bounds"])
        # the change of the probabilities reads no outcome
        assert entry["mean_absolute_change"]["p_E_end"]["mean"] is not None
    assert numbers(written([means, [entry["primary_loss"] for entry in moved.values()]])) == []
    out = two_by_two(rows, predictions, parsed)
    assert out["statements"] == 8 and out["scoreable_statements"] == 3
    for effect in out["effects_on_primary_loss"].values():
        assert effect["withheld"] is True and "delta" not in effect and effect["statements"] == 3
        assert effect["bounds"]["withheld"] is True
    assert numbers(written(out["effects_on_primary_loss"])) == []
    figures = sc.variance_figures(rows, predictions, parsed, sc.REFERENCE_CELL, 200, 5)
    for spread in figures["spread_of_the_mean_primary_loss"].values():
        assert spread["withheld"] is True and spread["bounds"]["withheld"] is True
        assert (spread["range"], spread["sd"], spread["range_ci95"]) == (None, None, None)
    assert numbers(written(figures["spread_of_the_mean_primary_loss"])) == []
    per_statement = figures["spread_across_the_paraphrases_per_statement"]
    assert per_statement["p_E_end"]["statements"] == 8 and per_statement["p_E_end"]["mean"] > 0


def test_the_changes_between_cells_and_their_effects_on_a_case_worked_by_hand() -> None:
    rows, predictions, parsed = four_cells()
    masked, shifted, both = sc.CELLS
    out = two_by_two(rows, predictions, parsed)
    assert out["statements"] == 6 and out["scoreable_statements"] == 5
    assert out["runs"] == {name: {"p_b_below_p_a": 0} for name in sc.CELLS}
    assert out["item_set_fixed_by_the_probe"] == {}
    # with both events yes the loss is (1 - p)^2: 0.04, 0.16, 0.01 and 0.25
    means = {name: entry["mean"] for name, entry in out["primary_brier"].items()}
    assert near(list(means.values()), [0.04, 0.16, 0.01, 0.25])
    change = out["change_from_the_reference_cell"]
    assert near(change[masked]["primary_loss"]["delta"], 0.12)
    assert near(change[shifted]["primary_loss"]["delta"], -0.03)
    assert near(change[both]["primary_loss"]["delta"], 0.21)
    assert change[masked]["primary_loss"]["statements"] == 5
    assert near(change[masked]["mean_absolute_change"]["p_E_end"]["mean"], 0.2)
    assert near(change[shifted]["mean_absolute_change"]["p_E_end90"]["mean"], 0.1)
    assert near(change[both]["mean_absolute_change"]["median_days"]["mean"], 40.0)
    assert change[both]["mean_absolute_change"]["median_days"]["statements"] == 6
    assert change[masked]["mean_absolute_change_both_parsed"]["p_E_end"]["statements"] == 5
    assert change[masked]["not_parsed"] == 1 and change[both]["not_parsed"] == 0
    effects = out["effects_on_primary_loss"]
    # names: (0.16 + 0.25) / 2 - (0.04 + 0.01) / 2; dates: (0.01 + 0.25) / 2 - (0.04 + 0.16) / 2
    assert near(effects["names_masked"]["delta"], 0.18)
    assert near(effects["dates_shifted"]["delta"], 0.03)
    # interaction: (0.25 - 0.01) - (0.16 - 0.04)
    assert near(effects["interaction"]["delta"], 0.12)


def test_prompt_variance_on_a_case_worked_by_hand() -> None:
    rows, _, _ = four_cells()
    ids = list(rows.index)
    levels = {
        "predictive-track-v1": 0.8,
        PARAPHRASES[0]: 0.6,
        PARAPHRASES[1]: 0.7,
        PARAPHRASES[2]: 0.9,
    }
    made = {name: forecasts(ids, [p] * 6, [p] * 6, 100 * p) for name, p in levels.items()}
    parsed = {name: pd.Series(True, index=ids) for name in levels}
    prepared = SimpleNamespace(
        paraphrases={"m": {name: made[name] for name in PARAPHRASES}},
        paraphrases_parsed={"m": {name: parsed[name] for name in PARAPHRASES}},
        paraphrases_runs={"m": {name: {"p_b_below_p_a": 0} for name in PARAPHRASES}},
        study=SimpleNamespace(
            predictions={"m:b": made["predictive-track-v1"]},
            parsed={"m:b": parsed["predictive-track-v1"]},
            first=pd.DataFrame({"event_date": "2023-03-01"}, index=ids),
        ),
    )
    more = SimpleNamespace(ids={"paraphrase": ids})
    out = sc.prompt_variance(prepared, rows, more, {}, 200, 5)["m"]
    assert out["runs"] == prepared.paraphrases_runs["m"]
    # losses (1 - p)^2: 0.04 for the registered prompt; 0.16, 0.09 and 0.01 for the paraphrases
    assert near(
        [entry["mean"] for entry in out["primary_brier"].values()], [0.04, 0.16, 0.09, 0.01]
    )
    spread = out["spread_of_the_mean_primary_loss"]
    assert spread["paraphrases"]["prompts"] == 3 and near(spread["paraphrases"]["range"], 0.15)
    assert near(spread["paraphrases"]["sd"], float(np.std([0.16, 0.09, 0.01], ddof=1)))
    assert spread["with_the_registered_prompt"]["prompts"] == 4
    assert near(
        spread["with_the_registered_prompt"]["sd"], float(np.std([0.04, 0.16, 0.09, 0.01], ddof=1))
    )
    assert near(spread["paraphrases"]["range_ci95"], [0.15, 0.15])
    per_statement = out["spread_across_the_paraphrases_per_statement"]
    # each statement has 0.6, 0.7 and 0.9 across the paraphrases
    assert near(per_statement["p_E_end"]["mean"], float(np.std([0.6, 0.7, 0.9], ddof=1)))
    assert near(per_statement["median_days"]["mean"], float(np.std([60, 70, 90], ddof=1)))
    assert per_statement["p_E_end90"]["statements"] == 6
    change = out["change_from_the_registered_prompt"]
    assert near(change[PARAPHRASES[0]]["primary_loss"]["delta"], 0.12)
    assert near(change[PARAPHRASES[2]]["mean_absolute_change"]["p_E_end"]["mean"], 0.1)


def test_the_interval_of_the_range_across_prompts_is_a_95_percent_percentile_interval() -> None:
    """The range of the mean loss across the paraphrases, drawn again for each registered draw
    of the episodes: eleven episodes of unequal size, so that the level and the seed show."""
    sizes = [1, 2, 3, 4, 5, 6, 2, 3, 4, 1, 5]
    episodes = [f"e{k}" for k, size in enumerate(sizes) for _ in range(size)]
    count = len(episodes)
    rng = np.random.default_rng(3)
    rows = typed(
        episode_id=episodes, y_a=(rng.random(count) < 0.5).astype(float), y_b=[1.0] * count
    )
    ids = list(rows.index)
    names = ["predictive-track-v1", *PARAPHRASES]
    made = {
        name: forecasts(
            ids, np.round(rng.random(count), 2), np.round(0.5 + rng.random(count) / 2, 2)
        )
        for name in names
    }
    parsed = {name: pd.Series(True, index=ids) for name in names}
    out = sc.variance_figures(rows, made, parsed, names[0], 2000, 5)
    loss = np.stack([brier(made[name], rows).to_numpy() for name in PARAPHRASES], axis=1)
    codes = pd.Categorical(rows["episode_id"]).codes
    sums = np.stack([np.bincount(codes, weights=loss[:, j]) for j in range(3)], axis=1)
    weights = np.bincount(codes).astype(float)

    def ends(seed: int, level: float) -> list[float]:
        taken = P.cluster_draws(len(sizes), 2000, seed).astype(float)
        drawn = (taken @ sums) / (taken @ weights)[:, None]
        spread = drawn.max(axis=1) - drawn.min(axis=1)
        return [float(end) for end in np.quantile(spread, [(1 - level) / 2, (1 + level) / 2])]

    got = out["spread_of_the_mean_primary_loss"]["paraphrases"]
    assert near(got["range_ci95"], ends(5, 0.95), 1e-12)
    assert not near(got["range_ci95"], ends(5, 0.90), 1e-4)
    assert not near(got["range_ci95"], ends(6, 0.95), 1e-4)
    assert near(got["range"], float(np.ptp(loss.mean(axis=0))), 1e-12)
    # the spread of each statement across the paraphrases, for the two probabilities and the
    # median: the standard deviation over the three, averaged over the statements
    per_statement = out["spread_across_the_paraphrases_per_statement"]
    for label, column in (("p_E_end", "p_a"), ("p_E_end90", "p_b"), ("median_days", "q50")):
        across = np.stack([made[name][column].to_numpy() for name in PARAPHRASES])
        assert near(per_statement[label]["mean"], across.std(axis=0, ddof=1).mean(), 1e-12), label


def test_the_hold_rate_by_revision_bucket_and_the_levels_of_the_widths() -> None:
    rows = typed(
        episode_id=list("aabbccddeeff"),
        analysis_set=["dated"] * 12,
        outcome=["recovered"] * 12,
        lower_days=[1.0] * 12,
        upper_days=[9.0] * 12,
        end_days=[30.0] * 12,
        y_a=[1.0] * 6 + [0.0] * 6,
        form=["month_year"] * 12,
        revision=["first"] * 6 + ["second"] * 6,
    )
    first = pd.DataFrame(
        {"event_date": "2021-05-15", "statement_type": "recovery", "company_name": "Acme"},
        index=rows.index,
    )
    by_revision = sc.descriptives(rows, first, 100, 0, 1, beside={})["hold_rate"]["by_revision"]
    assert list(by_revision) == list(P.REVISIONS) == ["first", "second", "third or later"]
    assert by_revision["first"]["among_determined"]["mean"] == 1.0
    assert by_revision["second"]["among_determined"]["mean"] == 0.0
    assert by_revision["third or later"]["statements"] == 0
    # the quantiles of the bracket widths, at their five levels
    wide = typed(
        episode_id=list("abcdefgh"),
        outcome=["recovered"] * 8,
        lower_days=[0.0] * 8,
        upper_days=[1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0],
    )
    record = sc.width_record(wide, 100, 1)
    width = np.array([1.0, 2, 4, 8, 16, 32, 64, 128])
    assert list(record["quantiles_days"]) == ["0.10", "0.25", "0.50", "0.75", "0.90"]
    for level in sc.WIDTH_LEVELS:
        assert near(record["quantiles_days"][f"{level:.2f}"], np.quantile(width, level), 1e-12)


def test_the_hold_rate_and_its_bounds_on_a_case_worked_by_hand() -> None:
    rows = typed(
        episode_id=["a", "a", "b", "b", "c", "c", "d"],
        y_a=[1.0, 0.0, np.nan, 1.0, np.nan, 0.0, 1.0],
    )
    record = sc.hold_record(rows, 300, 1)
    assert (record["statements"], record["determined"], record["undetermined"]) == (7, 5, 2)
    assert near(record["among_determined"]["mean"], 3 / 5)
    assert near(record["undetermined_as_no"]["mean"], 3 / 7)
    assert near(record["undetermined_as_yes"]["mean"], 5 / 7)
    assert record["among_determined"]["episodes"] == 4
    # three determined statements: the share among them is withheld, and the two shares over all
    # five with it, which times five are the number of the three that held
    few = sc.hold_record(rows.iloc[:5], 300, 1)
    assert (few["statements"], few["determined"], few["undetermined"]) == (5, 3, 2)
    for share in sc.HOLD_SHARES:
        assert few[share]["mean"] is None and few[share]["ci95"] is None
        assert few[share]["withheld"] is True


def written(record: Any) -> Any:
    """A record as a result file holds it: six decimals, nulls."""
    return json.loads(ev.report_text(record))


@pytest.mark.parametrize("side", ["abstained_on", "read"])
@pytest.mark.parametrize("few", [1, 2, 3, 4])
def test_a_part_of_selective_prediction_withheld_cannot_be_worked_out(side: str, few: int) -> None:
    """The two parts add up to the whole, whose loss is given: a part of one to four statements
    is withheld, and the other part with it."""
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(14)],
        y_a=[0.0, 1.0] * 7,
        y_b=[1.0] * 10 + [0.0, 1.0, 0.0, 1.0],
    )
    pred = forecasts(rows.index, np.linspace(0.2, 0.7, 14), np.linspace(0.5, 0.9, 14))
    days = pd.Series(10.0, index=rows.index)
    if side == "abstained_on":
        days.iloc[:few] = np.nan
    else:
        days.iloc[few:] = np.nan
    record = written(sc.selective(rows, pred, days, 50, 1))
    other = "read" if side == "abstained_on" else "abstained_on"
    part, rest, whole = (record[f"primary_brier_{name}"] for name in (side, other, "all"))
    assert whole["mean"] is not None and "withheld" not in whole
    # which statements a reader abstains on is open: of a part of a few, not even the number
    # of the scoreable ones is written, nor that of the other part, which the whole would give
    assert held_parts(record, days.notna().to_numpy(), rows["scoreable"].to_numpy()) == "bare"
    assert part == BARE_PART | {"bounds_all_statements": {"statements": few, "withheld": True}}
    assert rest["bounds_all_statements"] == {"statements": 14 - few, "withheld": True}
    # the same with a part of five statements of which fewer are scoreable
    rows.loc[rows.index[:2], "y_b"] = np.nan
    rows["scoreable"] = rows["y_a"].notna() & rows["y_b"].notna()
    days = pd.Series(10.0, index=rows.index)
    days.iloc[:5] = np.nan
    record = written(sc.selective(rows, pred, days, 50, 1))
    assert record["abstained"] == 5 and record["primary_brier_abstained_on"]["statements"] == 3
    assert record["primary_brier_read"]["mean"] is None and record["primary_brier_read"]["withheld"]


@pytest.mark.parametrize("determined", [1, 2, 3, 4])
def test_a_hold_rate_withheld_cannot_be_worked_out_from_its_bounds(determined: int) -> None:
    """A share over all statements, times their number, is the number that held among the
    determined ones: with one to four of those, all three shares are withheld."""
    held = [1.0, 0.0, 1.0, 1.0][:determined] + [np.nan] * (8 - determined)
    rows = typed(episode_id=[f"e{k // 2}" for k in range(8)], y_a=held)
    record = written(sc.hold_record(rows, 50, 1))
    assert (record["statements"], record["determined"]) == (8, determined)
    for share in sc.HOLD_SHARES:
        assert record[share]["mean"] is None and record[share]["withheld"] is True
    assert set(record) == {"statements", "determined", "undetermined", *sc.HOLD_SHARES}


def hidden_in(cells: dict[str, dict], determined: dict[str, int] | None = None) -> int:
    """The determined statements of the cells of a split whose hold rate is withheld
    (``determined``: by cell, where the cells do not all say)."""
    return sum(
        cell["determined"] if determined is None else determined[name]
        for name, cell in cells.items()
        if cell["among_determined"]["mean"] is None
    )


@pytest.mark.parametrize("lone", [("week",), ("week", "exact_day"), ("week", "exact_day", "year")])
def test_a_cell_withheld_cannot_be_worked_out_from_the_total(lone: tuple[str, ...]) -> None:
    """The cells of a split add up to the hold rate of all dated forms: the withheld cells hold
    no determined statement, or five or more together."""
    forms = ["month_year"] * 8 + ["quarter"] * 6 + list(lone)
    size = len(forms)
    held = np.array(
        [1.0, 0.0, 1.0, 1.0, 0.0, np.nan, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, np.nan]
        + [1.0] * len(lone)
    )
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(size)],
        analysis_set=["dated"] * size,
        outcome=["recovered"] * size,
        lower_days=np.where(held == 1.0, 20.0, np.where(held == 0.0, 50.0, 10.0)),
        upper_days=np.where(held == 1.0, 25.0, np.where(held == 0.0, 55.0, 60.0)),
        end_days=[30.0] * size,
        y_a=held,
    )
    rows["form"] = forms
    rows["revision"] = ["first"] * (size - len(lone)) + ["second"] * len(lone)
    first = pd.DataFrame(
        {"event_date": "2021-05-15", "statement_type": "recovery", "company_name": "Acme"},
        index=rows.index,
    )
    hold = written(sc.descriptives(rows, first, 50, 3, 1, beside={}))["hold_rate"]
    assert hold["all_dated_forms"]["among_determined"]["mean"] is not None
    for split in ("by_form", "by_revision"):
        cells = hold[split]
        column = "form" if split == "by_form" else "revision"
        truly = rows.groupby(column)["y_a"].count().to_dict() | {"third or later": 0}
        assert hidden_in(cells, truly) >= sc.MIN_SHOWN, split
        # a cell of one to four statements keeps their number alone, and one more cell of
        # the split with it: the counts of a split add up to those of all dated statements
        bare = [name for name, cell in cells.items() if cell["determined"] is None]
        tiny = [name for name, cell in cells.items() if 0 < cell["statements"] < sc.MIN_SHOWN]
        assert set(tiny) <= set(bare) and len(tiny) == (len(lone) if split == "by_form" else 1)
        assert sum(cells[name]["statements"] for name in bare) >= sc.MIN_SHOWN
        for name in bare:
            assert cells[name]["undetermined"] is None and numbers(cells[name]) == []
            assert all(cells[name][share] == BARE_PART for share in sc.HOLD_SHARES)
        # the lone cells, and with them the cell shown with the fewest determined statements
        # (the revision bucket of all the others, in that split)
        partner = [name for name, cell in cells.items() if cell.get(sc.WITH_ANOTHER)]
        assert partner == ["quarter" if split == "by_form" else "first"]
        assert sc.NEAR_SET not in json.dumps(cells)
        for share in sc.HOLD_SHARES:
            assert cells[partner[0]][share]["mean"] is None
            assert cells[partner[0]][share]["withheld"] is True
    assert hold["by_form"]["month_year"]["among_determined"]["mean"] is not None
    # five determined statements in the withheld cells together: no partner is needed

    def table(**events: list[float]) -> tuple[dict, dict]:
        """The hold rates by form of statements with these events, and each form's alone."""
        frame = typed(
            episode_id=[f"{form}{k}" for form, held in events.items() for k in range(len(held))],
            y_a=[event for held in events.values() for event in held],
        )
        frame["form"] = [form for form, held in events.items() for _ in held]
        cells = {form: frame[frame["form"] == form] for form in events}
        alone = {form: written(sc.hold_record(cell, 50, 1)) for form, cell in cells.items()}
        return written(sc.hold_tables(frame, {"by_form": cells}, 50, 1))["by_form"], alone

    six = [1.0, 0.0] * 3
    kept, cells = table(a=[1.0, 0.0, 1.0], b=[1.0, 0.0], c=six, d=[np.nan, np.nan])
    assert kept["c"] == cells["c"] and sc.WITH_ANOTHER not in json.dumps(kept)
    for name in "abd":  # of a few statements, their number alone
        assert kept[name] == {
            "statements": cells[name]["statements"],
            "determined": None,
            "undetermined": None,
            **dict.fromkeys(sc.HOLD_SHARES, BARE_PART),
        }
    # four determined statements in the cells withheld: the total less the cell shown would
    # give how many of the four held, so that cell's shares are withheld with theirs
    kept, cells = table(b=[1.0, 0.0], c=six, d=[np.nan, np.nan], e=[1.0], f=[0.0])
    assert kept["c"][sc.WITH_ANOTHER] is True and kept["c"]["determined"] == 6
    assert kept["c"]["among_determined"]["mean"] is None and numbers(kept) == []
    assert sc.WITH_ANOTHER not in kept["b"] and kept["d"]["determined"] is None
    # one cell of a few statements, none of them determined: its counts are withheld, and
    # those of a second cell, or all dated statements less the others would give them
    kept, cells = table(c=six, d=[np.nan, np.nan], g=six)
    assert kept["d"]["determined"] is None and kept["c"]["determined"] is None
    assert kept["c"][sc.WITH_ANOTHER] is True and kept["g"] == cells["g"]
    # two cells of a few statements, four together: the same, though neither is alone
    kept, cells = table(c=six, d=[np.nan, 1.0], g=six, h=[0.0, np.nan])
    assert [name for name in kept if kept[name]["determined"] is None] == ["c", "d", "h"]
    assert kept["c"][sc.WITH_ANOTHER] is True and kept["g"] == cells["g"]


def dated_by_type(
    kinds: Sequence[str], held: Sequence[float], forms: Sequence[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dated statements of the types ``kinds`` whose stated period held (1), did not (0) or is
    not determined (missing), in episodes of two, with the first-sight cells the descriptives
    read. A statement that held recovered 5 to 10 days before the stated end; one that did not,
    20 to 25 days after it; an undetermined one between 20 days before and 30 days after."""
    held = np.asarray(held, dtype=float)
    count = len(held)
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(count)],
        analysis_set=["dated"] * count,
        outcome=["recovered"] * count,
        lower_days=np.where(held == 1.0, 20.0, np.where(held == 0.0, 50.0, 10.0)),
        upper_days=np.where(held == 1.0, 25.0, np.where(held == 0.0, 55.0, 60.0)),
        end_days=[30.0] * count,
        y_a=held,
    )
    rows["form"] = list(forms) if forms is not None else ["month_year"] * count
    rows["revision"] = "first"
    first = pd.DataFrame(
        {
            "event_date": "2021-05-15",
            "statement_type": list(kinds),
            "company_name": "Acme",
        },
        index=rows.index,
    )
    return rows, first


def test_the_hold_rate_and_the_slip_by_statement_type_on_a_case_worked_by_hand() -> None:
    """PLAN section 5, E1: the hold rate "over all dated statements and by statement type";
    the slip distribution "by form, by statement type and by revision bucket". Six recovery
    statements of which four held, and eight next-delivery statements of which three held,
    three did not and two are not determined."""
    kinds = ["recovery"] * 6 + ["next_delivery"] * 8
    held = [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, np.nan, np.nan]
    rows, first = dated_by_type(kinds, held)
    got = written(sc.descriptives(rows, first, 200, 3, 1, beside={}))
    hold, slip = got["hold_rate"], got["slip"]
    # the two tables hold their splits in one order, the plan's for the slip
    order = ["all_dated_forms", "by_form", "by_statement_type", "by_revision"]
    assert list(hold) == order and list(slip) == order
    assert list(hold["by_statement_type"]) == list(slip["by_statement_type"]) == list(sc.TYPES)
    back, due = hold["by_statement_type"]["recovery"], hold["by_statement_type"]["next_delivery"]
    assert (back["statements"], back["determined"], back["undetermined"]) == (6, 6, 0)
    assert near(back["among_determined"]["mean"], 4 / 6)
    assert near(back["undetermined_as_no"]["mean"], 4 / 6)
    assert (due["statements"], due["determined"], due["undetermined"]) == (8, 6, 2)
    assert near(due["among_determined"]["mean"], 3 / 6)
    assert near(due["undetermined_as_no"]["mean"], 3 / 8)
    assert near(due["undetermined_as_yes"]["mean"], 5 / 8)
    assert near(hold["all_dated_forms"]["among_determined"]["mean"], 7 / 12)
    assert hold["by_form"]["month_year"] == hold["all_dated_forms"]  # one form: the same set
    for cell in (back, due):
        assert set(cell) == HOLD_KEYS and sc.WITH_ANOTHER not in cell and sc.NEAR_SET not in cell
    # the slip of a type: the share recovered by the stated end is the share that held; an
    # undetermined statement is shared out as the others of its type fall (3 of 6, so 1/2)
    by_day = "share_recovered_by_days_after_the_stated_end"
    shares = {name: cell[by_day] for name, cell in slip["by_statement_type"].items()}
    assert near(shares["recovery"]["0"], 4 / 6, 1e-4) and near(shares["recovery"]["30"], 1.0, 1e-4)
    assert near(shares["next_delivery"]["-30"], 0.0, 1e-4)
    for name, cell in slip["by_statement_type"].items():
        assert cell["statements"] == (6 if name == "recovery" else 8)
        assert cell["draws"] == 3 and len(cell["ci95"]) == len(sc.SLIP_DAYS)
        # the estimate of a cell is the one of ``slip_record`` on its statements
        part = rows[(first["statement_type"] == name).to_numpy()]
        alone = written(sc.slip_record(part, 3, 1))
        assert set(alone) == SLIP_KEYS
        if name == "recovery":
            assert cell == alone
            continue
        # two of the eight next-delivery statements are not determined: the share by the
        # stated end, times eight, less the three that held, would be what the estimate
        # puts before the stated end for those two; it is withheld, and nothing else is
        assert near(alone[by_day]["0"], 0.5, 1e-4) and alone["ci95"]["0"] is not None
        assert cell[sc.SHARES_WITHHELD] == ["0"]
        assert cell[by_day]["0"] is None and cell["ci95"]["0"] is None
        alone[by_day]["0"] = alone["ci95"]["0"] = None
        assert cell == alone | {sc.SHARES_WITHHELD: ["0"]}
    whole = slip["all_dated_forms"]
    assert whole[by_day]["0"] is None and whole[sc.SHARES_WITHHELD] == ["0"]
    assert near(sc.slip_record(rows, 3, 1)[by_day]["0"], 7 / 12, 1e-4)
    # a list of one type: its cell is the whole, and the other type holds no statement
    alone, cells = dated_by_type(["recovery"] * 14, held)
    one = written(sc.descriptives(alone, cells, 200, 3, 1, beside={}))
    assert one["hold_rate"]["by_statement_type"]["recovery"] == one["hold_rate"]["all_dated_forms"]
    assert one["hold_rate"]["by_statement_type"]["next_delivery"]["statements"] == 0
    assert one["slip"]["by_statement_type"]["next_delivery"] == {
        "statements": 0,
        "episodes": 0,
        "withheld": False,
    }


@pytest.mark.parametrize("few", [1, 3, 4, 5])
def test_a_statement_type_of_a_few_statements_in_the_tables_of_the_descriptives(few: int) -> None:
    """ "In the tables of the hold rate and of the slip, a further cell is withheld and marked
    where the cells written and the whole would otherwise give back the figure on 1 to 4
    statements." A type of one to four dated statements: its cell keeps their number alone,
    and the cell of the other type goes with it, or the whole less that cell would be the
    few."""
    kinds = ["recovery"] * 12 + ["next_delivery"] * few
    held = ([1.0, 0.0, 1.0, 1.0] * 5)[: 12 + few]
    rows, first = dated_by_type(kinds, held)
    got = written(sc.descriptives(rows, first, 100, 3, 1, beside={}))
    hold, slip = got["hold_rate"]["by_statement_type"], got["slip"]["by_statement_type"]
    assert (hold["recovery"]["statements"], hold["next_delivery"]["statements"]) == (12, few)
    assert got["hold_rate"]["all_dated_forms"]["among_determined"]["mean"] is not None
    assert "withheld" not in got["slip"]["all_dated_forms"]
    if few >= sc.MIN_SHOWN:
        assert numbers(hold["recovery"]) and numbers(hold["next_delivery"])
        assert "withheld" not in json.dumps(slip) and sc.WITH_ANOTHER not in json.dumps(hold)
        return
    for cell in hold.values():
        assert cell["determined"] is None and cell["undetermined"] is None
        assert all(cell[share] == BARE_PART for share in sc.HOLD_SHARES)
    assert (
        hold["recovery"][sc.WITH_ANOTHER] is True and sc.WITH_ANOTHER not in hold["next_delivery"]
    )
    assert numbers(hold) == [] and numbers(slip) == []
    assert slip["next_delivery"] == {
        "statements": few,
        "episodes": slip["next_delivery"]["episodes"],
        "withheld": True,
    }
    assert slip["recovery"] == {
        "statements": 12,
        "episodes": 6,
        "withheld": True,
        sc.WITH_ANOTHER: True,
    }


def bare_cells(hold: dict, slip: dict) -> tuple[list[str], list[str]]:
    """The cells of the splits of the two tables of E1 that keep the number of their statements
    alone: in the hold table, and in the slip table."""
    by_day = "share_recovered_by_days_after_the_stated_end"
    splits = [name for name in hold if name != "all_dated_forms"]
    assert splits == [name for name in slip if name != "all_dated_forms"]
    in_hold = [
        f"{split}/{name}"
        for split in splits
        for name, cell in hold[split].items()
        if cell["statements"] and cell["determined"] is None
    ]
    in_slip = [
        f"{split}/{name}"
        for split in splits
        for name, cell in slip[split].items()
        if cell["statements"] and by_day not in cell
    ]
    return in_hold, in_slip


@pytest.mark.parametrize("between", [1, 2, 4])
def test_a_statement_type_that_is_a_form_but_for_a_few_statements(between: int) -> None:
    """A cell of the split by statement type beside a cell of the split by form (PLAN, standing
    rules; section 5, E1): the next-delivery statements are those of the quarter form and one
    to four more. Of two splits the later one gives way, the same in both tables: the share
    recovered by the stated end of a slip estimate is the hold rate where no bracket holds the
    stated end, so a type kept by one table and a form kept by the other would give the few
    back."""
    kinds = ["recovery"] * 9 + ["next_delivery"] * (11 + between)
    forms = ["month_year"] * (9 + between) + ["quarter"] * 11
    held = np.random.default_rng(between).integers(0, 2, len(kinds)).astype(float)
    rows, first = dated_by_type(kinds, held, forms)
    got = written(sc.descriptives(rows, first, 100, 3, 1, beside={}))
    hold, slip = got["hold_rate"], got["slip"]
    by_day = "share_recovered_by_days_after_the_stated_end"
    for table in (hold, slip):
        assert numbers(table["by_form"]["quarter"]) and numbers(table["by_form"]["month_year"])
        assert numbers(table["by_statement_type"]) == []
        marks = [
            mark
            for cell in table["by_statement_type"].values()
            for mark in cell
            if mark in (sc.NEAR_SET, sc.WITH_ANOTHER)
        ]
        assert sorted(marks) == sorted([sc.NEAR_SET, sc.WITH_ANOTHER])
    in_hold, in_slip = bare_cells(hold, slip)
    assert in_hold == in_slip == ["by_statement_type/recovery", "by_statement_type/next_delivery"]
    # what the two tables together would have given: the statements of the type that held,
    # less the share of the form recovered by the stated end times its statements
    assert by_day in slip["by_form"]["quarter"]
    assert hold["by_statement_type"]["next_delivery"]["undetermined_as_no"] == BARE_PART
    # five statements apart: every cell of the three splits is written
    kinds = ["recovery"] * 5 + ["next_delivery"] * 16
    forms = ["month_year"] * 10 + ["quarter"] * 11
    rows, first = dated_by_type(kinds, [1.0, 0.0, 1.0] * 7, forms)
    got = written(sc.descriptives(rows, first, 100, 3, 1, beside={}))
    assert '"withheld": true' not in json.dumps(got["hold_rate"]) + json.dumps(got["slip"])


def test_the_two_tables_of_the_descriptives_withhold_the_same_cells_for_their_statements() -> None:
    """A form of three statements keeps their number alone, and a further cell goes with it,
    or the whole less the cells written would give the three back. The further cell is the
    one of the fewest statements in the hold table as in the slip table: were it the one of
    the fewest determined statements in the first, each table would write the cell the other
    withholds, and the two together would give the three."""
    forms = ["month"] * 3 + ["quarter"] * 10 + ["year"] * 8
    held = [1.0, 0.0, 1.0] + [1.0, 0.0, 1.0, 0.0, 1.0, 0.0] + [np.nan] * 4 + [1.0, 0.0] * 4
    rows, first = dated_by_type(["recovery"] * 21, held, forms)
    got = written(sc.descriptives(rows, first, 100, 3, 1, beside={}))
    hold, slip = got["hold_rate"], got["slip"]
    assert hold["by_form"]["quarter"]["determined"] == 6  # fewer than the eight of the year form
    in_hold, in_slip = bare_cells(hold, slip)
    assert in_hold == in_slip == ["by_form/month", "by_form/year"]
    assert hold["by_form"]["year"][sc.WITH_ANOTHER] is True
    assert slip["by_form"]["year"][sc.WITH_ANOTHER] is True
    assert numbers(hold["by_form"]["quarter"]) and numbers(slip["by_form"]["quarter"])


def item_set_among_dated(
    count: int, listed: int, forms: Sequence[str] | None = None
) -> tuple[SimpleNamespace, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """``count`` dated statements at risk, of which the first ``listed`` are the item set of a
    primary ``m``: five of every eight held. Condition (a) gives each statement its own
    probability of the first event and the base rate one half. Returns the prepared study,
    the statements of the item set, every statement, the first-sight cells and the item
    sets."""
    held = ([1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0] * count)[:count]
    everything, first = dated_by_type(["recovery"] * count, held, forms)
    rows = everything.iloc[:listed]
    ids = rows.index
    study = SimpleNamespace(
        predictions={
            "m:a": forecasts(ids, np.linspace(0.6, 0.95, listed), [0.9] * listed),
            ev.BASE: forecasts(ids, [0.5] * listed, [0.6] * listed),
        }
    )
    sets = {"m": (ids, {"switched": False, "evaluable": True, "items": ev.ALL_ITEMS})}
    return SimpleNamespace(study=study), rows, everything, first, sets


def test_the_mean_probability_less_the_turnbull_share_on_a_case_worked_by_hand() -> None:
    """PLAN section 13, "Reported beside it, for condition (a) and for the base rate on the same
    statements: ... the mean of P(E_end) minus the Turnbull share recovered by the stated end".
    Sixteen statements of an item set, ten of which recovered before the stated end and six
    after it: with every bracket on one side of the stated end the Turnbull share is the
    share that held, in the item set and in each draw of its episodes."""
    prepared, rows, everything, _, sets = item_set_among_dated(24, 16)
    got = written(sc.beside_the_criterion(prepared, rows, sets, 40, 3))["m"]
    held = rows["y_a"].to_numpy()
    assert held.sum() == 10 and len(everything) == 24
    assert got["item_set_fixed_by_the_probe"]["items"] == ev.ALL_ITEMS
    assert (got["statements"], got["episodes"], got["draws"]) == (16, 8, 40)
    assert near(got["turnbull_share_recovered_by_the_stated_end"], 10 / 16, 1e-5)
    p = prepared.study.predictions["m:a"]["p_a"].to_numpy()
    assert near(got["condition_a"]["mean_p_E_end"], p.mean())
    assert near(got["condition_a"]["mean_p_minus_the_turnbull_share"], p.mean() - 10 / 16, 1e-5)
    assert near(got["base_rate"]["mean_p_E_end"], 0.5)
    assert near(got["base_rate"]["mean_p_minus_the_turnbull_share"], 0.5 - 10 / 16, 1e-5)
    assert set(got["condition_a"]) == {"mean_p_E_end", "mean_p_minus_the_turnbull_share", "ci95"}
    # the interval: the first 40 of the registered draws of the eight episodes, the mean
    # probability and the share that held taken from the same draw
    taken = P.cluster_draws(8, ev.DRAWS, 3)[:40].astype(float)
    weights = np.repeat(taken, 2, axis=1)  # each episode holds two statements
    share = (weights @ held) / weights.sum(axis=1)
    for name, values in (("condition_a", p), ("base_rate", np.full(16, 0.5))):
        drawn = (weights @ values) / weights.sum(axis=1) - share
        wanted = [float(end) for end in np.quantile(drawn, [0.025, 0.975])]
        assert near(got[name]["ci95"], wanted, 1e-5), name
    assert got["base_rate"]["ci95"][0] < 0.5 - 10 / 16 < got["base_rate"]["ci95"][1]
    # the function behind it: the share, the share in each draw, and how often each statement
    # is taken; in one episode there is no draw and no interval
    share_all, drawn, counts = sc.turnbull_shares(rows, 40, 3)
    assert near(share_all, 10 / 16, 1e-5) and near(list(drawn), list(share), 1e-5)
    assert counts.shape == (40, 16) and (counts == weights).all()
    alone = rows.assign(episode_id="e")
    assert len(sc.turnbull_shares(alone, 40, 3)[1]) == 0
    one = sc.beside_the_criterion(prepared, alone, sets, 40, 3)["m"]
    assert one["draws"] == 0 and one["condition_a"]["ci95"] is None
    assert near(one["condition_a"]["mean_p_minus_the_turnbull_share"], p.mean() - 10 / 16, 1e-5)
    # a primary without an item set has the record of its item set alone
    none = {"m": (None, {"switched": True, "evaluable": False, "reason": "too few"})}
    assert sc.beside_the_criterion(prepared, rows, none, 40, 3) == {
        "m": {
            "item_set_fixed_by_the_probe": {
                "switched": True,
                "evaluable": False,
                "reason": "too few",
            }
        }
    }


BY_DAY = "share_recovered_by_days_after_the_stated_end"


def near_in_a_table(
    table: dict, dated: pd.DataFrame, first: pd.DataFrame, other: pd.Index, slip: bool
) -> list[str]:
    """Every set on which a table of E1 gives its figure (``table``: the hold table, or with
    ``slip`` the slip table, as written): all dated statements, a union of the cells written
    of one split and, beside the whole, the rest of the split. Those of them that are the
    statements ``other`` but for one to four are named. Worked out here, cell by cell."""

    def shown(record: dict) -> bool:
        if not record["statements"]:
            return False
        return BY_DAY in record if slip else record["determined"] is not None

    found = []
    whole = shown(table["all_dated_forms"])
    if whole and 0 < len(dated.index.symmetric_difference(other)) < sc.MIN_SHOWN:
        found.append("all_dated_forms")
    for split, cells in sc.dated_splits(dated, first).items():
        groups = {name: set(cells[name].index) for name in cells if shown(table[split][name])}
        rest = set(dated.index) - set().union(*groups.values())
        if whole and rest:
            groups["the rest"] = rest
        names = list(groups)
        for size in range(1, len(names) + 1):
            for chosen in itertools.combinations(names, size):
                union = set().union(*(groups[name] for name in chosen))
                if 0 < len(union ^ set(other)) < sc.MIN_SHOWN:
                    found.append(f"{split}: {' + '.join(chosen)}")
    return found


@pytest.mark.parametrize(
    ("count", "listed", "forms", "withheld"),
    [
        (24, 16, None, []),
        (16, 16, None, []),  # the item set is every dated statement: the same set
        # every dated statement but two: the whole, and the cells that are the whole
        (18, 16, None, ["all", "by_form/month_year", "by_statement_type/recovery", "first"]),
        (20, 16, None, ["all", "by_form/month_year", "by_statement_type/recovery", "first"]),
        (21, 16, None, []),  # but five
        # the item set is the statements of a form and three more: that form, and the other
        # with it, or the whole less the other would be the form
        (30, 16, ["quarter"] * 13 + ["month_year"] * 17, ["by_form/month_year", "by_form/quarter"]),
        (30, 16, ["quarter"] * 11 + ["month_year"] * 19, []),
        # two forms together are the item set and two statements more: one of the two, and
        # the third form with it
        (
            30,
            16,
            ["half"] * 9 + ["quarter"] * 9 + ["month_year"] * 12,
            ["by_form/half", "by_form/month_year"],
        ),
    ],
)
def test_the_tables_of_the_descriptives_give_way_to_an_item_set(
    count: int, listed: int, forms: list[str] | None, withheld: list[str]
) -> None:
    """The evaluator writes the frequency of the first event on the item set of a primary, and
    this file the Turnbull share: the tables of E1 hold the same figures on all dated
    statements and on the cells of their splits. A cell, the whole, or a set of cells with
    the whole, that is the item set but for one to four statements is withheld and marked, in
    the hold table and in the slip table alike (PLAN, standing rules; section 5, E1); the
    share beside the criterion stays."""
    prepared, rows, everything, first, sets = item_set_among_dated(count, listed, forms)
    beside = {"the item set of m": rows.index}
    got = written(sc.descriptives(everything, first, 100, 3, 3, beside=beside))
    hold, slip = got["hold_rate"], got["slip"]
    in_hold, in_slip = bare_cells(hold, slip)
    whole = ["all"] if hold["all_dated_forms"]["determined"] is None else []
    assert whole == (["all"] if BY_DAY not in slip["all_dated_forms"] else [])
    wanted = [name.replace("first", "by_revision/first") for name in withheld]
    assert whole + in_hold == whole + in_slip == wanted
    if whole:
        assert hold["all_dated_forms"][sc.NEAR_SET] is True
        assert slip["all_dated_forms"] == {
            "statements": count,
            "episodes": slip["all_dated_forms"]["episodes"],
            "withheld": True,
            sc.NEAR_SET: True,
        }
        assert numbers(hold) == [] and numbers(slip) == []
    # nothing that the tables still give is the item set but for a few statements
    for table, of_slip in ((hold, False), (slip, True)):
        assert near_in_a_table(table, everything, first, rows.index, of_slip) == []
        marks = [
            mark
            for cells in (table[split] for split in table if split != "all_dated_forms")
            for cell in cells.values()
            for mark in cell
            if mark in (sc.NEAR_SET, sc.WITH_ANOTHER)
        ]
        assert len(marks) == len(wanted) - len(whole)
    # without the item set beside them the tables are whole, and the item set is near them
    alone = written(sc.descriptives(everything, first, 100, 3, 3, beside={}))
    assert '"withheld": true' not in json.dumps(alone["hold_rate"]) + json.dumps(alone["slip"])
    near_it = near_in_a_table(alone["slip"], everything, first, rows.index, True)
    assert bool(near_it) == bool(withheld)
    # the share beside the criterion is written in every case
    share = written(sc.beside_the_criterion(prepared, rows, sets, 10, 3))["m"]
    assert "withheld" not in share and "turnbull_share_recovered_by_the_stated_end" in share
    assert share["condition_a"]["ci95"] is not None


def test_the_shares_of_a_hold_rate_beside_a_set_whose_determined_statements_are_near() -> None:
    """The three shares of a hold rate are one number, how many of the determined statements
    held, and the frequency on another set is the same number there. A form whose statements
    are an item set and six more, of which two are determined, would give with it how many
    of those two held: its shares are withheld and the cell is marked, its counts stay, and
    the slip table, which holds no such share, keeps the cell."""
    count, listed = 40, 20
    held = np.array(([1.0, 0.0, 1.0, 1.0] * 10)[:count])
    held[[20, 21, 22, 23]] = np.nan  # of the six statements after the item set, two are determined
    forms = ["quarter"] * 26 + ["month_year"] * 14
    everything, first = dated_by_type(["recovery"] * count, held, forms)
    beside = {"the item set of m": everything.index[:listed]}
    got = written(sc.descriptives(everything, first, 100, 3, 3, beside=beside))
    cell = got["hold_rate"]["by_form"]["quarter"]
    assert (cell["statements"], cell["determined"], cell["undetermined"]) == (26, 22, 4)
    assert cell[sc.NEAR_SET] is True and numbers({k: cell[k] for k in sc.HOLD_SHARES}) == []
    for share in sc.HOLD_SHARES:
        assert cell[share]["withheld"] is True and cell[share]["statements"] in (22, 26)
    other = got["hold_rate"]["by_form"]["month_year"]
    assert other[sc.WITH_ANOTHER] is True and other["among_determined"]["mean"] is None
    assert got["hold_rate"]["all_dated_forms"]["among_determined"]["mean"] is not None
    assert BY_DAY in got["slip"]["by_form"]["quarter"]
    # with all six determined nothing is withheld
    held[[20, 21, 22, 23]] = [1.0, 0.0, 1.0, 1.0]
    everything, first = dated_by_type(["recovery"] * count, held, forms)
    got = written(sc.descriptives(everything, first, 100, 3, 3, beside=beside))
    assert sc.NEAR_SET not in json.dumps(got["hold_rate"])
    assert got["hold_rate"]["by_form"]["quarter"]["among_determined"]["mean"] is not None
    # all dated statements are the item set and six more, two of them determined: the three
    # shares of the whole are withheld and marked, and its counts stay
    held = np.array(([1.0, 0.0, 1.0, 1.0] * 7)[:26])
    held[[20, 21, 22, 23]] = np.nan
    everything, first = dated_by_type(["recovery"] * 26, held)
    got = written(sc.descriptives(everything, first, 100, 3, 3, beside=beside))["hold_rate"]
    whole = got["all_dated_forms"]
    assert whole[sc.NEAR_SET] is True and (whole["determined"], whole["undetermined"]) == (22, 4)
    assert all(whole[share]["mean"] is None for share in sc.HOLD_SHARES)


def test_a_set_of_a_few_statements_stands_beside_no_cell_of_the_descriptives() -> None:
    """A set of one to four statements holds no figure (the floor of five), so no cell of E1
    gives way to it: a form of six statements beside three of them is written; beside five
    of them it is withheld and marked, with a second cell."""
    forms = ["quarter"] * 6 + ["month_year"] * 18
    held = ([1.0, 1.0, 0.0, 1.0, 0.0, 1.0] * 4)[:24]
    everything, first = dated_by_type(["recovery"] * 24, held, forms)
    alone = written(sc.descriptives(everything, first, 100, 3, 3, beside={}))
    assert '"withheld": true' not in json.dumps(alone["hold_rate"]) + json.dumps(alone["slip"])
    # the other sets have to be stated, were it that there is none: the call stops without
    with pytest.raises(TypeError, match="beside"):
        sc.descriptives(everything, first, 100, 3, 3)
    few = {"three statements": everything.index[:3], "none": everything.index[:0]}
    assert written(sc.descriptives(everything, first, 100, 3, 3, beside=few)) == alone
    five = {"five statements": everything.index[:5]}
    got = written(sc.descriptives(everything, first, 100, 3, 3, beside=five))
    for table in (got["hold_rate"], got["slip"]):
        assert table["by_form"]["quarter"][sc.NEAR_SET] is True
        assert table["by_form"]["month_year"][sc.WITH_ANOTHER] is True
        assert numbers(table["by_form"]) == [] and numbers(table["all_dated_forms"])


def as_dated(rows: pd.DataFrame, first: pd.DataFrame, forms: Sequence[str] | None = None) -> None:
    """Gives the statements of ``two_types`` what the descriptives of E1 read, in place: they
    are dated statements at risk whose first event is yes when they recovered 5 to 10 days
    before the stated end and no when they recovered 20 to 25 days after it."""
    held = rows["y_a"].to_numpy()
    rows["analysis_set"] = "dated"
    rows["lower_days"] = np.where(held == 1.0, 20.0, np.where(held == 0.0, 50.0, 10.0))
    rows["upper_days"] = np.where(held == 1.0, 25.0, np.where(held == 0.0, 55.0, 60.0))
    rows["end_days"] = 30.0
    rows["form"] = list(forms) if forms is not None else ev.MONTH_YEAR
    rows["revision"] = "first"
    first["form"] = rows["form"]
    first["company_name"] = "Acme"


def test_a_type_of_an_item_set_beside_the_same_type_among_the_dated_statements() -> None:
    """The registered list in small: a dated next-delivery statement at risk that is not
    eligible. The type of the item set and the cell of the same type of E1 then differ by
    that one statement, and the frequency of the first event on the one beside the hold rate
    of the other would give its event. The cell of E1 gives way in both tables, and the cell
    of the other type with it, or all dated statements less that cell would be the first; the
    analysis by statement type is written in full."""
    prepared, everything, sets = two_types(65, 121)
    first = prepared.study.first
    as_dated(everything, first)
    left_out = [*everything.index[:5], everything.index[-1]]  # five recovery, one next delivery
    rows = everything.drop(index=left_out)
    sets = {"m": (rows.index, sets["m"][1])}
    known = sc.known_sets(prepared.study, rows, sets)
    beside = sc.sets_beside_the_tables(known)
    assert {"every eligible statement", "the item set of m", "m: next_delivery"} <= set(beside)
    assert all(
        name.startswith(("every", "the item set", "the post-cutoff", "m: ")) for name in beside
    )
    e1 = written(sc.descriptives(everything, first, 100, 3, 5, beside=beside))
    hold, slip = e1["hold_rate"], e1["slip"]
    by_type = written(sc.by_statement_type(prepared, rows, sets, 100, 5))["models"]["m"]
    assert hold["by_statement_type"]["next_delivery"] == {
        "statements": 121,
        "determined": None,
        "undetermined": None,
        **dict.fromkeys(sc.HOLD_SHARES, BARE_PART),
        sc.NEAR_SET: True,
    }
    assert hold["by_statement_type"]["recovery"][sc.WITH_ANOTHER] is True
    assert numbers(hold["by_statement_type"]) == [] and numbers(slip["by_statement_type"]) == []
    assert slip["by_statement_type"]["next_delivery"][sc.NEAR_SET] is True
    assert slip["by_statement_type"]["recovery"][sc.WITH_ANOTHER] is True
    assert (
        bare_cells(hold, slip)
        == (["by_statement_type/recovery", "by_statement_type/next_delivery"],) * 2
    )
    # all dated statements, the form and the revision bucket, six statements from the list
    for table in (hold, slip):
        assert numbers(table["all_dated_forms"]) and numbers(table["by_form"][ev.MONTH_YEAR])
    for name, ids in beside.items():
        for table, of_slip in ((hold, False), (slip, True)):
            assert near_in_a_table(table, everything, first, ids, of_slip) == [], name
    # the type of the item set keeps every figure: 120 of the 121 dated statements
    block = by_type["types"]["next_delivery"]
    assert block["statements"] == 120 and "contrasts" in block and "overconfidence" in block
    limits = block["scores"][ev.BASE]["calibration_all_statements"]["E_end"]
    assert limits["smallest_frequency"] == 0.0 and limits["undetermined"] == 0
    assert by_type["next_delivery_minus_recovery"]
    # without the other sets beside them the two tables would give the cell, and with the
    # frequency on the type the event of the one statement
    alone = written(sc.descriptives(everything, first, 100, 3, 5, beside={}))["hold_rate"]
    cell = alone["by_statement_type"]["next_delivery"]
    assert cell["statements"] - block["statements"] == 1 and numbers(cell)
    # a type of an item set that is a post-cutoff slice, beside a form of the dated statements
    # that is the type and two more: the form gives way, and the other form with it
    prepared, everything, sets = two_types(60, 120)
    first = prepared.study.first
    as_dated(everything, first, ["quarter"] * 62 + [ev.MONTH_YEAR] * 118)
    record = {"switched": True, "evaluable": True, "items": ev.SLICE_ITEMS}
    sets = {"m": (everything.index[:120], record)}
    beside = sc.sets_beside_the_tables(sc.known_sets(prepared.study, everything, sets))
    e1 = written(sc.descriptives(everything, first, 100, 3, 5, beside=beside))
    for table in (e1["hold_rate"], e1["slip"]):
        assert table["by_form"]["quarter"][sc.NEAR_SET] is True
        assert table["by_form"][ev.MONTH_YEAR][sc.WITH_ANOTHER] is True
        assert numbers(table["by_form"]) == [] and numbers(table["by_statement_type"])
    by_type = written(sc.by_statement_type(prepared, everything, sets, 100, 5))["models"]["m"]
    assert by_type["types"]["recovery"]["statements"] == 60
    assert "scores" in by_type["types"]["recovery"]


@pytest.mark.parametrize("undetermined", [0, 1, 4, 5])
def test_a_share_of_a_turnbull_estimate_beside_the_number_of_statements_that_held(
    undetermined: int,
) -> None:
    """The share recovered by the stated end, times the number of statements, less the number
    that held (the evaluator's limits of calibration in the large on an item set; the hold
    rate of a cell of E1) is what the estimate puts before the stated end for the statements
    whose first event is undetermined. Where those are one to four it is a figure on their
    brackets (with one, it can be the place of the stated end between its two captures): the
    share is withheld, beside the criterion and in the slip table."""
    prepared, _, everything, first, sets = item_set_among_dated(40, 40)
    open_ones = everything.index[5 : 5 + undetermined]
    everything.loc[open_ones, ["lower_days", "upper_days", "y_a"]] = [27.0, 42.0, np.nan]
    share = written(sc.beside_the_criterion(prepared, everything, sets, 5, 3))["m"]
    by_day = "share_recovered_by_days_after_the_stated_end"
    slip = written(sc.descriptives(everything, first, 100, 5, 3, beside={}))["slip"][
        "all_dated_forms"
    ]
    hold = written(sc.descriptives(everything, first, 100, 5, 3, beside={}))["hold_rate"][
        "all_dated_forms"
    ]
    assert hold["undetermined"] == undetermined and numbers(hold["undetermined_as_no"])
    if 0 < undetermined < sc.MIN_SHOWN:
        assert share == {
            "item_set_fixed_by_the_probe": share["item_set_fixed_by_the_probe"],
            "statements": 40,
            "episodes": 20,
            "withheld": True,
        }
        assert slip[by_day]["0"] is None and slip["ci95"]["0"] is None
        assert slip[sc.SHARES_WITHHELD] == ["0"]
        assert slip[by_day]["30"] is not None and slip["ci95"]["-30"] is not None
        assert slip["slip_quantiles_days"]["0.50"] is not None
        return
    assert sc.SHARES_WITHHELD not in slip
    held = hold["undetermined_as_no"]["mean"] * 40
    # what the two figures give together: nothing with no undetermined statement, and with
    # five the mass of the five, three days after the lower capture of a bracket of fifteen
    for found in (share["turnbull_share_recovered_by_the_stated_end"], slip[by_day]["0"]):
        assert near(found * 40 - held, undetermined * 3 / 15, 1e-3)


def test_the_share_by_ninety_days_of_a_cell_that_is_a_set_of_another_section() -> None:
    """The share recovered by 90 days after the stated end is the frequency of the second
    event where no bracket holds that day. On a cell of E1 that is itself a set on which
    another section writes that frequency (here all dated statements are the eligible list),
    the share of that day is withheld where one to four statements have that event
    undetermined; on another cell nothing stands beside it."""
    _, _, everything, first, _ = item_set_among_dated(40, 40)
    everything["y_b"] = 1.0
    everything.loc[everything.index[:2], "y_b"] = np.nan
    by_day = "share_recovered_by_days_after_the_stated_end"
    alone = written(sc.descriptives(everything, first, 100, 5, 3, beside={}))["slip"]
    assert sc.SHARES_WITHHELD not in alone["all_dated_forms"]
    beside = {"every eligible statement": everything.index, "another": everything.index[:20]}
    slip = written(sc.descriptives(everything, first, 100, 5, 3, beside=beside))["slip"]
    for cell in (slip["all_dated_forms"], slip["by_form"]["month_year"]):
        assert cell[sc.SHARES_WITHHELD] == ["90"]
        assert cell[by_day]["90"] is None and cell["ci95"]["90"] is None
        assert cell[by_day]["0"] == alone["all_dated_forms"][by_day]["0"]
    # with five such statements the share of the day is written
    everything.loc[everything.index[:5], "y_b"] = np.nan
    slip = written(sc.descriptives(everything, first, 100, 5, 3, beside=beside))["slip"]
    assert sc.SHARES_WITHHELD not in slip["all_dated_forms"]
    assert sc.EVENT_DAYS == {"y_a": "0", "y_b": "90"} and "90" in map(str, sc.SLIP_DAYS)


def test_the_turnbull_share_of_an_item_set_of_three_statements() -> None:
    """The floor of five holds for the share by itself: an item set of three statements, far
    from every other set, keeps their number alone."""
    prepared, rows, _, _, sets = item_set_among_dated(30, 3)
    got = written(sc.beside_the_criterion(prepared, rows, sets, 5, 3))["m"]
    assert got == {
        "item_set_fixed_by_the_probe": got["item_set_fixed_by_the_probe"],
        "statements": 3,
        "episodes": 2,
        "withheld": True,
    }
    prepared, rows, _, _, sets = item_set_among_dated(30, 5)
    got = written(sc.beside_the_criterion(prepared, rows, sets, 5, 3))["m"]
    assert "turnbull_share_recovered_by_the_stated_end" in got


def test_the_turnbull_share_of_two_item_sets_that_differ_by_a_few_statements() -> None:
    """Two primaries whose item sets differ by two statements: the two shares, with the open
    probabilities, would give the brackets of the two. Neither is written."""
    prepared, rows, _, _, sets = item_set_among_dated(30, 16)
    predictions = prepared.study.predictions
    predictions["n:a"] = predictions["m:a"]
    record = {"switched": True, "evaluable": True, "items": ev.SLICE_ITEMS}
    both = sets | {"n": (rows.index[2:], record)}
    got = written(sc.beside_the_criterion(prepared, rows, both, 10, 3))
    assert got["m"]["withheld"] is True and got["n"]["withheld"] is True
    assert numbers(got) == [] and got["n"]["statements"] == 14
    # five apart: both are written, each on its own statements
    both = sets | {"n": (rows.index[5:], record)}
    got = written(sc.beside_the_criterion(prepared, rows, both, 10, 3))
    assert "withheld" not in json.dumps(got)
    assert got["n"]["statements"] == 11 and got["m"]["statements"] == 16
    # the same item set for both: one estimate, written for each
    both = sets | {"n": (rows.index, record)}
    got = written(sc.beside_the_criterion(prepared, rows, both, 10, 3))
    for key in ("turnbull_share_recovered_by_the_stated_end", "condition_a", "base_rate", "draws"):
        assert got["m"][key] == got["n"][key], key


def test_a_cell_of_one_split_that_nearly_matches_a_cell_of_the_other() -> None:
    """The hold rate and the slip estimate are written by form and by revision bucket: where
    the statements of a form are those of a bucket and one more, the two hold rates together
    give the event of that one. The later of the two is withheld and marked, and with it a
    second cell of its split, since the split adds up to the hold rate of all."""
    count = 21
    rng = np.random.default_rng(2)
    held = rng.integers(0, 2, count).astype(float)
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(count)],
        analysis_set=["dated"] * count,
        outcome=["recovered"] * count,
        lower_days=[10.0] * count,
        upper_days=[30.0] * count,
        end_days=[40.0] * count,
        y_a=held,
    )
    first = pd.DataFrame(
        {"event_date": "2024-06-15", "statement_type": "recovery", "company_name": "c"},
        index=rows.index,
    )

    def described(forms: list[str], revisions: list[str]) -> tuple[dict, dict]:
        rows["form"], rows["revision"] = forms, revisions
        got = written(sc.descriptives(rows, first, 100, 3, 1, beside={}))
        return got["hold_rate"], got["slip"]

    # the month statements are those of the first revision and one more
    hold, slip = described(
        ["month"] * 11 + ["quarter"] * 10, [P.REVISIONS[0]] * 10 + [P.REVISIONS[1]] * 11
    )
    assert hold["all_dated_forms"]["among_determined"]["mean"] is not None
    for cell in hold["by_form"].values():
        assert cell["among_determined"]["mean"] is not None and sc.NEAR_SET not in cell
    for name, mark in zip(P.REVISIONS[:2], (sc.NEAR_SET, sc.WITH_ANOTHER), strict=True):
        cell = hold["by_revision"][name]
        assert cell[mark] is True and numbers(cell) == [] and cell["determined"] is None
        assert slip["by_revision"][name] == {
            "statements": 10 if name == P.REVISIONS[0] else 11,
            "episodes": slip["by_revision"][name]["episodes"],
            "withheld": True,
            mark: True,
        }
    assert "share_recovered_by_days_after_the_stated_end" in slip["by_form"]["month"]
    # one bucket nearly matches a form and the other does not: the other is withheld with it,
    # or all dated statements less the other would give it back
    hold, slip = described(
        ["month"] * 11 + ["quarter"] * 5 + ["year"] * 5,
        [P.REVISIONS[0]] * 10 + [P.REVISIONS[1]] * 11,
    )
    for table in (hold, slip):
        assert table["by_revision"][P.REVISIONS[0]][sc.NEAR_SET] is True
        assert table["by_revision"][P.REVISIONS[1]][sc.WITH_ANOTHER] is True
        assert numbers(table["by_revision"]) == []
    # two forms together are a bucket and two statements more: a cell of the bucket's split
    # goes, and the other with it
    hold, slip = described(
        ["month"] * 6 + ["quarter"] * 6 + ["year"] * 9,
        [P.REVISIONS[0]] * 14 + [P.REVISIONS[1]] * 7,
    )
    for table in (hold, slip):
        assert sorted(
            mark
            for cell in table["by_revision"].values()
            for mark in cell
            if "_" in mark and mark.startswith("withheld_")
        ) == sorted([sc.NEAR_SET, sc.WITH_ANOTHER])
        assert numbers(table["by_revision"]) == [] and numbers(table["by_form"]) != []
    # two splits whose cells differ by five statements or more: everything is given
    hold, slip = described(
        ["month"] * 11 + ["quarter"] * 10, [P.REVISIONS[0]] * 5 + [P.REVISIONS[1]] * 16
    )
    assert '"withheld": true' not in json.dumps(hold) + json.dumps(slip)
    assert sc.NEAR_SET not in json.dumps(hold) + json.dumps(slip)
    # a cell that is the other split's cell exactly is the same figure twice
    hold, slip = described(
        ["month"] * 11 + ["quarter"] * 10, [P.REVISIONS[0]] * 11 + [P.REVISIONS[1]] * 10
    )
    assert hold["by_revision"][P.REVISIONS[0]] == hold["by_form"]["month"]
    # the statements with a determined event count as well: a form and a bucket of the same
    # statements, of which one more is determined in the form's... they are the same set, so
    # the determined ones are too; with two statements undetermined in a bucket that holds
    # them and the form's, the determined sets are equal while the sets differ by two
    rows.loc[rows.index[[11, 12]], "y_a"] = np.nan
    hold, slip = described(
        ["month"] * 11 + ["quarter"] * 10, [P.REVISIONS[0]] * 13 + [P.REVISIONS[1]] * 8
    )
    assert hold["by_revision"][P.REVISIONS[0]][sc.NEAR_SET] is True
    assert slip["by_revision"][P.REVISIONS[0]][sc.NEAR_SET] is True


def test_no_figure_withheld_in_the_result_file_comes_back_from_those_beside_it(
    base: SimpleNamespace,
) -> None:
    """On the synthetic study: a part of selective prediction is never withheld alone, and the
    withheld cells of a split of the hold rate hold no determined statement or five or more."""
    points = dict(base.report["selective_prediction"])
    for model, lists in base.report["secondary_lists"].items():
        for key, entry in lists.items():
            points[f"{model} {key}"] = entry["selective_prediction_of_condition_c"]
    alone = 0
    for name, point in points.items():
        if "primary_brier_all" not in point:  # the stale list: no horizon event, no loss
            continue
        read, left = point["primary_brier_read"], point["primary_brier_abstained_on"]
        small = [0 < part.get("statements", 1) < sc.MIN_SHOWN for part in (read, left)]
        if any(small):
            alone += 1
            assert read["mean"] is None and left["mean"] is None, name
            assert "undetermined_as_no" not in read["bounds_all_statements"], name
            assert "undetermined_as_no" not in left["bounds_all_statements"], name
            assert ("statements" in read) == ("statements" in left), name
    assert alone > 0
    # the study has no small cell of the hold rate (the cases worked by hand above do); the
    # rule holds on it all the same
    hold = base.report["descriptives"]["hold_rate"]
    for split in ("by_form", "by_revision"):
        assert not [name for name, cell in hold[split].items() if cell["determined"] is None]
        left = hidden_in(hold[split])
        assert left == 0 or left >= sc.MIN_SHOWN, split


def test_a_date_discontinued_cell_counts_as_a_discontinuation_at_its_capture() -> None:
    """PLAN section 2.5: a displayed presentation that is censored, or whose recovery is first
    shown at the capture of the cell or a later one, is discontinued there (discontinuation
    wins ties); one that had recovered at an earlier capture keeps its recovery."""
    cases = {
        # name: (outcome, lower, upper, capture of the cell) -> (outcome, upper)
        "censored, no cell": (("censored", "2023-05-01", "", ""), ("censored", "")),
        "censored": (("censored", "2023-05-01", "", "2023-04-01"), ("discontinued", "2023-04-01")),
        "recovered later": (
            ("recovered", "2023-05-01", "2023-06-01", "2023-05-15"),
            ("discontinued", "2023-05-15"),
        ),
        "recovered at the same capture": (
            ("recovered", "2023-05-01", "2023-06-01", "2023-06-01"),
            ("discontinued", "2023-06-01"),
        ),
        "recovered at an earlier capture": (
            ("recovered", "2023-05-01", "2023-06-01", "2023-06-02"),
            ("recovered", "2023-06-01"),
        ),
        "recovered, no cell": (
            ("recovered", "2023-05-01", "2023-06-01", ""),
            ("recovered", "2023-06-01"),
        ),
        "discontinued already": (
            ("discontinued", "2023-05-01", "2023-06-01", "2023-05-15"),
            ("discontinued", "2023-06-01"),
        ),
        "not at risk": (("not_at_risk", "", "", "2023-05-15"), ("not_at_risk", "")),
    }
    columns = ("outcome_B", "lower_date_B", "upper_date_B", sc.DISCONTINUED_CELL)
    rows = pd.DataFrame([given for given, _ in cases.values()], columns=columns, index=list(cases))
    assert D.DEFINITION == "B" and sc.DISCONTINUED_CELL == "date_discontinued_on_row_date"
    out = sc.discontinued_by_the_cell(rows)
    for name, (_, (kind, upper)) in cases.items():
        assert (out.loc[name, "outcome_B"], out.loc[name, "upper_date_B"]) == (kind, upper), name
    # the lower bound and the cell are left as they are, and the rows given are not changed
    assert out["lower_date_B"].equals(rows["lower_date_B"])
    assert rows.loc["censored", "outcome_B"] == "censored"
    # a discontinuation is no at every horizon, whatever its bounds
    assert D.horizon_event("discontinued", "2023-05-01", "2023-04-01", "2023-03-01") == "no"
    assert D.horizon_event("discontinued", "2023-05-01", "2023-04-01", "2024-03-01") == "no"


def test_a_row_that_left_the_list_counts_as_recovered_only_when_it_is_censored() -> None:
    """PLAN section 2.5: leaving the list without a resolution counts as recovery at the first
    capture where the row is missing. A row with a resolution keeps it, and its bracket,
    whatever its exit date."""
    cases = {
        # name: (outcome, upper, exit) -> (outcome, upper)
        "censored, still listed": (("censored", "", ""), ("censored", "")),
        "censored, left the list": (("censored", "", "2023-07-01"), ("recovered", "2023-07-01")),
        "recovered, and left later": (
            ("recovered", "2023-06-01", "2023-07-01"),
            ("recovered", "2023-06-01"),
        ),
        "discontinued, and left later": (
            ("discontinued", "2023-06-01", "2023-07-01"),
            ("discontinued", "2023-06-01"),
        ),
        "not at risk": (("not_at_risk", "", "2023-07-01"), ("not_at_risk", "")),
    }
    exit_column = sc.VARIANT_COLUMNS[sc.RECOVERY_VARIANTS[1]]
    assert exit_column == "exit_date_B" and sc.RECOVERY_VARIANTS[1].startswith("leaving_the_list")
    columns = ("outcome_B", "upper_date_B", exit_column)
    rows = pd.DataFrame([given for given, _ in cases.values()], columns=columns, index=list(cases))
    out = sc.recovered_on_leaving(rows)
    for name, (_, (kind, upper)) in cases.items():
        assert (out.loc[name, "outcome_B"], out.loc[name, "upper_date_B"]) == (kind, upper), name
    # the rows given are not changed
    assert rows.loc["censored, left the list", "outcome_B"] == "censored"


def test_the_statements_a_variant_moves_are_counted_on_the_item_set_of_each_model() -> None:
    """A primary is scored on the item set its probe fixed and a secondary model on every
    eligible statement. A variant that gives six statements of the list another horizon event,
    two of them in the slice of a primary, is withheld for the primary, with the two counted,
    and given for the secondary model."""
    prepared, rows, _ = variant_case(0)
    study = prepared.study
    study.selection = {"m": "b"}
    for condition in ev.CONDITIONS:
        study.predictions[f"s:{condition}"] = study.predictions[f"m:{condition}"]
    under = rows.copy()
    under.loc[under.index[:6], "y_a"] = 0.0
    fixed = {"m": (rows.index[4:], {})}
    label = sc.RECOVERY_VARIANTS[0]
    got = written(sc.recovery_rule(prepared, rows, {label: under}, fixed, ["s"], 200, 3))[label]
    assert got["statements_with_another_horizon_event"] == {"m": 2, "s": 6}
    assert got["withheld_beside_another_outcome"] == ["m"]
    assert list(got["contrasts"]["m"]) == ["H1", "H2", "H3"]
    for entry in got["contrasts"]["m"].values():
        # no count either: beside the counts under the primary outcome it would say how many
        # of the two are scoreable under the variant
        assert set(entry) == {"comparator", "tested", "withheld", "bounds"}
        assert entry["withheld"] is True and entry["bounds"] == {"withheld": True}
    shown = got["contrasts"]["s"]["H1"]
    assert shown["statements"] == 12 and "withheld" not in shown and "delta" in shown
    # the two counts over the eligible list are those of a variant that moves six of the list
    assert (got["scoreable_statements"], got["not_at_risk_under_the_variant"]) == (12, 0)
    # six statements moved in the slice as well: given for both
    under.loc[under.index[:10], "y_a"] = 0.0
    got = written(sc.recovery_rule(prepared, rows, {label: under}, fixed, ["s"], 200, 3))[label]
    assert got["statements_with_another_horizon_event"] == {"m": 6, "s": 10}
    assert got["withheld_beside_another_outcome"] == [] and "delta" in got["contrasts"]["m"]["H1"]


def variant_case(moved: int) -> tuple[SimpleNamespace, pd.DataFrame, pd.DataFrame]:
    """Twelve statements in six episodes with both events yes, and the same statements under a
    variant that turns the first event of ``moved`` of them to no; one model whose condition
    (b) is the better forecast."""
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(12)],
        y_a=[1.0] * 12,
        y_b=[1.0] * 12,
        outcome=["recovered"] * 12,
    )
    under = rows.copy()
    under.loc[under.index[:moved], "y_a"] = 0.0
    ids = rows.index
    levels = {"m:a": 0.5, "m:b": 0.8, "m:c": 0.6, ev.RULES: 0.7, ev.BASE: 0.4, ev.STRUCTURED: 0.3}
    predictions = {name: forecasts(ids, [p] * 12, [p] * 12) for name, p in levels.items()}
    prepared = SimpleNamespace(
        study=SimpleNamespace(predictions=predictions, comparator=ev.BASE, selection={}, parsed={})
    )
    return prepared, rows, under


@pytest.mark.parametrize("moved", [0, 1, 4, 5])
def test_a_variant_that_moves_a_few_statements_gives_no_contrast(moved: int) -> None:
    """Beside the contrast under the primary outcome, the one under a variant that gives one to
    four statements another horizon event would give the change of their losses."""
    prepared, rows, under = variant_case(moved)
    assert int(sc.other_events(rows, under).sum()) == moved
    label = sc.RECOVERY_VARIANTS[2]
    got = sc.recovery_rule(prepared, rows, {label: under}, {}, ["m"], 200, 3)[label]
    assert got["computed"] is True and got["eligible_statements"] == 12
    assert got["statements_with_another_horizon_event"] == {"m": moved}
    entry = got["contrasts"]["m"]["H1"]
    assert (entry["comparator"], entry["tested"]) == ("m:a", "m:b")
    if 0 < moved < sc.MIN_SHOWN:
        # the number of statements with another horizon event is given, and nothing else:
        # a count under the variant, beside the same under the primary outcome, would say
        # how many of those few are scoreable (PLAN, standing rules)
        assert entry == {
            "comparator": "m:a",
            "tested": "m:b",
            "withheld": True,
            "bounds": {"withheld": True},
        }
        assert got["scoreable_statements"] is None
        assert got["not_at_risk_under_the_variant"] is None
    else:
        assert entry["statements"] == 12 and entry["bounds"]["statements"] == 12
        assert (got["scoreable_statements"], got["not_at_risk_under_the_variant"]) == (12, 0)
        # the loss of a statement is (p - y_a)^2 / 2 + (1 - p)^2 / 2: H1 is a less b
        loss = {p: ((p - 0.0) ** 2 * moved + (1 - p) ** 2 * (24 - moved)) / 24 for p in (0.5, 0.8)}
        assert near(entry["delta"], loss[0.5] - loss[0.8]) and "withheld" not in entry
        assert near(entry["bounds"]["undetermined_as_no"]["delta"], loss[0.5] - loss[0.8])
    # an event that is undetermined under the variant and not under the primary outcome counts
    under.loc[under.index[-1], "y_b"] = np.nan
    assert int(sc.other_events(rows, under).sum()) == moved + 1
    # a variant whose column the outcome rows do not hold is said not to be computed
    missing = sc.recovery_rule(prepared, rows, {label: None}, {}, ["m"], 200, 3)[label]
    assert missing == {
        "computed": False,
        "reason": f"the outcome rows hold no column {sc.DISCONTINUED_CELL}",
    }


def test_the_contrasts_of_a_secondary_model_are_repeated_as_those_of_a_primary() -> None:
    """The repeats on frames built by hand: under an outcome variant, on the statements first
    captured by the stated end, with the companies as clusters, and H2 on the month-and-year
    form (the synthetic study cannot tell the first two from the contrast itself)."""
    prepared, rows, under = variant_case(5)
    rows["company"] = ["Acme"] * 6 + ["Bolt"] * 4 + ["Core"] * 2
    under["company"] = rows["company"]
    study = prepared.study
    study.first = pd.DataFrame(
        {
            "delayed_entry": ["True"] * 5 + ["False"] * 7,
            "form": [ev.MONTH_YEAR] * 7 + ["quarter"] * 5,
        },
        index=rows.index,
    )
    got = sc.repeats_of("m", rows, {"any_covered_presentation": under}, study, 300, 3)
    assert list(got) == [
        "h2_on_the_month_and_year_form",
        "first_captured_by_the_stated_end",
        "clusters_by_company",
        "any_covered_presentation",
    ]
    assert list(got["h2_on_the_month_and_year_form"]) == ["H2"]
    for label in list(got)[1:]:
        assert list(got[label]) == primary_names()
    # with both events yes the loss is (1 - p)^2: H1 is 0.25 - 0.04, H2 is 0.09 - 0.16
    monthly = got["h2_on_the_month_and_year_form"]["H2"]
    assert monthly["statements"] == 7 and near(monthly["delta"], -0.07)
    assert (monthly["comparator"], monthly["tested"]) == (ev.RULES, "m:c")
    early = got["first_captured_by_the_stated_end"]["H1"]
    assert early["statements"] == 7 and early["episodes"] == 4 and near(early["delta"], 0.21)
    company = got["clusters_by_company"]["H1"]
    assert company["statements"] == 12 and company["episodes"] == 3
    # under the variant the first event of five statements is no: (p^2 + (1 - p)^2) / 2 there
    variant = got["any_covered_presentation"]["H1"]
    loss = {p: (5 * (p**2 + (1 - p) ** 2) / 2 + 7 * (1 - p) ** 2) / 12 for p in (0.5, 0.8)}
    assert variant["statements"] == 12 and near(variant["delta"], loss[0.5] - loss[0.8])
    assert variant["interval_method"] == ev.PERCENTILE_INTERVAL and "percentile" not in variant
    # the interval by company is the one of the company sums, not of the episodes
    difference = pd.Series(np.where(np.arange(12) < 5, 0.5, 0.0), index=rows.index)
    study.predictions["m:b"] = forecasts(rows.index, 0.8 - difference, [0.8] * 12)
    again = sc.repeats_of("m", rows, {}, study, ev.DRAWS, ev.SEED)["clusters_by_company"]["H1"]
    paired = 0.25 - ((1 - (0.8 - difference)) ** 2 + 0.04) / 2
    delta, interval = by_hand(paired, rows["company"])
    assert near(again["delta"], delta) and near(again["ci95"], interval)
    assert not near(interval, by_hand(paired, rows["episode_id"])[1])


def test_a_contrast_that_is_not_evaluable_holds_no_interval() -> None:
    """A slice can hold 50 scoreable statements in one episode: the contrasts on it, and those
    against the structured-only model beside them, are not evaluable and stop nothing."""
    prepared, rows, _ = variant_case(0)
    whole = sc.contrasts_of("m", rows, prepared.study, 200, 3)
    assert list(whole) == primary_names()
    for name in primary_names()[2:]:
        beside = whole[name]["against_gbm_structured"]
        assert beside["evaluable"] is True and set(beside["percentile"]) == {"ci95", "ci90"}
        assert beside["interval_method"] == ev.interval_method(ev.P_VALUE_SOURCE)
        assert len(beside["ci95"]) == 2 and beside["bounds"]["statements"] == 12
    assert "against_gbm_structured" not in whole["H1"]
    rows["episode_id"] = "e0"
    alone = sc.contrasts_of("m", rows, prepared.study, 200, 3)
    for name in primary_names():
        assert alone[name]["evaluable"] is False and alone[name]["p"] is None, name
        assert alone[name]["reason"] == "fewer than two episodes"
    for name in primary_names()[2:]:
        beside = alone[name]["against_gbm_structured"]
        assert beside["evaluable"] is False and beside["p"] is None
        assert "ci95" not in beside and "percentile" not in beside
    # and one that is not evaluable carries no estimate: nothing but its counts and the reason
    record = written(alone)
    assert numbers(record) == []
    assert record["H1"] | {"bounds": 0, "both_sides_parsed": 0} == {
        "comparator": "m:a",
        "tested": "m:b",
        "sides": 1,
        "statements": 12,
        "episodes": 1,
        "evaluable": False,
        "reason": "fewer than two episodes",
        "p": None,
        "bounds": 0,
        "both_sides_parsed": 0,
        "scoreable_not_parsed": {"m:a": 0, "m:b": 0},
    }


def test_the_contrast_on_the_statements_both_readings_parsed() -> None:
    """PLAN section 4: beside a contrast on every scoreable statement, the same on the
    statements both compared readings parsed. Which readings failed is open. With one to four
    of them, or with as few that parsed, the record holds the number that failed and nothing
    else, since its counts would say which of those few statements are scoreable; otherwise
    it is withheld, counts apart, when it leaves out or rests on one to four scoreable
    statements. "Where the failed answers of one side, or of both, number 1 to 4, its counts
    are withheld as well": a few on one side are a few, however many failed on the other."""
    prepared, rows, _ = variant_case(0)
    rows.loc[rows.index[0], "y_a"] = np.nan  # one statement is not scoreable
    rows["scoreable"] = rows["y_a"].notna() & rows["y_b"].notna()
    study = prepared.study
    study.predictions["m:b"] = forecasts(rows.index, np.linspace(0.3, 0.85, 12), [0.8] * 12)
    loss_a = pd.Series(0.25, index=rows.index)
    loss_b = ((1 - study.predictions["m:b"]["p_a"]) ** 2 + 0.04) / 2
    scoreable = rows["scoreable"].to_numpy()
    kinds = {}
    for failed in (0, 1, 4, 5, 6, 8, 12):
        # the first readings fail; the first statement is the one that is not scoreable
        flags = pd.Series(np.arange(12) >= failed, index=rows.index)
        kept = scoreable & flags.to_numpy()
        both, count = sc.where_both_parsed(rows, study.predictions, "m:a", "m:b", flags, 200, 3)
        as_parsed_only(both, count, scoreable, ~flags.to_numpy(), (loss_a - loss_b)[kept].mean())
        kinds[failed] = "delta" in both, "statements" in both
        # the same rules in the record of a contrast of a secondary model, and the counts of
        # each side with them
        study.parsed = {"m:b": flags}
        entry = sc.contrast_entry(rows, study, "m:a", "m:b", 1, 200, 3)
        assert entry["both_sides_parsed"].get("delta") == both.get("delta")
        assert set(entry["both_sides_parsed"]) == set(both)
        left_out = int((scoreable & ~flags.to_numpy()).sum())
        if 0 < failed < sc.MIN_SHOWN or 0 < 12 - failed < sc.MIN_SHOWN:
            assert entry["scoreable_not_parsed"] == {"m:a": None, "m:b": None}
        else:
            assert entry["scoreable_not_parsed"] == {"m:a": 0, "m:b": left_out}
        assert entry["statements"] == 11 and near(
            entry["delta"], (loss_a - loss_b)[scoreable].mean()
        )
    # shown: no reading failed, or six failed (five scoreable ones left out, six left);
    # counts alone: five failed (four scoreable left out), all twelve (none left);
    # nothing but the number that failed: 1 to 4 failed, or 1 to 4 parsed (eight failed)
    assert kinds == {
        0: (True, True),
        1: (False, False),
        4: (False, False),
        5: (False, True),
        6: (True, True),
        8: (False, False),
        12: (False, True),
    }
    assert sc.MIN_SHOWN == ev.MIN_SHOWN == 5
    # one side fails on six statements and the other on two more: the readings that failed on
    # the second alone are a few known statements, and the counts of each side, or those of
    # the contrast on the parsed answers beside another record, would say how many of them
    # are scoreable
    study.parsed = {
        "m:a": pd.Series(np.arange(12) >= 6, index=rows.index),
        "m:b": pd.Series(np.arange(12) < 10, index=rows.index),
    }
    entry = sc.contrast_entry(rows, study, "m:a", "m:b", 1, 200, 3)
    assert entry["scoreable_not_parsed"] == {"m:a": None, "m:b": None}
    assert entry["both_sides_parsed"] == {"not_both_parsed": 8, "withheld": True}


SIDES = ("gpt-4o-mini:a", "gpt-4o-mini:b")
"""Two readings of the model of ``study_by_hand``, each of which can fail to parse."""


@pytest.mark.parametrize(
    ("failed_a", "failed_b", "strict"),
    [
        (range(3), range(10, 60), True),  # three on one side, fifty on the other
        (range(10, 60), range(3), True),
        (range(3), range(53), True),  # three on both sides, fifty more on one
        (range(50), range(3, 53), True),  # fifty each, three on either side alone
        (range(5), range(10, 60), False),  # five and fifty
        (range(5), range(55), False),  # five on both sides
        (range(64), range(64), False),  # six parsed by both
        (range(66), range(66), True),  # four parsed by both
        (range(0), range(0), False),
    ],
)
def test_the_counts_on_the_parsed_answers_where_the_failed_answers_of_one_side_are_a_few(
    failed_a: range, failed_b: range, strict: bool
) -> None:
    """PLAN section 4: "Where the failed answers of one side, or of both, number 1 to 4, its
    counts are withheld as well, since they would say how many of those few are scoreable."
    Anyone can name the answers that failed on each side: the count of scoreable statements
    left out by one record, less that of a record beside it, is a count over the few."""
    ids = [f"S{k}" for k in range(70)]
    flags = {
        name: pd.Series([k not in failed for k in range(70)], index=ids)
        for name, failed in zip(SIDES, (failed_a, failed_b), strict=True)
    }
    prepared, rows = study_by_hand(70, parsed=flags)
    study = prepared.study
    failed = len(set(failed_a) | set(failed_b))
    bare = {"not_both_parsed": failed, "withheld": True}
    entry = written(sc.contrast_entry(rows, study, *SIDES, 1, 200, 3))
    both, each = entry["both_sides_parsed"], entry["scoreable_not_parsed"]
    record, count = sc.where_both_parsed(
        rows, study.predictions, *SIDES, [flags[name] for name in SIDES], 200, 3
    )
    record = written(record)
    assert "delta" in entry  # the contrast on every scoreable statement is always written
    if strict:
        assert both == bare and each == dict.fromkeys(SIDES) and numbers(both) == []
        assert record == bare and count is None
    else:
        assert (both["not_both_parsed"], both["left_out"]) == (failed, failed)
        assert both["statements"] == 70 - failed and "delta" in both
        assert each == {SIDES[0]: len(failed_a), SIDES[1]: len(failed_b)}
        assert record["statements"] == 70 - failed and count == failed
    # the change of a loss from one prompt to another, and the sampled against the
    # verbalised quantiles, are held to the same rule
    two = {name: study.predictions[name] for name in SIDES}
    _, _, _, moved = sc.changes(rows, two, flags, SIDES[1], 200, 3)
    changed = written(moved[SIDES[0]])
    drawn = written(
        sc.sampled_scores(
            rows,
            study.predictions[SIDES[0]],
            study.predictions[SIDES[1]],
            [flags[name] for name in SIDES],
            200,
            3,
        )
    )["pinball"]["0.50"]
    if strict:
        assert changed["primary_loss_both_parsed"] == bare
        assert changed["scoreable_not_parsed_by_both"] is None
        assert drawn["verbalised_minus_sampled_both_parsed"] == bare
        assert drawn["not_parsed_by_both"] is None
    else:
        assert changed["primary_loss_both_parsed"]["left_out"] == failed
        assert changed["scoreable_not_parsed_by_both"] == failed
        assert drawn["verbalised_minus_sampled_both_parsed"]["left_out"] == failed


def study_by_hand(
    count: int,
    before: int = 0,
    scoreable: Sequence[bool] | None = None,
    parsed: dict[str, pd.Series] | None = None,
    delayed: Sequence[int] = (),
    other_form: Sequence[int] = (),
    seed: int = 11,
) -> tuple[SimpleNamespace, pd.DataFrame]:
    """A study built by hand for one secondary model whose slice lies inside the test split:
    ``count`` statements in episodes of two, the first ``before`` of them dated before the
    cutoff of the model, every statement with its own open predictions (so that a sum of
    losses over a few statements says which events they had). ``delayed`` and ``other_form``
    name the statements first captured after the stated end and those not of the
    month-and-year form."""
    rng = np.random.default_rng(seed)
    y_a = rng.integers(0, 2, count).astype(float)
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(count)],
        company=[f"c{k % 3}" for k in range(count)],
        y_a=y_a,
        y_b=np.maximum(y_a, rng.integers(0, 2, count).astype(float)),
        ttr_kind=["interval"] * count,
        ttr_lower=[10.0] * count,
        ttr_upper=[30.0] * count,
        ttr_mid=[20.0] * count,
        outcome=["recovered"] * count,
        end_days=[40.0] * count,
    )
    if scoreable is not None:
        rows.loc[~np.asarray(scoreable, dtype=bool), "y_a"] = np.nan
        rows["scoreable"] = rows["y_a"].notna() & rows["y_b"].notna()
    ids = rows.index
    cutoff = S.CUTOFF_MONTH_ENDS[SLICED]
    assert S.has_slice(cutoff) and cutoff.isoformat() == "2023-10-31"
    first = pd.DataFrame(
        {
            "event_date": ["2023-06-15"] * before + ["2024-06-15"] * (count - before),
            "delayed_entry": ["True" if k in delayed else "False" for k in range(count)],
            "form": ["quarter" if k in other_form else ev.MONTH_YEAR for k in range(count)],
        },
        index=ids,
    )
    names = [f"{SLICED}:a", f"{SLICED}:b", f"{SLICED}:c", ev.RULES, ev.BASE, ev.STRUCTURED]
    predictions = {}
    for name in names:
        made = pd.DataFrame(
            {"p_a": rng.uniform(0.05, 0.95, count), "p_b": rng.uniform(0.05, 0.95, count)},
            index=ids,
        ).round(4)
        for k, key in enumerate(P.QUANTILE_KEYS):
            made[key] = (rng.uniform(5, 60, count) + 20 * k).round(1)
        predictions[name] = made.astype(float)
    study = ev.Study(
        first=first,
        probe_ids=[],
        predictions=predictions,
        parsed=parsed or {},
        probe={},
        selection={},
        comparator=ev.BASE,
        runs={SLICED: {}},
        not_evaluable={},
        refit={},
    )
    return SimpleNamespace(study=study, reading_days={}), rows


SLICED = "gpt-4o-mini"
"""A secondary model whose post-cutoff slice lies inside the test split."""


def numbers(value: Any) -> list[float]:
    """Every number of a record that is not a whole number: what is written besides counts."""
    if isinstance(value, dict):
        return [number for item in value.values() for number in numbers(item)]
    if isinstance(value, list):
        return [number for item in value for number in numbers(item)]
    return [value] if isinstance(value, float) else []


@pytest.mark.parametrize("before", [0, 1, 4, 5])
def test_a_figure_on_the_slice_is_withheld_where_a_few_statements_lie_before_the_cutoff(
    before: int,
) -> None:
    """The same figure on every eligible statement and on the post-cutoff slice: where one to
    four statements lie before the cutoff, the two together would give their losses, and the
    predictions being open, their events. Nothing of the slice is then written but the number
    of its statements (PLAN, standing rules: "A count is withheld too where it says, by
    itself or by subtraction from a count beside it, how many of 1 to 4 statements are
    scoreable"): its counts, taken from those of the list, are counts over the few."""
    prepared, rows = study_by_hand(60, before)
    got = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))
    entry = got["models"][SLICED]
    assert entry["post_cutoff_slice"]["slice_statements"] == 60 - before
    whole, part = entry["on_every_eligible_statement"], entry["on_the_post_cutoff_slice"]
    every = got["scores_on_every_eligible_statement"][SLICED]
    blocks = {
        "contrasts": part,
        "decomposition": entry["decomposition_on_the_post_cutoff_slice"],
        "scores": entry["scores_on_the_post_cutoff_slice"],
    }
    assert numbers(whole) and numbers(every)
    if 0 < before < sc.MIN_SHOWN:
        bare = {"statements": 60 - before, "withheld": True}
        assert blocks == dict.fromkeys(blocks, bare)
        assert entry["post_cutoff_slice"] == {
            "cutoff_month_end": "2023-10-31",
            "slice_inside_the_test_split": True,
            "slice_statements": 60 - before,
            "slice_scoreable": None,
            "slice_scoreable_episodes": None,
            "slice_analysed": None,
            "withheld": True,
        }
        # the record is the same whatever the outcomes: here the statements before the
        # cutoff are not scoreable, and the slice holds fewer than 50 scoreable statements
        dim = [k >= before and k < 45 for k in range(60)]
        other, dim_rows = study_by_hand(60, before, dim)
        again = written(sc.secondary_models(other, dim_rows, {}, [SLICED], 200, 3))
        again = again["models"][SLICED]
        for key in entry:
            if "slice" in key:
                assert again[key] == entry[key], key
        assert again["on_every_eligible_statement"]["H1"]["statements"] == 45 - before
        return
    a, b = (prepared.study.predictions[f"{SLICED}:{c}"] for c in "ab")
    after = rows.iloc[before:]
    loss = brier(a.loc[after.index], after) - brier(b.loc[after.index], after)
    assert near(part["H1"]["delta"], loss.mean())
    assert near(blocks["scores"]["a"]["primary_brier"], brier(a.loc[after.index], after).mean())
    assert "withheld" not in json.dumps(blocks)
    if before == 0:  # the slice is the whole list: the same figures twice
        assert part == whole and blocks["scores"] == every
    else:
        # five statements before the cutoff: what the two give together is over five
        apart = 60 * whole["H1"]["loss_comparator"] - 55 * part["H1"]["loss_comparator"]
        assert near(apart, brier(a.iloc[:5], rows.iloc[:5]).sum(), 1e-4)


@pytest.mark.parametrize(
    ("failed_before", "scoreable_before", "kind"),
    [
        ([], [True] * 10, "shown"),
        ([0], [True] * 10, "number alone"),  # one failed reading before the cutoff
        ([0, 1, 2], [True] * 10, "number alone"),
        ([0, 1, 2, 3, 4], [True] * 10, "shown"),
        # six failed before the cutoff: the four that parsed there are a few, and the counts
        # of the list less those of the slice would say how many of them are scoreable
        ([0, 1, 2, 3, 4, 5], [False] * 4 + [True] * 6, "number alone"),
        ([0, 1, 2, 3, 4], [True] * 6 + [False] * 4, "counts alone"),  # one parsed and scoreable
    ],
)
def test_the_both_parsed_contrast_of_the_slice_beside_that_of_the_whole_list(
    failed_before: list[int], scoreable_before: list[bool], kind: str
) -> None:
    """The contrast on the statements both sides parsed is written on every eligible statement
    and again on the slice: each less the contrast beside it is the summed difference on the
    scoreable statements a failed reading leaves out, and the two taken from one another that
    of those before the cutoff. Five readings of condition (a) fail after the cutoff."""
    failed = [*failed_before, 20, 21, 22, 23, 24]
    flags = pd.Series([k not in failed for k in range(70)], index=[f"S{k}" for k in range(70)])
    prepared, rows = study_by_hand(
        70, 10, [*scoreable_before, *[True] * 60], parsed={f"{SLICED}:a": flags}
    )
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    whole, part = (
        entry[key]["H1"] for key in ("on_every_eligible_statement", "on_the_post_cutoff_slice")
    )
    assert part["statements"] == 60 and "delta" in part and "delta" in whole
    assert "delta" in whole["both_sides_parsed"]
    both, sides = part["both_sides_parsed"], part["scoreable_not_parsed"]
    if kind == "number alone":
        assert both == {"not_both_parsed": 5, "withheld": True}
        assert sides == {f"{SLICED}:a": None, f"{SLICED}:b": None}
    elif kind == "counts alone":
        assert both["withheld"] is True and "delta" not in both
        assert (both["not_both_parsed"], both["left_out"], both["statements"]) == (5, 5, 55)
        assert sides == {f"{SLICED}:a": 5, f"{SLICED}:b": 0}
    else:
        assert "withheld" not in both and both["statements"] == 55
        a, b = (prepared.study.predictions[f"{SLICED}:{c}"] for c in "ab")
        kept = [f"S{k}" for k in range(10, 70) if k not in failed]
        assert near(both["delta"], (brier(a.loc[kept], rows) - brier(b.loc[kept], rows)).mean())
    # the same holds for H3 with condition (a); H2, which condition (a) is no side of, has its
    # contrast on the statements both sides parsed twice, and it is the contrast itself
    other = entry["on_the_post_cutoff_slice"]["H3 with condition a"]["both_sides_parsed"]
    assert set(other) == set(both)
    plain = entry["on_the_post_cutoff_slice"]["H2"]
    assert near(plain["both_sides_parsed"]["delta"], plain["delta"])


def test_the_counts_of_the_slice_beside_those_of_the_list_where_both_are_withheld() -> None:
    """The contrast on the parsed answers can be withheld on the list and on the slice, each
    for its own few, with the counts apart: the counts of the two, taken from one another,
    would still say whether the one statement whose reading failed before the cutoff is
    scoreable. The record of the slice then holds the number of failed readings alone."""
    failed = [0, 20, 21, 22, 23, 24]
    scoreable = [k not in (20, 21) for k in range(70)]  # three of the five after the cutoff
    flags = pd.Series([k not in failed for k in range(70)], index=[f"S{k}" for k in range(70)])
    prepared, rows = study_by_hand(70, 10, scoreable, parsed={f"{SLICED}:a": flags})
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    whole, part = (
        entry[key]["H1"] for key in ("on_every_eligible_statement", "on_the_post_cutoff_slice")
    )
    both = whole["both_sides_parsed"]
    assert both["withheld"] is True and (both["not_both_parsed"], both["left_out"]) == (6, 4)
    assert whole["scoreable_not_parsed"] == {f"{SLICED}:a": 4, f"{SLICED}:b": 0}
    assert part["both_sides_parsed"] == {"not_both_parsed": 5, "withheld": True}
    assert part["scoreable_not_parsed"] == {f"{SLICED}:a": None, f"{SLICED}:b": None}
    # with no reading failed before the cutoff the slice keeps its counts: three left out
    flags.iloc[0] = True
    prepared, rows = study_by_hand(70, 10, scoreable, parsed={f"{SLICED}:a": flags})
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    both = entry["on_the_post_cutoff_slice"]["H1"]["both_sides_parsed"]
    assert both["withheld"] is True and (both["not_both_parsed"], both["left_out"]) == (5, 3)


def test_the_base_rate_beside_the_calibration_in_the_large_of_a_secondary_model() -> None:
    """PLAN section 7.2, "Calibration in the large": "Beside it stand the same quantities for
    the base rate by listing age on the same events". On every eligible statement and on the
    post-cutoff slice of a secondary model, worked out from the base rate's probabilities."""
    # ten statements are not scoreable, five of them before the cutoff
    scoreable = [k not in (0, 1, 2, 3, 4, 20, 27, 34, 41, 48) for k in range(70)]
    prepared, rows = study_by_hand(70, 10, scoreable)
    study = prepared.study
    got = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))
    base = study.predictions[ev.BASE]
    every = got["scores_on_every_eligible_statement"][SLICED]
    sliced = got["models"][SLICED]["scores_on_the_post_cutoff_slice"]
    for records, frame in ((every, rows), (sliced, rows.iloc[10:])):
        keep = frame["scoreable"].to_numpy()
        ids = frame.index
        for condition in ev.CONDITIONS:
            record = records[condition]
            own = study.predictions[f"{SLICED}:{condition}"]
            for event, p, y in ev.EVENTS:
                large = record["calibration_in_the_large"][event]
                gap = (base.loc[ids, p] - frame[y])[keep]
                assert near(large["base_rate"]["mean_p_minus_frequency"], gap.mean())
                assert set(large["base_rate"]) == {"mean_p_minus_frequency", "ci95"}
                assert near(
                    large["mean_p_minus_frequency"], (own.loc[ids, p] - frame[y])[keep].mean()
                )
                # over every statement: the least value counts an undetermined event as yes
                limits = record["calibration_all_statements"][event]
                least = (base.loc[ids, p] - frame[y].fillna(1.0)).mean()
                assert near(limits["base_rate"]["least"], least)
                assert near(limits["least"], (own.loc[ids, p] - frame[y].fillna(1.0)).mean())
                assert limits["base_rate"]["undetermined"] == limits["undetermined"]
    # the base rate's interval on the scoreable statements, by episode
    keep = rows["scoreable"].to_numpy()
    gap = (base["p_a"] - rows["y_a"])[keep]
    wanted = by_hand(gap, rows["episode_id"][keep])
    found = every["a"]["calibration_in_the_large"]["E_end"]["base_rate"]
    assert near(
        found["ci95"],
        [
            float(v)
            for v in np.quantile(
                P.bootstrap_means(gap.to_numpy(), list(rows["episode_id"][keep]), 200, 3)[:, 0],
                [0.025, 0.975],
            )
        ],
    )
    assert near(found["mean_p_minus_frequency"], wanted[0])
    # where the figures over every statement are withheld (three statements not scoreable),
    # the block stays as it is: no base rate is put into it
    prepared, rows = study_by_hand(70, 10, [k not in (20, 30, 40) for k in range(70)])
    got = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))
    record = got["scores_on_every_eligible_statement"][SLICED]["a"]
    assert record["calibration_in_the_large"]["withheld"] is True
    assert "base_rate" not in json.dumps(record)
    # two of the ten statements before the cutoff are not scoreable: the figures over every
    # statement of the slice, beside those of the list, would give their events, and the
    # mean probabilities on the scoreable statements would name them (PLAN section 2.5, for
    # the statements between the two sets). The losses of the slice stay.
    dim = [k not in (0, 7, 20, 27, 34, 41, 48, 55) for k in range(70)]
    prepared, rows = study_by_hand(70, 10, dim)
    got = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))
    record = got["models"][SLICED]["scores_on_the_post_cutoff_slice"]["a"]
    counts = {"statements": 60, "with_a_horizon_event_undetermined": 6, "withheld": True}
    for key in ("bounds_all_statements", "calibration_all_statements", "calibration_in_the_large"):
        assert record[key] == counts, key
    assert record["mean_p_E_end"] is None and record["mean_p_E_end90"] is None
    assert record["scoreable_statements"] == 54 and "primary_brier" in record
    assert "base_rate" not in json.dumps(record)
    whole = got["scores_on_every_eligible_statement"][SLICED]["a"]
    assert whole["mean_p_E_end"] is not None and "least" in json.dumps(whole)


def test_the_figures_of_a_predictor_that_reads_no_text_on_two_slices_a_few_statements_apart() -> (
    None
):
    """Some figures of a slice are the same whichever model it is the slice of: the base
    rate's calibration in the large, the two parts of the decomposition that compare
    predictors that read no text and, the predictions being open, the frequencies of the
    horizon events in the model's own records. Where the slice of a model stands near the
    slice of another secondary model, what the two would give back is withheld (PLAN,
    standing rules): everything but the number of statements where the two differ by one to
    four statements; those figures where their scoreable statements do; the figures that
    fill the horizon events where only their statements that are not scoreable do."""
    other = "gpt-oss-20b"
    assert other in sc.SECONDARY_MODELS and S.CUTOFF_MONTH_ENDS[other].isoformat() == "2024-06-30"
    blocks = ("bounds_all_statements", "calibration_all_statements", "calibration_in_the_large")
    slice_keys = ("on_the_post_cutoff_slice", "decomposition_on_the_post_cutoff_slice")

    def scored_with(between: int, dim: Sequence[int] = ()) -> dict:
        """``between`` statements dated after the cutoff of SLICED and before that of the
        other secondary model; the rest of the slice after both. The statements at the
        positions ``dim`` are not scoreable."""
        prepared, rows = study_by_hand(70, 10, [k not in dim for k in range(70)])
        first = prepared.study.first
        first.loc[first.index[10 + between :], "event_date"] = "2024-07-15"
        return written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]

    # two statements between the cutoffs: the number of statements of the slice alone, or
    # its counts beside those of the other slice would say how many of the two are scoreable
    entry = scored_with(2)
    bare = {"statements": 60, "withheld": True}
    assert entry["post_cutoff_slice"] == {
        "cutoff_month_end": "2023-10-31",
        "slice_inside_the_test_split": True,
        "slice_statements": 60,
        "slice_scoreable": None,
        "slice_scoreable_episodes": None,
        "slice_analysed": None,
        "withheld": True,
    }
    for key in (*slice_keys, "scores_on_the_post_cutoff_slice"):
        assert entry[key] == bare, key
    assert "delta" in entry["on_every_eligible_statement"]["H1"]
    # six between, two of them scoreable (five more that are not, in both slices): the figures
    # that are the same whichever model would give the events of the two
    entry = scored_with(6, (10, 11, 12, 13, *range(30, 35)))
    assert entry["post_cutoff_slice"]["slice_scoreable"] == 51
    counts = {"statements": 60, "with_a_horizon_event_undetermined": 9, "withheld": True}
    for condition in ev.CONDITIONS:
        record = entry["scores_on_the_post_cutoff_slice"][condition]
        assert "primary_brier" in record and "withheld" not in record
        assert record["scoreable_statements"] == 51 and "pinball_all_statements" in record
        for key in blocks:
            assert record[key] == counts, key
        assert record["mean_p_E_end"] is None and record["mean_p_E_end90"] is None
        assert record["murphy"] == {"withheld": True}
        assert "base_rate" not in json.dumps(record) and "frequency" not in json.dumps(record)
        assert "uncertainty" not in json.dumps(record)
    parts = entry["decomposition_on_the_post_cutoff_slice"]
    assert tuple(list(parts)[:2]) == sc.MODEL_FREE_PARTS
    assert parts["content_value_of_the_text"] == {
        "statements": 51,
        "episodes": parts["reading_loss"]["episodes"],
        "minuend": ev.BASE,
        "subtrahend": ev.RULES,
        "withheld": True,
    }
    assert parts["content_value_against_the_structured_model"]["withheld"] is True
    assert numbers(parts["content_value_against_the_structured_model"]) == []
    assert "delta" in parts["reading_loss"] and "delta" in parts["trust_loss"]
    assert "delta" in entry["on_the_post_cutoff_slice"]["H1"]
    # eight between, three of them not scoreable: the figures over every statement that fill
    # the horizon events would give the events of the three, and the mean probabilities
    # would name them (section 2.5); what is scored on the scoreable statements stays
    entry = scored_with(8, (10, 11, 12, *range(30, 35)))
    counts = {"statements": 60, "with_a_horizon_event_undetermined": 8, "withheld": True}
    for condition in ev.CONDITIONS:
        record = entry["scores_on_the_post_cutoff_slice"][condition]
        for key in blocks:
            assert record[key] == counts, key
        assert record["mean_p_E_end"] is None and "base_rate" not in json.dumps(record)
        assert "uncertainty" in record["murphy"]["E_end"] and "primary_brier" in record
    assert all("delta" in part for part in entry["decomposition_on_the_post_cutoff_slice"].values())
    assert "delta" in entry["on_the_post_cutoff_slice"]["H1"]
    assert "undetermined_as_no" in entry["on_the_post_cutoff_slice"]["H1"]["bounds"]
    # five statements between the two cutoffs, all scoreable: everything is written
    entry = scored_with(5, tuple(range(30, 35)))
    record = entry["scores_on_the_post_cutoff_slice"]["a"]
    assert "ci95" in record["calibration_in_the_large"]["E_end"]["base_rate"]
    assert "largest_frequency" in record["calibration_all_statements"]["E_end"]
    assert record["mean_p_E_end"] is not None and "uncertainty" in record["murphy"]["E_end"]
    assert all("delta" in part for part in entry["decomposition_on_the_post_cutoff_slice"].values())
    # the slice of a primary that is not its item set holds that primary's tests alone, but
    # the evaluator writes how many of its statements are scoreable: two statements between
    # the cutoff of SLICED and that of a primary leave the slice of SLICED its number alone
    assert S.CUTOFF_MONTH_ENDS[LLAMA].isoformat() == "2023-12-31"
    prepared, rows = study_by_hand(70, 10)
    first = prepared.study.first
    first.loc[first.index[10:12], "event_date"] = "2023-11-15"
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    assert entry["scores_on_the_post_cutoff_slice"] == bare
    assert entry["post_cutoff_slice"]["slice_scoreable"] is None
    # with six between, two of them scoreable, the tests of the primary on its slice are no
    # figure of SLICED, and nothing is withheld; where that slice is the item set of the
    # primary, the evaluator writes the base rate's figures on it, and those of SLICED go
    prepared, rows = study_by_hand(
        70, 10, [k not in (10, 11, 12, 13, *range(30, 35)) for k in range(70)]
    )
    first = prepared.study.first
    first.loc[first.index[10:16], "event_date"] = "2023-11-15"
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    record = entry["scores_on_the_post_cutoff_slice"]["a"]
    assert "ci95" in record["calibration_in_the_large"]["E_end"]["base_rate"]
    sets = {LLAMA: (rows.index[16:], {"switched": True, "evaluable": True})}
    first["statement_type"] = "recovery"
    known = sc.known_sets(prepared.study, rows, sets)
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3, None, known))
    record = entry["models"][SLICED]["scores_on_the_post_cutoff_slice"]["a"]
    assert record["calibration_in_the_large"]["withheld"] is True
    assert record["murphy"] == {"withheld": True} and "primary_brier" in record
    # a slice that is not analysed (fewer than 50 scoreable statements) keeps no count of its
    # scoreable statements either where it is another slice but for two statements
    prepared, rows = study_by_hand(40, 10)
    first = prepared.study.first
    first.loc[first.index[12:], "event_date"] = "2024-07-15"
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    assert entry["post_cutoff_slice"]["slice_statements"] == 30
    assert entry["post_cutoff_slice"]["slice_scoreable"] is None
    assert entry["post_cutoff_slice"]["slice_analysed"] is None
    first.loc[first.index[12:15], "event_date"] = "2024-06-15"  # five between
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 200, 3))["models"][SLICED]
    assert entry["post_cutoff_slice"]["slice_scoreable"] == 30
    assert entry["post_cutoff_slice"]["slice_analysed"] is False


def test_a_repeat_on_a_part_of_the_statements_beside_the_contrast_on_all() -> None:
    """The contrasts repeated on the statements first captured by the stated end, and H2 on
    the month-and-year form, stand beside the contrasts on every statement: a repeat that
    leaves out one to four scoreable statements is withheld, counts apart; one that leaves
    out one to four statements, which the open cells name, holds no count either (PLAN,
    standing rules: a count that says by subtraction how many of 1 to 4 statements are
    scoreable)."""
    names = ("first_captured_by_the_stated_end", "h2_on_the_month_and_year_form")

    def repeats(
        delayed: Sequence[int], other_form: Sequence[int], scoreable: Sequence[bool] | None = None
    ) -> tuple[dict, dict]:
        prepared, rows = study_by_hand(20, 0, scoreable, delayed=delayed, other_form=other_form)
        got = written(sc.repeats_of(SLICED, rows, {}, prepared.study, 200, 3))
        return got[names[0]]["H1"], got[names[1]]["H2"]

    # one statement captured late, one of another form: both repeats would give its loss,
    # and their counts whether it is scoreable
    early, monthly = repeats([5], [7])
    assert early == {"comparator": f"{SLICED}:a", "tested": f"{SLICED}:b", "withheld": True}
    assert monthly == {"comparator": ev.RULES, "tested": f"{SLICED}:c", "withheld": True}
    # four of each: still a few
    early, monthly = repeats([0, 1, 2, 3], [4, 5, 6, 7])
    assert set(early) == set(monthly) == {"comparator", "tested", "withheld"}
    # six of each, of which two are scoreable: the counts stay, over six statements
    few_scoreable = [k not in (2, 3, 4, 5, 12, 13, 14, 15) for k in range(20)]
    early, monthly = repeats(range(6), range(10, 16), few_scoreable)
    for record in (early, monthly):
        assert record["withheld"] is True and record["statements"] == 10
        assert numbers(record) == [] and "delta" not in record
    # five of each, and no statement in both groups: given
    early, monthly = repeats([0, 1, 2, 3, 4], [10, 11, 12, 13, 14])
    assert "withheld" not in early and "withheld" not in monthly
    assert early["statements"] == 15 and monthly["statements"] == 15
    # none: the repeat is the contrast itself
    early, monthly = repeats([], [])
    assert early["statements"] == monthly["statements"] == 20 and "delta" in early
    # the two parts differ from one another by one statement: H2 is written on both, and the
    # one on the month-and-year form is withheld, with its counts
    early, monthly = repeats([0, 1, 2, 3, 4], [0, 1, 2, 3, 4, 5])
    assert "withheld" not in early and early["statements"] == 15
    assert monthly == {"comparator": ev.RULES, "tested": f"{SLICED}:c", "withheld": True}


TYPE_LEVELS = {"m:a": 0.5, "m:b": 0.8, "m:c": 0.6, ev.RULES: 0.7, ev.BASE: 0.4, ev.STRUCTURED: 0.3}
"""The one probability each predictor of ``two_types`` gives to both events of a statement."""


def two_types(
    recovery: int = 60,
    next_delivery: int = 120,
    not_scoreable: Sequence[int] = (),
    dates: Sequence[str] | None = None,
) -> tuple[SimpleNamespace, pd.DataFrame, dict]:
    """A primary ``m`` whose item set is every statement of a list of the two types, worked by
    hand: the recovery statements first, in 60 episodes that each hold statements of both
    types where both number 60 or more. The second event is yes everywhere; the first is yes
    on a recovery statement and no on a next-delivery one, and undetermined at the positions
    of ``not_scoreable``. Every predictor gives one probability to both events
    (``TYPE_LEVELS``), and condition (b) is the selected one. Returns the prepared study, the
    statements and the item sets."""
    count = recovery + next_delivery
    kinds = ["recovery"] * recovery + ["next_delivery"] * next_delivery
    y_a = np.array([1.0] * recovery + [0.0] * next_delivery)
    y_a[list(not_scoreable)] = np.nan
    rows = typed(
        episode_id=[f"e{k % 60:02d}" for k in range(count)],
        y_a=y_a,
        y_b=[1.0] * count,
        outcome=["recovered"] * count,
        ttr_kind=["interval"] * count,
        ttr_lower=[10.0] * count,
        ttr_upper=[30.0] * count,
        ttr_mid=[20.0] * count,
        end_days=[40.0] * count,
    )
    ids = rows.index
    first = pd.DataFrame(
        {
            "statement_type": kinds,
            "event_date": list(dates) if dates is not None else ["2024-06-15"] * count,
            "delayed_entry": "False",
            "form": ev.MONTH_YEAR,
        },
        index=ids,
    )
    study = SimpleNamespace(
        predictions={
            name: forecasts(ids, [p] * count, [p] * count) for name, p in TYPE_LEVELS.items()
        },
        parsed={"m:a": pd.Series(True, index=ids)},
        comparator=ev.BASE,
        selection={"m": "b"},
        first=first,
    )
    sets = {"m": (ids, {"switched": False, "evaluable": True, "items": ev.ALL_ITEMS})}
    read = {"m": pd.Series(30.0, index=ids)}  # its literal reading reads every statement
    return SimpleNamespace(study=study, reading_days=read), rows, sets


def test_the_analysis_by_statement_type_on_a_case_worked_by_hand() -> None:
    """PLAN section 5, E3, "By statement type": on the recovery statements and on the
    next-delivery statements apart, the H1, H2 and H3 contrasts and Delta_GBM, the primary
    loss and the calibration in the large of the three conditions and of the base rate, and
    the overconfidence criterion; each contrast with the difference between the two types."""
    prepared, rows, sets = two_types()
    got = written(sc.by_statement_type(prepared, rows, sets, 400, 5))
    assert got["types"] == ["recovery", "next_delivery"] == list(sc.TYPES)
    assert got["fewest_scoreable_statements_of_a_type"] == sc.MIN_TYPE == 50
    assert "registered one on both types together" in got["note"]
    entry = got["models"]["m"]
    assert entry["statements"] == 180 and entry["episodes"] == 60
    assert entry["statements_of_another_type"] == 0
    assert entry["item_set_fixed_by_the_probe"]["items"] == ev.ALL_ITEMS
    back, due = entry["types"]["recovery"], entry["types"]["next_delivery"]
    for block, size in ((back, 60), (due, 120)):
        assert (block["statements"], block["scoreable_statements"]) == (size, size)
        assert (block["episodes"], block["scoreable_episodes"]) == (60, 60)
        assert list(block["contrasts"]) == ["H1", "H2", "H3", sc.DELTA_GBM]
        assert list(block["scores"]) == [ev.BASE, "a", "b", "c"]
    # a recovery statement has both events yes: the loss of a probability p is (1 - p)^2;
    # a next-delivery statement has the first event no: (p^2 + (1 - p)^2) / 2
    p = TYPE_LEVELS
    loss = {
        "recovery": {name: (1 - level) ** 2 for name, level in p.items()},
        "next_delivery": {name: (level**2 + (1 - level) ** 2) / 2 for name, level in p.items()},
    }
    pairs = {
        "H1": ("m:a", "m:b", 1),
        "H2": (ev.RULES, "m:c", 2),
        "H3": (ev.BASE, "m:b", 2),
        sc.DELTA_GBM: (ev.STRUCTURED, "m:b", 2),
    }
    for kind, block in entry["types"].items():
        for name, (comparator, tested, sides) in pairs.items():
            record = block["contrasts"][name]
            delta = loss[kind][comparator] - loss[kind][tested]
            assert (record["comparator"], record["tested"], record["sides"]) == (
                comparator,
                tested,
                sides,
            )
            assert near(record["delta"], delta), (kind, name)
            # every statement of a type has the same difference: the interval is one point
            assert (
                near(record["ci95"], [delta, delta]) and record["interval_method"] == "percentile"
            )
            assert record["statements"] == block["statements"] and record["episodes"] == 60
            # no event is undetermined: each scenario is the contrast itself
            for fill in sc.FILLS:
                assert near(record["bounds"][fill]["delta"], delta), (kind, name, fill)
            assert record["bounds"]["with_a_horizon_event_undetermined"] == 0
        for name, key in ((ev.BASE, ev.BASE), ("a", "m:a"), ("b", "m:b"), ("c", "m:c")):
            record = block["scores"][name]
            assert set(record) == set(sc.TYPE_SCORES) - {"withheld"}
            assert near(record["primary_brier"], loss[kind][key])
            assert near(record["ci95"], [loss[kind][key]] * 2)
            assert near(record["bounds_all_statements"]["undetermined_as_no"], loss[kind][key])
            # the mean probability less the frequency of the event: 1 or 0 for the first event
            rate = 1.0 if kind == "recovery" else 0.0
            large = record["calibration_in_the_large"]
            assert near(large["E_end"]["mean_p_minus_frequency"], p[key] - rate)
            assert near(large["E_end90"]["mean_p_minus_frequency"], p[key] - 1.0)
            assert near(large["E_end"]["ci95"], [p[key] - rate] * 2)
            limits = record["calibration_all_statements"]["E_end"]
            assert near(limits["least"], p[key] - rate) and near(limits["greatest"], p[key] - rate)
    assert near(back["contrasts"]["H1"]["delta"], 0.21) and near(
        due["contrasts"]["H1"]["delta"], -0.09
    )
    # the difference between the two types, next delivery minus recovery; each episode holds
    # one recovery statement and two next-delivery ones, so no draw is left out
    apart = entry["next_delivery_minus_recovery"]
    assert list(apart) == list(pairs)
    for name, (comparator, tested, _) in pairs.items():
        wanted = (loss["next_delivery"][comparator] - loss["next_delivery"][tested]) - (
            loss["recovery"][comparator] - loss["recovery"][tested]
        )
        assert near(apart[name]["difference"], wanted) and near(apart[name]["ci95"], [wanted] * 2)
        assert (apart[name]["draws"], apart[name]["draws_left_out"]) == (400, 0)
    assert near(apart["H1"]["difference"], -0.30) and near(apart[sc.DELTA_GBM]["difference"], -0.50)
    assert entry["opposite_signs_in_the_two_types"] == dict.fromkeys(pairs, True)
    # the criterion of section 13 on each type: condition (a) gives 0.5 to an event that is
    # always yes on the recovery statements (the greatest value is below zero: reading 1) and
    # always no on the next-delivery ones (both parts hold: 0.5 above the frequency, 0.1
    # above the base rate)
    for block, least, holds in ((back, -0.5, False), (due, 0.5, True)):
        found = block["overconfidence"]
        assert set(found) == {
            *sc.TYPE_CRITERION,
            "against_outcomes",
            "against_base_rate",
            "both_parts_hold",
        }
        outcomes, no_text = found["against_outcomes"], found["against_base_rate"]
        assert near(outcomes["least"], least) and near(outcomes["greatest"], least)
        assert near(outcomes["least_ci95"], [least, least]) and outcomes["undetermined"] == 0
        assert near(outcomes["base_rate"]["least"], least - 0.1)
        assert near(no_text["difference"], 0.1) and no_text["met"] is True
        assert outcomes["met"] is holds and found["both_parts_hold"] is holds
        assert found["criterion"] == ev.OVERCONFIDENCE_CRITERION
        # none of the five sentences of section 13 is read on a type
        assert "reading" not in found and "reading_in_words" not in found
    # on the item set a third of the events is yes: 0.5 - 1/3 above the frequency, and the
    # criterion holds there and not on the recovery statements
    assert entry["overconfidence_on_the_item_set"] == {"both_parts_hold": True}
    assert entry["overconfidence_holds_on_the_item_set_and_not_on_its_recovery_statements"] is True
    whole = ev.overconfidence(
        rows,
        prepared.study.predictions["m:a"],
        prepared.study.predictions[ev.BASE],
        prepared.study.parsed["m:a"],
        400,
        5,
    )
    assert near(whole["against_outcomes"]["E_end"]["least"], 0.5 - 1 / 3)


def test_the_difference_between_the_two_types_over_draws_of_the_episodes_of_the_item_set() -> None:
    """ "... the difference between the two types (next delivery minus recovery) and its 95%
    percentile interval over 10,000 draws of the episodes of the item set, both types taken
    from each draw; a draw with no scoreable statement of one type is left out." Seven
    episodes of unequal size, two of them with no next-delivery statement, one with no
    scoreable statement at all; worked out again from the episode sums."""
    kinds = ["recovery"] * 9 + ["next_delivery"] * 5
    episodes = ["a", "a", "b", "b", "b", "c", "d", "d", "g", "a", "b", "e", "e", "f"]
    rng = np.random.default_rng(4)
    rows = typed(
        episode_id=episodes,
        y_a=[1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, np.nan, 0.0, 1.0, 0.0, 1.0, 0.0],
        y_b=[1.0] * 14,
    )
    ids = rows.index
    made = {
        name: forecasts(ids, np.round(rng.random(14), 2), np.round(0.5 + rng.random(14) / 2, 2))
        for name in ("one", "other")
    }
    types = pd.Series(kinds, index=ids)
    got = sc.type_difference(rows, types, made, "one", "other", 3000, 7)
    paired = (brier(made["one"], rows) - brier(made["other"], rows)).fillna(0.0)
    keep = rows["scoreable"].to_numpy()
    back, due = (
        keep & (types == "recovery").to_numpy(),
        keep & (types == "next_delivery").to_numpy(),
    )
    assert near(got["difference"], paired[due].mean() - paired[back].mean(), 1e-12)
    # the registered draws of all seven episodes of the item set, in the order of their names
    names = sorted(set(episodes))
    assert len(names) == 7 and not keep[rows["episode_id"] == "g"].any()
    sums = np.array(
        [
            [
                paired[flags & (rows["episode_id"] == name).to_numpy()].sum(),
                (flags & (rows["episode_id"] == name).to_numpy()).sum(),
            ]
            for name in names
            for flags in (back, due)
        ],
        dtype=float,
    ).reshape(7, 4)
    taken = P.cluster_draws(7, 3000, 7).astype(float)
    totals = taken @ sums
    kept = (totals[:, 1] > 0) & (totals[:, 3] > 0)
    drawn = totals[kept, 2] / totals[kept, 3] - totals[kept, 0] / totals[kept, 1]
    assert 0 < int((~kept).sum()) < 3000  # some draws hold no scoreable statement of a type
    assert (got["draws"], got["draws_left_out"]) == (int(kept.sum()), int((~kept).sum()))
    assert near(got["ci95"], [float(v) for v in np.quantile(drawn, [0.025, 0.975])], 1e-12)
    # another seed, and another number of draws, give another interval
    assert not near(
        sc.type_difference(rows, types, made, "one", "other", 3000, 8)["ci95"], got["ci95"], 1e-6
    )
    # in one episode there is no interval
    alone = sc.type_difference(rows.assign(episode_id="e"), types, made, "one", "other", 3000, 7)
    assert (
        alone["ci95"] is None
        and alone["draws"] == 0
        and near(alone["difference"], got["difference"])
    )


@pytest.mark.parametrize(
    ("recovery", "next_delivery", "not_scoreable", "kinds"),
    [
        (117, 3, (), ("bare", "bare")),  # a type of three statements, and the rest of the set
        (4, 116, (), ("bare", "bare")),
        (100, 40, (), ("shown", "under the floor")),  # fewer than 50 scoreable statements
        (100, 49, (), ("shown", "under the floor")),
        (100, 50, (), ("shown", "shown")),
        (100, 60, tuple(range(100, 150)), ("shown", "under the floor")),  # ten scoreable of sixty
        # two scoreable statements of sixty: the other type's figures, beside those of the
        # item set, would give the losses of the two
        (100, 60, tuple(range(100, 158)), ("counts", "under the floor")),
        # three statements of a type are not scoreable: its own scenarios are withheld, and
        # those of the item set with them, so the other type gives nothing back
        (100, 60, (100, 101, 102), ("shown", "shown")),
        # and ten of the other type as well: the scenarios of the item set are written, and
        # less those of the other type they would be those of the type with the three; the
        # other type keeps what is scored on its scoreable statements
        (100, 60, (*range(10), 100, 101, 102), ("fills", "shown")),
        (100, 0, (), ("shown", "none")),  # one type alone: it is the item set
    ],
)
def test_a_type_within_its_item_set_is_held_to_the_rules_of_withholding(
    recovery: int, next_delivery: int, not_scoreable: tuple[int, ...], kinds: tuple[str, str]
) -> None:
    """A type within the item set is a set beside its whole (PLAN, standing rules): a type of
    one to four statements, and a type that is the item set but for so few, hold the number of
    their statements alone; a type whose figures would give a few scoreable statements back
    beside those of the item set holds its counts; a type whose statements that are not
    scoreable are those of the item set but for a few is written without the figures that
    fill the horizon events (section 2.5); "a type with fewer than 50 scoreable statements in
    an item set is reported by its counts alone"."""
    prepared, rows, sets = two_types(recovery, next_delivery, not_scoreable)
    entry = written(sc.by_statement_type(prepared, rows, sets, 200, 5))["models"]["m"]
    keep = rows["scoreable"].to_numpy()
    sizes = {"recovery": (recovery, int(keep[:recovery].sum()))}
    sizes["next_delivery"] = (next_delivery, int(keep[recovery:].sum()))
    for name, kind in zip(sc.TYPES, kinds, strict=True):
        block, (statements, scoreable) = entry["types"][name], sizes[name]
        counts = {"statements": statements, "scoreable_statements": scoreable}
        if kind == "none":
            assert block == {"statements": 0}
        elif kind == "bare":
            assert block == {"statements": statements, "withheld": True}
        elif kind == "shown":
            assert counts.items() <= block.items() and "withheld" not in block
            assert {"contrasts", "scores", "overconfidence"} <= set(block)
            if scoreable == statements:  # nothing of its own to withhold: its scenarios stand
                assert "undetermined_as_no" in block["contrasts"]["H1"]["bounds"], name
                assert "least" in block["scores"]["a"]["calibration_all_statements"]["E_end"]
                assert block["overconfidence"]["both_parts_hold"] is not None, name
        elif kind == "fills":
            apart = {
                "statements": statements,
                "with_a_horizon_event_undetermined": statements - scoreable,
                "withheld": True,
            }
            assert counts.items() <= block.items() and "withheld" not in block
            for name, record in block["contrasts"].items():
                assert "delta" in record and record["ci95"] is not None, name
                assert record["bounds"] == apart, name
            for name, record in block["scores"].items():
                assert record["primary_brier"] is not None and record["ci95"] is not None, name
                assert record["bounds_all_statements"] == apart, name
                assert record["calibration_all_statements"] == apart, name
                assert record["calibration_in_the_large"] == apart, name
            assert block["overconfidence"]["against_outcomes"] == apart
            assert block["overconfidence"]["both_parts_hold"] is None
            assert block["overconfidence"]["against_base_rate"]["met"] is True
            text = json.dumps(block)
            assert "_frequency" not in text and "undetermined_as" not in text
        else:
            assert counts.items() <= block.items() and numbers(block) == []
            assert set(block) - {
                "statements",
                "episodes",
                "scoreable_statements",
                "scoreable_episodes",
            } == ({"counts_alone"} if kind == "under the floor" else {"withheld"})
            if kind == "under the floor":
                assert block["counts_alone"] == "fewer than 50 scoreable statements"
    both = all(kind in ("shown", "fills") for kind in kinds)
    assert bool(entry["next_delivery_minus_recovery"]) is both
    assert bool(entry["opposite_signs_in_the_two_types"]) is both
    flag = entry["overconfidence_holds_on_the_item_set_and_not_on_its_recovery_statements"]
    on_all = entry["overconfidence_on_the_item_set"]["both_parts_hold"]
    # no reading where one to four statements of the item set are not scoreable
    assert (on_all is None) is (0 < int((~keep).sum()) < sc.MIN_SHOWN)
    assert (flag is None) is (kinds[0] != "shown" or on_all is None)
    # three statements that are not scoreable in a type: its own scenarios are withheld
    if not_scoreable[-3:] == (100, 101, 102):
        due = entry["types"]["next_delivery"]
        assert (
            due["contrasts"]["H1"]["bounds"]["withheld"] is True
            and "delta" in due["contrasts"]["H1"]
        )
        assert due["scores"]["a"]["bounds_all_statements"]["withheld"] is True
        assert due["overconfidence"]["against_outcomes"]["withheld"] is True
        assert due["overconfidence"]["both_parts_hold"] is None  # the criterion is not read
        assert due["overconfidence"]["against_base_rate"]["met"] is True


@pytest.mark.parametrize("others", [0, 1, 4, 5])
def test_the_statements_of_another_type_within_an_item_set(others: int) -> None:
    """The two types need not make up the item set. Where one to four of its statements are of
    another type, the figures of the item set less those of the two types would be those of
    the few, and its counts would say how many of them are scoreable: the type of the fewest
    statements keeps their number alone and is marked."""
    prepared, rows, sets = two_types(60, 120)
    first = prepared.study.first
    first.loc[rows.index[60 : 60 + others], "statement_type"] = "tbd"
    entry = written(sc.by_statement_type(prepared, rows, sets, 100, 5))["models"]["m"]
    assert entry["statements_of_another_type"] == others and entry["statements"] == 180
    back, due = entry["types"]["recovery"], entry["types"]["next_delivery"]
    assert due["statements"] == 120 - others and "contrasts" in due
    if 0 < others < sc.MIN_SHOWN:
        assert back == {"statements": 60, "withheld": True, sc.WITH_ANOTHER: True}
        assert entry["next_delivery_minus_recovery"] == {}
        assert (
            entry["overconfidence_holds_on_the_item_set_and_not_on_its_recovery_statements"] is None
        )
    else:
        assert "contrasts" in back and sc.WITH_ANOTHER not in json.dumps(entry)
        assert entry["next_delivery_minus_recovery"]
    # a type that keeps its number alone already: no second one goes
    prepared, rows, sets = two_types(3, 120)
    prepared.study.first.loc[rows.index[3:5], "statement_type"] = "tbd"
    entry = written(sc.by_statement_type(prepared, rows, sets, 100, 5))["models"]["m"]
    assert entry["types"]["recovery"] == {"statements": 3, "withheld": True}
    assert "contrasts" in entry["types"]["next_delivery"]
    assert entry["statements_of_another_type"] == 2


def test_a_type_that_is_another_set_but_for_a_few_statements() -> None:
    """The same figures are written on other sets than the item set: the post-cutoff slice of a
    model, the statements first captured by the stated end, those of the month-and-year form
    (``known_sets``). A type that is one of them but for one to four statements holds the
    number of its statements alone, like a type within its item set."""
    cutoff = S.CUTOFF_MONTH_ENDS[LLAMA].isoformat()
    assert cutoff == "2023-12-31" and S.has_slice(S.CUTOFF_MONTH_ENDS[LLAMA])
    # the 60 recovery statements and two of the 120 others are dated after the cutoff
    dates = ["2024-02-10"] * 62 + ["2023-06-15"] * 118
    prepared, rows, sets = two_types(60, 120, (), dates)
    known = sc.known_sets(prepared.study, rows, sets)
    after, fills, of = known[f"the post-cutoff slice of {SLICED}"]
    # on the slice of a secondary model the base rate's calibration stands beside the model's
    assert len(after) == 62 and fills is True and of is None
    assert sc.near_sets(rows.iloc[:60], rows.loc[after]) == "bare"
    # on the slice of a primary that is not its item set the evaluator repeats its tests:
    # the contrasts of that primary alone, which stand beside no figure of another model; but
    # they come with the number of its scoreable statements, so a set that is that slice but
    # for two statements keeps no count either, whichever model it is of
    assert known[f"the post-cutoff slice of {LLAMA}"][1:] == (False, LLAMA)
    assert sc.beside_known(rows.iloc[:60], rows, known, "m: recovery", "m") == "bare"
    alone = {name: entry for name, entry in known.items() if entry[2] == LLAMA}
    assert len(alone) == 1 and sc.beside_known(rows.iloc[:60], rows, alone, "", "m") == "bare"
    assert sc.beside_known(rows.iloc[:60], rows, alone, "", LLAMA) == "bare"
    # six statements apart, two of them scoreable: the contrasts of that primary would give
    # the losses of the two beside its own figures, and beside no figure of another model
    dim = rows.copy()
    dim.loc[dim.index[[56, 57, 58, 59]], "y_a"] = np.nan
    dim["scoreable"] = dim["y_a"].notna() & dim["y_b"].notna()
    assert sc.near_sets(dim.iloc[:56], dim.loc[after], False) == "counts"
    assert sc.beside_known(dim.iloc[:56], dim, alone, "", LLAMA) == "counts"
    assert sc.beside_known(dim.iloc[:56], dim, alone, "", "m") is None
    # a set of no statement holds no figure: a type of three statements is not near it
    empty = {"none": (rows.index[:0], True, None)}
    assert sc.near_sets(rows.iloc[:3], rows.iloc[:0]) == "bare"
    assert sc.beside_known(rows.iloc[:3], rows, empty) is None
    entry = written(sc.by_statement_type(prepared, rows, sets, 200, 5))["models"]["m"]
    assert entry["types"]["recovery"] == {"statements": 60, "withheld": True}
    assert "contrasts" in entry["types"]["next_delivery"]
    assert entry["next_delivery_minus_recovery"] == {}
    # with five of the others after the cutoff the type is written
    prepared, rows, sets = two_types(60, 120, (), ["2024-02-10"] * 65 + ["2023-06-15"] * 115)
    entry = written(sc.by_statement_type(prepared, rows, sets, 200, 5))["models"]["m"]
    assert "contrasts" in entry["types"]["recovery"] and entry["next_delivery_minus_recovery"]
    # the sets known, by name, and the three answers of the pair rule
    assert list(sc.known_sets(prepared.study, rows, sets))[:1] == ["every eligible statement"]
    assert {"the item set of m", "m: recovery", "m: next_delivery"} <= set(known)
    # every statement was first captured by the stated end and is of the month-and-year form:
    # those two parts are the item set, which has its own entry
    assert not [name for name in known if "captured" in name or "month" in name]
    assert (
        sc.near_sets(rows, rows) is None and sc.near_sets(rows.iloc[:60], rows.iloc[:64]) == "bare"
    )
    dim = rows.copy()
    dim.loc[dim.index[60:63], "y_a"] = np.nan
    dim["scoreable"] = dim["y_a"].notna() & dim["y_b"].notna()
    assert sc.near_sets(dim.iloc[:60], dim.iloc[:70]) is None
    assert sc.near_sets(dim.iloc[:60], dim.iloc[:66]) == "counts"  # three of the six are scoreable
    # three that are not scoreable in a set whose scenarios are withheld for them: nothing
    # to take from; with ten more in both sets the scenarios of both are written, and those
    # alone would give the three back
    assert sc.near_sets(dim.iloc[:60], dim.iloc[:120]) is None
    dim.loc[dim.index[:10], "y_a"] = np.nan
    dim["scoreable"] = dim["y_a"].notna() & dim["y_b"].notna()
    assert sc.near_sets(dim.iloc[:60], dim.iloc[:120]) == "fills"
    assert sc.NEAR_STATES == (None, "fills", "counts", "bare")
    # unless the other set holds contrasts on its scoreable statements alone: the statements
    # first captured by the stated end, those of the month-and-year form
    assert sc.near_sets(dim.iloc[:60], dim.iloc[:120], fills=False) is None
    assert [entry[1:] for name, entry in known.items() if name.startswith("m: ")] == [
        (True, None),
        (True, None),
    ]
    # the statements first captured by the stated end, and those of the month-and-year form:
    # the evaluator repeats the tests of the primary on them. A type that is one of them but
    # for a few statements holds its number alone; a part of the item set that is the item
    # set but for a few holds no figure and is not among the sets known
    for column, value, name in (
        ("delayed_entry", "True", "m: first captured by the stated end"),
        ("form", "quarter", "m: month-and-year form"),
    ):
        for more, state in ((2, "bare"), (4, "bare"), (5, None)):
            prepared, rows, sets = two_types(60, 120)
            first = prepared.study.first
            first.loc[rows.index[60 + more :], column] = value
            known = sc.known_sets(prepared.study, rows, sets)
            assert known[name][1:] == (False, "m") and len(known[name][0]) == 60 + more
            assert sc.beside_known(rows.iloc[:60], rows, known, "m: recovery", "m") == state
            block = written(sc.by_statement_type(prepared, rows, sets, 100, 5))
            block = block["models"]["m"]["types"]["recovery"]
            assert (block == {"statements": 60, "withheld": True}) is (state == "bare"), name
        first.loc[rows.index[4:], column] = first[column].iloc[0]  # all but four statements
        first.loc[rows.index[:4], column] = value
        assert name not in sc.known_sets(prepared.study, rows, sets)
        assert sc.written_part(np.arange(180) >= 5) and not sc.written_part(np.arange(180) >= 4)
        assert not sc.written_part(np.arange(180) >= 176) and not sc.written_part(np.ones(9, bool))
    # a set of a few scoreable statements is under the floor already: two scoreable statements
    # in one set, the same two and two more in the other, fifty statements apart
    _, thin, _ = two_types(100, 60, tuple(range(98)))
    one, other = thin.iloc[:100], thin.iloc[50:102]
    assert (int(one["scoreable"].sum()), int(other["scoreable"].sum())) == (2, 4)
    assert sc.near_sets(one, other) is None


def test_a_type_beside_the_other_sets_on_which_a_figure_of_its_primary_is_written() -> None:
    """The loss of condition (c) of a primary is also written on the two parts of its selective
    prediction; its tests, by the evaluator, on the statements both sides parsed, and both
    parts of the criterion on the answers of condition (a) that parsed; its loss of condition
    (b) on the paraphrase subset and on the subset of the 2x2. A type that is one of those
    sets but for one to four statements holds the number of its statements alone, like a type
    beside its item set (PLAN, standing rules)."""

    def recovery_block(
        read: int = 0, parsed: int = 0, chosen: int = 0, key: str = "", side: str = "m:a"
    ) -> dict:
        """The recovery type of 60 statements where the literal reading reads its statements
        and ``read`` more, where the answers of ``side`` parsed on them and ``parsed`` more,
        and where the subset ``key`` holds them and ``chosen`` more."""
        prepared, rows, sets = two_types(60, 120)
        study, ids = prepared.study, rows.index
        if read:
            days = np.where(np.arange(180) < 60 + read, 30.0, np.nan)
            prepared.reading_days["m"] = pd.Series(days, index=ids)
        if parsed:
            study.parsed[side] = pd.Series(np.arange(180) < 60 + parsed, index=ids)
        subsets = {key: list(ids[: 60 + chosen])} if key else None
        known = sc.known_sets(study, rows, sets, prepared.reading_days, subsets)
        got = written(sc.by_statement_type(prepared, rows, sets, 100, 5, known))
        block = got["models"]["m"]["types"]["recovery"]
        # the same through the sets the function works out itself, where it can
        if not key:
            alone = written(sc.by_statement_type(prepared, rows, sets, 100, 5))
            assert alone["models"]["m"]["types"]["recovery"] == block
        return {"block": block, "known": known}

    bare = {"statements": 60, "withheld": True}
    # the statements read by condition (c): the recovery statements and two more
    found = recovery_block(read=2)
    assert found["block"] == bare
    part, fills, of = found["known"]["m: read by condition (c)"]
    assert (len(part), fills, of) == (62, True, "m")
    assert len(found["known"]["m: abstained on by condition (c)"][0]) == 118
    assert "scores" in recovery_block(read=5)["block"]
    # the answers of condition (a) that parsed, and with them the statements both sides of
    # H1 parsed: the recovery statements and four more
    found = recovery_block(parsed=4)
    assert found["block"] == bare
    assert found["known"]["m: answers of condition (a) that parsed"][1:] == (True, None)
    assert found["known"]["m: both sides of H1 parsed"][1:] == (False, "m")
    assert len(found["known"]["m: both sides of H1 parsed"][0]) == 64
    assert "m: both sides of H2 parsed" not in found["known"]  # no answer of (c) failed
    assert "scores" in recovery_block(parsed=5)["block"]
    # the answers of the other side of H1 alone, and those of condition (c) for H2: every
    # answer of condition (a) parsed, so the statements both sides parsed stand alone
    for side, test in (("m:b", "H1"), ("m:c", "H2")):
        found = recovery_block(parsed=3, side=side)
        assert found["block"] == bare, side
        assert "m: answers of condition (a) that parsed" not in found["known"]
        assert list(found["known"][f"m: both sides of {test} parsed"][0]) == [
            f"S{k}" for k in range(63)
        ]
        assert "scores" in recovery_block(parsed=5, side=side)["block"], side
    # a subset on which the primary is read again
    for key in ("paraphrase", "twobytwo", "samples"):
        found = recovery_block(chosen=3, key=key)
        assert found["block"] == bare, key
        assert found["known"][f"m: the {key} subset"][1:] == (key != "samples", "m")
        assert "scores" in recovery_block(chosen=5, key=key)["block"], key
    # nothing failed and nothing was read again: the sets known are those of the cells
    prepared, rows, sets = two_types(60, 120)
    known = sc.known_sets(prepared.study, rows, sets, prepared.reading_days, {})
    assert not [name for name in known if "parsed" in name or "subset" in name or "(c)" in name]
    # the statements of a subset after the cutoff of a primary whose probe beat the base rate
    cutoff = S.CUTOFF_MONTH_ENDS[LLAMA].isoformat()
    record = {"switched": True, "evaluable": True, "cutoff_month_end": cutoff}
    prepared.study.first.loc[rows.index[:30], "event_date"] = "2023-06-15"
    later = sc.known_sets(
        prepared.study,
        rows,
        {LLAMA: (rows.index[30:], record)},
        None,
        {"paraphrase": list(rows.index[20:90]), "tbd": ["x"]},
    )
    assert len(later[f"{LLAMA}: the paraphrase subset"][0]) == 70
    assert list(later[f"{LLAMA}: the paraphrase subset after its cutoff"][0]) == list(
        rows.index[30:90]
    )
    assert not [name for name in later if "tbd" in name]
    # what stands beside the tables of E1: the sets with a frequency whichever model
    beside = sc.sets_beside_the_tables(recovery_block(parsed=5)["known"])
    assert list(beside["m: answers of condition (a) that parsed"]) == [f"S{k}" for k in range(65)]
    assert not [name for name in beside if "both sides" in name or "captured" in name]


def test_the_slice_of_a_secondary_model_beside_the_parts_of_its_selective_prediction() -> None:
    """The loss of condition (c) of a secondary model is written on its post-cutoff slice and
    on the two parts of its selective prediction. A slice that is the statements read but
    for one to four statements keeps its number alone; where their scoreable statements
    differ by so few, the record of condition (c) keeps its counts; where only those that
    are not scoreable do, it is written without the figures of section 2.5."""

    def scored_with(read: Sequence[int], dim: Sequence[int] = ()) -> dict:
        """Eighty statements, twenty of them before the cutoff: the literal reading reads
        those at the positions ``read``; those at ``dim`` are not scoreable."""
        prepared, rows = study_by_hand(80, 20, [k not in dim for k in range(80)])
        days = [30.0 if k in read else np.nan for k in range(80)]
        prepared.reading_days[SLICED] = pd.Series(days, index=rows.index)
        return written(sc.secondary_models(prepared, rows, {}, [SLICED], 100, 3))["models"][SLICED]

    after = range(20, 80)
    bare = {"statements": 60, "withheld": True}
    # the statements read are the slice and two more
    entry = scored_with([0, 1, *after])
    assert entry["scores_on_the_post_cutoff_slice"] == bare
    assert entry["post_cutoff_slice"]["slice_scoreable"] is None
    # the statements abstained on are the slice and three more
    entry = scored_with(range(3, 20))
    assert entry["on_the_post_cutoff_slice"] == bare
    # five more are read, two of them scoreable: the loss of (c) on the two
    entry = scored_with([*range(5), *after], (0, 1, 2, 18, 19, *range(40, 45)))
    on_the_slice = entry["scores_on_the_post_cutoff_slice"]
    assert on_the_slice["c"] == {
        "scoreable_statements": 55,
        "scoreable_episodes": on_the_slice["a"]["scoreable_episodes"],
        "statements": 60,
        "withheld": True,
    }
    for condition in ("a", "b"):
        assert "primary_brier" in on_the_slice[condition]
        assert "undetermined_as_no" in on_the_slice[condition]["bounds_all_statements"]
    assert "delta" in entry["on_the_post_cutoff_slice"]["H2"]
    # eight more are read, three of them not scoreable: the scenarios of (c) on the three
    entry = scored_with([*range(8), *after], (0, 1, 2, 18, 19, *range(40, 45)))
    on_the_slice = entry["scores_on_the_post_cutoff_slice"]
    record = on_the_slice["c"]
    assert record["bounds_all_statements"] == {
        "statements": 60,
        "with_a_horizon_event_undetermined": 5,
        "withheld": True,
    }
    assert record["mean_p_E_end"] is None and "primary_brier" in record
    assert "undetermined_as_no" in on_the_slice["a"]["bounds_all_statements"]
    # five more read, all scoreable: everything is written
    entry = scored_with([*range(5), *after], (15, 16, 17, 18, 19, *range(40, 45)))
    record = entry["scores_on_the_post_cutoff_slice"]["c"]
    assert "undetermined_as_no" in record["bounds_all_statements"] and "primary_brier" in record
    entry = scored_with([*range(16), *after])  # the slice is the statements read but for 16
    assert "primary_brier" in entry["scores_on_the_post_cutoff_slice"]["c"]
    # a reading that abstains on three statements: no part of its selective prediction is
    # written, so the slice, which is the statements read but for three, gives way to nothing
    prepared, rows = study_by_hand(80, 6)
    days = [np.nan if k < 3 else 30.0 for k in range(80)]
    prepared.reading_days[SLICED] = pd.Series(days, index=rows.index)
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 100, 3))["models"][SLICED]
    assert entry["post_cutoff_slice"]["slice_statements"] == 74
    assert "primary_brier" in entry["scores_on_the_post_cutoff_slice"]["c"]
    # with five abstained on, the statements read are a part that is written, one statement
    # from the slice
    days = [np.nan if k < 5 else 30.0 for k in range(80)]
    prepared.reading_days[SLICED] = pd.Series(days, index=rows.index)
    entry = written(sc.secondary_models(prepared, rows, {}, [SLICED], 100, 3))["models"][SLICED]
    assert entry["scores_on_the_post_cutoff_slice"] == {"statements": 74, "withheld": True}


def test_a_type_of_three_statements_where_no_other_set_stands_near_it() -> None:
    """The floor of five holds for a type by itself: here every statement is dated after
    every cutoff, so no set of the known ones is a set of no statement or of a few, and the
    type of three statements still keeps their number alone."""
    prepared, rows, sets = two_types(117, 3, (), ["2025-06-15"] * 120)
    known = sc.known_sets(prepared.study, rows, sets)
    assert sorted({len(ids) for ids, _, _ in known.values()}) == [3, 117, 120]
    frame = rows.iloc[117:]
    assert sc.beside_known(frame, rows, known, "m: next_delivery", "m") is None
    bare = {"statements": 3, "withheld": True}
    assert sc.type_block("m", frame, prepared.study, None, 100, 5) == bare
    got = written(sc.by_statement_type(prepared, rows, sets, 100, 5))["models"]["m"]["types"]
    assert got["next_delivery"] == bare
    assert got["recovery"] == {"statements": 117, "withheld": True}  # the item set but for three


def test_the_types_of_two_primaries_whose_item_sets_differ_by_a_few_statements() -> None:
    """The figures of a predictor that reads no text, and the frequencies of the events, are
    the same whichever primary a type is of: the recovery statements of two primaries whose
    item sets differ by two of them are both withheld; their next-delivery statements, one
    set for both, are written for each."""
    prepared, rows, sets = two_types(60, 120)
    record = {"switched": True, "evaluable": True, "items": ev.SLICE_ITEMS}
    sets["n"] = (rows.index[2:], record)
    study = prepared.study
    for condition in ev.CONDITIONS:
        study.predictions[f"n:{condition}"] = study.predictions[f"m:{condition}"]
    study.parsed["n:a"] = study.parsed["m:a"]
    study.selection["n"] = "b"
    # the sets known need the literal reading of every primary with an item set: without
    # that of the second one the analysis stops, and nothing is written
    with pytest.raises(ValueError, match="the literal reading of n is not given"):
        sc.by_statement_type(prepared, rows, sets, 100, 5)
    prepared.reading_days["n"] = prepared.reading_days["m"]
    got = written(sc.by_statement_type(prepared, rows, sets, 100, 5))["models"]
    assert got["m"]["types"]["recovery"] == {"statements": 60, "withheld": True}
    assert got["n"]["types"]["recovery"] == {"statements": 58, "withheld": True}
    for model in ("m", "n"):
        assert "scores" in got[model]["types"]["next_delivery"]
        assert got[model]["next_delivery_minus_recovery"] == {}
    # five apart: the types of both are written
    sets["n"] = (rows.index[5:], record)
    got = written(sc.by_statement_type(prepared, rows, sets, 100, 5))["models"]
    assert "scores" in got["m"]["types"]["recovery"] and "scores" in got["n"]["types"]["recovery"]


def test_the_scenarios_of_a_slice_where_those_of_the_list_are_withheld() -> None:
    """Two statements before the cutoff are not scoreable, and no other: the list's own
    figures over every statement are withheld for them (section 2.5), so those of the slice,
    which holds scoreable statements alone, have nothing beside them to give the two back,
    and are written."""
    prepared, rows = study_by_hand(70, 10, [k not in (0, 7) for k in range(70)])
    got = written(sc.secondary_models(prepared, rows, {}, [SLICED], 100, 3))
    whole = got["scores_on_every_eligible_statement"][SLICED]["a"]
    assert whole["bounds_all_statements"] == {
        "statements": 70,
        "with_a_horizon_event_undetermined": 2,
        "withheld": True,
    }
    assert whole["mean_p_E_end"] is None
    record = got["models"][SLICED]["scores_on_the_post_cutoff_slice"]["a"]
    assert "undetermined_as_no" in record["bounds_all_statements"]
    assert record["mean_p_E_end"] is not None
    assert "least" in record["calibration_all_statements"]["E_end"]
    assert "ci95" in record["calibration_in_the_large"]["E_end"]["base_rate"]


def after_cutoff_case(
    count: int = 26, before: int = 12, seed: int = 5
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A subset or list of a primary whose probe beat the base rate: ``count`` statements with
    their own open predictions, the first ``before`` of them dated before its cutoff. Returns
    the statements, those after the cutoff, and the predictions."""
    prepared, rows = study_by_hand(count, seed=seed)
    return rows, rows.iloc[before:], prepared.study.predictions[f"{SLICED}:a"]


def test_a_part_of_the_figures_after_the_cutoff_beside_the_same_part_on_the_whole() -> None:
    """The figures after the cutoff repeat those on the whole subset or list, part by part: a
    part of selective prediction, the statements both readings parsed, the statements with a
    target. Where one of these holds one to four statements before the cutoff, the figure on
    the whole less the figure after the cutoff is theirs."""
    rows, later, pred = after_cutoff_case()
    # selective prediction: six statements abstained on, one of them before the cutoff
    days = pd.Series(10.0, index=rows.index)
    days.iloc[[0, 13, 14, 15, 16, 17]] = np.nan

    def selective(chosen: pd.DataFrame, within: pd.DataFrame | None = None) -> dict[str, Any]:
        return {"selective": sc.selective(chosen, pred, days, 200, 3, True, within)}

    whole = written(selective(rows))
    got = written(sc.beside_the_whole(rows, later, selective, whole))["after_the_cutoff"]
    assert whole["selective"]["primary_brier_abstained_on"]["statements"] == 6
    point = got["selective"]
    assert point["abstained"] == 5 and point["statements"] == 14
    for part in ("read", "abstained_on"):  # the other part with it: the loss on all is given
        assert point[f"primary_brier_{part}"]["mean"] is None
        assert point[f"primary_brier_{part}"]["withheld"] is True
        assert "undetermined_as_no" not in point[f"primary_brier_{part}"]["bounds_all_statements"]
    assert point["primary_brier_all"]["mean"] is not None
    # with five of them before the cutoff and five after, both parts are given on both sets
    days = pd.Series(10.0, index=rows.index)
    days.iloc[[0, 1, 2, 3, 4, 13, 14, 15, 16, 17]] = np.nan
    whole = written(selective(rows))
    got = written(sc.beside_the_whole(rows, later, selective, whole))["after_the_cutoff"]
    assert got["selective"]["primary_brier_abstained_on"]["statements"] == 5
    assert got["selective"]["primary_brier_abstained_on"]["mean"] is not None
    assert got["selective"]["primary_brier_read"]["mean"] is not None

    # the paraphrases: six answers of one paraphrase failed, one of them before the cutoff
    names = ["registered", "p1", "p2", "p3"]
    rng = np.random.default_rng(9)
    predictions = {
        name: forecasts(
            rows.index, rng.uniform(0.1, 0.9, 26).round(3), rng.uniform(0.1, 0.9, 26).round(3)
        )
        for name in names
    }
    flags = {name: pd.Series(True, index=rows.index) for name in names}
    flags["p1"].iloc[[0, 13, 14, 15, 16, 17]] = False

    def variance(chosen: pd.DataFrame, within: pd.DataFrame | None = None) -> dict[str, Any]:
        return sc.variance_figures(chosen, predictions, flags, "registered", 200, 3, within)

    whole = written(variance(rows))
    on_whole = whole["change_from_the_registered_prompt"]["p1"]
    assert on_whole["primary_loss_both_parsed"]["statements"] == 20
    assert "delta" in on_whole["primary_loss_both_parsed"]
    got = written(sc.beside_the_whole(rows, later, variance, whole))["after_the_cutoff"]
    change = got["change_from_the_registered_prompt"]["p1"]
    assert change["primary_loss_both_parsed"] == {"not_both_parsed": 5, "withheld": True}
    assert change["scoreable_not_parsed_by_both"] is None
    assert "delta" in change["primary_loss"] and change["primary_loss"]["statements"] == 14
    # a paraphrase whose every answer was parsed is given on both sets
    other = got["change_from_the_registered_prompt"]["p2"]
    assert near(other["primary_loss_both_parsed"]["delta"], other["primary_loss"]["delta"])

    # the sampled quantiles: one statement before the cutoff has a target, five have none.
    # The guard of the whole block counts scoreable statements; the pinball loss runs over
    # the statements with a target
    part = typed(
        episode_id=[f"e{k // 2}" for k in range(14)],
        y_a=[0.0] * 14,
        y_b=[0.0] * 14,
        ttr_kind=["interval"] + ["right_censored"] * 5 + ["interval"] * 8,
        ttr_mid=[137.0] + [np.nan] * 5 + [40.0, 60.0, 80.0, 100.0, 120.0, 140.0, 160.0, 180.0],
    )
    part["ttr_lower"], part["ttr_upper"] = part["ttr_mid"] - 5, part["ttr_mid"] + 5
    sampled = forecasts(part.index, [0.5] * 14, [0.5] * 14, q=np.arange(30.0, 170.0, 10.0))
    verbal = forecasts(part.index, [0.5] * 14, [0.5] * 14, q=np.arange(50.0, 190.0, 10.0))
    parsed = pd.Series(True, index=part.index)

    def quantiles(chosen: pd.DataFrame, within: pd.DataFrame | None = None) -> dict[str, Any]:
        return sc.sampled_scores(chosen, sampled, verbal, parsed, 200, 3, within)

    whole = written(quantiles(part))
    got = written(sc.beside_the_whole(part, part.iloc[6:], quantiles, whole))["after_the_cutoff"]
    assert whole["pinball"]["0.50"]["sampled"]["statements"] == 9
    for level in got["pinball"].values():
        for name in ("sampled", "verbalised"):
            assert level[name] == {
                "statements": 8,
                "left_out_right_censored": 0,
                "withheld": True,
            }
        assert level["verbalised_minus_sampled"]["withheld"] is True
        assert "delta" not in level["verbalised_minus_sampled"]
        assert "delta" not in level["verbalised_minus_sampled_both_parsed"]
    assert numbers(got["pinball"]) == []
    # one statement without a target before the cutoff, five with one: the bounds of the loss
    # run over every statement, and would give the bracket of that one
    part["ttr_kind"] = ["interval"] * 5 + ["right_censored"] + ["interval"] * 8
    part["ttr_mid"] = [137.0, 30.0, 50.0, 70.0, 90.0, np.nan, *part["ttr_mid"].iloc[6:]]
    part["ttr_lower"], part["ttr_upper"] = part["ttr_mid"] - 5, part["ttr_mid"] + 5
    whole = written(quantiles(part))
    got = written(sc.beside_the_whole(part, part.iloc[6:], quantiles, whole))["after_the_cutoff"]
    assert whole["pinball"]["0.50"]["sampled"]["left_out_right_censored"] == 1
    assert got["pinball"]["0.50"]["sampled"]["withheld"] is True
    assert "delta" in got["pinball"]["0.50"]["verbalised_minus_sampled"]
    # six statements with a target before the cutoff and none without: the losses stand on
    # both sets
    part["ttr_kind"] = ["interval"] * 14
    part["ttr_mid"] = [137.0, 30.0, 50.0, 70.0, 90.0, 110.0, *part["ttr_mid"].iloc[6:]]
    part["ttr_lower"], part["ttr_upper"] = part["ttr_mid"] - 5, part["ttr_mid"] + 5
    whole = written(quantiles(part))
    got = written(sc.beside_the_whole(part, part.iloc[6:], quantiles, whole))["after_the_cutoff"]
    assert got["pinball"]["0.50"]["sampled"]["statements"] == 8
    assert "loss" in got["pinball"]["0.50"]["sampled"]
    assert "delta" in got["pinball"]["0.50"]["verbalised_minus_sampled_both_parsed"]


@pytest.mark.parametrize(
    ("before", "open_before", "open_after", "shown"),
    [
        (12, 0, 0, True),
        (1, 0, 0, False),  # one to four statements before the cutoff
        (4, 0, 0, False),
        (25, 0, 0, False),  # or after it
        (22, 0, 0, False),
        (12, 8, 0, False),  # or as many scoreable ones before it (four of twelve)
        (12, 0, 10, False),  # or after it (four of fourteen)
        (12, 2, 0, False),  # or as many that are not scoreable before it
        (12, 0, 3, False),  # or after it
        (12, 5, 5, True),
    ],
)
def test_the_figures_after_the_cutoff_are_withheld_where_a_side_of_it_holds_a_few(
    before: int, open_before: int, open_after: int, shown: bool
) -> None:
    rows, later, pred = after_cutoff_case(26, before)
    rows.loc[rows.index[:open_before], "y_a"] = np.nan
    rows.loc[rows.index[before : before + open_after], "y_a"] = np.nan
    rows["scoreable"] = rows["y_a"].notna() & rows["y_b"].notna()
    later = rows.iloc[before:]

    def figures(chosen: pd.DataFrame, within: pd.DataFrame | None = None) -> dict[str, Any]:
        return {
            "x": sc.mean_record(
                brier(pred.loc[chosen.index], chosen).dropna(),
                chosen["episode_id"][chosen["scoreable"]],
                100,
                1,
            )
        }

    got = sc.beside_the_whole(rows, later, figures, figures(rows))
    assert got["probe_excludes_the_statements_before_the_cutoff"] is True
    if shown:
        assert got["after_the_cutoff"]["statements"] == 26 - before
        assert got["after_the_cutoff"]["x"]["mean"] is not None
    else:
        assert got["after_the_cutoff"] == {"statements": 26 - before, "withheld": True}
    assert sc.beside_the_whole(rows, None, figures, {}) == {
        "probe_excludes_the_statements_before_the_cutoff": False
    }


def test_every_figure_has_the_floor_of_five_statements_whichever_function_made_it() -> None:
    """PLAN, standing rules: a secondary figure is withheld, its counts apart, where it rests
    on one to four statements. The evaluator's functions have a floor of two episodes for a
    contrast and none for a score; the records they give are held to five statements here,
    and a contrast that is not evaluable carries no estimate."""
    full = {"statements": 5, "episodes": 1, "evaluable": False, "reason": "why", "delta": 0.1}
    assert sc.floored(full) == {k: v for k, v in full.items() if k != "delta"}
    for count in (1, 4):
        few = full | {"statements": count, "evaluable": True, "ci95": [0.0, 0.2], "label": "x"}
        assert sc.floored(few) == {"statements": count, "episodes": 1, "withheld": True}
        assert sc.floored(few, "label")["label"] == "x"
    shown = full | {"evaluable": True, "ci95": [0.0, 0.2]}
    assert sc.floored(shown) == shown and sc.floored(shown) is not shown
    assert sc.floored({"statements": 0, "episodes": 0, "evaluable": False, "reason": "none"}) == {
        "statements": 0,
        "episodes": 0,
        "evaluable": False,
        "reason": "none",
    }
    # H2 on the month-and-year form with one such statement: one episode, and no estimate
    prepared, rows = study_by_hand(20, other_form=[k for k in range(20) if k != 7])
    repeated = written(sc.repeats_of(SLICED, rows, {}, prepared.study, 200, 3))
    assert repeated["h2_on_the_month_and_year_form"]["H2"] == {
        "comparator": ev.RULES,
        "tested": f"{SLICED}:c",
        "withheld": True,  # and not whether that one statement is scoreable
    }
    # a list of nine statements with two scoreable ones: no score on them, no contrast, and no
    # scenario either (the predictions are open: a scenario less its filled part is the sum)
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(9)],
        y_a=[1.0, 0.0] + [np.nan] * 7,
        y_b=[1.0, 1.0] + [np.nan] * 7,
        ttr_kind=["interval"] * 9,
        ttr_lower=[10.0] * 9,
        ttr_upper=[30.0] * 9,
        ttr_mid=[20.0] * 9,
    )
    rng = np.random.default_rng(4)
    made = {
        name: forecasts(rows.index, rng.uniform(0.1, 0.9, 9), rng.uniform(0.1, 0.9, 9), q=25.0)
        for name in (ev.BASE, "a", "b", "c")
    }
    flags = {c: pd.Series(True, index=rows.index) for c in "abc"}
    days = pd.Series([10.0] * 5 + [np.nan] * 4, index=rows.index)
    got = written(sc.list_figures(rows, "tbd", "m", made, flags, days, 200, 3))
    assert got["scoreable_statements"] == 2
    for name, record in got["scores"].items():
        assert set(record) == {
            "scoreable_statements",
            "scoreable_episodes",
            "statements",
            "withheld",
            "pinball_all_statements",
            "coverage_80",
        }, name
        assert record["scoreable_statements"] == 2 and record["withheld"] is True
        assert record["pinball_all_statements"]["0.50"]["statements"] == 9
        assert near(record["pinball_all_statements"]["0.50"]["loss"], 2.5)
    for condition, record in got["against_the_base_rate"].items():
        assert numbers(record) == [], condition
        assert record["statements"] == 2 and record["withheld"] is True
        assert record["bounds"] == {
            "statements": 9,
            "with_a_horizon_event_undetermined": 7,
            "withheld": True,
        }
    assert numbers(got["selective_prediction_of_condition_c"]) == [0.444444]  # the abstention rate
    # nine statements, of which three have a target: no pinball loss, and under five
    # statements nothing but counts
    rows["ttr_kind"] = ["interval"] * 3 + ["right_censored"] * 6
    assert sc.pinball_record(made["a"]["q50"], rows, 0.5) == {
        "statements": 3,
        "left_out_right_censored": 6,
        "withheld": True,
    }
    rows["ttr_kind"] = "interval"
    assert sc.scores(rows.iloc[:4], made["a"], 200, 3) == {"statements": 4, "withheld": True}
    assert sc.loss_bounds(rows.iloc[:4], made["a"]) == {"statements": 4, "withheld": True}
    assert sc.contrast_bounds(rows.iloc[:4], made, "a", "b") == {"statements": 4, "withheld": True}
    full_rows = rows.assign(y_a=1.0, y_b=1.0, scoreable=True)
    assert "primary_brier" in sc.scores(full_rows, made["a"], 200, 3)
    assert "withheld" not in sc.scores(full_rows, made["a"], 200, 3)
    # the probe test of a secondary model on four probe statements with a target
    study = SimpleNamespace(
        probe_ids=list(rows.index),
        probe={"m": made["a"], ev.BASE: made[ev.BASE]},
    )
    rows["ttr_kind"] = ["interval"] * 4 + ["right_censored"] * 5
    probe = written(sc.probe_of("m", study, rows, 200, 3))
    # PLAN section 5, E4: "The figures of a probe over 1 to 4 targets are withheld; its
    # verdict is given." The verdict is the one of the test on those four
    target = rows["ttr_mid"].to_numpy(dtype=float)[:4]
    test = ev.contrast(
        P.pinball(made[ev.BASE]["q50"].iloc[:4], target, ev.PROBE_LEVEL),
        P.pinball(made["a"]["q50"].iloc[:4], target, ev.PROBE_LEVEL),
        list(rows["episode_id"].iloc[:4]),
        200,
        3,
    )
    verdict = bool(ev.registered_p(test, 1, ev.P_VALUE_SOURCE) < ev.PROBE_ALPHA)
    few_targets = {"statements": 4, "left_out_right_censored": 5, "withheld": True}
    assert probe == {
        "probe_statements": 9,
        "left_out_right_censored": 5,
        "statements": 4,
        "episodes": 2,
        "evaluable": True,
        "withheld": True,
        "pinball_base_rate": few_targets,
        "pinball_model": few_targets,
        "p": None,
        "alpha": ev.PROBE_ALPHA,
        "beats_base_rate": verdict,
    }
    assert numbers(probe) == [ev.PROBE_ALPHA]
    rows["ttr_kind"] = "interval"
    probe = sc.probe_of("m", study, rows, 200, 3)
    assert probe["statements"] == 9 and "delta" in probe and "withheld" not in probe
    assert probe["beats_base_rate"] in (True, False) and "loss" in probe["pinball_model"]
    # in one episode the test cannot be made: no estimate, no verdict
    alone = sc.probe_of("m", study, rows.assign(episode_id="e"), 200, 3)
    assert alone["evaluable"] is False and "delta" not in alone
    assert alone["beats_base_rate"] is None and alone["p"] is None


def moved_frame(rows: pd.DataFrame, items: Sequence[int]) -> pd.DataFrame:
    """The statements under another outcome definition, which turns the first event of the
    statements at the positions ``items`` round."""
    under = rows.copy()
    under.loc[rows.index[list(items)], "y_a"] = 1.0 - rows["y_a"].iloc[list(items)]
    under["y_b"] = np.maximum(under["y_a"], under["y_b"])
    return under


def test_one_outcome_definition_beside_another() -> None:
    """A contrast is written under the primary outcome and again under other definitions of
    it: the outcome variants and the variants of the recovery rule. Two of them that give one
    to four statements other horizon events would give, together, the change of the losses of
    those few: the later one is withheld, whether the other is the primary outcome or not."""
    prepared, rows = study_by_hand(24)
    one, other = moved_frame(rows, range(5)), moved_frame(rows, range(6))
    few, far = moved_frame(rows, [3]), moved_frame(rows, range(10, 16))
    assert sc.near_definitions(
        rows, {"a": one, "b": other, "c": few, "d": far, "e": None}, rows.index
    ) == {
        "a": (5, False),
        "b": (6, True),  # one statement apart from the definition before it
        "c": (1, True),  # one statement apart from the primary outcome
        "d": (6, False),
    }
    # on a part of the statements the counts are those of the part
    assert sc.near_definitions(rows, {"a": one, "d": far}, rows.index[4:12]) == {
        "a": (1, True),
        "d": (2, True),
    }
    # PLAN section 2.5: "or 1 to 4 of those scoreable under either definition". A definition
    # gives eight statements another event, six of them scoreable under neither definition:
    # the contrast holds the losses of the two others, and beside the one under the primary
    # outcome it would give their change
    dim = rows.copy()
    dim.loc[rows.index[:6], "y_b"] = np.nan
    dim["scoreable"] = dim["y_a"].notna() & dim["y_b"].notna()
    lit = moved_frame(dim, range(8))
    lit.loc[rows.index[:6], "y_b"] = np.nan
    lit["scoreable"] = lit["y_a"].notna() & lit["y_b"].notna()
    assert ev.other_events(dim, lit) == 8 and ev.other_events(dim, lit, scored=True) == 2
    assert sc.near_definitions(dim, {"a": lit}, rows.index) == {"a": (8, True)}
    limited = sc.RECOVERY_VARIANTS[0]
    got = written(sc.recovery_rule(prepared, dim, {limited: lit}, {}, [SLICED], 200, 3))[limited]
    assert got["statements_with_another_horizon_event"] == {SLICED: 8}
    assert got["withheld_beside_another_outcome"] == [SLICED]
    assert numbers(got["contrasts"]) == []
    # with five of the eight scoreable under one of the two, the contrasts are written
    lit.loc[rows.index[3:6], "y_b"] = 1.0
    lit["scoreable"] = lit["y_a"].notna() & lit["y_b"].notna()
    assert ev.other_events(dim, lit) == 8 and ev.other_events(dim, lit, scored=True) == 5
    assert sc.near_definitions(dim, {"a": lit}, rows.index) == {"a": (8, False)}
    # the recovery rule: two variants that move five and six statements and differ on one
    limited, left, cell = sc.RECOVERY_VARIANTS
    got = written(sc.recovery_rule(prepared, rows, {left: one, cell: other}, {}, [SLICED], 200, 3))
    assert got[left]["statements_with_another_horizon_event"] == {SLICED: 5}
    assert got[cell]["statements_with_another_horizon_event"] == {SLICED: 6}
    assert got[left]["withheld_beside_another_outcome"] == []
    assert got[cell]["withheld_beside_another_outcome"] == [SLICED]
    assert "delta" in got[left]["contrasts"][SLICED]["H1"]
    for record in got[cell]["contrasts"][SLICED].values():
        assert set(record) == {"comparator", "tested", "withheld", "bounds"}
        assert record["withheld"] is True and record["bounds"] == {"withheld": True}
    assert got[left]["scoreable_statements"] == 24 and got[cell]["scoreable_statements"] is None
    # an outcome variant of the evaluator stands before the recovery rule: a variant of the
    # rule that is one statement apart from it is withheld, although it moves six
    got = written(
        sc.recovery_rule(prepared, rows, {limited: other}, {}, [SLICED], 200, 3, {"any": one})
    )
    assert got[limited]["statements_with_another_horizon_event"] == {SLICED: 6}
    assert got[limited]["withheld_beside_another_outcome"] == [SLICED]
    assert "delta" not in got[limited]["contrasts"][SLICED]["H1"]
    # the repeats of a secondary model under the outcome variants: the same rule
    variants = {
        "all_covered_presentations": few,
        "any_covered_presentation": one,
        "recovery_definition_A": other,
    }
    entry = written(sc.secondary_models(prepared, rows, variants, [SLICED], 200, 3))["models"][
        SLICED
    ]
    assert entry["outcome_variants"] == {
        "all_covered_presentations": {
            "statements_with_another_horizon_event": 1,
            "withheld_beside_another_outcome": True,
        },
        "any_covered_presentation": {
            "statements_with_another_horizon_event": 5,
            "withheld_beside_another_outcome": False,
        },
        "recovery_definition_A": {
            "statements_with_another_horizon_event": 6,
            "withheld_beside_another_outcome": True,
        },
    }
    repeated = entry["repeated_on_every_eligible_statement"]
    main = entry["on_every_eligible_statement"]["H1"]
    for label, shown in (
        ("all_covered_presentations", False),
        ("any_covered_presentation", True),
        ("recovery_definition_A", False),
    ):
        for name, record in repeated[label].items():
            assert ("delta" in record) is shown, (label, name)
            # withheld with its counts: the number moved stands in ``outcome_variants``
            assert shown or set(record) == {"comparator", "tested", "withheld"}, (label, name)
    a, b = (prepared.study.predictions[f"{SLICED}:{c}"] for c in "ab")
    assert near(
        repeated["any_covered_presentation"]["H1"]["delta"], (brier(a, one) - brier(b, one)).mean()
    )
    assert not near(repeated["any_covered_presentation"]["H1"]["delta"], main["delta"])
    # a variant that changes nothing is the contrast itself, and is given
    same = written(
        sc.repeats_of(
            SLICED, rows, {"any_covered_presentation": rows.copy()}, prepared.study, 200, 3
        )
    )
    assert near(same["any_covered_presentation"]["H1"]["delta"], main["delta"])
    # the definitions of the whole result file are looked at, whichever section is computed
    again = written(
        sc.repeats_of(
            SLICED,
            rows,
            {"recovery_definition_A": other},
            prepared.study,
            200,
            3,
            {"x": one, "recovery_definition_A": other},
        )
    )
    assert again["recovery_definition_A"]["H1"]["withheld"] is True
    alone = written(
        sc.repeats_of(SLICED, rows, {"recovery_definition_A": other}, prepared.study, 200, 3)
    )
    assert "delta" in alone["recovery_definition_A"]["H1"]


def test_a_record_beside_the_same_record_on_a_set_that_holds_it() -> None:
    whole = {
        "statements": 20,
        "episodes": 9,
        "delta": 0.1,
        "bounds": {
            "statements": 24,
            "with_a_horizon_event_undetermined": 4,
            "undetermined_as_no": 0.2,
        },
        "pinball": {"0.50": {"statements": 18, "left_out_right_censored": 6, "loss": 3.0}},
        "label": "x",
    }
    same = sc.beside(whole, whole)
    assert same == whole and same is not whole
    # a part that leaves out six statements, none of them with an undetermined event, three of
    # them with a target: the scenarios stay, the pinball loss is withheld
    part = {
        "statements": 14,
        "episodes": 7,
        "delta": 0.3,
        "bounds": {
            "statements": 18,
            "with_a_horizon_event_undetermined": 4,
            "undetermined_as_no": 0.1,
        },
        "pinball": {"0.50": {"statements": 15, "left_out_right_censored": 3, "loss": 2.0}},
        "label": "x",
    }
    got = sc.beside(whole, part)
    assert got["delta"] == 0.3 and got["bounds"] == part["bounds"] and got["label"] == "x"
    assert got["pinball"]["0.50"] == {
        "statements": 15,
        "left_out_right_censored": 3,
        "withheld": True,
    }
    # a part that leaves out four scoreable statements: the whole record is withheld
    assert sc.beside(whole, part | {"statements": 16}) == {
        "statements": 16,
        "episodes": 7,
        "withheld": True,
    }
    # a figure that one of the two withholds has no neighbour to be taken from
    hidden = {"statements": 19, "episodes": 9, "withheld": True}
    assert sc.beside(whole, hidden) == hidden
    assert sc.beside(hidden, part | {"statements": 16})["delta"] == 0.3
    # a count of readings that were not parsed is open: where the two differ by a few, the
    # counts of the part would say how many of those few known statements are scoreable
    assert sc.beside(
        {"not_both_parsed": 7, "left_out": 7, "statements": 30},
        {"not_both_parsed": 5, "left_out": 5, "statements": 20},
    ) == {"not_both_parsed": 5, "withheld": True}
    # a record over no statement holds nothing to withhold, and is not marked
    assert sc.withheld({"statements": 0, "episodes": 0, "delta": None}) == {
        "statements": 0,
        "episodes": 0,
        "withheld": False,
    }
    assert sc.beside(3, 4) == 4 and sc.beside(whole, None) is None


def test_sampled_against_verbalised_where_both_were_parsed() -> None:
    """The pinball difference again on the statements whose verbalised answer was parsed and
    that have a parsed sample: twelve statements, of which five fail one or the other."""
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(12)],
        ttr_kind=["interval"] * 11 + ["right_censored"],
        ttr_lower=[0.0] * 12,
        ttr_upper=[20.0] * 11 + [np.nan],
        ttr_mid=[10.0] * 11 + [np.nan],
    )
    ids = list(rows.index)
    sampled = forecasts(ids, [0.5] * 12, [0.5] * 12, q=np.arange(12, 24))
    verbal = forecasts(ids, [0.5] * 12, [0.5] * 12, q=np.arange(20, 44, 2))
    parsed = pd.Series([False] * 5 + [True] * 7, index=ids)
    out = sc.sampled_scores(rows, sampled, verbal, parsed, 200, 5)["pinball"]["0.50"]
    # at 0.5 the pinball loss is half the distance from the target of 10
    spoken, drawn = 0.5 * (np.arange(20, 44, 2) - 10.0), 0.5 * (np.arange(12, 24) - 10.0)
    assert out["verbalised_minus_sampled"]["statements"] == 11
    assert near(out["verbalised_minus_sampled"]["delta"], (spoken - drawn)[:11].mean())
    assert out["not_parsed_by_both"] == 5
    both = out["verbalised_minus_sampled_both_parsed"]
    assert both["statements"] == 6 and near(both["delta"], (spoken - drawn)[5:11].mean())
    assert (both["not_both_parsed"], both["left_out"]) == (5, 5)
    # five answers not parsed, four of them on statements with a target (the last statement
    # has none): the difference would rest on all but four, and is withheld, counts apart
    parsed = pd.Series([False] * 4 + [True] * 7 + [False], index=ids)
    again = sc.sampled_scores(rows, sampled, verbal, parsed, 200, 5)["pinball"]["0.50"]
    assert again["not_parsed_by_both"] == 4
    assert again["verbalised_minus_sampled_both_parsed"] == {
        "not_both_parsed": 5,
        "left_out": 4,
        "statements": 7,
        "episodes": 4,
        "withheld": True,
    }
    assert again["verbalised_minus_sampled"] == out["verbalised_minus_sampled"]
    # four answers not parsed: which statements those are is open, so the counts of the record
    # would say how many of the four have a target; they are withheld with it
    parsed = pd.Series([False] * 4 + [True] * 8, index=ids)
    few = sc.sampled_scores(rows, sampled, verbal, parsed, 200, 5)["pinball"]["0.50"]
    assert few["not_parsed_by_both"] is None
    assert few["verbalised_minus_sampled_both_parsed"] == {"not_both_parsed": 4, "withheld": True}


def open_case(not_scoreable: int) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Twelve statements in six episodes, the first event of the last ``not_scoreable`` of them
    undetermined, and two forecasts."""
    held = [1.0, 0.0] * 6
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(12)],
        y_a=held[: 12 - not_scoreable] + [np.nan] * not_scoreable,
        y_b=[1.0] * 12,
        ttr_kind=["interval"] * 12,
        ttr_lower=[0.0] * 12,
        ttr_upper=[20.0] * 12,
        ttr_mid=[10.0] * 12,
    )
    predictions = {
        "one": forecasts(rows.index, [0.5] * 12, [0.8] * 12),
        "other": forecasts(rows.index, [0.7] * 12, [0.9] * 12),
    }
    return rows, predictions


@pytest.mark.parametrize("not_scoreable", [0, 1, 4, 5])
def test_the_two_scenarios_are_withheld_where_a_few_statements_are_not_scoreable(
    not_scoreable: int,
) -> None:
    """PLAN section 2.5: beside the figures on the scoreable statements of a set, those over
    every statement would give the horizon events of one to four statements that are not
    scoreable. Counts stay."""
    rows, predictions = open_case(not_scoreable)
    few = 0 < not_scoreable < sc.MIN_SHOWN
    assert sc.few_open(rows) is few
    counts = {"statements": 12, "with_a_horizon_event_undetermined": not_scoreable}
    mean = sc.loss_bounds(rows, predictions["one"])
    pair = sc.contrast_bounds(rows, predictions, "one", "other")
    record = sc.scores(rows, predictions["one"], 200, 3)
    if few:
        assert mean == pair == counts | {"withheld": True}
        assert record["bounds_all_statements"] == counts | {"withheld": True}
        assert record["calibration_all_statements"] == counts | {"withheld": True}
        assert record["calibration_in_the_large"] == counts | {"withheld": True}
    else:
        # the loss of a statement under "one": ((0.5 - y_a)^2 + 0.04) / 2, whatever y_a is
        assert near(mean["undetermined_as_no"], 0.145) and near(mean["undetermined_as_yes"], 0.145)
        held = np.array([1.0, 0.0] * 6)[: 12 - not_scoreable]
        for fill, value in (("undetermined_as_no", 0.0), ("undetermined_as_yes", 1.0)):
            y = np.concatenate([held, np.full(not_scoreable, value)])
            other = float((((0.7 - y) ** 2 + 0.01) / 2).mean())
            assert near(pair[fill]["loss_tested"], other) and near(
                pair[fill]["delta"], 0.145 - other
            )
        assert set(record["bounds_all_statements"]) == set(sc.FILLS)
        assert set(record["calibration_all_statements"]) == {"E_end", "E_end90"}
    # the scores on the scoreable statements, and the pinball losses, stay in either case
    assert record["scoreable_statements"] == 12 - not_scoreable
    assert near(record["primary_brier"], 0.145) and "pinball_all_statements" in record
    # under five statements the scenarios are withheld whatever is undetermined
    assert sc.loss_bounds(rows.iloc[:4], predictions["one"])["withheld"] is True
    assert sc.contrast_bounds(rows.iloc[:4], predictions, "one", "other")["withheld"] is True
    assert sc.loss_bounds(rows.iloc[:0], predictions["one"]) == {
        "statements": 0,
        "with_a_horizon_event_undetermined": 0,
        "withheld": False,
    }
    # the effects of the 2x2 and the spread across prompts take the scenarios of their cells,
    # and are withheld with them
    cells = {name: sc.loss_bounds(rows, pred) for name, pred in predictions.items()}
    effect = sc.combined_bounds(cells, ["one"], ["other"], 1.0)
    spread = sc.spread_bounds(list(cells.values()))
    if few:
        assert effect == spread == counts | {"withheld": True}
    else:
        for fill in sc.FILLS:
            assert near(effect[fill], cells["one"][fill] - cells["other"][fill])
            assert near(spread[fill]["range"], abs(effect[fill]))
            assert near(spread[fill]["sd"], abs(effect[fill]) / np.sqrt(2))
        assert effect["statements"] == spread["statements"] == 12


def test_a_part_of_selective_prediction_with_a_few_statements_not_scoreable() -> None:
    """The scenarios of a part with one to four statements that are not scoreable are withheld,
    and those of the other part with them, although it holds five such statements: the
    scenarios of the whole, which are given, less those of the part shown would give the
    events of the few back. The losses on the scoreable statements stay."""
    rows = typed(
        episode_id=[f"e{k // 2}" for k in range(24)],
        y_a=[1.0, 0.0] * 5 + [np.nan] * 2 + [1.0] * 7 + [np.nan] * 5,
        y_b=[1.0] * 24,
    )
    pred = forecasts(rows.index, [0.5] * 24, [0.8] * 24)
    days = pd.Series([10.0] * 12 + [np.nan] * 12, index=rows.index)
    record = sc.selective(rows, pred, days, 200, 3)
    read, left, whole = (
        record[f"primary_brier_{part}"] for part in ("read", "abstained_on", "all")
    )
    assert (read["statements"], left["statements"], whole["statements"]) == (10, 7, 17)
    assert near(read["mean"], 0.145) and near(left["mean"], 0.145) and near(whole["mean"], 0.145)
    assert read["bounds_all_statements"] == {
        "statements": 12,
        "with_a_horizon_event_undetermined": 2,
        "withheld": True,
    }
    # five statements of this part are not scoreable: withheld for the other part's sake alone
    assert left["bounds_all_statements"] == {
        "statements": 12,
        "with_a_horizon_event_undetermined": 5,
        "withheld": True,
    }
    assert whole["bounds_all_statements"]["with_a_horizon_event_undetermined"] == 7
    assert near(whole["bounds_all_statements"]["undetermined_as_no"], 0.145)
    assert set(sc.FILLS) <= set(sc.loss_bounds(rows.iloc[12:], pred))
    # one part with none and the other with seven: nothing is hidden
    days = pd.Series([10.0] * 10 + [np.nan] * 14, index=rows.index)
    record = sc.selective(rows, pred, days, 200, 3)
    assert set(sc.FILLS) <= set(record["primary_brier_read"]["bounds_all_statements"])
    assert set(sc.FILLS) <= set(record["primary_brier_abstained_on"]["bounds_all_statements"])
    # a list without horizon events: the abstention rate alone, no loss and no scenario
    bare = sc.selective(rows, pred, days, 200, 3, with_loss=False)
    assert bare == {"statements": 24, "abstained": 14, "abstention_rate": 14 / 24}


def test_the_scenarios_of_a_recovery_variant_are_over_the_statements_at_risk_under_it() -> None:
    """A statement that is not at risk under a variant has no horizon event there: it is no
    undetermined event to fill, and the scenarios beside a contrast leave it out."""
    prepared, rows, under = variant_case(0)
    gone = under.index[:6]
    under.loc[gone, "outcome"] = "not_at_risk"
    under.loc[gone, ["y_a", "y_b"]] = np.nan
    under["scoreable"] = under["y_a"].notna() & under["y_b"].notna()
    label = sc.RECOVERY_VARIANTS[0]
    got = sc.recovery_rule(prepared, rows, {label: under}, {}, ["m"], 200, 3)[label]
    assert got["not_at_risk_under_the_variant"] == 6 and got["scoreable_statements"] == 6
    assert got["statements_with_another_horizon_event"] == {"m": 6}
    entry = got["contrasts"]["m"]["H1"]
    assert entry["statements"] == 6 and near(entry["delta"], 0.21)
    assert entry["bounds"]["statements"] == 6
    assert entry["bounds"]["with_a_horizon_event_undetermined"] == 0
    assert near(entry["bounds"]["undetermined_as_yes"]["delta"], 0.21)
    # the evaluator's own function on the whole frame would fill six events that do not exist
    bare = ev.bounds(under, prepared.study.predictions, "m:a", "m:b")
    assert bare["statements"] == 12 and bare["with_a_horizon_event_undetermined"] == 6


def test_no_scenario_in_the_result_file_stands_beside_a_few_statements_not_scoreable(
    base: SimpleNamespace,
) -> None:
    """On the synthetic study: every record of the result file that counts the statements with
    an undetermined horizon event holds the two scenarios, or is withheld; it is withheld
    wherever one to four statements are not scoreable."""
    found: list[dict] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "with_a_horizon_event_undetermined" in value:
                found.append(value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(base.report)
    shown = [record for record in found if "withheld" not in record]
    assert len(found) > 200 and len(shown) > 100
    for record in found:
        few = 0 < record["with_a_horizon_event_undetermined"] < sc.MIN_SHOWN
        if few or 0 < record["statements"] < sc.MIN_SHOWN:
            assert record["withheld"] is True and not set(sc.FILLS) & set(record), record
        if "withheld" not in record:
            assert set(sc.FILLS) <= set(record)
    # the stale list has no horizon event: an abstention rate, and no loss
    for model in ev.PRIMARIES:
        point = base.report["secondary_lists"][model]["stale"][
            "selective_prediction_of_condition_c"
        ]
        assert set(point) == {"statements", "abstained", "abstention_rate"}
        other = base.report["secondary_lists"][model]["tbd"]["selective_prediction_of_condition_c"]
        assert "primary_brier_all" in other


def test_the_rule_reader_abstains_on_no_eligible_statement() -> None:
    """Eligibility fixes the abstention rate of the rule reader at zero: the point is marked,
    and the mark is held to the data."""
    prepared, rows, _ = variant_case(0)
    rows["end_days"] = 30.0
    study = prepared.study
    study.first = pd.DataFrame(index=rows.index)
    got = sc.selective_prediction(prepared, rows, {}, [], 200, 3)
    assert list(got) == ["rule_reader"]
    point = got["rule_reader"]
    assert point["abstained"] == 0 and point["abstention_rate"] == 0.0
    assert point["abstention_rate_fixed_by_eligibility"] is True
    assert near(point["primary_brier_read"]["mean"], 0.09) and point["statements"] == 12
    rows.loc[rows.index[3], "end_days"] = np.nan
    with pytest.raises(ValueError, match="an eligible statement has no stated period"):
        sc.selective_prediction(prepared, rows, {}, [], 200, 3)


def slip_rows() -> pd.DataFrame:
    """Six dated statements whose stated end is day 30: two recovered in (20, 25] (slip in
    (-10, -5]), one in (50, 55], one in (130, 140], one censored at day 200, one discontinued."""
    return typed(
        episode_id=["a", "a", "b", "b", "c", "d"],
        analysis_set=["dated"] * 6,
        outcome=["recovered", "recovered", "recovered", "recovered", "censored", "discontinued"],
        lower_days=[20.0, 20.0, 50.0, 130.0, 200.0, 60.0],
        upper_days=[25.0, 25.0, 55.0, 140.0, np.nan, 90.0],
        end_days=[30.0] * 6,
    )


def test_the_slip_distribution_is_a_turnbull_estimate_worked_by_hand() -> None:
    rows = slip_rows()
    record = sc.slip_record(rows, 12, 1)
    shares = record["share_recovered_by_days_after_the_stated_end"]
    # masses: 2/6 on (-10, -5], 1/6 on (20, 25], 1/6 on (100, 110], 2/6 never within reach
    assert list(shares) == ["-30", "0", "30", "90", "180", "365"]
    assert near(list(shares.values()), [0.0, 2 / 6, 3 / 6, 3 / 6, 4 / 6, 4 / 6], 1e-6)
    assert near(record["share_not_recovered_within_reach"], 2 / 6, 1e-6)
    # a quarter is three quarters of the way through (-10, -5]; a half is reached at 25
    assert near(record["slip_quantiles_days"]["0.25"], -6.25, 1e-4)
    assert near(record["slip_quantiles_days"]["0.50"], 25.0, 1e-4)
    assert record["slip_quantiles_days"]["0.75"] is None
    assert record["slip_quantiles_days"]["0.90"] is None
    # the curve stands at one half from day 25 until the next recovery, after day 100: the
    # median is the start of that flat stretch, and its end is given beside it
    assert record["slip_quantiles_days"]["0.50"] == 25.0
    assert record["slip_quantiles_flat_to_days"] == {"0.50": 100.0}
    assert (record["statements"], record["episodes"], record["draws"]) == (6, 4, 12)
    # the interval: the first 12 of the registered draws of the four episodes, a fit for each
    left, right = P.slip_brackets(rows)
    codes = pd.Categorical(rows["episode_id"]).codes
    drawn = []
    for counts in P.cluster_draws(4, ev.DRAWS, 1)[:12]:
        chosen = np.repeat(np.arange(6), counts[codes])
        drawn.append(P.turnbull(left[chosen], right[chosen]).cdf(np.array([0.0, 180.0])))
    drawn = np.array(drawn)
    assert near(record["ci95"]["0"], P.interval(drawn[:, 0], 0.95))
    assert near(record["ci95"]["180"], P.interval(drawn[:, 1], 0.95))
    assert record["ci95"]["0"][0] < record["ci95"]["0"][1]
    # no draw asked for, or one episode: no interval; under five statements: withheld
    assert sc.slip_record(rows, 0, 1)["ci95"] is None
    assert sc.slip_record(rows.assign(episode_id="a"), 12, 1)["ci95"] is None
    assert sc.slip_record(rows.iloc[:4], 12, 1) == {
        "statements": 4,
        "episodes": 2,
        "withheld": True,
    }


def bracketed(left: Sequence[float], right: Sequence[float]) -> pd.DataFrame:
    """Dated statements whose stated end is their own day, with these brackets of recovery (an
    infinite right end: censored at the left one)."""
    known = np.isfinite(np.asarray(right, dtype=float))
    return typed(
        episode_id=[f"e{k}" for k in range(len(left))],
        outcome=np.where(known, "recovered", "censored"),
        lower_days=list(left),
        upper_days=np.where(known, right, np.nan),
        end_days=[0.0] * len(left),
    )


def test_a_slip_quantile_on_a_flat_stretch_is_the_start_of_the_stretch() -> None:
    """Where the estimate reaches a level exactly and then stays flat, the quantile is the day
    on which it reaches it, whatever the iteration left over: here the fit stops a little
    short of one half, and the plain search would give a day far along the flat stretch."""
    # five statements: the estimate is 1/2 on (20, 30], nothing on (40, 50], 1/2 on (50, 60]
    five = bracketed([50.0, 0.0, 20.0, 40.0, 20.0], [80.0, 30.0, 50.0, 60.0, 50.0])
    record = sc.slip_record(five, 0, 1)
    assert record["slip_quantiles_days"]["0.50"] == 30.0
    assert record["slip_quantiles_flat_to_days"] == {"0.50": 40.0}
    curve = P.turnbull(*P.slip_brackets(five))
    assert float(curve.quantile(np.asarray(0.5))) > 40.0  # what the search alone gives
    # a level the curve crosses inside an interval is the search's own value
    assert record["slip_quantiles_days"]["0.25"] == float(curve.quantile(np.asarray(0.25)))
    assert near(record["slip_quantiles_days"]["0.25"], 25.0, 1e-4)
    assert near(record["slip_quantiles_days"]["0.75"], 52.5, 1e-4)
    # eight statements, two of them censored at day 100: 1/2 by day 30, nothing until day 50,
    # 3/4 by day 60, and no more within reach of the data
    eight = bracketed(
        [50.0, 0.0, 20.0, 40.0, 20.0, 0.0, 100.0, 100.0],
        [80.0, 30.0, 50.0, 60.0, 50.0, 30.0, np.inf, np.inf],
    )
    record = sc.slip_record(eight, 0, 1)
    assert record["slip_quantiles_days"]["0.50"] == 30.0
    assert record["slip_quantiles_days"]["0.75"] == 60.0
    assert record["slip_quantiles_days"]["0.90"] is None
    assert record["slip_quantiles_flat_to_days"] == {"0.50": 50.0, "0.75": None}
    assert near(record["share_not_recovered_within_reach"], 0.25, 1e-4)
    # a corner that stands off the level is not moved, however near it is
    curve = P.turnbull(*P.slip_brackets(eight))
    off = sc.slip_quantile(curve, lambda: curve, 0.5 + 5e-4)
    assert off == (float(curve.quantile(np.asarray(0.5 + 5e-4))), False, None)
    # nor is any, when the tighter fit does not settle
    assert sc.slip_quantile(curve, lambda: None, 0.5)[1:] == (False, None)
    assert (sc.SLIP_NEAR, sc.SLIP_TIGHTER, sc.SLIP_SETTLED) == (1e-3, 1e-2, 1e-9)


def test_bracket_widths_and_counts_on_a_case_worked_by_hand() -> None:
    rows = slip_rows()
    record = sc.width_record(rows, 300, 1)
    # widths 5, 5, 5, 10 and 30 (the discontinuation); the censored statement has none
    assert record["statements"] == 6 and record["with_a_finite_bracket"] == 5
    assert record["right_censored"] == 1
    assert near(record["quantiles_days"]["0.50"], 5.0) and near(
        record["quantiles_days"]["0.90"], 22.0
    )
    assert near(record["mean_days"]["mean"], 11.0)
    assert near(record["share_of_31_days_or_less"]["mean"], 1.0)
    wide = sc.width_record(rows.assign(upper_days=[25.0, 25.0, 55.0, 190.0, np.nan, 92.0]), 300, 1)
    assert near(wide["share_of_31_days_or_less"]["mean"], 3 / 5)
    assert sc.width_record(rows.iloc[[0, 1, 4]], 300, 1)["withheld"] is True
    rows = rows.assign(form=["quarter", "month_year"] * 3, revision=["first"] * 4 + ["second"] * 2)
    first = pd.DataFrame(
        {
            "event_date": [
                "2023-01-15",
                "2023-02-15",
                "2024-01-15",
                "2024-03-15",
                "2024-05-15",
                "2025-01-15",
            ],
            "statement_type": ["recovery"] * 5 + ["next_delivery"],
            "company_name": ["Acme", "Acme", "Borealis", "Acme", "Borealis", "Acme"],
        },
        index=rows.index,
    )
    counts = sc.count_record(rows, first)
    assert counts["by_year"] == {"2023": 2, "2024": 3, "2025": 1}
    assert counts["by_form"] == {"month_year": 3, "quarter": 3}
    assert counts["by_statement_type"] == {"next_delivery": 1, "recovery": 5}
    assert counts["by_company"] == {"Acme": 4, "Borealis": 2}
    assert counts["by_revision"] == {"first": 4, "second": 2}
    assert counts["by_analysis_set"] == {"dated": 6}


HOLD_KEYS = {"statements", "determined", "undetermined", *sc.HOLD_SHARES}
MEAN_KEYS = {"statements", "episodes", "mean", "ci95"}
SLIP_KEYS = {
    "statements",
    "episodes",
    "share_recovered_by_days_after_the_stated_end",
    "slip_quantiles_days",
    "slip_quantiles_flat_to_days",
    "share_not_recovered_within_reach",
    "ci95",
    "draws",
}
WIDTH_KEYS = {
    "statements",
    "with_a_finite_bracket",
    "right_censored",
    "quantiles_days",
    "mean_days",
    f"share_of_{C.OBSERVABLE_WIDTH_DAYS}_days_or_less",
}
PART_KEYS = {*MEAN_KEYS, "bounds_all_statements"}
"""The keys of the records of E1 and of a part of selective prediction: a new leaf in one of
them is a new number about the statements of a cell, and is looked at before it is written."""


def test_bracket_widths_are_withheld_by_the_number_of_finite_brackets() -> None:
    rows = typed(
        episode_id=list("abcdef"),
        outcome=["recovered", "recovered"] + ["censored"] * 4,
        lower_days=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        upper_days=[15.0, 30.0] + [np.nan] * 4,
    )
    assert sc.width_record(rows, 100, 1) == {
        "statements": 6,
        "with_a_finite_bracket": 2,
        "right_censored": 4,
        "withheld": True,
    }
    # five finite brackets among six statements: given
    rows = typed(
        episode_id=list("abcdef"),
        outcome=["recovered"] * 5 + ["censored"],
        lower_days=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        upper_days=[15.0, 30.0, 45.0, 60.0, 75.0, np.nan],
    )
    record = sc.width_record(rows, 100, 1)
    assert set(record) == WIDTH_KEYS and near(record["mean_days"]["mean"], 15.0)
    assert set(record["mean_days"]) == MEAN_KEYS


def test_the_records_of_the_descriptives_hold_the_keys_they_are_known_to_hold(
    base: SimpleNamespace,
) -> None:
    """The exact keys of every hold rate, slip estimate, width record and part of selective
    prediction, on a worked case and in the result file of the synthetic study."""
    rows = typed(episode_id=list("aabbccd"), y_a=[1.0, 0.0, np.nan, 1.0, np.nan, 0.0, 1.0])
    record = sc.hold_record(rows, 50, 1)
    assert set(record) == HOLD_KEYS
    assert all(set(record[share]) == MEAN_KEYS for share in sc.HOLD_SHARES)
    assert set(sc.slip_record(slip_rows(), 3, 1)) == SLIP_KEYS
    got = base.report["descriptives"]
    hold, slip = got["hold_rate"], got["slip"]
    splits = ("by_statement_type", "by_form", "by_revision")
    assert set(hold) == set(slip) == {"all_dated_forms", *splits}
    holds = [hold["all_dated_forms"], *(cell for name in splits for cell in hold[name].values())]
    slips = [slip["all_dated_forms"], *(cell for name in splits for cell in slip[name].values())]
    assert len(holds) >= 7 and len(slips) == len(holds)
    # the synthetic study holds recovery statements alone: that type is every dated statement
    assert hold["by_statement_type"]["recovery"] == hold["all_dated_forms"]
    assert slip["by_statement_type"]["recovery"] == slip["all_dated_forms"]
    assert hold["by_statement_type"]["next_delivery"]["statements"] == 0
    for record in holds:
        assert set(record) - {"withheld_with_another_cell"} == HOLD_KEYS
        for share in sc.HOLD_SHARES:
            assert set(record[share]) - {"withheld"} == MEAN_KEYS
            assert ("withheld" in record[share]) == (record[share]["mean"] is None)
    for record in slips:
        small = {"statements", "episodes", "withheld"}
        assert set(record) - {sc.SHARES_WITHHELD} == (small if "withheld" in record else SLIP_KEYS)
    assert set(got["bracket_widths"]) == WIDTH_KEYS
    assert set(got) == {
        "statements",
        "episodes",
        "dated_statements_not_stale",
        "counts",
        "hold_rate",
        "slip",
        "bracket_widths",
    }
    for name, point in base.report["selective_prediction"].items():
        parts = {key: value for key, value in point.items() if key.startswith("primary_brier_")}
        assert set(parts) == {f"primary_brier_{part}" for part in ("read", "abstained_on", "all")}
        for part in parts.values():
            bare = "statements" not in part  # a part of a few statements: no count of outcomes
            assert set(part) - {"withheld"} == PART_KEYS - (
                {"statements", "episodes"} if bare else set()
            )
        extra = set(point) - set(parts) - {"statements", "abstained", "abstention_rate"}
        if name == "rule_reader":
            assert extra == {"abstention_rate_fixed_by_eligibility"}
        else:
            assert extra == {
                "items",
                "failed_counted_as_abstain",
                "abstain",
                "period_of_another_statement_type",
            }


def test_descriptives_split_the_dated_statements_by_form_and_revision() -> None:
    rows = pd.concat([slip_rows(), slip_rows()], ignore_index=True)
    rows.index = [f"S{k}" for k in range(12)]
    rows["y_a"] = [1.0, 1.0, 0.0, 0.0, 0.0, 0.0] * 2
    rows["form"] = ["month_year"] * 6 + ["quarter"] * 6
    rows["revision"] = ["first"] * 9 + ["second"] * 3
    rows.loc["S11", "analysis_set"] = "tbd"
    first = pd.DataFrame(
        {"event_date": "2021-05-15", "statement_type": "recovery", "company_name": "Acme"},
        index=rows.index,
    )
    out = sc.descriptives(rows, first, 200, 5, 1, beside={})
    assert (out["statements"], out["dated_statements_not_stale"]) == (12, 11)
    assert list(out["hold_rate"]["by_form"]) == ["month_year", "quarter"]
    assert out["hold_rate"]["by_form"]["quarter"]["statements"] == 5
    assert near(out["hold_rate"]["all_dated_forms"]["among_determined"]["mean"], 4 / 11)
    assert list(out["slip"]["by_revision"]) == list(P.REVISIONS)
    assert out["slip"]["by_revision"]["first"]["statements"] == 9
    assert out["slip"]["by_revision"]["second"] == {
        "statements": 2,
        "episodes": 2,
        "withheld": True,
    }
    assert out["slip"]["by_revision"]["third or later"] == {
        "statements": 0,
        "episodes": 0,
        "withheld": False,
    }
    assert out["slip"]["by_form"]["month_year"]["draws"] == 5
    assert out["bracket_widths"]["with_a_finite_bracket"] == 10
    assert out["counts"]["by_analysis_set"] == {"dated": 11, "tbd": 1}


def test_stored_horizons_are_held_to_those_of_the_statement_table() -> None:
    first = pd.DataFrame(
        {
            "horizon_a": ["2023-04-15", "2023-03-31"],
            "horizon_b": ["2023-07-14", "2023-06-29"],
            "horizon_rule": ["fallback", "stated_end"],
        },
        index=["T1", "S1"],
    )
    asked = {
        "T1": {"horizons": {"a": "2023-04-15", "b": "2023-07-14", "rule": "fallback"}},
        "S1": {"horizons": {"a": "2023-03-31", "b": "2023-06-29", "rule": "stated_end"}},
        "X9": {"horizons": {"a": "2000-01-01", "b": "2000-01-02", "rule": "fallback"}},
    }
    assert sc.asked_wrongly(asked, first) == 0
    for key, value in (("a", "2023-04-16"), ("b", "2023-07-15"), ("rule", "stated_end")):
        other = {**asked, "T1": {"horizons": {**asked["T1"]["horizons"], key: value}}}
        assert sc.asked_wrongly(other, first) == 1
    assert sc.asked_wrongly({"T1": {}, "S1": {}}, first) == 2
    assert sc.asked_wrongly({}, first) == 0


# --------------------------------------------------------------------------------------------
# The sections on the synthetic study
# --------------------------------------------------------------------------------------------


def subset_ids(study: SimpleNamespace, column: str) -> list[str]:
    return sorted(study.eligible.loc[study.eligible[column] == 1, "statement_group_id"])


def list_ids(study: SimpleNamespace, key: str) -> list[str]:
    population = study.population
    return sorted(population.loc[population["analysis_set"] == key, "statement_group_id"])


def test_the_two_counts_taken_out_are_the_evaluators_own_words(study: SimpleNamespace) -> None:
    """The evaluator's check refuses a sampled or masked run on two counts and nothing else;
    ``decoded_group`` takes out exactly those and holds every row to the plan's decoding."""
    first = study.table.set_index("statement_group_id")
    ids = subset_ids(study, "samples20")
    name = f"{LLAMA} {sc.SAMPLES_LINE}"
    plain = sc.checked_group(
        study.plan, study.paths.runs, LLAMA, sc.SAMPLES_LINE, ids, first.loc[ids]
    )
    assert set(plain.problems) == {
        sc.SAMPLES_FAULT.format(name=name, samples=20),
        sc.DECODING_FAULT.format(name=name, rows=len(ids)),
    }
    group, rows = sc.decoded_group(
        study.plan, study.paths.runs, LLAMA, sc.SAMPLES_LINE, ids, first.loc[ids]
    )
    assert group.problems == () and len(rows) == 20 * len(ids)
    assert {sample for _, sample in rows} == set(range(20))
    ids = subset_ids(study, "twobytwo")
    for cell, decoding in sc.CELLS.items():
        plain = sc.checked_group(
            study.plan, study.paths.runs, DEEPSEEK, sc.CELLS_LINE, ids, first.loc[ids], **decoding
        )
        assert plain.problems == (
            sc.DECODING_FAULT.format(name=f"{DEEPSEEK} {sc.CELLS_LINE}", rows=len(ids)),
        ), cell
        group, rows = sc.decoded_group(
            study.plan, study.paths.runs, DEEPSEEK, sc.CELLS_LINE, ids, first.loc[ids], **decoding
        )
        assert group.problems == () and len(rows) == len(ids) == len(group.rows)
    # a run of the phase rest is handed over under the phase whose track record it showed
    runs = sc.runs_of(study.plan, NOISY, "e3-b")
    assert [run["phase"] for run in runs] == [sc.REST] and runs[0]["track"] == "fit+dev"
    shown = sc.as_checked(study.plan, runs)
    assert [run["phase"] for run in shown["runs"]] == [sc.CHECKED_AS]
    assert ev.TRACK_OF_PHASE[sc.CHECKED_AS] == "fit+dev"
    assert sc.runs_of(study.plan, NOISY, "e3-b", list="tbd") == []
    assert sc.sheet_models(sc.PROBE_LINE) == rd.NOT_GEMINI


def test_the_contrasts_of_the_secondary_models_against_a_computation_made_here(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    ids, y = fit.ids, fit.y.loc[fit.ids]
    keep = y["scoreable"].to_numpy()
    episodes = y.loc[keep, "episode"]
    assert base.report["h3_comparator"] == ev.BASE
    assert base.report["secondary_models_scored"] == list(sc.SECONDARY_MODELS)
    for model in sc.SECONDARY_MODELS:
        made = {c: given(study, model, c, ids, fit.base)[0] for c in ("a", "b")}
        made["c"] = fit.fitted[ev.RULES].predict(fit.frame.loc[ids], read_days(study, model, ids))
        pairs = {
            "H1": (made["a"], made["b"], 1),
            "H2": (fit.free[ev.RULES], made["c"], 2),
            **{f"H3 with condition {c}": (fit.base, made[c], 2) for c in ev.CONDITIONS},
        }
        report = base.report["secondary_models"]["models"][model]["on_every_eligible_statement"]
        assert list(report) == list(pairs)
        for name, (comparator, tested, sides) in pairs.items():
            got = report[name]
            one, other = brier(comparator.loc[ids], y)[keep], brier(tested.loc[ids], y)[keep]
            delta, interval = by_hand(one - other, episodes)
            assert got["statements"] == int(keep.sum()) and got["sides"] == sides, (model, name)
            assert got["episodes"] == episodes.nunique()
            assert near(got["delta"], delta) and near(got["loss_comparator"], one.mean())
            assert near(got["loss_tested"], other.mean())
            assert near(got["percentile"]["ci95"], interval), (model, name)
            wanted = ev.contrast(one, other, list(episodes))["p_values"][ev.P_VALUE_SOURCE]
            assert near(got["p"], wanted["one_sided" if sides == 1 else "two_sided"])
            assert got["interval_method"] == ev.interval_method(ev.P_VALUE_SOURCE)
            assert ("ci90" in got) == (name == "H2")
        # the descriptive decomposition: each part is the first loss minus the second, two-sided,
        # with a percentile interval
        entry = base.report["secondary_models"]["models"][model]
        parts = {
            "content_value_of_the_text": (ev.BASE, ev.RULES),
            "content_value_against_the_structured_model": (ev.STRUCTURED, ev.RULES),
            "reading_loss": (f"{model}:c", ev.RULES),
            "trust_loss": (f"{model}:a", f"{model}:c"),
        }
        named = {**fit.free, **{f"{model}:{c}": pred for c, pred in made.items()}}
        decomposition = entry["decomposition_on_every_eligible_statement"]
        assert list(decomposition) == list(parts)
        for name, (first, second) in parts.items():
            got = decomposition[name]
            one, other = (
                brier(named[first].loc[ids], y)[keep],
                brier(named[second].loc[ids], y)[keep],
            )
            delta, interval = by_hand(one - other, episodes)
            assert (got["minuend"], got["subtrahend"]) == (first, second), (model, name)
            assert near(got["delta"], delta) and near(got["ci95"], interval), (model, name)
            assert got["interval_method"] == ev.PERCENTILE_INTERVAL
            wanted = ev.contrast(one, other, list(episodes))["p_values"][ev.P_VALUE_SOURCE]
            assert near(got["p"], wanted["two_sided"]) and got["statements"] == int(keep.sum())
        assert near(decomposition["reading_loss"]["delta"], -report["H2"]["delta"])
        assert near(
            decomposition["reading_loss"]["ci95"],
            [-end for end in reversed(report["H2"]["percentile"]["ci95"])],
        )
        assert ("decomposition_on_the_post_cutoff_slice" in entry) == (
            "on_the_post_cutoff_slice" in entry
        )
        # the contrasts again, in short, as the evaluator repeats the tests of a primary
        repeated = entry["repeated_on_every_eligible_statement"]
        assert list(repeated) == list(REPEATS)
        month = (study.filled.loc[ids, "merged_form"] == ev.MONTH_YEAR).to_numpy()
        assert 0 < int((keep & month).sum()) < int(keep.sum())
        got = repeated["h2_on_the_month_and_year_form"]
        one, other = brier(fit.free[ev.RULES].loc[ids], y), brier(made["c"].loc[ids], y)
        assert list(got) == ["H2"] and got["H2"]["statements"] == int((keep & month).sum())
        assert near(got["H2"]["delta"], (one - other)[keep & month].mean())
        got = repeated["clusters_by_company"]["H1"]
        one, other = brier(made["a"].loc[ids], y)[keep], brier(made["b"].loc[ids], y)[keep]
        delta, interval = by_hand(one - other, study.filled.loc[ids, "company_name"][keep])
        assert near(got["delta"], delta) and near(got["ci95"], interval), model
        assert got["episodes"] == study.filled.loc[ids, "company_name"][keep].nunique()
        under_a = D.attach_outcomes(study.listed, study.sealed_rows, "A")
        under_a = under_a.set_index("statement_group_id").loc[ids]
        events = {"yes": 1.0, "no": 0.0}
        y_a = pd.DataFrame(
            {"y_a": under_a["E_end"].map(events), "y_b": under_a["E_end90"].map(events)}
        )
        kept = (y_a["y_a"].notna() & y_a["y_b"].notna()).to_numpy()
        got = repeated["recovery_definition_A"]["H1"]
        wanted = (brier(made["a"].loc[ids], y_a) - brier(made["b"].loc[ids], y_a))[kept].mean()
        assert got["statements"] == int(kept.sum()) and near(got["delta"], wanted), model
        assert not near(wanted, report["H1"]["delta"])
        for label in ("first_captured_by_the_stated_end", *REPEATS[3:]):
            assert list(repeated[label]) == primary_names(), label
        # the interval of the registered source, once for a contrast of each kind
        one, other = brier(made["a"], y)[keep], brier(made["b"], y)[keep]
        if model in (INFORMED, NOISY):
            wanted = ev.contrast(
                one, other, list(episodes), source=ev.P_VALUE_SOURCE, levels=("ci95",)
            )
            assert near(report["H1"]["ci95"], wanted["ci95"])
            beside = report["H3 with condition b"]["against_gbm_structured"]
            structured = brier(fit.free[ev.STRUCTURED].loc[ids], y)[keep]
            assert near(beside["delta"], float((structured - other).mean()))
            assert beside["interval_method"] == ev.interval_method(ev.P_VALUE_SOURCE)
            # both intervals: the one of the registered test, and the percentile one beside it
            assert near(beside["percentile"]["ci95"], by_hand(structured - other, episodes)[1])
            wanted = ev.contrast(
                structured, other, list(episodes), source=ev.P_VALUE_SOURCE, levels=("ci95",)
            )
            assert near(beside["ci95"], wanted["ci95"])
            assert not near(beside["ci95"], beside["percentile"]["ci95"])


def filled_with(y: pd.DataFrame, value: float) -> pd.DataFrame:
    return y.assign(y_a=y["y_a"].fillna(value), y_b=y["y_b"].fillna(value))


def same_bounds(got: dict, comparator: pd.DataFrame, tested: pd.DataFrame, y: pd.DataFrame) -> None:
    """The two scenarios beside a contrast, by hand: both losses and their difference over
    every statement with each undetermined event set to no, then to yes."""
    assert got["statements"] == len(y)
    assert got["with_a_horizon_event_undetermined"] == int((~y["scoreable"]).sum())
    for fill, value in (("undetermined_as_no", 0.0), ("undetermined_as_yes", 1.0)):
        one = brier(comparator.loc[y.index], filled_with(y, value))
        other = brier(tested.loc[y.index], filled_with(y, value))
        assert near(got[fill]["loss_comparator"], one.mean()), fill
        assert near(got[fill]["loss_tested"], other.mean()), fill
        assert near(got[fill]["delta"], (one - other).mean()), fill


def test_the_numbers_written_beside_a_contrast_of_a_secondary_model(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    """Beside each contrast: the two scenarios, the equivalence reading of H2 with its two
    p-values, on how many statements and episodes the losses differ, and the contrast against
    the structured-only model, each against a computation made here."""
    ids, y = fit.ids, fit.y.loc[fit.ids]
    keep = y["scoreable"].to_numpy()
    episodes = y.loc[keep, "episode"]
    source = ev.P_VALUE_SOURCE
    level = ev.tail_of(ev.LEVELS[ev.EQUIVALENCE_LEVEL])
    after = (study.filled.loc[ids, "event_date"] > "2023-10-31").to_numpy() & keep
    for model in sc.SECONDARY_MODELS:
        made = {c: given(study, model, c, ids, fit.base)[0] for c in ("a", "b")}
        made["c"] = fit.fitted[ev.RULES].predict(fit.frame.loc[ids], read_days(study, model, ids))
        pairs = {
            "H1": (made["a"], made["b"]),
            "H2": (fit.free[ev.RULES], made["c"]),
            **{f"H3 with condition {c}": (fit.base, made[c]) for c in ev.CONDITIONS},
        }
        entry = base.report["secondary_models"]["models"][model]
        got = entry["on_every_eligible_statement"]
        for name, (comparator, tested) in pairs.items():
            same_bounds(got[name]["bounds"], comparator, tested, y)
        # H2: the two one-sided p-values at the margin, and the reading they give
        one, other = brier(pairs["H2"][0].loc[ids], y), brier(pairs["H2"][1].loc[ids], y)
        for chosen, where in (
            (keep, "on_every_eligible_statement"),
            (after, "on_the_post_cutoff_slice"),
        ):
            if where not in entry:
                continue
            wanted = ev.contrast(
                one[chosen],
                other[chosen],
                list(y.loc[chosen, "episode"]),
                source=source,
                levels=("ci95", ev.EQUIVALENCE_LEVEL),
                margin=ev.H2_MARGIN,
            )
            reading = entry[where]["H2"]["equivalence"]
            for key, value in wanted["at_the_margin"].items():
                assert near(reading[key], value), (model, where, key)
            assert reading["margin"] == ev.H2_MARGIN
            assert reading["declared"] is all(p < level for p in wanted["at_the_margin"].values())
            assert near(entry[where]["H2"]["ci90"], wanted["ci90"])
        assert got["H2"]["losses_differ"] == TE.counts_apart((one - other)[keep], episodes), model
        # beside H3: the structured-only model as the comparator, two-sided
        for condition in ev.CONDITIONS:
            beside = got[f"H3 with condition {condition}"]["against_gbm_structured"]
            structured = brier(fit.free[ev.STRUCTURED].loc[ids], y)[keep]
            mine = brier(made[condition].loc[ids], y)[keep]
            wanted = ev.contrast(structured, mine, list(episodes), source=source, levels=("ci95",))
            assert near(beside["ci95"], wanted["ci95"]), (model, condition)
            assert near(beside["p"], wanted["p_values"][source]["two_sided"])
            same_bounds(beside["bounds"], fit.free[ev.STRUCTURED], made[condition], y)
    slices = [m for m in sc.SECONDARY_MODELS if "on_the_post_cutoff_slice" in models_of(base)[m]]
    assert slices == ["gpt-4o-mini"]
    # the losses of one model differ on more episodes one way than the other: the two counts
    # are told apart
    apart = models_of(base)[NOISY]["on_every_eligible_statement"]["H2"]["losses_differ"]
    assert apart["episodes_with_a_positive_sum"] != apart["episodes_with_a_negative_sum"]
    # the printout gives the estimate and the p-value of each contrast
    shown = models_of(base)[INFORMED]["on_every_eligible_statement"]["H1"]
    assert f"  {INFORMED:17s} H1: delta {shown['delta']:.4f}, p {shown['p']:.4f}" in base.printed


def models_of(base: SimpleNamespace) -> dict[str, Any]:
    return base.report["secondary_models"]["models"]


def test_planted_effects_are_found_and_a_null_is_not(base: SimpleNamespace) -> None:
    models = base.report["secondary_models"]["models"]
    informed = models[INFORMED]["on_every_eligible_statement"]
    assert informed["H1"]["delta"] > 0.3 and informed["H1"]["p"] < 0.01
    assert informed["H1"]["ci95"][0] > 0.2
    # its literal reading is the rule reading: the two losses are the same on every statement
    assert informed["H2"]["delta"] == 0.0 and informed["H2"]["p"] == 1.0
    assert informed["H2"]["losses_differ"]["statements"] == 0
    assert informed["H2"]["equivalence"]["declared"] is True
    assert informed["H2"]["equivalence"]["margin"] == ev.H2_MARGIN
    assert "at_the_margin" not in informed["H2"]
    assert informed["H3 with condition b"]["delta"] > 0.1
    assert informed["H3 with condition a"]["delta"] < 0
    null = models["grok-4.20"]["on_every_eligible_statement"]
    assert abs(null["H1"]["delta"]) < 0.05 and null["H1"]["p"] > 0.05
    assert null["H2"]["losses_differ"]["statements"] > 0
    assert null["H1"]["bounds"]["statements"] == base.report["items"]["eligible_statements"]
    assert null["H1"]["bounds"]["with_a_horizon_event_undetermined"] > 0
    assert set(null["H1"]["bounds"]) >= {"undetermined_as_no", "undetermined_as_yes"}
    # nothing here is a test of the family: no adjusted p-value, no verdict, no reading
    assert not {"p_holm", "holds", "reading"} & set(strings(base.report))
    silent = base.report["where_the_plan_is_silent"]
    assert any("2x2" in line and "P(E_end90)" in line for line in silent)
    assert any("none is read as a verdict" in line for line in silent)


@pytest.mark.parametrize("not_scoreable", [0, 1, 4, 5])
def test_the_mean_probability_on_the_scoreable_statements_names_the_few_that_are_not(
    not_scoreable: int,
) -> None:
    """The predictions are open. Their mean over the scoreable statements, times the number of
    those, is their sum over every statement less the sum over the statements that are not
    scoreable: with one to four of those, the sum says which they are. The mean is withheld
    there, and the calibration in the large with it, which is the mean less a frequency that
    Murphy's uncertainty gives."""
    rows, _ = open_case(not_scoreable)
    pred = forecasts(rows.index, [0.31 + 0.05 * k for k in range(12)], [0.8] * 12)
    record = written(sc.scores(rows, pred, 200, 3))
    scoreable = 12 - not_scoreable
    over_the_rest = float(pred["p_a"].iloc[scoreable:].sum())
    rate = float(rows["y_a"].mean())
    assert near(record["murphy"]["E_end"]["uncertainty"], rate * (1 - rate))
    if 0 < not_scoreable < sc.MIN_SHOWN:
        assert record["mean_p_E_end"] is None and record["mean_p_E_end90"] is None
        assert record["calibration_in_the_large"] == {
            "statements": 12,
            "with_a_horizon_event_undetermined": not_scoreable,
            "withheld": True,
        }
        # nothing left is the sum of the probabilities over the statements that are not
        # scoreable, by either road
        for value in numbers(record):
            for mean in (value, value + rate, value + 1 - rate):
                assert not near(float(pred["p_a"].sum()) - scoreable * mean, over_the_rest)
    else:
        # the same arithmetic where it gives back nothing about a few statements
        assert near(float(pred["p_a"].sum()) - scoreable * record["mean_p_E_end"], over_the_rest)
        gap = record["calibration_in_the_large"]["E_end"]["mean_p_minus_frequency"]
        assert near(gap + rate, record["mean_p_E_end"]) and record["mean_p_E_end90"] == 0.8


def test_every_score_of_section_7_2_for_the_six_secondary_models_and_conditions(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    # the scores of a primary are the evaluator's, on the item set its probe fixed: none here
    scores = base.report["secondary_models"]["scores_on_every_eligible_statement"]
    assert list(scores) == list(sc.SECONDARY_MODELS) and not set(scores) & set(ev.PRIMARIES)
    assert "evaluator (losses)" in base.report["secondary_models"]["scores_of_the_primaries"]
    held = json.loads(study.paths.confirmatory.read_text())["losses"]
    assert all(f"{model}:{c}" in held for model in ev.PRIMARIES for c in ev.CONDITIONS)
    wanted = {"primary_brier", "ci95", "bounds_all_statements", "pinball_all_statements"}
    wanted |= {"calibration_in_the_large", "murphy", "coverage_80", "scoreable_statements"}
    for model in sc.SECONDARY_MODELS:
        assert list(scores[model]) == list(ev.CONDITIONS)
        assert all(wanted <= set(scores[model][c]) for c in ev.CONDITIONS), model
    ids, y = fit.ids, fit.y.loc[fit.ids]
    keep = y["scoreable"].to_numpy()
    pred, parsed = given(study, NOISY, "b", ids, fit.base)
    got = scores[NOISY]["b"]
    assert near(got["primary_brier"], brier(pred, y)[keep].mean())
    assert near(got["mean_p_E_end"], pred.loc[keep, "p_a"].mean())
    gap = pred.loc[keep, "p_a"].mean() - y.loc[keep, "y_a"].mean()
    assert near(got["calibration_in_the_large"]["E_end"]["mean_p_minus_frequency"], gap)
    # beside it, the same quantities for the base rate on the same statements (section 7.2)
    for model in sc.SECONDARY_MODELS:
        for condition in ev.CONDITIONS:
            record = scores[model][condition]
            beside_it = record["calibration_in_the_large"]["E_end"]["base_rate"]
            theirs = (fit.base.loc[ids, "p_a"] - y["y_a"])[keep]
            assert near(beside_it["mean_p_minus_frequency"], theirs.mean()), (model, condition)
            assert near(beside_it["ci95"], by_hand(theirs, y["episode"][keep])[1])
            limits = record["calibration_all_statements"]["E_end90"]["base_rate"]
            least = (fit.base.loc[ids, "p_b"] - y["y_b"].fillna(1.0)).mean()
            assert near(limits["least"], least) and limits["undetermined"] > sc.MIN_SHOWN
    assert set(got["pinball_all_statements"]) == {"0.50", "0.80", "0.95"}
    assert set(got["murphy"]["E_end90"]) == {"bins", "reliability", "resolution", "uncertainty"}
    # the rule for tied probabilities, which language models give often, stands in the file:
    # tied statements count with their common frequency, whatever the order of the statements
    # (PLAN section 7.2 gives the rule, so the file carries it among what the plan says)
    (ties,) = [line for line in base.report["as_the_plan_says"] if "Brier decomposition" in line]
    assert "do not depend on the order of the statements" in ties
    assert "a forecast of one value has no resolution" in ties
    assert "E1" not in ties and "Turnbull" not in ties
    assert not [line for line in base.report["where_the_plan_is_silent"] if "share a prob" in line]
    one_value = ev.murphy([0.3] * 30, [1.0] * 5 + [0.0] * 25)
    assert one_value["bins"] == 10 and abs(one_value["resolution"]) < 1e-12
    other_order = ev.murphy([0.3] * 30, [0.0, 0.0, 0.0, 0.0, 0.0, 1.0] * 5)
    assert all(near(one_value[key], other_order[key]) for key in one_value)
    # the failed answers of the run take the base rate, and are counted with its rates
    run = base.report["secondary_models"]["models"][NOISY]["runs"]["b"]
    failed = int((~parsed).sum())
    assert failed > 0 and run["replaced_by_base_rate"] == failed
    assert run["by_status"]["failed"] == failed and near(
        run["parse_failure_rate"], failed / len(ids)
    )
    assert run["line"] == "e3-b" and run["rows"] == len(ids) and run["refusal_rate"] == 0.0
    missed = base.report["secondary_models"]["models"][NOISY]["on_every_eligible_statement"]["H1"]
    left_out = int((~parsed[keep]).sum())
    assert missed["scoreable_not_parsed"] == {f"{NOISY}:a": 0, f"{NOISY}:b": left_out}
    both = y[keep & parsed.to_numpy()]
    assert missed["both_sides_parsed"]["statements"] == len(both)
    # the contrast on the statements both sides parsed leaves out a few scoreable ones here:
    # beside the contrast on all of them it would give the summed difference on the few
    assert 0 < left_out < sc.MIN_SHOWN <= failed
    assert missed["both_sides_parsed"] == {
        "not_both_parsed": failed,
        "left_out": left_out,
        "statements": len(both),
        "episodes": both["episode"].nunique(),
        "withheld": True,
    }
    # with none left out it is the contrast itself
    whole = base.report["secondary_models"]["models"][INFORMED]["on_every_eligible_statement"]
    assert whole["H1"]["scoreable_not_parsed"] == {f"{INFORMED}:a": 0, f"{INFORMED}:b": 0}
    assert near(whole["H1"]["both_sides_parsed"]["delta"], whole["H1"]["delta"])
    assert whole["H1"]["both_sides_parsed"]["interval_method"] == ev.PERCENTILE_INTERVAL
    assert (
        whole["H1"]["both_sides_parsed"]["not_both_parsed"],
        whole["H1"]["both_sides_parsed"]["left_out"],
    ) == (0, 0)


def test_the_probe_and_the_post_cutoff_slice_of_a_secondary_model(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    models = base.report["secondary_models"]["models"]
    assert models["gemini-3.8-flash"]["probe"] is None
    y = fit.y.loc[fit.ids]
    day = study.filled.loc[fit.ids, "event_date"]
    horizons = dict(zip(("h_a", "h_b"), (float(days) for days in D.FALLBACK_DAYS), strict=True))
    probe_base = fit.fitted[ev.BASE].predict(fit.frame.loc[fit.probe_ids].assign(**horizons))
    cells = study.filled.loc[fit.probe_ids]
    kept = (cells["ttr_kind"] != "right_censored").to_numpy()
    target = pd.to_numeric(cells.loc[kept, "ttr_mid_days"]).to_numpy()
    assert 0 < kept.sum() < len(fit.probe_ids)
    for model in sc.SECONDARY_MODELS:
        entry, cutoff = models[model], S.CUTOFF_MONTH_ENDS[model].isoformat()
        after = (day > cutoff).to_numpy() & S.has_slice(S.CUTOFF_MONTH_ENDS[model])
        sliced = entry["post_cutoff_slice"]
        assert sliced["cutoff_month_end"] == cutoff
        assert sliced["slice_statements"] == int(after.sum())
        assert sliced["slice_scoreable"] == int((after & y["scoreable"]).sum())
        analysed = sliced["slice_scoreable"] >= ev.MIN_SLICE
        assert ("on_the_post_cutoff_slice" in entry) == analysed == sliced["slice_analysed"]
        if model != "gemini-3.8-flash":
            # the probe by hand: pinball loss at 0.5 of the scripted median against the base
            # rate's, on the probe statements whose target is not right-censored
            probe = entry["probe"]
            wanted = ev.contrast(
                P.pinball(probe_base.loc[kept, "q50"], target, ev.PROBE_LEVEL),
                P.pinball(
                    np.full(len(target), 3.0 + rd.STUDY_MODELS.index(model)), target, ev.PROBE_LEVEL
                ),
                list(cells.loc[kept, "episode_id"]),
            )
            assert probe["probe_statements"] == len(fit.probe_ids)
            assert probe["statements"] == int(kept.sum())
            assert probe["left_out_right_censored"] == len(fit.probe_ids) - int(kept.sum())
            assert near(probe["delta"], wanted["delta"]), model
            assert near(probe["p"], wanted["p_values"][ev.P_VALUE_SOURCE]["one_sided"])
            assert near(probe["ci95"], wanted["ci95"])  # the registered draws and seed
            assert probe["beats_base_rate"] is (probe["p"] < ev.PROBE_ALPHA) and probe["delta"] < 0
    assert models["grok-4.20"]["post_cutoff_slice"]["slice_inside_the_test_split"] is False
    early = models["gpt-4o-mini"]
    after = (day > "2023-10-31").to_numpy() & y["scoreable"].to_numpy()
    assert int(after.sum()) >= ev.MIN_SLICE
    a, _ = given(study, "gpt-4o-mini", "a", fit.ids, fit.base)
    b, _ = given(study, "gpt-4o-mini", "b", fit.ids, fit.base)
    # the decomposition again on the slice: the trust loss is condition (a) less condition (c)
    c = fit.fitted[ev.RULES].predict(
        fit.frame.loc[fit.ids], read_days(study, "gpt-4o-mini", fit.ids)
    )
    trust = early["decomposition_on_the_post_cutoff_slice"]["trust_loss"]
    assert trust["statements"] == int(after.sum())
    assert near(trust["delta"], (brier(a, y) - brier(c, y))[after].mean())
    assert sum("decomposition_on_the_post_cutoff_slice" in entry for entry in models.values()) == 1
    got = early["on_the_post_cutoff_slice"]["H1"]
    assert got["statements"] == int(after.sum())
    assert near(got["delta"], (brier(a, y) - brier(b, y))[after].mean())
    assert near(
        early["scores_on_the_post_cutoff_slice"]["b"]["primary_brier"], brier(b, y)[after].mean()
    )


def list_predictions(
    study: SimpleNamespace, fit: SimpleNamespace, model: str, key: str
) -> dict[str, pd.DataFrame]:
    ids = list_ids(study, key)
    rows = fit.frame.loc[ids]
    base = fit.fitted[ev.BASE].predict(rows)
    made = {c: given(study, model, c, ids, base)[0] for c in ("a", "b")}
    made["c"] = fit.fitted[ev.RULES].predict(rows, read_days(study, model, ids))
    return {ev.BASE: base, **made}


def test_stale_value_uptake_on_the_stale_list(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    ids = list_ids(study, "stale")
    assert len(ids) >= 5 and base.report["secondary_lists"][LLAMA]["stale"]["statements"] == len(
        ids
    )
    for model in rd.PRIMARIES:
        entry = base.report["secondary_lists"][model]["stale"]
        assert "scores" not in entry and "against_the_base_rate" not in entry
        made = list_predictions(study, fit, model, "stale")
        for condition in ev.CONDITIONS:
            got = entry["stale_value_uptake"][condition]
            share = float((made[condition]["p_a"] > 0.5).mean())
            assert near(got["share_above_one_half"]["mean"], share), (model, condition)
            assert got["share_above_one_half"]["statements"] == len(ids)
            assert got["not_parsed"] == 0
    # the first primary puts 0.9 on a period that has passed under (a), and 0.2 under (b)
    uptake = base.report["secondary_lists"][LLAMA]["stale"]["stale_value_uptake"]
    assert uptake["a"]["share_above_one_half"]["mean"] == 1.0
    assert uptake["b"]["share_above_one_half"]["mean"] == 0.0
    second = base.report["secondary_lists"][DEEPSEEK]["stale"]["stale_value_uptake"]["a"]
    above = [0.3 + 0.4 * TE.unit(item, "la") > 0.5 for item in ids]
    assert 0 < sum(above) < len(ids)
    assert near(second["share_above_one_half"]["mean"], sum(above) / len(ids))
    # under (c) the second primary abstains on some stale statements
    days = read_days(study, DEEPSEEK, ids)
    selective = base.report["secondary_lists"][DEEPSEEK]["stale"][
        "selective_prediction_of_condition_c"
    ]
    assert selective["abstained"] == int(days.isna().sum()) > 0


def test_tbd_and_silent_statements_against_the_base_rate(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    for model in rd.PRIMARIES:
        for key in sc.FALLBACK_LISTS:
            ids = list_ids(study, key)
            y = fit.y.loc[ids]
            keep = y["scoreable"].to_numpy()
            entry = base.report["secondary_lists"][model][key]
            assert entry["statements"] == len(ids) and "stale_value_uptake" not in entry
            assert entry["scoreable_statements"] == int(keep.sum())
            assert int(keep.sum()) >= ev.MIN_EPISODES  # of the setup: enough to contrast
            assert entry["horizon_events"] == "recovery within 90 and within 180 days"
            made = list_predictions(study, fit, model, key)
            for condition in ev.CONDITIONS:
                got = entry["against_the_base_rate"][condition]
                gain = (brier(made[ev.BASE], y) - brier(made[condition], y))[keep]
                assert got["statements"] == int(keep.sum()), (model, key, condition)
                assert near(got["delta"], gain.mean()), (model, key, condition)
                assert got["bounds"]["statements"] == len(ids)
                assert got["interval_method"] == ev.PERCENTILE_INTERVAL
                wanted = ev.contrast(
                    brier(made[ev.BASE], y)[keep],
                    brier(made[condition], y)[keep],
                    list(y.loc[keep, "episode"]),
                )
                assert near(got["p"], wanted["p_values"][ev.P_VALUE_SOURCE]["two_sided"])
                assert near(got["ci95"], wanted["ci95"]), (model, key, condition)
                if 0 < int((~keep).sum()) < sc.MIN_SHOWN:
                    assert got["bounds"]["withheld"] is True
                else:
                    same_bounds(got["bounds"], made[ev.BASE], made[condition], y)
                # section 4: the same contrast where the reading was parsed (the base rate
                # always is), withheld when that leaves out or keeps a few scoreable statements
                flags = np.array([fails(model, condition, item) < 2 for item in ids])
                as_parsed_only(
                    got["both_sides_parsed"],
                    got["scoreable_not_parsed_by_both"],
                    keep,
                    ~flags,
                    gain[flags[keep]].mean() if (keep & flags).any() else None,
                )
                assert "scoreable_not_parsed" not in got
                score = entry["scores"][f"{model}:{condition}"]
                assert near(score["primary_brier"], brier(made[condition], y)[keep].mean())
            assert near(
                entry["scores"][ev.BASE]["primary_brier"], brier(made[ev.BASE], y)[keep].mean()
            )
            # the horizons are 90 and 180 days after the statement, as the prompts asked
            assert set(fit.frame.loc[ids, "h_a"]) == {90.0} and set(fit.frame.loc[ids, "h_b"]) == {
                180.0
            }
            days = read_days(study, model, ids)
            selective = entry["selective_prediction_of_condition_c"]
            assert selective["abstained"] == int(days.isna().sum())
            assert near(selective["primary_brier_all"]["mean"], brier(made["c"], y)[keep].mean())
            assert selective["primary_brier_all"]["statements"] == int(keep.sum())
    # the first primary follows the outcome under (b); it abstains on every TBD statement
    first = base.report["secondary_lists"][LLAMA]["tbd"]
    assert first["against_the_base_rate"]["b"]["delta"] > 0.05
    assert first["selective_prediction_of_condition_c"]["abstention_rate"] == 1.0
    second = base.report["secondary_lists"][DEEPSEEK]["tbd"]["selective_prediction_of_condition_c"]
    assert 0 < second["abstention_rate"] < 1.0


def sampled_by_hand(study: SimpleNamespace, model: str, ids: Sequence[str], base: pd.DataFrame):
    """The sampled quantiles of each statement by the rank rule, and how many statements have
    no parsed sample, how many samples were parsed and how many statements have a sample left
    out."""
    values, bare, parsed, short = [], 0, 0, 0
    for item in ids:
        row = study.known.loc[item].to_dict()
        medians = sorted(
            answer(model, "samples", row, k)["days_to_recovery"]["q50"]
            for k in range(20)
            if fails(model, "samples", item, k) < 2
        )
        parsed += len(medians)
        short += len(medians) < 20
        if not medians:
            bare += 1
            values.append(base.loc[item, list(P.QUANTILE_KEYS)].tolist())
            continue
        ranks = [max(1, -(-pct * len(medians) // 100)) for pct in (10, 50, 80, 90, 95)]
        values.append([float(medians[rank - 1]) for rank in ranks])
    table = pd.DataFrame(values, index=list(ids), columns=list(P.QUANTILE_KEYS))
    return table, bare, parsed, short


def test_sampled_against_verbalised_quantiles_on_the_subset(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    ids = subset_ids(study, "samples20")
    cells = study.filled.loc[ids]
    scored_rows = (cells["ttr_kind"] != "right_censored").to_numpy()
    target = pd.to_numeric(cells.loc[scored_rows, "ttr_mid_days"]).to_numpy()
    assert 0 < scored_rows.sum() < len(ids)
    for model in rd.PRIMARIES:
        entry = base.report["sampled_quantiles"][model]
        sampled, bare, parsed, short = sampled_by_hand(study, model, ids, fit.base)
        assert entry["statements"] == len(ids) == 60 and entry["samples_per_statement"] == 20
        assert entry["samples_parsed"] == parsed < 20 * len(ids)
        assert entry["statements_with_no_parsed_sample"] == bare == int(model == DEEPSEEK)
        # a statement with a sample left out is counted, whether or not any of its samples parsed
        assert entry["statements_with_a_sample_left_out"] == short
        assert bare < short < len(ids)
        # the scripted samples never put P(E_end90) below P(E_end)
        assert entry["p_b_below_p_a"] == 0
        assert entry["run"]["rows"] == 20 * len(ids)
        assert near(entry["run"]["parse_failure_rate"], 1 - parsed / (20 * len(ids)))
        assert entry["run"]["refusal_rate"] == 0.0 and entry["run"]["parse_failure_rate"] > 0
        verbal, flags = given(study, model, "a", ids, fit.base)
        assert entry["verbalised_not_parsed"] == int((~flags).sum())
        for level, key in ((0.5, "q50"), (0.8, "q80"), (0.95, "q95")):
            got = entry["pinball"][f"{level:.2f}"]
            mine = P.pinball(sampled.loc[scored_rows, key], target, level)
            theirs = P.pinball(verbal.loc[scored_rows, key], target, level)
            assert got["sampled"]["statements"] == int(scored_rows.sum())
            assert near(got["sampled"]["loss"], mine.mean()), (model, level)
            assert near(got["verbalised"]["loss"], theirs.mean()), (model, level)
            assert near(got["verbalised_minus_sampled"]["delta"], (theirs - mine).mean())
            wanted = ev.contrast(theirs, mine, list(cells.loc[scored_rows, "episode_id"]))
            two_sided = wanted["p_values"][ev.P_VALUE_SOURCE]["two_sided"]
            assert near(got["verbalised_minus_sampled"]["p"], two_sided), (model, level)
            assert near(got["verbalised_minus_sampled"]["ci95"], wanted["ci95"])
        counted = entry["coverage_80"]["sampled"]
        assert (
            counted["inside"] + counted["outside"] + counted["bracket_straddles_the_interval"] == 60
        )
    assert BARE["item"] == ids[0]
    # the rule for a sample that did not parse stands in the result file
    (rule,) = [line for line in base.report["where_the_plan_is_silent"] if "j-th smallest" in line]
    assert "a sample that did not parse is left out, not replaced by the base rate" in rule
    assert "a statement with no parsed sample takes the base-rate quantiles" in rule


def test_the_2x2_reports_what_the_cells_move(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    ids = subset_ids(study, "twobytwo")
    y = fit.y.loc[ids]
    keep = y["scoreable"].to_numpy()
    for model in rd.PRIMARIES:
        entry = base.report["name_date_2x2"][model]
        assert entry["statements"] == len(ids) == 80 and entry["scoreable_statements"] == keep.sum()
        made = {sc.REFERENCE_CELL: given(study, model, "b", ids, fit.base)}
        made |= {CELL_NAMES[kind]: given(study, model, kind, ids, fit.base) for kind in CELL_SHIFT}
        loss = {cell: brier(pred, y)[keep] for cell, (pred, _) in made.items()}
        assert list(entry["primary_brier"]) == list(made)
        for cell in sc.CELLS:
            got = entry["change_from_the_reference_cell"][cell]
            assert near(entry["primary_brier"][cell]["mean"], loss[cell].mean()), (model, cell)
            change = (loss[cell] - loss[sc.REFERENCE_CELL]).mean()
            assert near(got["primary_loss"]["delta"], change), (model, cell)
            moved = (made[cell][0]["p_a"] - made[sc.REFERENCE_CELL][0]["p_a"]).abs().mean()
            assert near(got["mean_absolute_change"]["p_E_end"]["mean"], moved)
            assert got["not_parsed"] == int((~made[cell][1]).sum())
            assert entry["runs"][cell]["rows"] == len(ids)
            # the counts of section 4 for the run of the cell: readings replaced by the base
            # rate, and parsed answers that put P(E_end90) below P(E_end)
            pred, flags = made[cell]
            assert entry["runs"][cell]["replaced_by_base_rate"] == got["not_parsed"]
            below = int((pred["p_b"] < pred["p_a"])[flags.to_numpy()].sum())
            assert entry["runs"][cell]["p_b_below_p_a"] == below
            # the change in the loss again where both readings were parsed
            both = flags.to_numpy() & made[sc.REFERENCE_CELL][1].to_numpy()
            as_parsed_only(
                got["primary_loss_both_parsed"],
                got["scoreable_not_parsed_by_both"],
                keep,
                ~both,
                (loss[cell] - loss[sc.REFERENCE_CELL])[both[keep]].mean(),
            )
        real, masked, shifted, both = (loss[cell] for cell in made)
        effects = entry["effects_on_primary_loss"]
        assert near(
            effects["names_masked"]["delta"], ((masked + both) / 2 - (real + shifted) / 2).mean()
        )
        assert near(
            effects["dates_shifted"]["delta"], ((shifted + both) / 2 - (real + masked) / 2).mean()
        )
        assert near(effects["interaction"]["delta"], (both - masked - shifted + real).mean())
    # the second primary parses every cell: each moves the probabilities and the median as planned
    second = base.report["name_date_2x2"][DEEPSEEK]["change_from_the_reference_cell"]
    for kind, (more, days) in CELL_SHIFT.items():
        got = second[CELL_NAMES[kind]]["mean_absolute_change"]
        assert near(got["p_E_end"]["mean"], abs(more), 1e-4) and near(
            got["median_days"]["mean"], days
        )
        assert (
            second[CELL_NAMES[kind]]["mean_absolute_change_both_parsed"]["p_E_end"]["statements"]
            == 80
        )
    first = base.report["name_date_2x2"][LLAMA]["change_from_the_reference_cell"]
    assert first[CELL_NAMES["mask"]]["not_parsed"] > 0


def test_prompt_variance_on_the_subset(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    ids = subset_ids(study, "paraphrase")
    y = fit.y.loc[ids]
    keep = y["scoreable"].to_numpy()
    for model in rd.PRIMARIES:
        entry = base.report["prompt_variance"][model]
        assert entry["statements"] == len(ids) == 50 and list(entry["runs"]) == list(PARAPHRASES)
        made = {"predictive-track-v1": given(study, model, "b", ids, fit.base)[0]}
        made |= {name: given(study, model, name, ids, fit.base)[0] for name in PARAPHRASES}
        means = {name: brier(pred, y)[keep].mean() for name, pred in made.items()}
        assert list(entry["primary_brier"]) == list(made)
        for name in PARAPHRASES:  # the counts of section 4 for the run of each paraphrase
            flags = given(study, model, name, ids, fit.base)[1].to_numpy()
            run = entry["runs"][name]
            assert run["replaced_by_base_rate"] == int((~flags).sum()) and run["rows"] == len(ids)
            assert run["p_b_below_p_a"] == int((made[name]["p_b"] < made[name]["p_a"])[flags].sum())
        for name in made:
            assert near(entry["primary_brier"][name]["mean"], means[name]), (model, name)
        three = [means[name] for name in PARAPHRASES]
        spread = entry["spread_of_the_mean_primary_loss"]
        assert near(spread["paraphrases"]["range"], max(three) - min(three))
        assert near(spread["paraphrases"]["sd"], float(np.std(three, ddof=1)))
        four = list(means.values())
        assert near(spread["with_the_registered_prompt"]["range"], max(four) - min(four))
        low, high = spread["paraphrases"]["range_ci95"]
        assert 0 <= low <= high
        across = np.stack([made[name]["p_a"].to_numpy() for name in PARAPHRASES])
        per_statement = entry["spread_across_the_paraphrases_per_statement"]
        assert near(per_statement["p_E_end"]["mean"], across.std(axis=0, ddof=1).mean())
        change = entry["change_from_the_registered_prompt"]
        assert list(change) == list(PARAPHRASES)
        gain = means[PARAPHRASES[1]] - means["predictive-track-v1"]
        assert near(change[PARAPHRASES[1]]["primary_loss"]["delta"], gain)
    assert (
        base.report["prompt_variance"][LLAMA]["change_from_the_registered_prompt"][PARAPHRASES[0]][
            "not_parsed"
        ]
        > 0
    )


def test_the_descriptives_of_the_test_period(study: SimpleNamespace, base: SimpleNamespace) -> None:
    got, filled = base.report["descriptives"], study.filled
    assert got["statements"] == len(filled) == base.report["items"]["test_split_statements_at_risk"]
    assert got["episodes"] == filled["episode_id"].nunique()
    counts = got["counts"]
    assert counts["by_analysis_set"] == filled["analysis_set"].value_counts().sort_index().to_dict()
    assert counts["by_year"] == filled["event_date"].str[:4].value_counts().sort_index().to_dict()
    assert counts["by_company"] == filled["company_name"].value_counts().sort_index().to_dict()
    assert counts["by_form"] == filled["merged_form"].value_counts().sort_index().to_dict()
    assert sum(counts["by_statement_type"].values()) == len(filled)
    dated = filled[filled["analysis_set"] == "dated"]
    assert got["dated_statements_not_stale"] == len(dated)
    held = dated["E_end"].map({"yes": 1.0, "no": 0.0})
    rate = got["hold_rate"]["all_dated_forms"]
    assert rate["determined"] == int(held.notna().sum()) and rate["undetermined"] > 0
    assert near(rate["among_determined"]["mean"], held.mean())
    assert near(rate["undetermined_as_no"]["mean"], held.fillna(0.0).mean())
    assert near(rate["undetermined_as_yes"]["mean"], held.fillna(1.0).mean())
    assert rate["undetermined_as_no"]["ci95"][0] <= rate["undetermined_as_no"]["mean"]
    quarter = dated[dated["merged_form"] == "quarter"]
    assert got["hold_rate"]["by_form"]["quarter"]["statements"] == len(quarter)
    # slip, from the sealed brackets: recovery minus the stated end
    end = pd.to_numeric(dated["stated_end"].map(lambda d: D.days_between("2000-01-01", d)))
    day = pd.to_numeric(dated["event_date"].map(lambda d: D.days_between("2000-01-01", d)))
    lower, upper = pd.to_numeric(dated["lower_days"]), pd.to_numeric(dated["upper_days"])
    kind = dated["outcome"].to_numpy()
    left = np.where(kind == "discontinued", P.NEVER, lower - (end - day))
    right = np.where(kind == "recovered", upper - (end - day), np.inf)
    curve = P.turnbull(left, right)
    slip = got["slip"]["all_dated_forms"]
    assert near(slip["share_recovered_by_days_after_the_stated_end"]["0"], curve.cdf(0.0), 1e-5)
    assert near(slip["share_recovered_by_days_after_the_stated_end"]["90"], curve.cdf(90.0), 1e-5)
    assert near(slip["share_not_recovered_within_reach"], 1 - curve.reached, 1e-5)
    assert slip["draws"] == SLIP_DRAWS and len(slip["ci95"]) == len(sc.SLIP_DAYS)
    # a flat stretch at one half in the quarter form: the median is its start
    by_quarter = got["slip"]["by_form"]["quarter"]
    assert by_quarter["slip_quantiles_days"]["0.50"] == 32.0
    assert by_quarter["slip_quantiles_flat_to_days"]["0.50"] == 62.0
    for cell in (slip, *got["slip"]["by_form"].values(), *got["slip"]["by_revision"].values()):
        if "withheld" not in cell:
            assert set(cell["slip_quantiles_flat_to_days"]) <= set(cell["slip_quantiles_days"])
    assert base.report["bootstrap"]["draws_of_a_turnbull_estimate"] == SLIP_DRAWS
    assert list(got["slip"]["by_revision"]) == list(P.REVISIONS)
    finite = filled[filled["outcome"].isin(["recovered", "discontinued"])]
    width = pd.to_numeric(finite["upper_days"]) - pd.to_numeric(finite["lower_days"])
    widths = got["bracket_widths"]
    assert widths["with_a_finite_bracket"] == len(finite)
    assert widths["right_censored"] == int((filled["outcome"] == "censored").sum()) > 0
    assert near(widths["quantiles_days"]["0.50"], width.median())
    assert near(widths["mean_days"]["mean"], width.mean())
    assert near(widths["share_of_31_days_or_less"]["mean"], (width <= 31).mean())


def shortened(
    monkeypatch: pytest.MonkeyPatch, change: Callable[[str, pd.Index], pd.Index | None]
) -> None:
    """Lets ``score`` take, for each primary with an item set, the statements ``change`` makes
    of it (None: the item set as the probe fixed it) in place of the item set itself: a study
    in which another set stands near the sets the sections write on."""
    real = sc.fixed_sets

    def other_sets(*args: Any, **kwargs: Any) -> dict:
        sets = real(*args, **kwargs)
        for model, (ids, record) in list(sets.items()):
            made = None if ids is None else change(model, ids)
            if made is not None:
                sets[model] = (made, record)
        return sets

    monkeypatch.setattr(sc, "fixed_sets", other_sets)


def test_the_descriptives_of_the_test_period_give_way_to_the_item_set_of_a_primary(
    study: SimpleNamespace,
    base: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the ``score`` command: the tables of E1 are told of the sets the other sections
    and the evaluator write on, whichever section is asked for. Here the dated statements at
    risk are the eligible list; with a primary whose item set is the list but for two
    statements, the hold rate and the slip estimate of all dated statements are withheld and
    marked, and so is a cell of every split."""
    as_it_is = base.report["descriptives"]
    assert as_it_is["dated_statements_not_stale"] == base.report["items"]["eligible_statements"]
    assert sc.NEAR_SET not in json.dumps(as_it_is)
    model = next(
        model
        for model, record in json.loads(study.paths.confirmatory.read_text())["item_sets"].items()
        if record.get("items") == ev.ALL_ITEMS
    )
    shortened(monkeypatch, lambda name, ids: ids[2:] if name == model else None)
    report, _ = scored(study, tmp_path, capsys, section=["descriptives"])
    got = report["descriptives"]
    assert report["sections"] == ["descriptives"]
    for table in (got["hold_rate"], got["slip"]):
        assert table["all_dated_forms"][sc.NEAR_SET] is True
        assert numbers(table["all_dated_forms"]) == []
        for split in ("by_form", "by_statement_type", "by_revision"):
            marks = [mark for cell in table[split].values() for mark in cell if "withheld_" in mark]
            assert marks, split
    assert got["hold_rate"]["all_dated_forms"]["determined"] is None
    assert (
        got["bracket_widths"] == as_it_is["bracket_widths"] and got["counts"] == as_it_is["counts"]
    )


def test_the_sets_of_the_primaries_stand_beside_the_other_sections_through_the_command(
    study: SimpleNamespace,
    base: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the ``score`` command, the sets known are those of the item sets the probes
    fixed, of the literal readings and of the subsets, whichever section is asked for. With a
    primary whose item set is the slice of a secondary model but for two statements, that
    slice keeps its number alone; with one whose item set is the paraphrase subset and two
    statements more, its recovery type does."""
    model = next(
        model
        for model, record in json.loads(study.paths.confirmatory.read_text())["item_sets"].items()
        if record.get("items") == ev.ALL_ITEMS
    )
    as_it_is = base.report["secondary_models"]["models"][SLICED]
    assert as_it_is["post_cutoff_slice"]["slice_analysed"] is True
    assert "primary_brier" in as_it_is["scores_on_the_post_cutoff_slice"]["a"]
    cutoff = S.CUTOFF_MONTH_ENDS[SLICED].isoformat()

    def after_the_cutoff(name: str, ids: pd.Index) -> pd.Index | None:
        later = ids[(study.filled.loc[ids, "event_date"] > cutoff).to_numpy()]
        return later[2:] if name == model else None

    with monkeypatch.context() as patch:
        shortened(patch, after_the_cutoff)
        report, _ = scored(study, tmp_path, capsys, section=["secondary_models"])
    entry = report["secondary_models"]["models"][SLICED]
    count = as_it_is["post_cutoff_slice"]["slice_statements"]
    assert entry["post_cutoff_slice"]["withheld"] is True
    assert entry["post_cutoff_slice"]["slice_scoreable"] is None
    assert entry["scores_on_the_post_cutoff_slice"] == {"statements": count, "withheld": True}
    assert entry["on_every_eligible_statement"] == as_it_is["on_every_eligible_statement"]
    # the recovery type of an item set that is the paraphrase subset and two statements more
    chosen = subset_ids(study, "paraphrase")
    assert base.report["by_statement_type"]["models"][model]["types"]["recovery"]["contrasts"]

    def subset_and_two(name: str, ids: pd.Index) -> pd.Index | None:
        if name != model:
            return None
        return ids[ids.isin([*chosen, *ids[~ids.isin(chosen)][:2]])]

    with monkeypatch.context() as patch:
        shortened(patch, subset_and_two)
        report, _ = scored(study, tmp_path, capsys, section=["by_statement_type"])
    block = report["by_statement_type"]["models"][model]["types"]["recovery"]
    assert block == {"statements": len(chosen) + 2, "withheld": True}


def test_selective_prediction_on_the_eligible_list(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    got = base.report["selective_prediction"]
    assert list(got) == ["rule_reader", *(f"{model}:c" for model in rd.STUDY_MODELS)]
    ids, y = fit.ids, fit.y.loc[fit.ids]
    keep = y["scoreable"].to_numpy()
    assert got["rule_reader"]["abstained"] == 0 and got["rule_reader"]["abstention_rate"] == 0.0
    assert near(
        got["rule_reader"]["primary_brier_read"]["mean"], brier(fit.free[ev.RULES], y)[keep].mean()
    )
    assert got["rule_reader"]["primary_brier_abstained_on"]["statements"] == 0
    # its rate of zero is fixed by eligibility, and is marked so; no other point is
    assert got["rule_reader"]["abstention_rate_fixed_by_eligibility"] is True
    assert not [
        name for name, point in got.items() if name != "rule_reader" and "fixed" in str(list(point))
    ]
    (said,) = [
        line
        for line in base.report["where_the_plan_is_silent"]
        if line.startswith("selective prediction is one point per reader")
    ]
    assert "by the definition of eligibility" in said and "zero by construction" in said
    hidden: dict[str, bool] = {}
    kinds: dict[str, str] = {}
    for model in rd.STUDY_MODELS:
        entry = got[f"{model}:c"]
        days = read_days(study, model, ids)
        pred = fit.fitted[ev.RULES].predict(fit.frame.loc[ids], days)
        read = days.notna().to_numpy()
        assert entry["statements"] == len(ids) and entry["abstained"] == int((~read).sum())
        assert near(entry["abstention_rate"], (~read).mean())
        assert near(entry["primary_brier_all"]["mean"], brier(pred, y)[keep].mean())
        assert entry["primary_brier_all"]["statements"] == int(keep.sum())
        # a part of one to four statements, or of as many scoreable ones, is withheld, and the
        # other part with it: the loss on all less the part shown would give it back
        kinds[model] = held_parts(entry, read, keep)
        hidden[model] = kinds[model] in ("bare", "withheld")
        for name, part in (("read", read), ("abstained_on", ~read)):
            shown = entry[f"primary_brier_{name}"]
            if not hidden[model] and (keep & part).any():
                assert near(shown["mean"], brier(pred, y)[keep & part].mean()), (model, name)
        counted = ("failed_counted_as_abstain", "abstain", "period_of_another_statement_type")
        assert sum(entry[name] for name in counted) == entry["abstained"]
        assert entry["items"] == ev.ALL_ITEMS
    assert got[f"{INFORMED}:c"]["abstained"] == 0
    assert got[f"{DEEPSEEK}:c"]["abstained"] >= sc.MIN_SHOWN
    # the synthetic study holds both cases: a model with a part withheld, and one with both shown
    assert True in hidden.values() and False in hidden.values()


def test_the_sensitivity_analyses_of_the_recovery_rule(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    rows, listed = study.sealed_rows, study.listed
    left = (rows["outcome_B"] == "censored") & (rows["exit_date_B"] != "")
    moved = rows.copy()
    moved.loc[left, "outcome_B"] = "recovered"
    moved.loc[left, "upper_date_B"] = moved.loc[left, "exit_date_B"]
    assert int((left & rows["event_id"].isin(set(listed["event_id"]))).sum()) > 0
    assert sc.DISCONTINUED_CELL in rows.columns
    variants = dict(
        zip(
            sc.RECOVERY_VARIANTS,
            (
                D.attach_outcomes(listed, rows, "BL"),
                D.attach_outcomes(listed, moved),
                D.attach_outcomes(listed, sc.discontinued_by_the_cell(rows)),
            ),
            strict=True,
        )
    )
    events = {"yes": 1.0, "no": 0.0}
    a, _ = given(study, INFORMED, "a", fit.ids, fit.base)
    b, _ = given(study, INFORMED, "b", fit.ids, fit.base)
    primary = base.report["secondary_models"]["models"][INFORMED]["on_every_eligible_statement"][
        "H1"
    ]
    changed_somewhere = False
    for label, filled in variants.items():
        filled = filled.set_index("statement_group_id").loc[fit.ids]
        y = pd.DataFrame({"y_a": filled["E_end"].map(events), "y_b": filled["E_end90"].map(events)})
        keep = (y["y_a"].notna() & y["y_b"].notna()).to_numpy()
        got = base.report["recovery_rule"][label]
        assert got["computed"] is True and got["eligible_statements"] == len(fit.ids)
        assert got["scoreable_statements"] == int(keep.sum())
        # how many statements have another horizon event than under the primary outcome
        was = fit.y.loc[fit.ids]
        same = pd.Series(True, index=y.index)
        for column in ("y_a", "y_b"):
            same &= (y[column] == was[column]) | (y[column].isna() & was[column].isna())
        moved = got["statements_with_another_horizon_event"]
        assert moved[INFORMED] == int((~same).sum()) and list(moved) == list(rd.STUDY_MODELS)
        assert moved[INFORMED] == 0 or moved[INFORMED] >= sc.MIN_SHOWN
        entry = got["contrasts"][INFORMED]["H1"]
        assert entry["statements"] == int(keep.sum())
        assert near(entry["delta"], (brier(a, y) - brier(b, y))[keep].mean())
        assert entry["interval_method"] == ev.PERCENTILE_INTERVAL
        # H1 is one-sided and the others two-sided, under the registered procedure
        wanted = ev.contrast(
            brier(a, y)[keep], brier(b, y)[keep], list(fit.y.loc[fit.ids, "episode"][keep])
        )["p_values"][ev.P_VALUE_SOURCE]
        assert near(entry["p"], wanted["one_sided"])
        c = fit.fitted[ev.RULES].predict(fit.frame.loc[fit.ids], read_days(study, NOISY, fit.ids))
        rules = fit.free[ev.RULES].loc[fit.ids]
        wanted = ev.contrast(
            brier(rules, y)[keep], brier(c, y)[keep], list(fit.y.loc[fit.ids, "episode"][keep])
        )["p_values"][ev.P_VALUE_SOURCE]
        assert wanted["two_sided"] != wanted["one_sided"]
        assert near(got["contrasts"][NOISY]["H2"]["p"], wanted["two_sided"]), label
        changed_somewhere |= not near(entry["delta"], primary["delta"])
        assert list(got["contrasts"]) == list(rd.STUDY_MODELS)
        assert list(got["contrasts"][INFORMED]) == list(primary_names())
        # a primary keeps the three tests of the family, with the condition selected for H3
        family = {
            entry["hypothesis"]: entry["tested"]
            for entry in json.loads(study.paths.confirmatory.read_text())["family"]
            if entry["model"] == LLAMA
        }
        mine = got["contrasts"][LLAMA]
        assert {name: mine[name]["tested"] for name in mine} == family
    assert changed_somewhere


def test_the_contrasts_by_statement_type_on_the_synthetic_study(
    study: SimpleNamespace,
    base: SimpleNamespace,
    fit: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The analysis by statement type through the ``score`` command, worked out again from the
    scripted answers. The synthetic study holds recovery statements alone, so that type is the
    item set and its contrasts are the tests of the family; then a third of the eligible
    statements is read as next delivery (the cell of the statement table, changed once the
    predictions are made) and every contrast of the two types is recomputed, with the
    difference between them over draws of the episodes of the item set."""
    ids = fit.ids
    y = fit.y.loc[ids]
    keep, episodes = y["scoreable"].to_numpy(), y["episode"]
    family = {
        (entry["model"], entry["hypothesis"]): entry
        for entry in json.loads(study.paths.confirmatory.read_text())["family"]
    }
    as_it_is = base.report["by_statement_type"]
    assert list(as_it_is["models"]) == list(ev.PRIMARIES)
    for model in ev.PRIMARIES:
        entry = as_it_is["models"][model]
        assert entry["statements"] == len(ids) and entry["statements_of_another_type"] == 0
        assert entry["types"]["next_delivery"] == {"statements": 0}
        block = entry["types"]["recovery"]
        assert block["scoreable_statements"] == int(keep.sum()) >= sc.MIN_TYPE
        for name in ("H1", "H2", "H3"):  # the estimate of the registered test itself
            assert near(block["contrasts"][name]["delta"], family[model, name]["delta"])
            assert block["contrasts"][name]["tested"] == family[model, name]["tested"]
        assert entry["next_delivery_minus_recovery"] == {}
        assert entry["opposite_signs_in_the_two_types"] == {}
    # a third of the statements read as next delivery
    moved = sorted(ids[::3])
    kinds = pd.Series("recovery", index=ids)
    kinds.loc[moved] = "next_delivery"
    real = sc.prepare

    def with_two_types(*args: Any, **kwargs: Any) -> Any:
        prepared = real(*args, **kwargs)
        prepared.study.first.loc[moved, "statement_type"] = "next_delivery"
        return prepared

    monkeypatch.setattr(sc, "prepare", with_two_types)
    monkeypatch.setattr(sc, "MIN_TYPE", 20)
    report, _ = scored(study, tmp_path, capsys, section=["by_statement_type"])
    got = report["by_statement_type"]
    assert got["fewest_scoreable_statements_of_a_type"] == 20
    names = sorted(set(episodes))
    taken = P.cluster_draws(len(names), ev.DRAWS, ev.SEED).astype(float)
    for model in ev.PRIMARIES:
        entry = got["models"][model]
        a, parsed = given(study, model, "a", ids, fit.base)
        made = {
            f"{model}:a": a,
            f"{model}:b": given(study, model, "b", ids, fit.base)[0],
            f"{model}:c": fit.fitted[ev.RULES].predict(
                fit.frame.loc[ids], read_days(study, model, ids)
            ),
            ev.RULES: fit.free[ev.RULES].loc[ids],
            ev.BASE: fit.free[ev.BASE].loc[ids],
            ev.STRUCTURED: fit.free[ev.STRUCTURED].loc[ids],
        }
        best = family[model, "H3"]["tested"]
        pairs = {
            "H1": (f"{model}:a", f"{model}:b"),
            "H2": (ev.RULES, f"{model}:c"),
            "H3": (ev.BASE, best),
            sc.DELTA_GBM: (ev.STRUCTURED, best),
        }
        assert family[model, "H3"]["comparator"] == ev.BASE
        loss = {name: brier(pred, y) for name, pred in made.items()}
        of_type = {kind: (kinds == kind).to_numpy() for kind in sc.TYPES}
        for kind, flags in of_type.items():
            block = entry["types"][kind]
            assert block["statements"] == int(flags.sum())
            assert block["scoreable_statements"] == int((flags & keep).sum()) >= 20
            assert block["episodes"] == episodes[flags].nunique()
            for name, (comparator, tested) in pairs.items():
                paired = (loss[comparator] - loss[tested])[flags & keep]
                delta, interval = by_hand(paired, episodes[flags & keep])
                record = block["contrasts"][name]
                assert (record["comparator"], record["tested"]) == (comparator, tested)
                assert near(record["delta"], delta), (model, kind, name)
                assert near(record["ci95"], interval), (model, kind, name)
                assert record["statements"] == int((flags & keep).sum())
                assert record["bounds"]["statements"] == int(flags.sum())
            # the primary loss and the calibration in the large of the three conditions and
            # of the base rate
            for name, key in ((ev.BASE, ev.BASE), *((c, f"{model}:{c}") for c in ev.CONDITIONS)):
                record = block["scores"][name]
                mean, interval = by_hand(loss[key][flags & keep], episodes[flags & keep])
                assert near(record["primary_brier"], mean) and near(record["ci95"], interval)
                gap = (made[key]["p_a"] - y["y_a"])[flags & keep]
                large = record["calibration_in_the_large"]["E_end"]
                assert near(large["mean_p_minus_frequency"], gap.mean())
                assert near(large["ci95"], by_hand(gap, episodes[flags & keep])[1])
            # the criterion over every statement of the type: the mean probability of
            # condition (a) less the largest frequency the captures allow, and less the
            # mean probability of the base rate
            found = block["overconfidence"]
            least = (a["p_a"] - y["y_a"].fillna(1.0))[flags]
            outcomes = found["against_outcomes"]
            assert near(outcomes["least"], least.mean())
            assert near(outcomes["least_ci95"], by_hand(least, episodes[flags])[1])
            assert outcomes["undetermined"] == int((flags & y["y_a"].isna().to_numpy()).sum())
            against = (a["p_a"] - made[ev.BASE]["p_a"])[flags]
            assert near(found["against_base_rate"]["difference"], against.mean())
            assert found["statements"] == int(flags.sum())
            both = outcomes["met"] and found["against_base_rate"]["met"]
            assert found["both_parts_hold"] is both
        assert parsed.all() or not parsed.all()  # which answers parsed changes no figure here
        # next delivery minus recovery, over the registered draws of the episodes of the item
        # set, both types from each draw
        back, due = of_type["recovery"] & keep, of_type["next_delivery"] & keep
        for name, (comparator, tested) in pairs.items():
            paired = (loss[comparator] - loss[tested]).fillna(0.0)
            sums = np.array(
                [
                    [paired[flags & (episodes == episode).to_numpy()].sum() for episode in names]
                    for flags in (back, due)
                ]
            )
            sizes = np.array(
                [
                    [float((flags & (episodes == episode).to_numpy()).sum()) for episode in names]
                    for flags in (back, due)
                ]
            )
            totals, counted = taken @ sums.T, taken @ sizes.T
            kept = (counted > 0).all(axis=1)
            drawn = totals[kept, 1] / counted[kept, 1] - totals[kept, 0] / counted[kept, 0]
            apart = entry["next_delivery_minus_recovery"][name]
            assert near(apart["difference"], paired[due].mean() - paired[back].mean()), name
            assert near(apart["ci95"], [float(v) for v in np.quantile(drawn, [0.025, 0.975])])
            assert (apart["draws"], apart["draws_left_out"]) == (
                int(kept.sum()),
                int((~kept).sum()),
            )
            shown = [entry["types"][kind]["contrasts"][name]["delta"] for kind in sc.TYPES]
            assert near(apart["difference"], shown[1] - shown[0])
            assert entry["opposite_signs_in_the_two_types"][name] is bool(shown[0] * shown[1] < 0)
        flag = entry["overconfidence_holds_on_the_item_set_and_not_on_its_recovery_statements"]
        on_all = entry["overconfidence_on_the_item_set"]["both_parts_hold"]
        there = entry["types"]["recovery"]["overconfidence"]["both_parts_hold"]
        assert flag is (on_all and not there)
        whole = json.loads(study.paths.confirmatory.read_text())["secondaries"]
        # the evaluator's own record of the criterion on the item set
        assert on_all is whole["overconfidence_of_condition_a"][model]["met"]
    # under the registered floor the smaller type is reported by its counts alone
    monkeypatch.setattr(sc, "MIN_TYPE", 50)
    report, _ = scored(study, tmp_path, capsys, section=["by_statement_type"])
    for model in ev.PRIMARIES:
        entry = report["by_statement_type"]["models"][model]
        due = entry["types"]["next_delivery"]
        assert due["counts_alone"] == "fewer than 50 scoreable statements" and numbers(due) == []
        assert "contrasts" in entry["types"]["recovery"]
        assert entry["next_delivery_minus_recovery"] == {}


def test_the_turnbull_share_beside_the_criterion_on_the_synthetic_study(
    study: SimpleNamespace, base: SimpleNamespace, fit: SimpleNamespace
) -> None:
    """Section 13, "Reported beside it": for each primary on its item set, the mean of P(E_end)
    of condition (a) and of the base rate, each less the Turnbull share recovered by the
    stated end, worked out again from the brackets of the eligible statements."""
    got = base.report["beside_the_overconfidence_criterion"]
    assert list(got) == list(ev.PRIMARIES)
    ids = fit.ids
    filled = study.filled.loc[ids]
    end = pd.to_numeric(filled["stated_end"].map(lambda d: D.days_between("2000-01-01", d)))
    day = pd.to_numeric(filled["event_date"].map(lambda d: D.days_between("2000-01-01", d)))
    lower, upper = pd.to_numeric(filled["lower_days"]), pd.to_numeric(filled["upper_days"])
    kind = filled["outcome"].to_numpy()
    left = np.where(kind == "discontinued", P.NEVER, lower - (end - day))
    right = np.where(kind == "recovered", upper - (end - day), np.inf)
    share = float(P.turnbull(left, right).cdf(0.0))
    # in the synthetic study the eligible list is every dated statement at risk: the share of
    # the item set is the estimate the descriptives write on all dated statements
    dated = study.filled[study.filled["analysis_set"] == "dated"]
    assert set(dated.index) == set(ids)
    for model in ev.PRIMARIES:
        entry = got[model]
        assert entry["item_set_fixed_by_the_probe"]["items"] == ev.ALL_ITEMS
        assert entry["statements"] == len(ids) and entry["draws"] == SLIP_DRAWS
        assert entry["episodes"] == filled["episode_id"].nunique()
        assert near(entry["turnbull_share_recovered_by_the_stated_end"], share, 1e-5)
        mine = {
            "condition_a": given(study, model, "a", ids, fit.base)[0]["p_a"],
            "base_rate": fit.base.loc[ids, "p_a"],
        }
        for name, p in mine.items():
            record = entry[name]
            assert near(record["mean_p_E_end"], p.mean()), (model, name)
            assert near(record["mean_p_minus_the_turnbull_share"], p.mean() - share, 1e-5)
            low, high = record["ci95"]
            assert (
                low <= high and low - 0.2 < record["mean_p_minus_the_turnbull_share"] < high + 0.2
            )
        # the two primaries share the item set: one estimate, and the base rate's the same
    one, other = (got[model] for model in ev.PRIMARIES)
    assert one["base_rate"] == other["base_rate"]
    assert (
        one["turnbull_share_recovered_by_the_stated_end"]
        == (other["turnbull_share_recovered_by_the_stated_end"])
    )
    slip = base.report["descriptives"]["slip"]["all_dated_forms"]
    assert near(
        one["turnbull_share_recovered_by_the_stated_end"],
        slip["share_recovered_by_days_after_the_stated_end"]["0"],
    )


REPEATS = (
    "h2_on_the_month_and_year_form",
    "first_captured_by_the_stated_end",
    "clusters_by_company",
    "all_covered_presentations",
    "any_covered_presentation",
    "recovery_definition_A",
)
"""The repeats of the contrasts of a secondary model, under the evaluator's names."""


def primary_names() -> list[str]:
    return ["H1", "H2", *(f"H3 with condition {c}" for c in ev.CONDITIONS)]


# --------------------------------------------------------------------------------------------
# Refusals: nothing before the six tests and before every run is complete
# --------------------------------------------------------------------------------------------


@pytest.fixture
def sealed_unread(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fails the test if the sealed file is read or its rows are parsed; returns the list of
    files that were read."""
    read: list[str] = []
    real = S.file_bytes

    def file_bytes(path: Path, what: str) -> bytes:
        read.append(what)
        if what == "the sealed file":
            pytest.fail("the sealed file was read")
        return real(path, what)

    monkeypatch.setattr(S, "file_bytes", file_bytes)
    monkeypatch.setattr(ev, "unseal", lambda *a, **k: pytest.fail("the sealed rows were parsed"))
    monkeypatch.setattr(
        sc, "unseal_population", lambda *a, **k: pytest.fail("the sealed rows were parsed")
    )
    return read


def at(index: int, change: Callable[[dict], Any]) -> Callable[[dict], Any]:
    """Pass the stored row at a position through ``change`` (None drops it)."""
    seen = iter(range(10**7))

    def apply(row: dict) -> Any:
        return change(row) if next(seen) == index else row

    return apply


def test_a_missing_or_wrong_hash_is_refused_and_the_sealed_file_is_not_read(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("expect_sha256", "expect_eligible_sha256", "expect_baselines_sha256"):
        for value in (None, "abc", "z" * 64, study.sealed_sha[:15]):
            why = refused(study, tmp_path, capsys, **{name: value})
            assert f"--{name.replace('_', '-')} takes a sha256 or its first 16 or more" in why
    why = refused(study, tmp_path, capsys, expect_eligible_sha256="0" * 64)
    assert "the eligible list is not the expected file" in why
    # a hash other than that of the file the six tests were computed on
    why = refused(study, tmp_path, capsys, expect_sha256="0" * 64)
    assert "cannot stand behind the secondaries" in why and "for: the sealed file" in why
    why = refused(study, tmp_path, capsys, expect_sha256=study.eligible_sha)
    assert "for: the sealed file" in why
    why = refused(study, tmp_path, capsys, expect_baselines_sha256="0" * 64)
    assert "for: the model-free predictions" in why
    # a refit that gives other predictions than those hashed at the freeze
    monkeypatch.setattr(ev, "baseline_hash", lambda *a: "f" * 64)
    why = refused(study, tmp_path, capsys)
    assert "the model-free predictions are not those hashed at the freeze" in why
    assert "starts with ffffffffffffffff" in why and "the sealed file" not in sealed_unread


def test_a_sealed_file_with_another_hash_is_not_parsed(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ev, "unseal", lambda *a, **k: pytest.fail("the sealed rows were parsed"))
    real = ev.table_of
    other = tmp_path / "other.csv.gz"
    other.write_bytes(study.paths.sealed.read_bytes() + b" ")

    def table_of(data: bytes, gzipped: bool) -> pd.DataFrame:
        assert data != other.read_bytes(), "the sealed bytes were parsed"
        return real(data, gzipped)

    monkeypatch.setattr(ev, "table_of", table_of)
    why = refused(study, tmp_path, capsys, sealed=other)
    # PLAN, standing rules: no character of a sealed file's hash where it is refused for it
    assert why == (
        "refused: the sealed file is not the expected file: its sha256 is not the one given; "
        "no character of the hash of a sealed file is printed"
    )
    assert TE.file_sha(other)[:6] not in why and not re.search(r"[0-9a-f]{8}", why)
    why = refused(study, tmp_path, capsys, sealed=tmp_path / "nothing.csv.gz")
    assert "the sealed file cannot be read (FileNotFoundError)" in why


def test_no_secondary_score_without_the_result_file_of_the_evaluator(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    why = refused(study, tmp_path, capsys, confirmatory=None)
    assert "--confirmatory is required" in why
    why = refused(study, tmp_path, capsys, confirmatory=tmp_path / "confirmatory.json")
    assert "no secondary score before the six tests" in why and "is not there" in why
    path = study.paths.confirmatory
    changes: tuple[tuple[Callable[[dict], Any], str], ...] = (
        (lambda r: r.clear(), "it is not a result of the confirmatory command"),
        (lambda r: r.update(about="another file"), "it is not a result of the confirmatory"),
        (lambda r: r.update(family=r["family"][:5]), "it does not hold the six tests"),
        (lambda r: r["family"][2].pop("p_holm"), "it does not hold the six tests"),
        (
            lambda r: r["registered"].update(p_value_source="percentile"),
            "it was written under other registered constants than those in force",
        ),
        (lambda r: r["inputs"].update(sealed_outcomes_sha256="0" * 64), "for: the sealed file"),
        (
            lambda r: r["inputs"].update(baseline_predictions_sha256="0" * 64),
            "for: the model-free predictions",
        ),
        (lambda r: r["inputs"].update(eligible_sha256="0" * 64), "for: the eligible list"),
        (lambda r: r["inputs"].update(statements_sha256="0" * 64), "for: the statement table"),
        (lambda r: r["inputs"].pop("events_sha256"), "for: the events table"),
        (
            lambda r: r["h3"]["selections"][LLAMA].update(sha256="abc"),
            "names no selection file hash",
        ),
    )
    for change, said in changes:
        with TE.json_with(path, change):
            why = refused(study, tmp_path, capsys)
        assert said in why, said
    with TE.changed(path):
        path.write_text("[1, 2")
        assert "it is not a result of the confirmatory" in refused(study, tmp_path, capsys)
    # the selection file must be the one the six tests were computed with
    with TE.json_with(path, lambda r: r["h3"]["selections"][LLAMA].update(sha256="0" * 64)):
        why = refused(study, tmp_path, capsys)
    assert why == (
        f"refused: {sc.CANNOT_STAND}it was computed with another selection file than the one "
        f"hashed at the freeze for: {LLAMA}"
    )
    assert sealed_unread.count("the result file of the evaluator") >= len(changes)
    assert "the sealed file" not in sealed_unread


def test_a_declaration_is_confirmed_by_the_result_file_and_never_granted_by_it(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    """The field of the result file that waives the runs of a primary opens nothing: every
    primary declared is refused, a declaration counts only when this command line gives it too,
    and the tests of the family must say the same."""
    path = study.paths.confirmatory
    said = "its route was withdrawn"
    reason = sc.DECLARATION + said
    alone = "no test of the family can have been computed, and the sealed file is not opened"
    for section in (["descriptives"], ["secondary_models"], ["by_statement_type"], []):
        # one field changed: both primaries declared, by the file alone
        declare = dict.fromkeys(ev.PRIMARIES, reason)
        with TE.json_with(path, lambda r, d=declare: r.update(not_evaluable_by_declaration=d)):
            why = refused(study, tmp_path, capsys, section=section)
        assert why.startswith(f"refused: {sc.CANNOT_STAND}it declares every primary not evaluable")
        assert alone in why
    # and by the command line: refused before a file is opened
    before = len(sealed_unread)
    both = [f"{model}={said}" for model in ev.PRIMARIES]
    why = refused(study, tmp_path, capsys, not_evaluable=both, expect_selection_sha256=None)
    assert why.startswith("refused: every primary is declared not evaluable") and alone in why
    assert len(sealed_unread) == before
    # a file typed by hand, with no confirmatory run and no selection file on disk
    honest = json.loads(path.read_text())
    typed_by_hand = {
        "about": ev.ABOUT_RESULTS,
        "family": [{"p_holm": None} for _ in range(ev.TESTS)],
        "registered": honest["registered"],
        "inputs": {
            key: honest["inputs"][key]
            for key in (
                "sealed_outcomes_sha256",
                "baseline_predictions_sha256",
                "eligible_sha256",
                "statements_sha256",
                "events_sha256",
            )
        },
        "not_evaluable_by_declaration": dict.fromkeys(ev.PRIMARIES, reason),
    }
    forged = tmp_path / "typed_by_hand.json"
    forged.write_text(json.dumps(typed_by_hand))
    selections = [study.paths.selections / ev.SELECTION_NAME.format(model=m) for m in ev.PRIMARIES]
    with ExitStack() as stack:
        for model in ev.PRIMARIES:
            for line in ev.LINES["confirmatory"].values():
                stack.enter_context(TE.moved_away(TE.run_folder(study, model, line)))
        stack.enter_context(TE.changed(*selections))
        for selection in selections:
            selection.unlink()
        for section in (["descriptives"], ["descriptives", "selective_prediction"]):
            why = refused(study, tmp_path, capsys, confirmatory=forged, section=section)
            assert "it declares every primary not evaluable" in why
        # with one primary declared, the family it holds is not the six tests
        typed_by_hand["not_evaluable_by_declaration"] = {DEEPSEEK: reason}
        forged.write_text(json.dumps(typed_by_hand))
        one = {"not_evaluable": [f"{DEEPSEEK}={said}"]}
        one["expect_selection_sha256"] = [v for v in study.selection_shas if v.startswith(LLAMA)]
        why = refused(study, tmp_path, capsys, confirmatory=forged, section=["descriptives"], **one)
        assert (
            why == f"refused: {sc.CANNOT_STAND}its six tests are not H1, H2 and H3 of each primary"
        )
    # a declaration added to the file alone: this command line did not give it
    declare = {DEEPSEEK: reason}
    with (
        TE.json_with(path, lambda r: r.update(not_evaluable_by_declaration=declare)),
        TE.manifest_with(study, DEEPSEEK, "e3-a", complete=False),
    ):
        why = refused(study, tmp_path, capsys)
        assert f"declared not evaluable (['{DEEPSEEK}']) are not those that --not-evaluable" in why
        # given on the command line too, it still stands against the tests the family holds
        why = refused(study, tmp_path, capsys, **one)
        assert why == (
            f"refused: {sc.CANNOT_STAND}it holds tests of {DEEPSEEK}, which it declares not "
            "evaluable"
        )
        # nor does another model than a primary pass as declared
        with TE.json_with(path, lambda r: r.update(not_evaluable_by_declaration={NOISY: reason})):
            why = refused(study, tmp_path, capsys)
        assert f"(['{NOISY}']) are not those that --not-evaluable names" in why
    # the command line declares what the file does not, or with another reason than the file's
    why = refused(study, tmp_path, capsys, **one)
    assert "declared not evaluable ([]) are not those that --not-evaluable names" in why

    def as_declared(record: dict) -> None:
        record["not_evaluable_by_declaration"] = {DEEPSEEK: sc.DECLARATION + "another reason"}
        for entry in record["family"]:
            if entry["model"] == DEEPSEEK:
                entry.update(evaluable=False, reason=sc.DECLARATION + "another reason")

    with TE.json_with(path, as_declared):
        why = refused(study, tmp_path, capsys, **one)
    assert "are not those that --not-evaluable names, each with the reason given there" in why

    # declared on both sides with the same reason, while the tests of the family give another
    # reason for not being evaluable: the family does not say what the declaration says
    def another_reason_in_the_tests(record: dict) -> None:
        record["not_evaluable_by_declaration"] = {DEEPSEEK: reason}
        for entry in record["family"]:
            if entry["model"] == DEEPSEEK:
                entry.update(evaluable=False, reason="fewer than two episodes")

    holds = f"it holds tests of {DEEPSEEK}, which it declares not evaluable"
    with TE.json_with(path, another_reason_in_the_tests):
        assert refused(study, tmp_path, capsys, **one) == f"refused: {sc.CANNOT_STAND}{holds}"

    # the declarations are recorded as the evaluator writes them: a mapping, empty when none
    for other in ([DEEPSEEK], "none", None, {DEEPSEEK: ["withdrawn"]}):
        with TE.json_with(
            path, lambda r, other=other: r.update(not_evaluable_by_declaration=other)
        ):
            why = refused(study, tmp_path, capsys)
        assert why == (
            f"refused: {sc.CANNOT_STAND}it does not record, model by model with the reason, "
            "which primaries were declared not evaluable"
        )
    with TE.json_with(path, lambda r: r.pop("not_evaluable_by_declaration")):
        assert "which primaries were declared not evaluable" in refused(study, tmp_path, capsys)

    # a test of a primary that is not declared says whether it is evaluable, and never that it
    # was declared
    def unsaid(record: dict) -> None:
        record["family"][1].pop("evaluable")

    def half_declared(record: dict) -> None:
        record["family"][4].update(evaluable=False, reason=reason)

    for change, model in ((unsaid, LLAMA), (half_declared, DEEPSEEK)):
        with TE.json_with(path, change):
            why = refused(study, tmp_path, capsys)
        assert f"it does not say whether each test of {model} is evaluable" in why
    assert "the sealed file" not in sealed_unread


def test_a_stale_or_edited_result_file_stands_behind_no_secondary(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    """The result file of the evaluator is held to the confirmatory runs and the selection
    files on disk: the readings its tests were computed on, the tests the selection files
    give, and the item set of each primary with the tests that name it."""
    path = study.paths.confirmatory
    # a confirmatory run read again since the six tests: complete, and with other readings
    for model, line in (
        (LLAMA, "e3-a"),
        (LLAMA, "e3-b"),
        (DEEPSEEK, "e3-c"),
        (DEEPSEEK, "e4-probe"),
    ):
        with TE.rewritten(study, model, line, at(0, lambda row: row | {"read_again": True})):
            why = refused(study, tmp_path, capsys)
        assert why == (
            f"refused: {sc.CANNOT_STAND}the stored readings are not those the six tests were "
            f"computed on ({model} {line})"
        )
    with TE.json_with(path, lambda r: r.pop("runs")):
        why = refused(study, tmp_path, capsys, section=["descriptives"])
    assert "the stored readings are not those the six tests were computed on" in why
    assert all(f"{model} {line}" in why for model in ev.PRIMARIES for line in ("e3-a", "e4-probe"))
    record = json.loads(path.read_text())
    selected = record["family"][2]["tested"]
    another = next(f"{LLAMA}:{c}" for c in ev.CONDITIONS if f"{LLAMA}:{c}" != selected)
    whole = sum(S.has_slice(S.CUTOFF_MONTH_ENDS[model]) for model in ev.PRIMARIES)
    assert whole and record["item_sets"][LLAMA]["items"] == ev.ALL_ITEMS

    def not_evaluable(record: dict) -> None:
        record["item_sets"][DEEPSEEK].update(
            evaluable=False, reason="the probe could not be tested"
        )

    def other_set(record: dict) -> None:
        record["item_sets"][LLAMA]["items"] = ev.SLICE_ITEMS

    changes: tuple[tuple[Callable[[dict], Any], str], ...] = (
        (
            lambda r: r["family"][2].update(tested=another),
            f"its tests of {LLAMA} are not those the selection file gives",
        ),
        (
            lambda r: r["family"][0].update(sides=2),
            f"its tests of {LLAMA} are not those the selection file gives",
        ),
        (
            lambda r: r["family"][5].update(comparator=ev.STRUCTURED),
            f"its tests of {DEEPSEEK} are not those the selection file gives",
        ),
        (
            lambda r: r["h3"].update(comparator=ev.STRUCTURED),
            "its comparator of H3 is not the one of the selection files",
        ),
        (lambda r: r.pop("item_sets"), f"the item set the probe fixed for {LLAMA}"),
        (
            lambda r: r["item_sets"][LLAMA].update(evaluable="yes"),
            f"the item set the probe fixed for {LLAMA}",
        ),
        (
            lambda r: r["item_sets"][LLAMA].update(items="the statements that suit"),
            f"the item set the probe fixed for {LLAMA}",
        ),
        # the item set says one thing and the tests that name it another
        (other_set, f"the item set the probe fixed for {LLAMA}"),
        (not_evaluable, f"the item set the probe fixed for {DEEPSEEK}"),
        (
            lambda r: r["family"][4].pop("items"),
            f"the item set the probe fixed for {DEEPSEEK}",
        ),
        (
            lambda r: r["item_sets"][DEEPSEEK].update(slice_statements=1),
            f"the item set the probe fixed for {DEEPSEEK}",
        ),
    )
    for change, said in changes:
        with TE.json_with(path, change):
            why = refused(study, tmp_path, capsys, section=["recovery_rule"])
        assert why.startswith(f"refused: {sc.CANNOT_STAND}") and said in why, said
    assert "the sealed file" not in sealed_unread


def test_no_start_without_the_hash_of_each_selection_file(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    """PLAN section 6: no start without the sha256 of each primary's selection file. The hashes
    come from the command line, as the freeze records them; the result file of the evaluator
    and the file on disk are both held to them."""
    needed = "--expect-selection-sha256 is required for {}: the H3 selections are held to the"
    why = refused(study, tmp_path, capsys, expect_selection_sha256=None)
    assert needed.format(list(ev.PRIMARIES)) in why and sealed_unread == []
    mine = {model: value for model, value in (v.split("=") for v in study.selection_shas)}
    why = refused(study, tmp_path, capsys, expect_selection_sha256=[f"{LLAMA}={mine[LLAMA]}"])
    assert needed.format([DEEPSEEK]) in why and sealed_unread == []
    malformed = (
        [f"{LLAMA}={mine[LLAMA][:15]}", f"{DEEPSEEK}={mine[DEEPSEEK]}"],
        [f"{LLAMA}=", f"{DEEPSEEK}={mine[DEEPSEEK]}"],
        [f"{NOISY}={mine[LLAMA]}", *study.selection_shas],
        [*study.selection_shas, f"{LLAMA}={mine[LLAMA]}"],
    )
    for values in malformed:
        why = refused(study, tmp_path, capsys, expect_selection_sha256=values)
        assert "--expect-selection-sha256 takes" in why and sealed_unread == []
    # another hash than the result file records
    other = [f"{LLAMA}={'0' * 64}", f"{DEEPSEEK}={mine[DEEPSEEK]}"]
    why = refused(study, tmp_path, capsys, expect_selection_sha256=other)
    assert why == (
        f"refused: {sc.CANNOT_STAND}it was computed with another selection file than the one "
        f"hashed at the freeze for: {LLAMA}"
    )
    # a selection file replaced since the freeze, with its new hash written into the result
    # file: the hash of the freeze, given here, is the pin, and not the file
    selection = study.paths.selections / ev.SELECTION_NAME.format(model=LLAMA)
    with TE.changed(selection):
        selection.write_bytes(selection.read_bytes() + b" ")
        new = TE.file_sha(selection)
        why = refused(study, tmp_path, capsys)
        assert "is not the selection file hashed at the freeze" in why
        with TE.json_with(
            study.paths.confirmatory, lambda r: r["h3"]["selections"][LLAMA].update(sha256=new)
        ):
            why = refused(study, tmp_path, capsys)
            assert f"than the one hashed at the freeze for: {LLAMA}" in why
    assert "the sealed file" not in sealed_unread


INCOMPLETE = (
    (NOISY, "e3-b", f"{NOISY} e3-b: run e3-b-{NOISY} is not finished"),
    ("grok-4.20", "e4-probe", "grok-4.20 e4-probe: run e4-probe-grok-4.20 is not finished"),
    (LLAMA, "e3-tbd-a", f"tbd list, {LLAMA} e3-secondary-a: run e3-tbd-a-{LLAMA} is not finished"),
    (
        DEEPSEEK,
        "e3-stale-c",
        f"stale list, {DEEPSEEK} e3-secondary-c: run e3-stale-c-{DEEPSEEK} is not finished",
    ),
    (LLAMA, "e3-samples", f"{LLAMA} e3-samples: run e3-samples-{LLAMA} is not finished"),
    (
        DEEPSEEK,
        "e4-2x2-shift",
        f"real names, shifted dates, {DEEPSEEK} e4-2x2: run e4-2x2-shift-{DEEPSEEK} is not finished",
    ),
    (
        LLAMA,
        "e3-para2",
        f"{PARAPHRASES[1]}, {LLAMA} e3-paraphrases: run e3-para2-{LLAMA} is not finished",
    ),
)


def test_a_run_that_is_not_complete_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    with TE.manifest_with(study, LLAMA, "e3-a", complete=False):
        why = refused(study, tmp_path, capsys)
    assert "no secondary score before every confirmatory run is complete" in why
    assert f"run e3-a-{LLAMA} is not finished (partial)" in why
    for model, part, said in INCOMPLETE:
        with TE.manifest_with(study, model, part, complete=False):
            why = refused(study, tmp_path, capsys)
        assert "no secondary score before every run it scores is complete" in why, part
        assert f"{said} (partial)" in why, part
    for model, part, said in INCOMPLETE[::3]:
        with TE.moved_away(TE.run_folder(study, model, part)):
            why = refused(study, tmp_path, capsys)
        assert f"{said} (none)" in why, part
    assert "the sealed file" not in sealed_unread and not [
        i for i in study.filled.index if i in why
    ]


def test_a_run_of_another_route_item_set_track_record_or_decoding_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    later = next(
        k
        for k, row in enumerate(TE.stored_rows(study, LLAMA, "e3-samples"))
        if row["sample"] == 5 and row["status"] == "ok"
    )
    rewrites: tuple[tuple[str, str, Callable[[dict], Any], str], ...] = (
        (NOISY, "e3-c", lambda row: None, "(1 items missing, 0 not on the list)"),
        (
            NOISY,
            "e3-a",
            lambda row: row | {"provider_pin": "elsewhere"},
            "1 rows with another model id or provider pin than the registered route",
        ),
        (
            DEEPSEEK,
            "e3-para1",
            lambda row: row | {"template_sha256": "0" * 64},
            "1 rows with another template or pin than the frozen one",
        ),
        (LLAMA, "e3-samples", lambda row: None, "(1 items missing, 0 not on the list)"),
        (
            LLAMA,
            "e3-samples",
            lambda row: row | {"temperature": 0.0},
            f"{LLAMA} e3-samples: 1 rows with another decoding than the registered one",
        ),
        (
            LLAMA,
            "e3-samples",
            lambda row: row | {"status": "failed"},
            f"{LLAMA} e3-samples: 1 rows that the evaluator's row checks refuse",
        ),
        (
            LLAMA,
            "e3-samples",
            lambda row: row | {"horizons": row["horizons"] | {"a": "2000-01-01"}},
            f"{LLAMA} e3-samples: rows of a later sample asked about other horizons",
        ),
        (
            DEEPSEEK,
            "e4-2x2-mask",
            lambda row: row | {"shift_years": 2},
            f"masked names, true dates, {DEEPSEEK} e4-2x2: 1 rows with another decoding",
        ),
        (
            LLAMA,
            "e3-tbd-a",
            lambda row: row | {"horizons": row["horizons"] | {"rule": "stated_end"}},
            f"tbd list, {LLAMA} e3-secondary-a: 1 rows asked about other horizons than the",
        ),
    )
    for model, part, change, said in rewrites:
        with TE.rewritten(study, model, part, at(later, change)):
            why = refused(study, tmp_path, capsys)
        assert "no secondary score before every run it scores is complete" in why, said
        assert said in why, said
    # a first sample without the decoding of the run: the evaluator's own count no longer fits
    with TE.rewritten(study, LLAMA, "e3-samples", at(0, lambda row: row | {"temperature": 0.0})):
        why = refused(study, tmp_path, capsys)
    assert "59 rows with masked names, shifted dates or a temperature above zero" in why
    assert "1 rows with another decoding than the registered one" in why
    with TE.manifest_with(study, NOISY, "e3-b", track_record_split="fit"):
        why = refused(study, tmp_path, capsys)
    assert f"run e3-b-{NOISY} showed another track record than the fit+dev one" in why
    plan = lp.plan_path(study.paths.runs)
    plans: tuple[tuple[Callable[[dict], Any], str], ...] = (
        (
            lambda r: r["lists"]["samples"].update(item_ids_sha256="0" * 64),
            "the plan's item list 'samples' is not the samples subset of the list",
        ),
        (
            lambda r: r["lists"]["stale"].update(item_ids_sha256="0" * 64),
            "the plan's item list 'stale' is not the registered stale list",
        ),
        (
            lambda r: r["routes"][NOISY].update(provider="elsewhere"),
            f"{NOISY} e3-a: the plan was made for another route than the registered one",
        ),
        (
            lambda r: r.update(runs=[x for x in r["runs"] if x["line"] != sc.PARAPHRASE_LINE]),
            f"{LLAMA} e3-paraphrases: the plan holds no run",
        ),
        (
            lambda r: r.update(runs=[x for x in r["runs"] if x["run"] != f"e3-c-{NOISY}"]),
            f"{NOISY} e3-c: the plan holds no run",
        ),
    )
    for change, said in plans:
        with TE.json_with(plan, change):
            why = refused(study, tmp_path, capsys)
        assert said in why, said
    with TE.json_with(
        study.paths.counts,
        lambda r: r["outputs"]["items"]["e3_tbd.jsonl"].update(sha256="0" * 16),
    ):
        why = refused(study, tmp_path, capsys)
    assert "the item file of list 'tbd' in the plan is not the one the counts file" in why
    assert "the sealed file" not in sealed_unread
    assert not [item for item in study.filled.index if item in why]


@contextmanager
def replanned(
    study: SimpleNamespace,
    name: str,
    kind: str | None = None,
    change: Callable[[dict, dict], Any] | None = None,
    **cells: Any,
) -> Iterator[None]:
    """The plan of the runs with other ``cells`` on the run ``name`` (and ``change(plan, run)``
    applied), and that run made again under the changed plan by the harness's own reader: a run
    that is complete and is what its plan says. Everything is put back afterwards."""
    path, local = lp.plan_path(study.paths.runs), study.root / "local"
    before = path.read_bytes()
    plan = json.loads(before)
    (run,) = [run for run in plan["runs"] if run["run"] == name]
    run.update(cells)
    if change is not None:
        change(plan, run)
    run["calls"] = plan["lists"][run["list"]]["items"] * run["samples"]
    with ExitStack() as stack:
        for folder in (study.paths.runs / name, local / name):
            if folder.exists():
                stack.enter_context(TE.moved_away(folder))
            stack.callback(shutil.rmtree, folder, ignore_errors=True)
        try:
            path.write_text(lp.plan_text(plan), encoding="utf-8")
            make_run(plan, run, study.known, local, kind)
            yield
        finally:
            path.write_bytes(before)


def test_a_run_is_held_to_the_registered_run_sheet_whatever_its_plan_says(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that is complete and is exactly what the plan of the runs says, under a plan that
    is not the registered run sheet: other samples, another temperature, another template,
    another item list. The plan is no witness for itself."""
    before = "refused: no secondary score before every run it scores is complete: "
    not_registered = (
        "the plan holds 1 runs that are not runs of the registered run sheet (item list, "
        "template, samples, temperature, masking or shift)"
    )
    samples, cell, para = f"e3-samples-{LLAMA}", f"e4-2x2-mask-{DEEPSEEK}", f"e3-para1-{LLAMA}"
    masked = CELL_NAMES["mask"]

    def other_list(plan: dict, run: dict) -> None:
        copy = tmp_path / "other_items.jsonl"
        shutil.copy(plan["lists"]["twobytwo"]["path"], copy)
        plan["lists"]["other"] = plan["lists"]["twobytwo"] | {"path": str(copy)}
        run.update(list="other", items=str(copy))

    cases: tuple[tuple[str, str, str, dict[str, Any], str], ...] = (
        # 20 samples at temperature 1 are registered
        (samples, "sampled_quantiles", "", {"samples": 1, "temperature": 0.0}, ""),
        (samples, "sampled_quantiles", "", {"samples": 3}, ""),
        (samples, "sampled_quantiles", "", {"temperature": 0.3}, ""),
        (
            samples,
            "sampled_quantiles",
            "",
            {"template": "predictive-track-v1", "track": "fit+dev"},
            "",
        ),
        # the cells of the 2x2 are read at temperature zero, under the prompt of condition (b)
        (cell, "name_date_2x2", f"{masked}, ", {"temperature": 0.7}, ""),
        (cell, "name_date_2x2", f"{masked}, ", {"template": "predictive-v1", "track": None}, ""),
        # a paraphrase run under the registered prompt is no paraphrase
        (para, "prompt_variance", "", {"template": "predictive-track-v1"}, "b"),
    )
    for name, section, where, cells, kind in cases:
        model, line = next(
            (run["model"], run["line"]) for run in study.plan["runs"] if run["run"] == name
        )
        with replanned(study, name, kind or None, **cells):
            why = refused(study, tmp_path, capsys, section=[section])
        if name == para:
            # the template of the harness has no run, and the line holds one that is not its own
            assert why == (
                f"{before}{model} {line}: {not_registered}; "
                f"{PARAPHRASES[0]}, {model} {line}: the plan holds no run"
            )
        else:
            assert why == f"{before}{where}{model} {line}: {not_registered}", cells
    # a cell of the 2x2 on another item file, under a list key of its own
    with replanned(study, cell, change=other_list):
        why = refused(study, tmp_path, capsys, section=["name_date_2x2"])
    assert why == f"{before}{masked}, {DEEPSEEK} {sc.CELLS_LINE}: {not_registered}"
    # one paraphrase run only
    plan = lp.plan_path(study.paths.runs)
    kept = f"e3-para2-{LLAMA}"

    def one_paraphrase(record: dict) -> None:
        record["runs"] = [
            run
            for run in record["runs"]
            if run["line"] != sc.PARAPHRASE_LINE or run["run"] == kept or run["model"] != LLAMA
        ]

    with TE.json_with(plan, one_paraphrase):
        why = refused(study, tmp_path, capsys, section=["prompt_variance"])
    for template in (PARAPHRASES[0], PARAPHRASES[2]):
        assert f"{template}, {LLAMA} {sc.PARAPHRASE_LINE}: the plan holds no run" in why
    assert PARAPHRASES[1] not in why
    assert "the sealed file" not in sealed_unread

    # the launcher's rule is itself held to the run sheet of the harness and to the plan of
    # the study: a rule that plans other samples, another temperature or another shift
    assert [sc.sheet_problems(line) for line in sc.DECODINGS] == [[], [], []]
    assert sc.sheet_problems("e3-a") == sc.sheet_problems("e3-secondary-b") == []
    part = lp.PARTS[sc.SAMPLES_LINE][0]
    wrong_decoding = "the launcher's runs do not have the registered decoding"
    wrong_calls = "the launcher's runs do not give the 20 calls per item of the run sheet"
    rules: tuple[tuple[str, tuple, list[str]], ...] = (
        (sc.SAMPLES_LINE, (replace(part, temperature=0.0),), [wrong_decoding]),
        (sc.SAMPLES_LINE, (replace(part, samples=10),), [wrong_calls, wrong_decoding]),
        (sc.SAMPLES_LINE, (replace(part, mask_names=True),), [wrong_decoding]),
        (
            sc.CELLS_LINE,
            tuple(replace(p, shift_years=p.shift_years // 2) for p in lp.PARTS[sc.CELLS_LINE]),
            [wrong_decoding],
        ),
        (sc.CELLS_LINE, lp.PARTS[sc.CELLS_LINE][:2], ["do not give the 3 calls", wrong_decoding]),
        ("e3-b", (replace(lp.PARTS["e3-b"][0], temperature=0.5),), [wrong_decoding]),
        ("e3-secondary-a", lp.PARTS["e3-secondary-a"][:2], ["do not give the 1 calls per item"]),
    )
    for line, parts, said in rules:
        with monkeypatch.context() as patch:
            patch.setitem(lp.PARTS, line, parts)
            found = sc.sheet_problems(line)
            assert len(found) == len(said) and all(
                problem.startswith(f"{line}: ") and text in problem
                for problem, text in zip(found, said, strict=True)
            ), line
            if line == sc.SAMPLES_LINE:
                why = refused(study, tmp_path, capsys, section=["sampled_quantiles"])
                assert before in why and all(text in why for text in said)
    with monkeypatch.context() as patch:
        patch.setattr(lp, "paraphrase_templates", lambda: list(PARAPHRASES[:2]))
        (found,) = sc.sheet_problems(sc.PARAPHRASE_LINE)
        assert found.startswith(f"{sc.PARAPHRASE_LINE}: read.TEMPLATES holds 2 paraphrase")
        why = refused(study, tmp_path, capsys, section=["prompt_variance"])
        assert found in why
    assert "the sealed file" not in sealed_unread
    # the values the plan of the study fixes stand here, whatever the launcher says
    assert (sc.SAMPLES, sc.SAMPLES_TEMPERATURE, sc.PARAPHRASES, sc.SHIFT_YEARS) == (20, 1.0, 3, 4)


def test_readings_that_cannot_be_turned_into_predictions_name_no_item(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a stored reading that the harness's parser does not accept is refused with the runs, as a
    # count, before any prediction is made
    broken = at(0, lambda row: row | {"reading": {"p_by_horizon_a": 0.5}})
    item = TE.stored_rows(study, NOISY, "e3-a")[0]["item_id"]
    with TE.rewritten(study, NOISY, "e3-a", broken):
        why = refused(study, tmp_path, capsys)
    assert why == (
        "refused: no secondary score before every run it scores is complete: "
        f"{NOISY} e3-a: {TE.NOT_ACCEPTED}"
    )
    assert item not in why and "the sealed file" not in sealed_unread
    # a stored file that is not as the harness writes it stops the check, by its type alone
    readings = TE.run_folder(study, LLAMA, "e3-tbd-b") / "readings.jsonl"
    with TE.changed(readings):
        readings.write_text(readings.read_text() + "{half a row\n")
        why = refused(study, tmp_path, capsys)
    assert "the completeness check stopped on the plan or the stored runs (JSONDecodeError)" in why

    # a stop while the readings are turned into predictions: the type of the error and nothing
    # of its message, which here names an item
    def stops(*args: Any, **kwargs: Any) -> None:
        raise KeyError(item)

    with monkeypatch.context() as patch:
        patch.setattr(ev, "model_predictions", stops)
        why = refused(study, tmp_path, capsys)
    assert why == "refused: the readings could not be turned into predictions (KeyError)"
    assert item not in why and "the sealed file" not in sealed_unread
    # a statement left without a prediction, on the eligible list and on a secondary list: the
    # evaluator's own check finds the gap, and nothing is scored
    real = ev.predictive

    def with_a_gap(rows: Any, first: Any, base: Any) -> Any:
        frame, parsed, counts = real(rows, first, base)
        frame = frame.copy()
        frame.iloc[0, 0] = float("nan")
        return frame, parsed, counts

    with monkeypatch.context() as patch:
        patch.setattr(ev, "predictive", with_a_gap)
        why = refused(study, tmp_path, capsys)
    gap = "a statement is left without a prediction"
    assert why.startswith("refused: the readings cannot be scored: ")
    assert f"{NOISY} e3-a: {gap}" in why and f"{LLAMA} e3-b: {gap}" in why
    assert f"{LLAMA} tbd list, e3-secondary-a: {gap}" in why
    assert item not in why and "the sealed file" not in sealed_unread


def test_an_output_or_an_input_in_the_wrong_place_and_a_malformed_option_are_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    def stops(match: str, *extra: str, **replace: Any) -> None:
        with pytest.raises(SystemExit, match=match) as stop:
            sc.main(["score", *options(study, **replace), *extra])
        assert str(stop.value.code).startswith("refused: ")

    stops("--out is required")
    there = tmp_path / "there.json"
    there.write_text("{}")
    stops("already there, and nothing is overwritten", "--out", str(there))
    assert there.read_text() == "{}"
    stops("folder of the output does not exist", "--out", str(tmp_path / "none" / "r.json"))
    vault = tmp_path / "sealed"
    vault.mkdir()
    stops("--out lies in a sealed folder", "--out", str(vault / "r.json"))
    out = ["--out", str(tmp_path / "r.json")]
    for name in ("statements", "eligible", "events", "counts", "confirmatory"):
        copy = vault / getattr(study.paths, name).name
        copy.write_bytes(getattr(study.paths, name).read_bytes())
        stops(f"--{name} would be read from a sealed folder", *out, **{name: copy})
    stops("--statements would be read from a sealed folder", *out, statements=study.paths.sealed)
    stops("--section takes a name of", *out, section=["everything"])
    stops("--left-out takes MODEL=REASON with a secondary model", *out, left_out=[f"{LLAMA}=x"])
    stops("--left-out takes MODEL=REASON with a secondary model", *out, left_out=[f"{NOISY}="])
    # a reason that is not printable text on one line could not be written into the result
    for reason in ("two\nlines", "a tab\there", "a byte that was no text \udce9"):
        stops("--left-out takes a REASON of printable text", *out, left_out=[f"{NOISY}={reason}"])
        stops(
            "--not-evaluable takes a REASON of printable text",
            *out,
            not_evaluable=[f"{DEEPSEEK}={reason}"],
        )
    assert sealed_unread == []
    # the draws of a Turnbull interval are no choice of the one who runs the command
    stops("unrecognized arguments: --slip-draws", *out, slip_draws=1000)
    stops("unrecognized arguments", *out, "--draws", "5")
    with pytest.raises(SystemExit, match="refused: "):
        sc.main(["confirmatory"])
    # a statement table that the counts file does not record
    other = tmp_path / "statements.csv.gz"
    other.write_bytes(study.paths.statements.read_bytes() + b" ")
    stops("not the files the counts file of the dataset builder records", *out, statements=other)
    assert not (tmp_path / "r.json").exists() and "the sealed file" not in sealed_unread
    assert capsys.readouterr().out == ""


def test_a_stop_anywhere_else_is_a_refusal_that_gives_the_type_alone(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "S0001 recovered on 2024-05-01"

    def stop(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(secret)

    monkeypatch.setattr(ev, "open_tables", stop)
    why = refused(study, tmp_path, capsys)
    assert why.startswith("refused: the command stopped (RuntimeError); the message is withheld")
    assert secret not in why and "the sealed file" not in sealed_unread
    monkeypatch.setattr(ev, "same_build", stop)
    with pytest.raises(SystemExit) as halt:
        sc.main(
            [
                "train-descriptives",
                "--out",
                str(tmp_path / "t.json"),
                "--statements",
                str(study.paths.statements),
                *counts_of(study),
            ]
        )
    assert str(halt.value.code).startswith("refused: the command stopped (RuntimeError)")
    assert halt.value.__context__ is None and not (tmp_path / "t.json").exists()


def test_a_result_that_cannot_be_written_leaves_nothing_behind(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record and the printout are made, and encoded, before a file exists: a text that
    cannot be encoded, or a stop while the printout is made, is a refusal with nothing at
    ``--out`` (``refused`` holds the folder to be empty)."""
    stopped = "refused: the scoring stopped on the sealed rows ({}); the message is withheld"
    real = ev.report_text

    def unencodable(report: Any) -> str:
        """The text of a result file with a character that no file can hold (a byte that was
        no text reaches a program as one); any other record as it is."""
        text = real(report)
        return text + "\udce9" if report.get("about") in (sc.ABOUT, sc.ABOUT_TRAIN) else text

    with monkeypatch.context() as patch:
        patch.setattr(ev, "report_text", unencodable)
        why = refused(study, tmp_path, capsys, section=["descriptives"])
    assert why.startswith(stopped.format("UnicodeEncodeError"))

    def stop(report: Any) -> list[str]:
        raise RuntimeError("S0001 recovered on 2024-05-01")

    with monkeypatch.context() as patch:
        patch.setattr(sc, "summary_lines", stop)
        why = refused(study, tmp_path, capsys, section=["descriptives"])
    assert why.startswith(stopped.format("RuntimeError")) and "S0001" not in why
    # the train command writes its text the same way
    args = ["--statements", str(study.paths.statements), *counts_of(study)]
    out = tmp_path / "train.json"
    with monkeypatch.context() as patch:
        patch.setattr(ev, "report_text", unencodable)
        with pytest.raises(SystemExit) as halt:
            sc.main(["train-descriptives", "--out", str(out), *args])
    assert str(halt.value.code).startswith("refused: the command stopped (UnicodeEncodeError)")
    assert not out.exists() and capsys.readouterr().out == ""


def test_a_result_is_written_whole_or_not_at_all(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disk that fills in the middle of the write leaves no part of a result file behind,
    and a file that took the name while the scores were computed is not overwritten."""
    real_open = Path.open
    partly: list[str] = []

    class Full:
        """A file on a disk that holds a hundred characters more."""

        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> Full:
            self.handle.__enter__()
            return self

        def __exit__(self, *args: Any) -> Any:
            return self.handle.__exit__(*args)

        def write(self, text: str) -> None:
            self.handle.write(text[:100])
            self.handle.flush()
            partly.append(self.handle.name)
            raise OSError(28, "No space left on device")

    def open_full(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        handle = real_open(self, mode, *args, **kwargs)
        return Full(handle) if "x" in mode and self.parent.name == "refused" else handle

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_full)
        why = refused(study, tmp_path, capsys, section=["descriptives"])  # the folder is empty
    assert why.startswith("refused: the output cannot be written (OSError): ")
    assert len(partly) == 1 and not Path(partly[0]).exists()
    # the train command writes in the same way
    train = ["--statements", str(study.paths.statements), *counts_of(study)]
    out = tmp_path / "refused" / "train.json"
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_full)
        with pytest.raises(SystemExit) as halt:
            sc.main(["train-descriptives", "--out", str(out), *train])
    assert str(halt.value.code).startswith("refused: the output cannot be written (OSError): ")
    assert list(out.parent.iterdir()) == [] and len(partly) == 2
    # a file of someone else under the name, written while the scores were computed
    taken = tmp_path / "taken" / "result.json"
    taken.parent.mkdir()
    real_lines = sc.summary_lines

    def meanwhile(report: Any) -> list[str]:
        taken.write_text("the file of someone else")
        return real_lines(report)

    capsys.readouterr()
    with monkeypatch.context() as patch:
        patch.setattr(sc, "summary_lines", meanwhile)
        with pytest.raises(SystemExit) as halt:
            sc.main(["score", "--out", str(taken), *options(study, section=["descriptives"])])
    assert str(halt.value.code) == (
        f"refused: the output cannot be written (FileExistsError): {taken.as_posix()}"
    )
    assert taken.read_text() == "the file of someone else"
    assert list(taken.parent.iterdir()) == [taken] and capsys.readouterr().out == ""


def test_a_printout_that_cannot_be_made_says_that_the_file_is_written(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader of the printout can be gone when the summary is printed (a closed pipe). The
    result file is written by then: the command says so, and does not call it a refusal."""
    real_print = builtins.print

    def closed(*args: Any, **kwargs: Any) -> None:
        if "file" in kwargs:
            return real_print(*args, **kwargs)
        raise BrokenPipeError(32, "Broken pipe")

    train = ["--statements", str(study.paths.statements), *counts_of(study)]
    commands = (
        ["score", *options(study, section=["descriptives"])],
        ["train-descriptives", *train],
    )
    for number, command in enumerate(commands):
        out = tmp_path / f"piped_{number}.json"
        with monkeypatch.context() as patch:
            patch.setattr(builtins, "print", closed)
            with pytest.raises(SystemExit) as halt:
                sc.main([command[0], "--out", str(out), *command[1:]])
        said = str(halt.value.code)
        assert said == (
            f"wrote {out.as_posix()}: the result file is written and whole; its summary could "
            "not be printed (BrokenPipeError)"
        )
        assert "refused" not in said and halt.value.__context__ is None
        assert "descriptives" in json.loads(out.read_text())
        assert sorted(path.name for path in tmp_path.glob("*piped_*")) == [
            f"piped_{k}.json" for k in range(number + 1)
        ]


def watched_sealed(
    study: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, list[str]]:
    """``test_evaluate.watched_vault`` (a copy of the synthetic sealed file in a folder of its
    own, made the default sealed path, and every look the file system is asked for at that
    folder), with the built-in ``open`` watched as well: a read through it, gzip or pandas is
    seen too, wherever in the command it happens."""
    sealed, touched = TE.watched_vault(study, tmp_path, monkeypatch)
    real = builtins.open

    def watched(path: Any, *args: Any, **kwargs: Any) -> Any:
        if "vault" in str(path):
            touched.append(f"builtins.open {path}")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched)
    return sealed, touched


def test_a_plan_that_names_a_sealed_file_is_not_followed(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sealed, touched = watched_sealed(study, tmp_path, monkeypatch)
    plan = lp.plan_path(study.paths.runs)
    said = "the plan of the runs names a path in a sealed folder; none of its files is read"
    for key in ("tbd", "samples", "twobytwo"):
        with TE.json_with(plan, lambda r, key=key: r["lists"][key].update(path=str(sealed))):
            why = refused(study, tmp_path, capsys, sealed=None)
        assert said in why and touched == []

    # wherever the plan names it: the launcher writes an item path on every run as well
    def on_a_run(record: dict) -> None:
        record["runs"][-1]["items"] = str(sealed)

    def in_a_field_of_its_own(record: dict) -> None:
        record["options"]["notes"] = [{"see": str(sealed.parent / "." / sealed.name)}]

    def in_a_sealed_folder(record: dict) -> None:
        record["runs"][0]["items"] = str(tmp_path / "sealed" / "items.jsonl")

    def through_a_link(record: dict) -> None:
        record["runs"][0]["items"] = str(tmp_path / "a_link.jsonl")

    os.symlink(sealed, tmp_path / "a_link.jsonl")
    read: list[str] = []
    real = S.file_bytes
    monkeypatch.setattr(S, "file_bytes", lambda path, what: read.append(what) or real(path, what))
    for change in (on_a_run, in_a_field_of_its_own, in_a_sealed_folder, through_a_link):
        with TE.json_with(plan, change):
            why = refused(study, tmp_path, capsys, sealed=None)
        assert why == f"refused: {said}" and touched == [], change.__name__
    assert read == []  # refused before any input of the command line is opened


@contextmanager
def linked(path: Path, target: Path) -> Iterator[None]:
    """``path`` as a symbolic link to ``target``; what it was is put back afterwards."""
    aside = path.with_name(path.name + ".aside")
    path.rename(aside)
    os.symlink(target, path)
    try:
        yield
    finally:
        path.unlink()
        aside.rename(path)


def test_nothing_is_read_through_a_link_to_the_sealed_file(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored file that is a symbolic link to the sealed file would be read, and hashed, as
    an open one. Every path the command is about to read is followed link by link first, and
    one that leads to the sealed file is refused before anything is opened: nothing in the
    folder of the sealed file is looked at, and no hash is printed."""
    sealed, touched = watched_sealed(study, tmp_path, monkeypatch)
    read: list[str] = []
    real = S.file_bytes
    monkeypatch.setattr(S, "file_bytes", lambda path, what: read.append(what) or real(path, what))
    leads = "leads into a sealed folder; only --sealed names a sealed file"
    selection = study.paths.selections / ev.SELECTION_NAME.format(model=DEEPSEEK)
    other = tmp_path / "selections"
    other.mkdir()
    for model in ev.PRIMARIES:
        mine = study.paths.selections / ev.SELECTION_NAME.format(model=model)
        os.symlink(sealed if model == LLAMA else mine, other / mine.name)
    hop = tmp_path / "hop"
    os.symlink(sealed, tmp_path / "last_hop")
    os.symlink(tmp_path / "last_hop", hop)
    cases: tuple[tuple[str, Path, Path, dict[str, Any]], ...] = (
        ("readings", TE.run_folder(study, LLAMA, "e3-a") / "readings.jsonl", sealed, {}),
        ("manifest", TE.run_folder(study, NOISY, "e3-a") / "run_manifest.json", sealed, {}),
        ("plan", lp.plan_path(study.paths.runs), sealed, {}),
        ("selection", selection, sealed, {}),
        ("two links", TE.run_folder(study, DEEPSEEK, "e4-probe") / "readings.jsonl", hop, {}),
        # a model that is declared left out: its runs are read by the completeness check
        (
            "left out",
            TE.run_folder(study, NOISY, "e3-b") / "readings.jsonl",
            sealed,
            {"left_out": [f"{NOISY}=stopped"], "section": ["selective_prediction"]},
        ),
        # the whole folder of a run, as a link to the folder of the sealed file
        ("folder", TE.run_folder(study, INFORMED, "e3-c"), sealed.parent, {}),
        # the sealed file of the study itself, in a folder named as the registered one
        ("by name", TE.run_folder(study, LLAMA, "e3-b") / "readings.jsonl", study.paths.sealed, {}),
    )
    for name, path, target, more in cases:
        with linked(path, target):
            why = refused(study, tmp_path, capsys, sealed=None, **more)
        assert leads in why and touched == [] and read == [], name
        assert not re.search(r"[0-9a-f]{16}", why), name
    why = refused(study, tmp_path, capsys, sealed=None, selections=other)
    assert f"the selection file of {LLAMA} {leads}" in why and touched == [] and read == []
    # an input of the command line, and the name of the output: refused in the words that
    # refuse a path in a sealed folder, and here too without a look at the sealed file
    for name in ("statements", "events", "confirmatory"):
        link = tmp_path / f"{name}_link"
        os.symlink(sealed, link)
        why = refused(study, tmp_path, capsys, sealed=None, **{name: link})
        assert f"--{name} would be read from a sealed folder" in why and touched == [], name
    os.symlink(tmp_path / "sealed", tmp_path / "out_link")  # a folder named as the sealed one
    with pytest.raises(SystemExit, match="refused: --out lies in a sealed folder"):
        sc.main(
            ["score", "--out", str(tmp_path / "out_link" / "r.json"), *options(study, sealed=None)]
        )
    train = ["--statements", str(tmp_path / "statements_link"), *counts_of(study)]
    with pytest.raises(SystemExit, match="--statements would be read from a sealed folder"):
        sc.main(["train-descriptives", "--out", str(tmp_path / "t.json"), *train])
    with pytest.raises(SystemExit, match="refused: --out lies in a sealed folder"):
        sc.main(
            [
                "train-descriptives",
                "--out",
                str(tmp_path / "out_link" / "t.json"),
                "--statements",
                str(study.paths.statements),
                *counts_of(study),
            ]
        )
    assert touched == [] and read == []
    # and the function itself: as text first, then link by link, a circle of links included
    os.symlink(tmp_path / "round_b", tmp_path / "round_a")
    os.symlink(tmp_path / "round_a", tmp_path / "round_b")
    plain = tmp_path / "plain.json"
    plain.write_text("{}")
    os.symlink(plain, tmp_path / "to_plain")
    os.symlink("vault/../vault/outcomes_test.csv.gz", tmp_path / "relative")
    wanted = {
        sealed: True,
        sealed.parent: True,
        tmp_path / "vault" / ".." / "vault" / sealed.name: True,
        hop: True,
        tmp_path / "relative": True,
        tmp_path / "round_a": True,
        tmp_path / "sealed" / "x.csv": True,  # a folder named as the registered one
        plain: False,
        tmp_path / "to_plain": False,
        tmp_path / "not_there" / "x.json": False,
        tmp_path / "elsewhere" / sealed.name: False,
        "a name with\x00 no path": False,
    }
    for path, answer in wanted.items():
        assert sc.leads_to_sealed(path, sealed) is answer, path
    assert touched == []
    # another file in the folder of the sealed file is sealed by the name of the folder alone
    assert sc.leads_to_sealed(sealed.parent / "another_file", sealed) is False
    assert sc.leads_to_sealed(tmp_path / "sealed" / "another_file", sealed) is True
    assert list(sealed.parent.iterdir()) == [sealed]  # and nothing was written beside it


def test_a_sealed_file_of_another_build_and_a_stop_inside_the_rules(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    recwarn: pytest.WarningsRecorder,
) -> None:
    other = tmp_path / "sealed" / "outcomes_test.csv.gz"
    other.parent.mkdir()
    C.write_gz(study.sealed_rows.iloc[:-1], other)
    sha = TE.file_sha(other)
    # even with a result file that records this other file, the checked reader refuses it
    with TE.json_with(
        study.paths.confirmatory, lambda r: r["inputs"].update(sealed_outcomes_sha256=sha)
    ):
        why = refused(study, tmp_path, capsys, sealed=other, expect_sha256=sha)
    assert "the sealed file and the events table are not from the same build" in why
    secret, real = "recovered on 2024-05-01", D.attach_outcomes

    def stop(*args: Any, **kwargs: Any) -> None:
        raise ValueError(f"E0001: {secret}")

    monkeypatch.setattr(D, "attach_outcomes", stop)
    why = refused(study, tmp_path, capsys, section=["descriptives"])
    assert why == (
        "refused: the scoring stopped on the sealed rows (ValueError); the message is withheld "
        "because it may quote a sealed value"
    )

    def warn(*args: Any, **kwargs: Any) -> None:
        TE.warnings.warn(f"odd cell: {secret}", stacklevel=1)
        raise KeyError(secret)

    monkeypatch.setattr(D, "attach_outcomes", real)
    monkeypatch.setattr(sc, "descriptives", warn)
    why = refused(study, tmp_path, capsys, section=["descriptives"])
    assert "(KeyError)" in why and secret not in why
    assert not [w for w in recwarn if secret in str(w.message)]


# --------------------------------------------------------------------------------------------
# The order of the reads, the choice of sections, runs in parts, and what the output holds
# --------------------------------------------------------------------------------------------

CHEAP = ["secondary_lists", "descriptives", "selective_prediction"]
"""Sections that need no interval of the registered test: quick to compute."""


def test_the_sealed_file_is_read_last_behind_everything_else(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    real_bytes = S.file_bytes

    def file_bytes(path: Path, what: str) -> bytes:
        order.append(what)
        return real_bytes(path, what)

    def logged(name: str, call: Callable[..., Any]) -> Callable[..., Any]:
        def inner(*args: Any, **kwargs: Any) -> Any:
            order.append(name)
            return call(*args, **kwargs)

        return inner

    monkeypatch.setattr(S, "file_bytes", file_bytes)
    monkeypatch.setattr(ev, "gather", logged("confirmatory runs", ev.gather))
    monkeypatch.setattr(sc, "gather_more", logged("secondary runs", sc.gather_more))
    monkeypatch.setattr(sc, "prepare", logged("predictions", sc.prepare))
    monkeypatch.setattr(ev, "unseal", logged("unseal", ev.unseal))
    monkeypatch.setattr(sc, "unseal_population", logged("population", sc.unseal_population))
    scored(study, tmp_path, capsys, section=CHEAP)
    opened_at = order.index("the sealed file")
    assert order[:opened_at] == [
        "the eligible list",
        "the statement table",
        "the events table",
        "the counts file",
        "the result file of the evaluator",
        "confirmatory runs",
        "secondary runs",
        "predictions",
    ]
    assert order[opened_at + 1 : opened_at + 3] == ["unseal", "population"]
    assert order.count("the sealed file") == 1


def test_nothing_looks_at_the_sealed_path_before_every_run_is_complete(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused ``score`` command and the train-period command do not read the sealed file,
    and do not ask the file system whether it is there."""
    sealed, touched = watched_sealed(study, tmp_path, monkeypatch)
    assert sc.arguments(["score"]).sealed == sealed
    with TE.manifest_with(study, DEEPSEEK, "e3-silent-b", complete=False):
        why = refused(study, tmp_path, capsys, sealed=None)
    assert "is not finished (partial)" in why and touched == []
    with TE.manifest_with(study, DEEPSEEK, "e4-probe", complete=False):
        why = refused(study, tmp_path, capsys, sealed=None)
    assert "before every confirmatory run is complete" in why and touched == []
    with TE.changed(study.paths.confirmatory):
        study.paths.confirmatory.unlink()
        why = refused(study, tmp_path, capsys, sealed=None)
    assert "no secondary score before the six tests" in why and touched == []
    train = ["train-descriptives", "--out", str(tmp_path / "train.json")]
    assert sc.main([*train, "--statements", str(study.paths.statements), *counts_of(study)]) == 0
    assert touched == [] and not hasattr(sc.arguments(train), "sealed")
    # the same watch sees the sealed file when a complete study is scored
    report, _ = scored(study, tmp_path, capsys, sealed=None, section=["descriptives"])
    assert touched and report["inputs"]["sealed_outcomes_sha256"] == study.sealed_sha


def test_nothing_looks_at_the_sealed_path_before_the_predictions_are_those_of_the_freeze(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three refusals that come after the completeness checks, and the checks of the
    result file against the runs, leave the sealed path alone: no read of the file, by
    whatever call, and no question to the file system."""
    _, touched = watched_sealed(study, tmp_path, monkeypatch)
    # the refit is not the one hashed at the freeze
    with monkeypatch.context() as patch:
        patch.setattr(ev, "baseline_hash", lambda *a: "f" * 64)
        why = refused(study, tmp_path, capsys, sealed=None)
    assert "the model-free predictions are not those hashed at the freeze" in why
    assert touched == [], touched[:3]

    # a stop while the readings are turned into predictions
    def stop(*args: Any, **kwargs: Any) -> None:
        raise KeyError("S0001")

    with monkeypatch.context() as patch:
        patch.setattr(ev, "model_predictions", stop)
        why = refused(study, tmp_path, capsys, sealed=None)
    assert why == "refused: the readings could not be turned into predictions (KeyError)"
    assert touched == [], touched[:3]
    # a statement left without a prediction
    real = ev.model_predictions

    def lacking(*args: Any, **kwargs: Any) -> Any:
        made, parsed, counts, problems = real(*args, **kwargs)
        return made, parsed, counts, [*problems, "e3-a: a statement is left without a prediction"]

    with monkeypatch.context() as patch:
        patch.setattr(ev, "model_predictions", lacking)
        why = refused(study, tmp_path, capsys, sealed=None, section=["descriptives"])
    assert why.startswith("refused: the readings cannot be scored: ")
    assert f"{LLAMA} e3-a: a statement is left without a prediction" in why
    assert touched == [], touched[:3]
    # a result file that does not stand behind the runs, a declaration it alone makes, a
    # secondary model left out with complete runs, a run that is not of the run sheet
    with TE.rewritten(study, LLAMA, "e3-b", at(0, lambda row: row | {"read_again": True})):
        why = refused(study, tmp_path, capsys, sealed=None)
    assert "the stored readings are not those the six tests were computed on" in why
    declare = dict.fromkeys(ev.PRIMARIES, sc.DECLARATION + "withdrawn")
    with TE.json_with(
        study.paths.confirmatory, lambda r: r.update(not_evaluable_by_declaration=declare)
    ):
        why = refused(study, tmp_path, capsys, sealed=None, section=["descriptives"])
    assert "it declares every primary not evaluable" in why
    why = refused(study, tmp_path, capsys, sealed=None, left_out=[f"{NOISY}=dropped"])
    assert "whose runs pass the completeness check" in why
    why = refused(study, tmp_path, capsys, sealed=None, expect_selection_sha256=None)
    assert "--expect-selection-sha256 is required" in why
    assert touched == [], touched[:3]
    # the same watch sees the sealed file when a complete study is scored, by the reader of
    # the checked bytes and by nothing else
    report, _ = scored(study, tmp_path, capsys, sealed=None, section=["descriptives"])
    assert touched and report["inputs"]["sealed_outcomes_sha256"] == study.sealed_sha
    assert not [look for look in touched if look.startswith("builtins.open")]


SECTION_OF_SUBSET = {
    "samples": "sampled_quantiles",
    "twobytwo": "name_date_2x2",
    "paraphrase": "prompt_variance",
}


@pytest.mark.parametrize("key", list(SECTION_OF_SUBSET))
def test_the_item_file_of_a_subset_is_held_to_the_counts_file(
    key: str,
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    name = f"{lp.LIST_BY_KEY[key].stem}.jsonl"
    assert name in {"subset_samples20.jsonl", "subset_twobytwo.jsonl", "subset_paraphrase.jsonl"}
    with TE.json_with(
        study.paths.counts, lambda r: r["outputs"]["items"][name].update(sha256="0" * 16)
    ):
        why = refused(study, tmp_path, capsys, section=[SECTION_OF_SUBSET[key]])
    assert f"the item file of list {key!r} in the plan is not the one the counts file" in why
    assert "the sealed file" not in sealed_unread


@pytest.mark.parametrize("column", ["event_date", "statement_group_id"])
def test_the_wider_population_is_held_to_the_outcome_rows_of_its_display_rows(
    column: str, study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A synthetic sealed file in which the display row of one TBD statement, which is not on
    the eligible list, has another date or another statement: the checked reader holds the
    population of the descriptives and the lists to its outcome rows too."""
    rows = study.sealed_rows.copy()
    tbd = study.population[study.population["analysis_set"] == "tbd"]
    assert not set(tbd["statement_group_id"]) & set(study.listed["statement_group_id"])
    size = rows.groupby("statement_group_id")["event_id"].size()
    alone = [
        event
        for event, group in zip(tbd["event_id"], tbd["statement_group_id"], strict=True)
        if size.get(group, 0) == 1
    ]
    here = rows["event_id"] == alone[0]
    assert here.sum() == 1
    if column == "statement_group_id":
        rows.loc[here, column] = "another-statement"
    else:
        was = rows.loc[here, column].iloc[0]
        rows.loc[here, column] = next(d for d in sorted(set(tbd["event_date"])) if d != was)
    other = tmp_path / "sealed" / "outcomes_test.csv.gz"
    other.parent.mkdir()
    C.write_gz(rows, other)
    sha = TE.file_sha(other)
    with TE.json_with(
        study.paths.confirmatory, lambda r: r["inputs"].update(sealed_outcomes_sha256=sha)
    ):
        why = refused(
            study, tmp_path, capsys, sealed=other, expect_sha256=sha, section=["descriptives"]
        )
    assert "have no outcome row of their display row" in why


def counts_of(study: SimpleNamespace) -> list[str]:
    return ["--counts", str(study.paths.counts)]


def test_sections_can_be_chosen_and_a_secondary_model_left_out(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    # a section that is not asked for is not held up by its runs, and is not computed
    with TE.manifest_with(study, LLAMA, "e4-2x2-mask", complete=False):
        report, printed = scored(study, tmp_path, capsys, section=CHEAP[::-1])
        why = refused(study, tmp_path, capsys, section=["name_date_2x2"])
    assert report["sections"] == CHEAP and "is not finished (partial)" in why
    assert not set(sc.SECTIONS) - set(CHEAP) & set(report)
    for name in CHEAP:
        assert report[name] == base.report[name], name
    assert report["items"] == base.report["items"] and "wrote" in printed
    # a secondary model whose runs cannot be completed is declared, and the rest is scored
    reason = f"{NOISY}=its route was withdrawn"
    with TE.manifest_with(study, NOISY, "e3-b", complete=False):
        why = refused(study, tmp_path, capsys, section=["selective_prediction"])
        report, _ = scored(
            study, tmp_path, capsys, section=["selective_prediction"], left_out=[reason]
        )
    assert f"run e3-b-{NOISY} is not finished (partial)" in why
    assert report["secondary_models_left_out"] == {
        NOISY: "declared on the command line: its route was withdrawn"
    }
    assert NOISY not in report["secondary_models_scored"]
    assert f"{NOISY}:c" not in report["selective_prediction"]
    kept = {
        key: value for key, value in base.report["selective_prediction"].items() if NOISY not in key
    }
    assert report["selective_prediction"] == kept
    # what the completeness check found of the model left out stands in the result file
    assert report["secondary_models_left_out_check"] == {
        NOISY: [
            f"{NOISY} e3-b: run e3-b-{NOISY} is not finished (partial)",
            f"{NOISY} e3-b: 1 runs are not complete",
        ]
    }
    assert base.report["secondary_models_left_out_check"] == {}


def test_a_secondary_model_whose_runs_are_complete_is_not_left_out(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--left-out`` is a declaration that the runs of a model could not be completed: the
    completeness check is run on them all the same, and a model it finds nothing wrong with is
    scored."""
    reason = f"{NOISY}=its route was withdrawn"

    def complete(*models: str) -> str:
        return (
            "refused: --left-out names a secondary model whose runs pass the completeness check "
            f"({', '.join(models)}): a model is left out only when its runs are not complete "
            "(PLAN sections 9 and 12)"
        )

    for section in (["descriptives"], ["selective_prediction"], ["secondary_models"], []):
        assert refused(study, tmp_path, capsys, section=section, left_out=[reason]) == complete(
            NOISY
        )
    everyone = [f"{model}=dropped" for model in sc.SECONDARY_MODELS]
    assert refused(study, tmp_path, capsys, left_out=everyone) == complete(*sc.SECONDARY_MODELS)
    # beside a model whose runs are really not complete
    both = [reason, "grok-4.20=its route was withdrawn"]
    with TE.manifest_with(study, "grok-4.20", "e3-a", complete=False):
        assert refused(study, tmp_path, capsys, left_out=both) == complete(NOISY)
    # its probe alone is not finished: only the section of the secondary models reads the probe
    with TE.manifest_with(study, NOISY, "e4-probe", complete=False):
        why = refused(study, tmp_path, capsys, section=["selective_prediction"], left_out=[reason])
        assert why == complete(NOISY)
    assert "the sealed file" not in sealed_unread
    # a model that is not left out is held to its runs as before
    with TE.manifest_with(study, NOISY, "e4-probe", complete=False):
        why = refused(study, tmp_path, capsys, section=["secondary_models"])
    assert f"run e4-probe-{NOISY} is not finished (partial)" in why
    assert "the sealed file" not in sealed_unread


def test_a_secondary_model_left_out_has_what_the_check_found_in_the_result_file(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    reason = f"{NOISY}=its route was withdrawn"
    section = ["secondary_models"]
    # the probe not finished, where the probe is read
    with TE.manifest_with(study, NOISY, "e4-probe", complete=False):
        report, _ = scored(study, tmp_path, capsys, section=section, left_out=[reason])
    assert report["secondary_models_left_out_check"] == {
        NOISY: [
            f"{NOISY} e4-probe: run e4-probe-{NOISY} is not finished (partial)",
            f"{NOISY} e4-probe: 1 runs are not complete",
        ]
    }
    assert list(report["secondary_models"]["models"]) == [
        model for model in sc.SECONDARY_MODELS if model != NOISY
    ]
    for model, entry in report["secondary_models"]["models"].items():
        assert entry == base.report["secondary_models"]["models"][model], model
    # a readings file cut inside a line: the check stops on it, and that is what it found
    readings = TE.run_folder(study, NOISY, "e3-c") / "readings.jsonl"
    item = TE.stored_rows(study, NOISY, "e3-c")[-1]["item_id"]
    with TE.changed(readings):
        readings.write_text(readings.read_text()[:-40])
        report, _ = scored(
            study, tmp_path, capsys, section=["selective_prediction"], left_out=[reason]
        )
    (found,) = report["secondary_models_left_out_check"][NOISY]
    assert found == f"{NOISY} e3-c: the check stopped on the stored run (JSONDecodeError)"
    assert item not in json.dumps(report["secondary_models_left_out_check"])
    # the run folder gone, and the run missing from the plan
    with TE.moved_away(TE.run_folder(study, NOISY, "e3-a")):
        report, _ = scored(study, tmp_path, capsys, section=["descriptives"], left_out=[reason])
    found = report["secondary_models_left_out_check"][NOISY]
    assert found[0] == f"{NOISY} e3-a: run e3-a-{NOISY} is not finished (none)"
    assert all(problem.startswith(f"{NOISY} e3-a: ") for problem in found)

    def unplanned(record: dict) -> None:
        record["runs"] = [run for run in record["runs"] if run["model"] != NOISY]

    with TE.json_with(lp.plan_path(study.paths.runs), unplanned):
        report, _ = scored(study, tmp_path, capsys, section=["descriptives"], left_out=[reason])
    assert report["secondary_models_left_out_check"][NOISY] == [
        f"{NOISY} {line}: the plan holds no run" for line in sc.E3_LINES.values()
    ]


def in_two(study: SimpleNamespace, name: str) -> tuple[list[Path], Callable[[dict], None]]:
    """A stored run cut into the two shards the harness would make of it, each with its own
    manifest; and the change that lists the two in the plan in its place."""
    whole = study.paths.runs / name
    rows = [json.loads(text) for text in (whole / "readings.jsonl").read_text().splitlines()]
    manifest = json.loads((whole / "run_manifest.json").read_text())
    parts = []
    for k in range(2):
        mine = [row for row in rows if rd.shard_of(row["item_id"], 2) == k]
        folder = study.paths.runs / f"{name}.s{k}"
        folder.mkdir()
        readings = folder / "readings.jsonl"
        readings.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in mine))
        items = {row["item_id"] for row in mine}
        record = manifest | {
            "shard": f"{k}/2",
            "items": len(items),
            "item_ids_sha256": lp.ids_sha256(items),
            "expected_rows": len(mine),
            "readings": len(mine),
            "readings_sha256": TE.file_sha(readings),
        }
        (folder / "run_manifest.json").write_text(json.dumps(record))
        parts.append((folder, record))
    assert min(record["items"] for _, record in parts) > 0

    def change(plan: dict) -> None:
        runs = []
        for run in plan["runs"]:
            shards = [
                run
                | {
                    "run": folder.name,
                    "shard": record["shard"],
                    "calls": record["expected_rows"],
                    "item_ids_sha256": record["item_ids_sha256"],
                }
                for folder, record in parts
            ]
            runs += shards if run["run"] == name else [run]
        plan["runs"] = runs

    return [folder for folder, _ in parts], change


def test_a_run_stored_in_several_parts_gives_the_same_result(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    """PLAN section 6: a run stored in several parts is accepted. A run of each kind (a
    condition of a secondary model, a secondary list, the 20 samples, a cell of the 2x2) is cut
    in two, and the sections that score them say what they said of the whole runs."""
    names = (
        f"e3-b-{INFORMED}",
        f"e3-silent-c-{DEEPSEEK}",
        f"e3-samples-{LLAMA}",
        f"e4-2x2-mask-{LLAMA}",
    )
    sections = ["secondary_lists", "sampled_quantiles", "name_date_2x2", "recovery_rule"]
    folders: list[Path] = []
    plan = lp.plan_path(study.paths.runs)
    try:
        with TE.changed(plan):
            for name in names:
                made, change = in_two(study, name)
                folders += made
                record = json.loads(plan.read_text())
                change(record)
                plan.write_text(json.dumps(record))
                (study.paths.runs / name).rename(study.paths.runs / f"{name}.aside")
            report, _ = scored(study, tmp_path, capsys, section=sections)
            # one part that is not complete is a refusal
            second = folders[5] / "run_manifest.json"
            with TE.changed(second):
                second.write_text(json.dumps(json.loads(second.read_text()) | {"complete": False}))
                why = refused(study, tmp_path, capsys, section=sections)
            assert f"run {folders[5].name} is not finished (partial)" in why
    finally:
        for folder in folders:
            shutil.rmtree(folder)
        for name in names:
            aside = study.paths.runs / f"{name}.aside"
            if aside.exists():
                aside.rename(study.paths.runs / name)

    def without_runs(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: without_runs(v) for k, v in value.items() if k not in ("run", "runs")}
        return value

    for name in sections:
        assert without_runs(report[name]) == without_runs(base.report[name]), name
    assert report["sampled_quantiles"][LLAMA]["run"]["runs"] == 2
    assert report["sampled_quantiles"][LLAMA]["run"]["rows"] == 1200
    assert report["secondary_lists"][DEEPSEEK]["silent"]["runs"]["c"]["runs"] == 2
    assert report["name_date_2x2"][LLAMA]["runs"][CELL_NAMES["mask"]]["runs"] == 2
    assert report["name_date_2x2"][LLAMA]["runs"][CELL_NAMES["shift"]]["runs"] == 1
    assert report["inputs"]["plan_sha256"] != base.report["inputs"]["plan_sha256"]
    # the study is whole again
    assert all((study.paths.runs / name / "run_manifest.json").is_file() for name in names)
    assert not list(study.paths.runs.glob("*.aside")) and not list(study.paths.runs.glob("*.s0"))


def test_two_runs_write_the_same_bytes_and_the_record_of_what_was_read(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    texts = []
    # the second time the hashes of the selection files are given by their first 16 characters
    short = [
        f"{model}={value[:16]}" for model, value in (v.split("=") for v in study.selection_shas)
    ]
    for hashes in (study.selection_shas, short):
        out = TE.fresh(tmp_path)
        chosen = options(study, section=CHEAP, expect_selection_sha256=hashes)
        assert sc.main(["score", "--out", str(out), *chosen]) == 0
        texts.append(out.read_text())
    assert texts[0] == texts[1] and capsys.readouterr().err == ""
    report = base.report
    assert report["about"] == sc.ABOUT and report["registered"] == json.loads(
        ev.report_text(ev.registered_record())
    )
    inputs = report["inputs"]
    assert inputs["sealed_outcomes_sha256"] == study.sealed_sha
    assert inputs["eligible_sha256"] == study.eligible_sha
    assert inputs["baseline_predictions_sha256"] == study.baselines_sha
    assert inputs["confirmatory_result_sha256"] == TE.file_sha(study.paths.confirmatory)
    assert inputs["selection_sha256"] == dict(v.split("=") for v in study.selection_shas)
    assert list(inputs["selection_sha256"]) == list(ev.PRIMARIES)
    assert "--expect-selection-sha256 <model>=<selection file>" in report["command"]
    assert inputs["plan_sha256_of_the_confirmatory_result"] == inputs["plan_sha256"]
    assert inputs["code_sha256"]["secondary_scores.py"] == TE.file_sha(Path(sc.__file__))
    assert inputs["events_sha256"] == TE.file_sha(study.paths.events)
    assert inputs["statements_sha256"] == TE.file_sha(study.paths.statements)
    assert inputs["dataset_counts_sha256"] == TE.file_sha(study.paths.counts)
    assert inputs["plan_sha256"] == TE.file_sha(lp.plan_path(study.paths.runs))
    opened = ("events_sha256", "statements_sha256", "dataset_counts_sha256", "plan_sha256")
    assert len({inputs[key] for key in opened}) == len(opened)
    assert inputs["code_sha256"]["evaluate.py"] == TE.file_sha(Path(ev.__file__))
    # the code that wrote the evaluator's result file is recorded beside the code that runs now
    theirs = json.loads(study.paths.confirmatory.read_text())["inputs"]["code_sha256"]
    assert inputs["code_sha256_of_the_confirmatory_result"] == theirs
    assert theirs["evaluate.py"] == inputs["code_sha256"]["evaluate.py"]
    assert report["where_the_plan_is_silent"] == list(sc.WHERE_THE_PLAN_IS_SILENT)
    # what the plan states stands apart from the choices of the code, each with its section
    assert report["as_the_plan_says"] == list(sc.AS_THE_PLAN_SAYS)
    assert all("(section " in line or "(standing rules; " in line for line in sc.AS_THE_PLAN_SAYS)
    assert not set(sc.AS_THE_PLAN_SAYS) & set(sc.WHERE_THE_PLAN_IS_SILENT)
    stated = " ".join(sc.AS_THE_PLAN_SAYS)
    for words in (
        'the base rate by listing age for the secondary models too (section 6, "Comparator")',
        "90 and 180 days after the statement date",
        "the pinball levels 0.5, 0.8 and 0.95 (section 7.2)",
        "a sample that fails to parse is left out and counted",
        "the fourth cell of the 2x2 is the run of condition (b)",
        "a primary keeps the item set its probe fixed",
        "is discontinued there",
        "use the first 1,000 of the 10,000 registered draws",
        "are given again on the statements dated after its cutoff",
        "a declaration that the evaluator's result file does not record is refused",
    ):
        assert words in stated, words
    # where the list quotes the plan, it quotes it as the plan reads: these words stand in
    # both, letter for letter (the case of a first letter and the line breaks apart)
    plan = Path(sc.__file__).with_name("plan") / "PLAN.md"
    registered = " ".join(plan.read_text(encoding="utf-8").split()).lower()
    for words in (
        # standing rules
        "where the same figure is also written on a set that differs from its own by 1 to 4 "
        "statements, so that the two together would give back the outcomes of those few (a "
        "slice within its whole, the answers that parsed within all, one outcome definition "
        "beside another)",
        "the second check is made on pairs of sets",
        "how many of 1 to 4 statements are scoreable or have a determined event",
        "are never withheld on the second ground: the figure that stands beside one of them is "
        "the one withheld",
        "reads no stored file that leads into a sealed folder through a link",
        "prints no character of a sealed file's hash where it refuses the file for its hash",
        # section 2.5
        "the mean probabilities and the calibration in the large on the scoreable statements, "
        "which name the few that are not, are then withheld too",
        "the same holds where only 1 to 4 statements of a set are scoreable",
        "the pinball losses and the coverage stay",
        "or 1 to 4 of those scoreable under either definition",
        "the number of statements with another horizon event is given",
        # section 4
        "where the failed answers of one side, or of both, number 1 to 4, its counts are "
        "withheld as well, since they would say how many of those few are scoreable",
        # section 5, E1 and E4
        "a further cell is withheld and marked where the cells written and the whole would "
        "otherwise give back the figure on 1 to 4 statements",
        "over all dated statements and by statement type",
        "a turnbull estimate by form, by statement type and by revision bucket",
        "the figures of a probe over 1 to 4 targets are withheld; its verdict is given",
        # section 7.2
        "statements that share a probability count with the frequency of the event among all "
        "of them, so that the figures do not depend on the order of the statements",
        "a forecast of one value has no resolution",
        # section 5, E3, "By statement type"
        "the primary loss and the calibration in the large of the three conditions and of the "
        "base rate",
        "each quantity comes with its 95% percentile interval by episode and the two scenarios "
        "of section 7.2",
        "the difference between the two types (next delivery minus recovery) and its 95% "
        "percentile interval over 10,000 draws of the episodes of the item set, both types "
        "taken from each draw; a draw with no scoreable statement of one type is left out",
        "a type with fewer than 50 scoreable statements in an item set is reported by its "
        "counts alone",
        "the verdict of each test is the registered one on both types together",
        "the two types differ in certainty class and in form, so a difference is not read as "
        "an effect of the type alone",
        # section 13, "Reported beside it", and section 7.2, "Calibration in the large"
        "for condition (a) and for the base rate on the same statements",
        "minus the turnbull share recovered by the stated end",
        "stand the same quantities for the base rate by listing age on the same events",
    ):
        assert words in stated.lower(), words
        assert words in registered, words
    chosen = " ".join(sc.WHERE_THE_PLAN_IS_SILENT)
    assert "not a silence" not in chosen and "departure" not in chosen
    assert "registered draws" not in chosen and "floor (two shortage episodes" not in chosen
    # and what the plan states is no longer called a choice of the code
    for words in (
        "would name the few that are not",
        "share a probability",
        "a count is withheld (null) where it would say",
        "the least and greatest calibration in the large over every statement is withheld",
        "so a further cell is withheld and marked",
    ):
        assert words not in chosen, words
    assert (ev.DRAWS, sc.MIN_SHOWN) == (10000, 5)  # the draws of a slip interval are fewer here
    # what is not computed here: by another script of the study, or by no script yet
    elsewhere, nowhere = sc.COMPUTED_BY_ANOTHER_SCRIPT, sc.COMPUTED_BY_NO_SCRIPT
    assert report["not_computed_here"] == {
        "computed_by_another_script": list(elsewhere),
        "computed_by_no_script": list(nowhere),
        "if_no_script_computes_it": sc.STILL_NOT_COMPUTED,
    }
    assert not set(elsewhere) & set(nowhere) and "named in the paper as not run" in (
        sc.STILL_NOT_COMPUTED
    )
    named = {name for text in elsewhere for name in re.findall(r"\w+\.py", text)}
    assert named == {"literal_scores.py", "audit_reference.py", "power.py"}
    assert all((Path(sc.__file__).parent / name).is_file() for name in named)
    assert not [text for text in nowhere if ".py" in text]
    assert len(nowhere) == 3
    for analysis in (
        "the fit that leaves out the dominant company",
        "the full-follow-up refit",
        "E7",
    ):
        assert sum(text.startswith(analysis) for text in nowhere) == 1, analysis
    assert not [text for text in nowhere if "Date Discontinued" in text]
    assert report["bootstrap"]["draws"] == ev.DRAWS and report["bootstrap"]["seed"] == ev.SEED
    assert report["refit"]["splits"] == "fit and dev"
    assert report["primaries_not_evaluable_by_declaration"] == {}
    assert "no multiplicity claim" in base.printed and f"{INFORMED}" in base.printed


def strings(value: Any) -> Iterator[str]:
    """Every key and every text value of a record."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str):
        yield value


def test_no_output_says_anything_about_a_single_statement(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    table = study.table
    named = set(table["statement_group_id"]) | set(table["event_id"]) | set(table["thread_id"])
    named |= set(table["episode_id"]) | set(table["generic_name"]) | set(table["presentation"])
    sealed = study.sealed_rows
    dates = set()
    for column in ("lower_date_B", "upper_date_B", "exit_date_B", "followup_end_date"):
        dates |= set(sealed[column]) - {""}
    assert len(named) > 500 and len(dates) > 20
    for text in (base.text, base.printed):
        assert not [name for name in named if name and name in text]
        assert not [day for day in dates if day in text]
    found = list(strings(base.report))
    assert not [text for text in found if TE.NDC.search(text)]
    # no outcome cell: the words of the outcome columns stand nowhere as values
    values = {
        text for text in found if text in ("recovered", "censored", "discontinued", "yes", "no")
    }
    assert values == set()
    # the companies are counted, never scored: they stand in the counts of E1 alone
    companies = set(table["company_name"])
    where = [key for key, value in base.report.items() if companies & set(strings(value))]
    assert where == ["descriptives"]
    assert companies == set(base.report["descriptives"]["counts"]["by_company"])


def test_the_date_discontinued_cell_moves_the_contrasts_of_the_statements_it_is_on(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
    fit: SimpleNamespace,
) -> None:
    """The synthetic captures hold no Date Discontinued cell, so the third variant of the study
    is the primary outcome. Here the cell is written into the outcome rows of eight eligible
    statements that are censored or recovered, at the day of the statement: under the variant
    they are discontinuations, and both their horizon events are no."""
    label = sc.RECOVERY_VARIANTS[2]
    whole = base.report["recovery_rule"][label]
    primary = base.report["secondary_models"]["models"][INFORMED]["on_every_eligible_statement"]
    assert whole["statements_with_another_horizon_event"][INFORMED] == 0
    assert near(whole["contrasts"][INFORMED]["H1"]["delta"], primary["H1"]["delta"])
    rows = study.sealed_rows.copy()
    assert (rows[sc.DISCONTINUED_CELL] == "").all()
    y = fit.y.loc[fit.ids].copy()
    listed = study.listed.set_index("statement_group_id").loc[fit.ids]
    live = (
        listed["event_id"]
        .map(rows.set_index("event_id")["outcome_B"])
        .isin(["censored", "recovered"])
    )
    yes = (y["y_a"] == 1.0) | (y["y_b"] == 1.0) | ~y["scoreable"]
    chosen = list(y.index[(live & yes).to_numpy()][:8])
    assert len(chosen) == 8
    planted = rows["event_id"].isin(set(listed.loc[chosen, "event_id"]))
    rows.loc[planted, sc.DISCONTINUED_CELL] = rows.loc[planted, "event_date"]
    other = tmp_path / "outcomes_test.csv.gz"
    C.write_gz(rows, other)
    sha = TE.file_sha(other)
    with TE.json_with(
        study.paths.confirmatory, lambda r: r["inputs"].update(sealed_outcomes_sha256=sha)
    ):
        report, _ = scored(
            study, tmp_path, capsys, sealed=other, expect_sha256=sha, section=["recovery_rule"]
        )
    got = report["recovery_rule"]
    for unchanged in sc.RECOVERY_VARIANTS[:2]:
        assert got[unchanged] == base.report["recovery_rule"][unchanged]
    assert got[label]["statements_with_another_horizon_event"][INFORMED] == 8
    y.loc[chosen, ["y_a", "y_b"]] = 0.0
    assert got[label]["scoreable_statements"] == int((y["y_a"].notna() & y["y_b"].notna()).sum())
    keep = (y["y_a"].notna() & y["y_b"].notna()).to_numpy()
    a, _ = given(study, INFORMED, "a", fit.ids, fit.base)
    b, _ = given(study, INFORMED, "b", fit.ids, fit.base)
    entry = got[label]["contrasts"][INFORMED]["H1"]
    assert entry["statements"] == int(keep.sum())
    assert near(entry["delta"], (brier(a, y) - brier(b, y))[keep].mean())
    assert not near(entry["delta"], primary["H1"]["delta"])
    assert entry["bounds"]["statements"] == len(fit.ids)


def test_a_primary_declared_not_evaluable_is_left_out_of_its_sections(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    declared = tmp_path / "confirmatory_one_primary.json"
    reason = f"{DEEPSEEK}=its route was withdrawn"
    hashes = [value for value in study.selection_shas if value.startswith(LLAMA)]
    with redirect_stdout(io.StringIO()):
        assert (
            ev.main(
                [
                    "confirmatory",
                    "--out",
                    str(declared),
                    "--not-evaluable",
                    reason,
                    *TE.options(study, expect_selection_sha256=hashes),
                ]
            )
            == 0
        )
    sections = ["secondary_lists", "name_date_2x2", "selective_prediction", "recovery_rule"]
    with (
        TE.manifest_with(study, DEEPSEEK, "e4-2x2-mask", complete=False),
        TE.manifest_with(study, DEEPSEEK, "e3-b", complete=False),
    ):
        report, _ = scored(
            study,
            tmp_path,
            capsys,
            confirmatory=declared,
            section=sections,
            not_evaluable=[reason],
            expect_selection_sha256=hashes,
        )
    assert list(report["primaries_not_evaluable_by_declaration"]) == [DEEPSEEK]
    assert list(report["name_date_2x2"]) == list(report["secondary_lists"]) == [LLAMA]
    assert report["name_date_2x2"][LLAMA] == base.report["name_date_2x2"][LLAMA]
    assert f"{DEEPSEEK}:c" not in report["selective_prediction"]
    assert f"{LLAMA}:c" in report["selective_prediction"]
    for variant in sc.RECOVERY_VARIANTS:
        assert DEEPSEEK not in report["recovery_rule"][variant]["contrasts"]
        assert LLAMA in report["recovery_rule"][variant]["contrasts"]


# --------------------------------------------------------------------------------------------
# The train-period descriptives: open data only
# --------------------------------------------------------------------------------------------


def test_the_train_descriptives_command_reads_the_open_table_alone(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    out = tmp_path / "train.json"
    args = ["--statements", str(study.paths.statements), *counts_of(study)]
    assert sc.main(["train-descriptives", "--out", str(out), *args]) == 0
    report = json.loads(out.read_text())
    printed = capsys.readouterr().out
    assert sealed_unread == [
        "the statement table",
        "the counts file",
        "secondary_scores.py",
        *sealed_unread[3:],
    ]
    assert "the sealed file" not in sealed_unread and "train period:" in printed
    frame = P.prepare(study.table)
    rows = frame[frame["period"] == "train"]
    wanted = sc.descriptives(rows, study.table.set_index("statement_group_id"), beside={})
    assert report["descriptives"] == json.loads(ev.report_text(wanted))
    assert (
        report["about"] == sc.ABOUT_TRAIN
        and report["bootstrap"]["draws_of_a_turnbull_estimate"] == sc.SLIP_DRAWS == SLIP_DRAWS
    )
    assert report["inputs"]["statements_sha256"] == TE.file_sha(study.paths.statements)
    got = report["descriptives"]
    train = study.table[(study.table["period"] == "train") & D.true(study.table["at_risk_B"])]
    assert got["statements"] == len(train) and set(got["counts"]["by_year"]) <= {
        "2019",
        "2020",
        "2021",
        "2022",
    }
    assert got["hold_rate"]["all_dated_forms"]["determined"] > 50
    # from the open table itself: the dated statements, how many have a determined event at
    # the stated end, how many of those held, and the statements by year
    dated = train[train["analysis_set"] == "dated"]
    held = dated["E_end"].map({"yes": 1.0, "no": 0.0})
    rate = got["hold_rate"]["all_dated_forms"]
    assert got["dated_statements_not_stale"] == rate["statements"] == len(dated)
    assert rate["determined"] == int(held.notna().sum())
    assert near(rate["among_determined"]["mean"], held.mean())
    assert near(rate["undetermined_as_yes"]["mean"], held.fillna(1.0).mean())
    assert got["counts"]["by_year"] == (
        train["event_date"].str[:4].value_counts().sort_index().to_dict()
    )
    assert got["episodes"] == train["episode_id"].nunique()
    assert got["slip"]["all_dated_forms"]["draws"] == SLIP_DRAWS
    # of the two lists every result file carries, the lines on the descriptives of E1
    for key, lines in (
        ("as_the_plan_says", sc.AS_THE_PLAN_SAYS),
        ("where_the_plan_is_silent", sc.WHERE_THE_PLAN_IS_SILENT),
    ):
        assert report[key] == sc.of_the_descriptives(lines)
        named = [line for line in lines if "E1" in line or "Turnbull" in line]
        # the Turnbull share beside the overconfidence criterion is no descriptive of E1
        assert [line for line in named if line not in report[key]] == [
            line for line in named if "criterion" in line
        ]
        assert len([line for line in named if "criterion" in line]) == 1
        assert report[key] and not [
            line
            for line in report[key]
            if "2x2" in line or "paraphrase" in line or "selective prediction" in line
        ]
    assert len(report["as_the_plan_says"]) == 5 and len(report["where_the_plan_is_silent"]) == 7
    # by statement type as well: every dated train statement of the synthetic table is a
    # recovery statement, so that cell is the whole
    for table in ("hold_rate", "slip"):
        cells = got[table]["by_statement_type"]
        assert list(cells) == list(sc.TYPES) and cells["recovery"] == got[table]["all_dated_forms"]
        assert cells["next_delivery"]["statements"] == 0
    said = " ".join(report["as_the_plan_says"])
    assert "the first 1,000 of the 10,000 registered draws" in said
    assert "a further cell is withheld and marked where the cells written and the whole" in said
    assert "in the tables of E1 also on the cells written with their whole" in said
    with pytest.raises(SystemExit, match="unrecognized arguments: --slip-draws"):
        sc.main(["train-descriptives", "--out", str(tmp_path / "x.json"), "--slip-draws", "6"])
    # the command takes no sealed path, and refuses what is not the open table of this build
    with pytest.raises(SystemExit, match="unrecognized arguments"):
        sc.main(["train-descriptives", "--out", str(tmp_path / "x.json"), "--sealed", "x"])
    with pytest.raises(SystemExit, match="already there, and nothing is overwritten"):
        sc.main(["train-descriptives", "--out", str(out), *args])
    vault = tmp_path / "sealed"
    vault.mkdir()
    copy = vault / "statements.csv.gz"
    copy.write_bytes(study.paths.statements.read_bytes())
    new = ["train-descriptives", "--out", str(tmp_path / "new.json")]
    with pytest.raises(SystemExit, match="--statements would be read from a sealed folder"):
        sc.main([*new, "--statements", str(copy), *counts_of(study)])
    # a table that holds an outcome of the test period is refused, by the type of the stop alone
    filled = study.table.set_index("statement_group_id")
    filled.update(study.filled[list(D.OUTCOME_COLUMNS)])
    other = tmp_path / "statements.csv.gz"
    other.write_bytes(TE.F.gz_bytes(filled.reset_index()[list(D.COLUMNS)]))
    with (
        TE.json_with(
            study.paths.counts,
            lambda r: r["outputs"][D.STATEMENTS.name].update(sha256=TE.file_sha(other)),
        ),
        pytest.raises(SystemExit) as stop,
    ):
        sc.main([*new, "--statements", str(other), *counts_of(study)])
    assert stop.value.code == (
        "refused: the statement table is not as the dataset builder writes it (ValueError)"
    )
    with pytest.raises(SystemExit, match="not the files the counts file of the dataset builder"):
        sc.main([*new, "--statements", str(other), *counts_of(study)])
    assert not (tmp_path / "new.json").exists()


def test_a_primary_is_scored_on_the_item_set_its_probe_fixed(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
    fit: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A primary whose probe beats the base rate is switched to its post-cutoff slice (PLAN
    section 5, E4). The evaluator's result is made again on probe runs that remember the
    outcomes: the first primary, with a cutoff that leaves it a slice of 50 scoreable
    statements, is scored on that slice; the second has too small a slice and no item set. A
    result file that names another item set than the probe readings give stops the scoring."""
    # the cutoff is put on the day of a statement of the paraphrase subset, the latest that
    # leaves a slice of 50 scoreable statements: a statement dated on the cutoff is not after it
    day = study.filled.loc[fit.ids, "event_date"]
    scoreable = fit.y.loc[fit.ids, "scoreable"].to_numpy()
    days = sorted(set(study.filled.loc[subset_ids(study, "paraphrase"), "event_date"]))
    early = date.fromisoformat(
        max(d for d in days if int(((day > d).to_numpy() & scoreable).sum()) >= ev.MIN_SLICE)
    )
    monkeypatch.setitem(S.CUTOFF_MONTH_ENDS, LLAMA, early)
    after = (day > early.isoformat()).to_numpy()
    assert ev.MIN_SLICE <= int((after & scoreable).sum()) < int(scoreable.sum())
    assert int((day == early.isoformat()).sum()) > 0 and S.has_slice(early)
    switched = tmp_path / "confirmatory_switched.json"
    sections = ["secondary_models", "selective_prediction", "recovery_rule"]
    subsets = ["secondary_lists", "sampled_quantiles", "prompt_variance", "name_date_2x2"]

    def forged(record: dict) -> None:
        record["item_sets"][LLAMA].update(items=ev.ALL_ITEMS, switched=False)
        for entry in record["family"]:
            if entry["model"] == LLAMA:
                entry["items"] = ev.ALL_ITEMS

    with (
        TE.rewritten(study, LLAMA, "e4-probe", TE.informed(study)),
        TE.rewritten(study, DEEPSEEK, "e4-probe", TE.informed(study)),
    ):
        with redirect_stdout(io.StringIO()):
            assert ev.main(["confirmatory", "--out", str(switched), *TE.options(study)]) == 0
        fixed = json.loads(switched.read_text())["item_sets"]
        assert fixed[LLAMA]["switched"] is True and fixed[LLAMA]["items"] == ev.SLICE_ITEMS
        assert fixed[DEEPSEEK]["switched"] is True and fixed[DEEPSEEK]["evaluable"] is False
        report, _ = scored(
            study, tmp_path, capsys, confirmatory=switched, section=[*sections, *subsets]
        )
        # the file says every eligible statement, in its item sets and in its family alike:
        # nothing before the sealed file can tell, and the probe readings then do
        with TE.json_with(switched, forged):
            why = refused(study, tmp_path, capsys, confirmatory=switched, section=sections[1:])
        assert why.startswith("refused: the scoring stopped on the sealed rows (ValueError)")

        # the right item set by its name is not enough: the record is the one the probe
        # readings give, count by count, and holds nothing more
        def one_more(record: dict) -> None:
            record["item_sets"][LLAMA]["slice_scoreable"] += 1

        def a_field_more(record: dict) -> None:
            record["item_sets"][LLAMA]["note"] = "as agreed"

        for change in (one_more, a_field_more):
            with TE.json_with(switched, change):
                why = refused(study, tmp_path, capsys, confirmatory=switched, section=sections[1:])
            assert why.startswith("refused: the scoring stopped on the sealed rows (ValueError)")
    # the result file of the study as it is, whose probes lost, no longer fits these cutoffs
    why = refused(study, tmp_path, capsys, section=sections[1:])
    assert "it was written under other registered constants than those in force" in why
    # no score of a primary here: the evaluator holds them, on the item set of the probe
    assert not set(report["secondary_models"]["scores_on_every_eligible_statement"]) & set(
        ev.PRIMARIES
    )
    # selective prediction: the point of the first primary is on its slice, with the counts of
    # its readings on the same statements; the second has no point
    selective = report["selective_prediction"]
    assert f"{DEEPSEEK}:c" not in selective
    point = selective[f"{LLAMA}:c"]
    days = read_days(study, LLAMA, fit.ids)[after]
    assert point["items"] == ev.SLICE_ITEMS and point["statements"] == int(after.sum())
    assert point["abstained"] == int(days.isna().sum())
    counted = ("failed_counted_as_abstain", "abstain", "period_of_another_statement_type")
    assert sum(point[name] for name in counted) == point["abstained"]
    whole = base.report["selective_prediction"]
    assert whole[f"{LLAMA}:c"]["statements"] == len(fit.ids) > point["statements"]
    # the counts of the whole run would not add up on the slice
    assert sum(whole[f"{LLAMA}:c"][name] for name in counted) > point["abstained"]
    assert selective[f"{INFORMED}:c"] == whole[f"{INFORMED}:c"]
    assert selective["rule_reader"] == whole["rule_reader"]
    # the recovery rule: the three tests of the first primary on the scoreable statements of
    # its slice under each variant, none of the second, the secondary models as before
    events = {"yes": 1.0, "no": 0.0}
    filled = D.attach_outcomes(study.listed, study.sealed_rows, "BL")
    filled = filled.set_index("statement_group_id").loc[fit.ids]
    under_bl = (
        filled["E_end"].map(events).notna() & filled["E_end90"].map(events).notna()
    ).to_numpy()
    for variant in sc.RECOVERY_VARIANTS:
        got = report["recovery_rule"][variant]["contrasts"]
        assert list(got) == [LLAMA, *sc.SECONDARY_MODELS]
        assert got[INFORMED] == base.report["recovery_rule"][variant]["contrasts"][INFORMED]
        assert list(got[LLAMA]) == ["H1", "H2", "H3"]
    got = report["recovery_rule"][sc.RECOVERY_VARIANTS[0]]["contrasts"]
    assert got[LLAMA]["H1"]["statements"] == int((under_bl & after).sum())
    whole = base.report["recovery_rule"][sc.RECOVERY_VARIANTS[0]]["contrasts"]
    assert whole[LLAMA]["H1"]["statements"] == int(under_bl.sum()) > int((under_bl & after).sum())
    # on a subset of the eligible list and on a secondary list a primary is read on every
    # statement; the probe excludes a switched one from outcome claims before its cutoff, so
    # what is scored against outcomes is given again on the statements after it
    y = fit.y
    for section in ("sampled_quantiles", "prompt_variance", "name_date_2x2"):
        for model in ev.PRIMARIES:
            got, was = report[section][model], base.report[section][model]
            assert got["item_set_fixed_by_the_probe"]["switched"] is True
            assert was["item_set_fixed_by_the_probe"] == {
                "switched": False,
                "evaluable": True,
                "items": ev.ALL_ITEMS,
            }
            if section == "name_date_2x2":  # the memory control keeps the whole subset
                assert (
                    "after_the_cutoff" not in got and got["primary_brier"] == was["primary_brier"]
                )
                continue
            assert got["probe_excludes_the_statements_before_the_cutoff"] is True
            assert was["probe_excludes_the_statements_before_the_cutoff"] is False
            assert "after_the_cutoff" not in was
    ids = subset_ids(study, "paraphrase")
    later = [item for item in ids if study.filled.loc[item, "event_date"] > early.isoformat()]
    kept = [item for item in later if y.loc[item, "scoreable"]]
    assert len(kept) >= sc.MIN_SHOWN and len(ids) - len(later) >= sc.MIN_SHOWN
    got = report["prompt_variance"][LLAMA]
    assert got["statements"] == len(ids) and got["after_the_cutoff"]["statements"] == len(later)
    assert got["after_the_cutoff"]["scoreable_statements"] == len(kept)
    b, _ = given(study, LLAMA, "b", ids, fit.base)
    registered = got["after_the_cutoff"]["primary_brier"]["predictive-track-v1"]
    assert near(registered["mean"], brier(b, y.loc[ids]).loc[kept].mean())
    assert registered["bounds_all_statements"]["statements"] == len(later)
    assert got["primary_brier"] == base.report["prompt_variance"][LLAMA]["primary_brier"]
    ids = subset_ids(study, "samples20")
    later = [item for item in ids if study.filled.loc[item, "event_date"] > early.isoformat()]
    got = report["sampled_quantiles"][LLAMA]
    assert got["after_the_cutoff"]["statements"] == len(later) < got["statements"] == len(ids)
    assert set(got["after_the_cutoff"]) == {"statements", "pinball", "coverage_80"}
    shown = got["after_the_cutoff"]["pinball"]["0.50"]["sampled"]
    assert shown["statements"] + shown["left_out_right_censored"] == len(later)
    assert got["pinball"] == base.report["sampled_quantiles"][LLAMA]["pinball"]
    for key in sc.LIST_KEYS:
        got, was = report["secondary_lists"][LLAMA][key], base.report["secondary_lists"][LLAMA][key]
        assert got["item_set_fixed_by_the_probe"]["switched"] is True
        if key not in sc.FALLBACK_LISTS:  # stale-value uptake reads no outcome
            assert "after_the_cutoff" not in got and "after_the_cutoff" not in was
            assert got["stale_value_uptake"] == was["stale_value_uptake"]
            continue
        assert got["probe_excludes_the_statements_before_the_cutoff"] is True
        assert was["probe_excludes_the_statements_before_the_cutoff"] is False
        ids = list_ids(study, key)
        later = [item for item in ids if study.filled.loc[item, "event_date"] > early.isoformat()]
        assert got["statements"] == len(ids) and got["scores"] == was["scores"]
        assert got["after_the_cutoff"]["statements"] == len(later)
        if "withheld" not in got["after_the_cutoff"]:
            scores = got["after_the_cutoff"]["scores"][f"{LLAMA}:b"]
            kept = [item for item in later if y.loc[item, "scoreable"]]
            pred = list_predictions(study, fit, LLAMA, key)["b"]
            assert scores["scoreable_statements"] == len(kept)
            assert near(scores["primary_brier"], brier(pred, y.loc[ids]).loc[kept].mean())
