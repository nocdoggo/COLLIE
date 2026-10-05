"""Tests for the registered evaluator (``evaluate.py``).

No test reads the study's sealed folder, opens a network connection or reads a key. Everything
but the last test runs on one synthetic study in a temporary folder:

* capture files (the first day of each month from December 2019 to September 2026, and a last one
  on 2026-09-26) built by ``corpus.build_corpus`` and ``dataset.build`` into the open tables, the
  eligible list, the counts file and the item files; the test-period outcome rows are written,
  as the corpus builder writes them, to a file that stands in for the sealed one;
* a plan made by ``launch.make_plan``, and the dev and confirmatory runs of both primaries read
  by the harness's own reader (``read.Reader``, ``read.write_run``) around a scripted client, so
  the stored rows and manifests are in the harness's format;
* scripted answers that are a fixed function of the statement (``answer``): for the first
  primary, condition (b) follows the outcome and condition (a) does not (a planted H1 effect),
  and its literal reading is the rule reading (H2 exactly null); for the second primary, (a) and
  (b) are the same noise around fixed probabilities (no effect), and some literal readings
  differ from the rule's. A few answers fail to parse, once or twice, so that repaired and
  failed readings exist.

Variants of the study are made by rewriting stored rows, manifests or files in place, inside
``changed`` (which puts every byte back).

Covered: Holm on a hand-worked example; every p-value procedure on cases small enough to work
out by hand, against its definition one draw at a time, on the registered draws and against
``size_check.py``; a bootstrap draw that is exactly zero, counted on both sides; the two
registered constants and every candidate of each, from the dev command to the result file; the
readings as predictions, with the base-rate and ABSTAIN fallbacks and their counts; the dev
command, its selection, its comparator and its refusals; the completeness check, which reads no
outcome and never looks at the sealed path; every refusal of a partial, mismatched or wrong-set
run, of a wrong hash, of files of another build and of a stop inside the rules, each with the
sealed file left unread; the probe test, the switch to the post-cutoff slice, the small-slice
rule at its boundary and a primary declared not evaluable; the six tests against a computation
made here from the scripted answers and the synthetic outcomes; bounds, secondaries and scores;
the hash of the model-free predictions; the same result on a second run; no statement in any
output. The last test runs the dev command on the open train-period data with stand-in readings
made from the model-free predictors and compares it with ``power.py`` (and with
``out/dev_losses.json`` when that file is of the same build); it is skipped when the open
tables are absent.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_evaluate.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import socket
import warnings
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from analysis.coling import corpus as C
from analysis.coling import dataset as D
from analysis.coling import evaluate as ev
from analysis.coling import forms as F
from analysis.coling import gbm as G
from analysis.coling import launch as lp
from analysis.coling import power as W
from analysis.coling import predictors as P
from analysis.coling import read as rd
from analysis.coling import sealed_counts as S
from analysis.coling import size_check as SC
from collie.llm.client import EndpointConfig

LLAMA, DEEPSEEK = rd.PRIMARIES
HEADER = (
    "Generic Name,Company Name, Contact Info, Presentation, Type of Update,Date of Update, "
    "Availability Information, Related Information, Resolved Note, Reason for Shortage, "
    "Therapeutic Category, Status, Change Date, Date Discontinued, Initial Posting Date"
)
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
LAST = date(2026, 9, 26)
COMPANIES = ("Acme Pharma", "Borealis Labs", "Cobalt Generics")
REASONS = ("Demand increase for the drug", "Manufacturing delay", "Other")
K_VALUES = (0, 2, 5, None, 1, 4)
NDC = re.compile(r"NDC 12345-(\d+)-90")
GARBAGE = "I cannot answer in that form."
TRACK = {
    "schema": "coling-track-record-v1",
    "split": "fit",
    "since": "2019-10-01",
    "through": "2020-12-31",
    "seed": 20261001,
    "min_cell": 100,
    "source": {"outcomes_sha256": "0" * 64},
    "slip_table": [
        {
            "form": "a month and year",
            "revision": "first",
            "statements": 412,
            "basis": "cell",
            "share_by_stated_end": 0.31,
            "share_by_stated_end_90": 0.62,
            "median_days_to_recovery": 140,
        }
    ],
    "examples": [{"item_id": "X0001", "date_of_update": "2020-07-01", "outcome": "discontinued"}],
}
MEMO: dict[tuple[str, int], Any] = {}
REAL_REFIT, REAL_DEV_FIT = ev.refit, W.fit_and_predict


# --------------------------------------------------------------------------------------------
# Guards for every test
# --------------------------------------------------------------------------------------------


def frame_key(frame: pd.DataFrame) -> int:
    return int(pd.util.hash_pandas_object(frame.astype(str), index=True).sum())


def cached_refit(frame: pd.DataFrame) -> Any:
    """``evaluate.refit``, fitted once per frame for the whole module (the fit is the slow step
    and is deterministic; ``test_the_refit_is_reproducible`` runs the real one twice)."""
    key = ("refit", frame_key(frame))
    if key not in MEMO:
        MEMO[key] = REAL_REFIT(frame)
    return MEMO[key]


def cached_dev_fit(frame: pd.DataFrame, min_cell: int = P.MIN_CELL) -> Any:
    key = ("dev", frame_key(frame) + min_cell)
    if key not in MEMO:
        MEMO[key] = REAL_DEV_FIT(frame, min_cell)
    return MEMO[key]


def guard(monkeypatch: pytest.MonkeyPatch, nowhere: Path) -> None:
    """What no test may do, made impossible: reach the study's sealed file by default, open a
    network connection, read a key, or use the real repository."""

    def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a test tried to open a network connection")

    def no_key(self: Any) -> None:
        raise AssertionError("a test tried to read an API key")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(EndpointConfig, "resolve_key", no_key)
    for name in list(os.environ):
        if name.endswith("_API_KEY") or name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(rd, "REPO", nowhere)
    monkeypatch.setattr(ev, "SEALED", nowhere / "no_default" / "outcomes_test.csv.gz")
    monkeypatch.setattr(S, "SEALED", nowhere / "no_default" / "outcomes_test.csv.gz")
    monkeypatch.setattr(ev, "refit", cached_refit)
    monkeypatch.setattr(W, "fit_and_predict", cached_dev_fit)


@pytest.fixture(autouse=True)
def sealed_off(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    guard(monkeypatch, tmp_path_factory.mktemp("nowhere"))


# --------------------------------------------------------------------------------------------
# The synthetic corpus
# --------------------------------------------------------------------------------------------


def month_start(month: str, shift: int = 0) -> date:
    """The first day of ``month`` (YYYY-MM), ``shift`` months later."""
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + number - 1 + shift
    return date(index // 12, index % 12 + 1, 1)


CAPTURE_DAYS = (*(month_start("2019-12", i) for i in range(82)), LAST)


@dataclass(frozen=True)
class Line:
    """One presentation: its statement, and the capture from which it reads Available."""

    generic: str
    company: str
    day: str
    text: str
    back: date | None
    posted: str
    reason: str


def span(first: str, count: int) -> list[str]:
    """``count`` months from ``first``, without November (a statement of November gives
    January, whose end plus 90 days can fall on a capture day)."""
    months = [month_start(first, i) for i in range(count)]
    return [f"{m.year}-{m.month:02d}" for m in months if m.month != 11]


def layout() -> list[Line]:
    """The statements: dated the 15th of a month, giving the month two months on (or its
    quarter, or TBD), and back ``k`` months after that month's first day, with ``k`` drawn per
    drug so that episodes differ. 14 drugs in the fit split, 10 in dev, 40 in the test split
    (2023-01 to 2025-04, so that few statements are dated after 2024), one in the late split."""
    rng = np.random.default_rng(20261001)
    out: list[Line] = []

    def add(generic: str, months: Sequence[str], tbd_every: int = 0) -> None:
        company = COMPANIES[int(rng.integers(len(COMPANIES)))]
        posted = f"0{int(rng.integers(1, 9))}/05/{int(rng.integers(2016, 2020))}"
        lean = rng.dirichlet([2.0, 1.5, 2.0, 1.5, 0.8, 0.8])
        for n, month in enumerate(months):
            stated = month_start(month, 2)
            k = K_VALUES[int(rng.choice(len(K_VALUES), p=lean))]
            if tbd_every and n % tbd_every == tbd_every - 1:
                text = "Estimated recovery: TBD"
            elif n % 7 == 3:
                text = f"Estimated recovery: Q{(stated.month - 1) // 3 + 1} {stated.year}"
            else:
                text = f"Estimated recovery: {MONTHS[stated.month - 1]} {stated.year}"
            back = None if k is None else month_start(month, 2 + k)
            reason = REASONS[int(rng.integers(len(REASONS)))]
            out.append(Line(generic, company, f"{month}-15", text, back, posted, reason))

    for g in range(14):
        add(f"Fitdrug {g:02d}", span("2019-12", 13), tbd_every=6)
    for g in range(10):
        add(f"Devdrug {g:02d}", span("2021-01", 17), tbd_every=8)
    for g in range(40):
        add(f"Testdrug {g:02d}", span("2023-01", 28)[g % 3 :: 3], tbd_every=9)
    add("Latedrug 00", ["2026-01", "2026-02"])
    return out


def presentation(index: int) -> str:
    return f"{index % 9 + 1} mg vial (NDC 12345-{1000 + index}-90)"


def capture_rows(day: date, lines: Sequence[Line]) -> list[list[str]]:
    """The listing on one capture day: every presentation whose statement is dated by then."""
    rows = []
    for index, line in enumerate(lines):
        stated = date.fromisoformat(line.day)
        if stated > day:
            continue
        back = line.back is not None and day >= line.back
        rows.append(
            [
                line.generic,
                line.company,
                "800-000-0000",
                presentation(index),
                "Revised",
                stated.strftime("%m/%d/%Y"),
                "Available" if back else "Unavailable",
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


def write_captures(directory: Path, lines: Sequence[Line]) -> list[dict[str, str]]:
    """Write the capture files and return the rows of their manifest."""
    manifest = []
    for day in CAPTURE_DAYS:
        buffer = io.StringIO()
        csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            capture_rows(day, lines)
        )
        data = ("\r\n" + HEADER + "\r\n" + buffer.getvalue()).encode("utf-8")
        stamp = day.strftime("%Y%m%d") + "000000"
        (directory / f"{stamp}.csv").write_bytes(data)
        manifest.append(
            {
                "file": f"{stamp}.csv",
                "timestamp": stamp,
                "bytes": str(len(data)),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return manifest


# --------------------------------------------------------------------------------------------
# The scripted answers
# --------------------------------------------------------------------------------------------


def unit(item_id: str, tag: str) -> float:
    """A fixed number in [0, 1) for an item and a tag."""
    return int(hashlib.sha256(f"{tag}/{item_id}".encode()).hexdigest()[:8], 16) / 2**32


def forecast(p_a: float, p_b: float, median: float) -> dict[str, Any]:
    days = [min(365, max(0, round(median * factor))) for factor in (0.5, 1.0, 1.5, 2.0, 2.5)]
    return {
        "p_by_horizon_a": round(p_a, 4),
        "p_by_horizon_b": round(p_b, 4),
        "days_to_recovery": dict(zip(P.QUANTILE_KEYS, days, strict=True)),
    }


def literal(kind: str, start: str, end: str) -> dict[str, Any]:
    interval: Any = {"start": start, "end": end} if start else "ABSTAIN"
    return {
        "statement_type": kind,
        "interval": interval,
        "certainty": "estimated",
        "stale": False,
        "quote": "Estimated recovery",
    }


def answer(model: str, condition: str, row: dict[str, str]) -> dict[str, Any]:
    """The scripted reading of one statement (``row``: its cells in the statement table, with
    the outcome cells ``E_end`` and ``E_end90`` of the synthetic outcomes)."""
    item = row["statement_group_id"]
    end = D.days_between(row["event_date"], row["stated_end"])
    truth = {"yes": 1.0, "no": 0.0}
    if condition == "probe":
        return forecast(0.5, 0.5, 2.0 if model == LLAMA else 4.0)
    if condition == "c":
        if model == LLAMA:
            return literal("recovery", row["stated_start"], row["stated_end"])
        draw = unit(item, "literal")
        if draw < 0.15:
            later = (date.fromisoformat(row["stated_end"]) + timedelta(days=31)).isoformat()
            return literal("recovery", row["stated_start"], later)
        if draw < 0.21:
            return literal("recovery", "", "")
        if draw < 0.25:
            return literal("depletion", row["stated_start"], row["stated_end"])
        return literal("next_delivery", row["stated_start"], row["stated_end"])
    if model == LLAMA and condition == "a":
        return forecast(0.9, 0.95, end)
    if model == LLAMA:
        p_a = 0.2 + 0.6 * truth.get(row["E_end"], 0.5) + 0.1 * (unit(item, "b1") - 0.5)
        p_b = 0.2 + 0.6 * truth.get(row["E_end90"], 0.5) + 0.1 * (unit(item, "b2") - 0.5)
        return forecast(p_a, p_b, end + 30)
    p_a = 0.3 + 0.2 * (unit(item, f"{condition}1") - 0.5)
    p_b = 0.5 + 0.2 * (unit(item, f"{condition}2") - 0.5)
    return forecast(p_a, p_b, 120)


def fails(model: str, condition: str, item: str) -> int:
    """How many attempts of this reading come back unparsable: 2 (failed), 1 (repaired), 0."""
    planned = {(LLAMA, "a"): 0.06, (LLAMA, "c"): 0.04, (DEEPSEEK, "probe"): 0.06}
    share = planned.get((model, condition), 0.0)
    draw = unit(item, f"fail-{condition}")
    return 2 if draw < share / 2 else 1 if draw < share else 0


class ScriptedSDK:
    """Stands in for the SDK client inside the real ``read.RouteCheckedClient``: it echoes the
    model it was asked for, names the pinned provider, and answers with ``reply(prompt)``."""

    def __init__(self, reply: Callable[[str], str]) -> None:
        self.reply = reply
        self.chat = self.completions = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        text = self.reply(kwargs["messages"][-1]["content"])
        return SimpleNamespace(
            model=kwargs["model"],
            provider="DeepInfra",
            openrouter_metadata=None,
            usage=SimpleNamespace(prompt_tokens=500, completion_tokens=60, total_tokens=560),
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        )


def make_run(plan: dict, run: dict, reply: Callable[[str], str], local: Path) -> None:
    """One run of the plan, read by the harness's reader around a scripted client and written
    by ``read.write_run`` with the fields the harness's command line adds to the manifest."""
    model, out_dir = run["model"], Path(plan["options"]["out_root"]) / run["run"]
    every = rd.load_items(Path(run["items"]))
    shard = rd.parse_shard(run["shard"])
    items = [i for i in every if shard is None or rd.shard_of(i.item_id, shard[1]) == shard[0]]
    items = items[: run["limit"]]
    track = None
    if run["track"]:
        track = rd.load_track_record(Path(plan["tracks"][run["track"]]["path"]))
    route = rd.ROUTES[model]
    client = rd.RouteCheckedClient(
        rd.route_endpoint(model), rd.served_as(model), route=route, sdk=ScriptedSDK(reply)
    )
    endpoint, transport = rd.build_transport(
        model,
        spend_log=out_dir / "spend_log.jsonl",
        spend_cap_usd=1000.0,
        max_physical_calls=10**6,
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
        route=route,
    )
    rows, status = rd.read_items(reader, items, samples=run["samples"])
    meta = {
        "run_name": run["run"],
        "status": status,
        "items_sha256": hashlib.sha256(Path(run["items"]).read_bytes()).hexdigest(),
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


def condition_of(line: str) -> str:
    return line.rsplit("-", 1)[1]


# --------------------------------------------------------------------------------------------
# The synthetic study
# --------------------------------------------------------------------------------------------


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_study(root: Path) -> SimpleNamespace:
    """The synthetic study on disk (see the module docstring), with what the tests need to
    work out the expected numbers on their own."""
    captures, out, vault, local = root / "captures", root / "out", root / "sealed", root / "local"
    items_dir, runs = out / "items", out / "read"
    for folder in (captures, vault, items_dir, runs, local):
        folder.mkdir(parents=True)
    lines = layout()
    manifest = pd.DataFrame(write_captures(captures, lines))
    manifest.to_csv(out / "capture_manifest.csv", index=False, lineterminator="\n")
    corpus = C.build_corpus(captures)
    train = corpus.outcomes[corpus.outcomes["period"] == "train"]
    built = D.build(
        D.Inputs(
            events=D.as_text(corpus.events),
            outcomes=D.require_train(D.as_text(train)),
            days=tuple(sorted({d.date() for d in corpus.captures.dates})),
            examples=(),
            source={"events": "synthetic captures"},
        )
    )
    paths = SimpleNamespace(
        statements=out / D.STATEMENTS.name,
        eligible=out / D.ELIGIBLE.name,
        counts=out / D.COUNTS.name,
        events=out / "events.csv.gz",
        sealed=vault / "outcomes_test.csv.gz",
        runs=runs,
        selections=out,
    )
    paths.statements.write_bytes(built.statements_gz)
    paths.eligible.write_text(built.eligible_csv, encoding="utf-8")
    paths.counts.write_text(built.report_text, encoding="utf-8")
    C.write_gz(corpus.events, paths.events)
    C.write_gz(corpus.outcomes[corpus.outcomes["period"] == "test"], paths.sealed)
    for name, text in built.item_text.items():
        (items_dir / name).write_text(text, encoding="utf-8")
    (items_dir / "track_fit.json").write_text(json.dumps(TRACK, indent=1))
    both = TRACK | {"split": "fit+dev", "through": "2022-12-31"}
    (items_dir / "track_fit_dev.json").write_text(json.dumps(both, indent=1))

    # what the scripted client knows about each statement, the synthetic outcomes included
    table = built.table
    listed = table[D.true(table["e3_eligible"])].sort_values("statement_group_id")
    listed = listed.reset_index(drop=True)
    sealed_rows = D.read_table(paths.sealed)
    filled = D.attach_outcomes(listed, sealed_rows)
    known = pd.concat([table[table["period"] == "train"], filled]).set_index(
        "statement_group_id", drop=False
    )
    by_presentation = {
        NDC.search(text).group(1): gid  # type: ignore[union-attr]
        for gid, text in zip(known["statement_group_id"], known["presentation"], strict=True)
    }

    def reply_for(model: str, condition: str) -> Callable[[str], str]:
        def reply(prompt: str) -> str:
            item = by_presentation[NDC.search(prompt).group(1)]  # type: ignore[union-attr]
            attempt = int("Your previous reply was:" in prompt)
            if attempt < fails(model, condition, item):
                return GARBAGE
            return json.dumps(answer(model, condition, known.loc[item].to_dict()))

        return reply

    options = lp.default_options(items_dir)
    options |= {"out_root": str(runs), "local_root": str(local)}
    plan = lp.make_plan(options)
    lp.plan_path(runs).parent.mkdir(parents=True)
    lp.plan_path(runs).write_text(lp.plan_text(plan), encoding="utf-8")
    for run in lp.select(plan, ["dev", "confirmatory"], models=rd.PRIMARIES):
        make_run(plan, run, reply_for(run["model"], condition_of(run["line"])), local)
    return SimpleNamespace(
        root=root,
        paths=paths,
        plan=plan,
        table=table,
        eligible=built.eligible,
        listed=listed,
        filled=filled.set_index("statement_group_id", drop=False),
        known=known,
        sealed_sha=file_sha(paths.sealed),
        eligible_sha=file_sha(paths.eligible),
    )


@pytest.fixture(scope="module")
def study(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    patch = pytest.MonkeyPatch()
    guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        built = build_study(tmp_path_factory.mktemp("study"))
        for model in rd.PRIMARIES:
            out = built.paths.selections / ev.SELECTION_NAME.format(model=model)
            assert ev.main(["dev", "--model", model, "--out", str(out), *dev_options(built)]) == 0
        # what the freeze amendment records: the hash of each selection file and of the
        # model-free predictions as the baselines command prints them
        built.selection_shas = selection_args(built.paths.selections)
        record = tmp_path_factory.mktemp("freeze") / "baselines.json"
        with redirect_stdout(io.StringIO()):
            assert ev.main(["baselines", "--out", str(record), *options(built, *OPEN)]) == 0
        built.baselines_sha = json.loads(record.read_text())["predictions_sha256"]
        yield built
    finally:
        patch.undo()


def selection_args(folder: Path) -> list[str]:
    """``--expect-selection-sha256`` for the selection files of both primaries in ``folder``."""
    return [
        f"{model}={file_sha(folder / ev.SELECTION_NAME.format(model=model))}"
        for model in rd.PRIMARIES
    ]


def dev_options(study: SimpleNamespace) -> list[str]:
    return options(study, "statements", "counts", "out-root")


CHECK = ("statements", "eligible", "counts", "out-root", "selections")
OPEN = ("statements", "eligible", "events", "counts")


def options(study: SimpleNamespace, *names: str, **replace: Any) -> list[str]:
    """The options of a command on the synthetic study: those named (all of the confirmatory
    command when none is), with the values of ``replace`` in place of the study's (None leaves
    an option out; a list gives the option once for each value)."""
    values: dict[str, Any] = {
        "statements": study.paths.statements,
        "eligible": study.paths.eligible,
        "events": study.paths.events,
        "counts": study.paths.counts,
        "out-root": study.paths.runs,
        "selections": study.paths.selections,
        "sealed": study.paths.sealed,
        "expect-sha256": study.sealed_sha,
        "expect-eligible-sha256": study.eligible_sha,
        "expect-baselines-sha256": getattr(study, "baselines_sha", None),
        "expect-selection-sha256": getattr(study, "selection_shas", None),
    }
    values.update({key.replace("_", "-"): value for key, value in replace.items()})
    chosen = names or tuple(values)
    return [
        str(part)
        for name in chosen
        if values[name] is not None
        for value in (values[name] if isinstance(values[name], list) else [values[name]])
        for part in (f"--{name}", value)
    ]


def fresh(tmp_path: Path, name: str = "results") -> Path:
    """A result file that does not exist yet, in a folder of this test that does."""
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    return folder / f"confirmatory_{len(list(folder.iterdir()))}.json"


def confirm(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    **replace: Any,
) -> tuple[dict[str, Any], str, str]:
    """Run the confirmatory command on the synthetic study: the record, the table and the
    printout."""
    out = fresh(tmp_path)
    capsys.readouterr()
    assert ev.main(["confirmatory", "--out", str(out), *options(study, **replace), *extra]) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    return json.loads(out.read_text()), out.with_suffix(".md").read_text(), printed.out


def refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    **replace: Any,
) -> str:
    """The reason of a refusal of the confirmatory command: nothing printed, nothing written,
    and no other error travelling with it."""
    out = fresh(tmp_path, "refused")
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        ev.main(["confirmatory", "--out", str(out), *options(study, **replace), *extra])
    assert isinstance(stop.value.code, str) and stop.value.code.startswith("refused: ")
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == ""
    assert list(out.parent.iterdir()) == []
    return stop.value.code


@contextmanager
def changed(*paths: Path) -> Iterator[None]:
    """Let a test rewrite or remove files of the shared study; every byte is put back."""
    before = {path: path.read_bytes() if path.is_file() else None for path in paths}
    try:
        yield
    finally:
        for path, data in before.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


def run_folder(study: SimpleNamespace, model: str, line: str) -> Path:
    return study.paths.runs / f"{line}-{model}"


def stored_rows(study: SimpleNamespace, model: str, line: str) -> list[dict]:
    readings = run_folder(study, model, line) / "readings.jsonl"
    return [json.loads(text) for text in readings.read_text().splitlines()]


@contextmanager
def rewritten(
    study: SimpleNamespace,
    model: str,
    line: str,
    change: Callable[[dict], Any],
    keep_manifest_hash: bool = False,
) -> Iterator[None]:
    """The stored rows of a run passed through ``change``: it returns the row, None to drop it,
    or a list of rows to put in its place. The hash of the readings is updated in the manifest
    unless asked not to."""
    folder = run_folder(study, model, line)
    readings, manifest = folder / "readings.jsonl", folder / "run_manifest.json"
    with changed(readings, manifest):
        kept: list[dict] = []
        for row in stored_rows(study, model, line):
            new = change(row)
            kept += new if isinstance(new, list) else [] if new is None else [new]
        readings.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in kept))
        if not keep_manifest_hash:
            record = json.loads(manifest.read_text())
            record["readings_sha256"] = file_sha(readings)
            manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        yield


@contextmanager
def manifest_with(study: SimpleNamespace, model: str, line: str, **change: Any) -> Iterator[None]:
    manifest = run_folder(study, model, line) / "run_manifest.json"
    with changed(manifest):
        manifest.write_text(json.dumps(json.loads(manifest.read_text()) | change))
        yield


@contextmanager
def json_with(path: Path, change: Callable[[dict], None]) -> Iterator[None]:
    with changed(path):
        record = json.loads(path.read_text())
        change(record)
        path.write_text(json.dumps(record))
        yield


@pytest.fixture(scope="module")
def base(study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """One confirmatory run on the untouched synthetic study, for the tests that only read it."""
    out = tmp_path_factory.mktemp("base") / "confirmatory.json"
    patch, printed = pytest.MonkeyPatch(), io.StringIO()
    guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        with redirect_stdout(printed):
            assert ev.main(["confirmatory", "--out", str(out), *options(study)]) == 0
    finally:
        patch.undo()
    return SimpleNamespace(
        report=json.loads(out.read_text()),
        json_text=out.read_text(),
        table=out.with_suffix(".md").read_text(),
        printed=printed.getvalue(),
    )


def entry_of(report: dict, hypothesis: str, model: str) -> dict:
    return next(e for e in report["family"] if (e["hypothesis"], e["model"]) == (hypothesis, model))


# --------------------------------------------------------------------------------------------
# What the tests work out on their own from the scripted answers and the synthetic outcomes
# --------------------------------------------------------------------------------------------


def truth(study: SimpleNamespace) -> pd.DataFrame:
    """The two horizon events of each eligible statement as 1, 0 or missing."""
    events = {"yes": 1.0, "no": 0.0}
    filled = study.filled
    return pd.DataFrame(
        {
            "y_a": filled["E_end"].map(events),
            "y_b": filled["E_end90"].map(events),
            "episode": filled["episode_id"],
            "day": filled["event_date"],
        }
    )


def given(study: SimpleNamespace, model: str, condition: str) -> pd.DataFrame:
    """The scripted probabilities and median of a model's condition on the eligible list."""
    rows = []
    for row in study.filled.to_dict("records"):
        reading = answer(model, condition, row)
        rows.append(
            [
                reading["p_by_horizon_a"],
                reading["p_by_horizon_b"],
                reading["days_to_recovery"]["q50"],
            ]
        )
    return pd.DataFrame(rows, index=study.filled.index, columns=["p_a", "p_b", "q50"])


def brier(pred: pd.DataFrame, y: pd.DataFrame) -> pd.Series:
    return ((pred["p_a"] - y["y_a"]) ** 2 + (pred["p_b"] - y["y_b"]) ** 2) / 2


# --------------------------------------------------------------------------------------------
# The synthetic study is what the tests assume
# --------------------------------------------------------------------------------------------


def test_the_layout_gives_a_study_of_the_planned_shape(study: SimpleNamespace) -> None:
    table, filled = study.table, study.filled
    assert len(study.eligible) == 320 and study.eligible["episode_id"].nunique() == 40
    assert int((study.eligible["probe"].astype(int)).sum()) == 300
    scoreable = filled[D.true(filled["scoreable"])]
    assert 200 < len(scoreable) < len(filled)
    after = {day: scoreable[scoreable["event_date"] > day] for day in ("2023-12-31", "2024-12-31")}
    assert len(after["2023-12-31"]) >= ev.MIN_SLICE > len(after["2024-12-31"]) > 0
    dev = table[(table["split"] == "dev") & D.true(table["scoreable"])]
    assert len(dev) > 80 and 0 not in D.mix(dev).values()
    names = sorted(p.name for p in study.paths.runs.iterdir() if p.name != "_launch")
    assert len(names) == 2 * (3 + 4) and f"e4-probe-{DEEPSEEK}" in names
    # the stored rows are the harness's own: parsed, repaired and failed readings among them
    statuses = [row["status"] for row in stored_rows(study, LLAMA, "e3-a")]
    assert {"ok", "repaired", "failed"} == set(statuses) and len(statuses) == 320
    planned = [fails(LLAMA, "a", item) for item in study.filled.index]
    assert statuses.count("failed") == planned.count(2) > 0
    assert statuses.count("repaired") == planned.count(1) > 0
    assert {row["echo"] for row in stored_rows(study, DEEPSEEK, "e4-probe")} == {"ok"}
    assert all(
        lp.run_state(study.plan, run) == "finished"
        for run in lp.select(study.plan, ["dev", "confirmatory"], models=rd.PRIMARIES)
    )


def test_no_test_can_reach_the_sealed_folder_the_network_or_a_key() -> None:
    assert "no_default" in ev.SEALED.parts and not ev.SEALED.exists()
    assert ev.arguments(["confirmatory"]).sealed == ev.SEALED
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("example.invalid", 443))
    with pytest.raises(AssertionError, match="API key"):
        rd.route_endpoint(LLAMA).resolve_key()


# --------------------------------------------------------------------------------------------
# Holm and the p-value procedures
# --------------------------------------------------------------------------------------------


def test_holm_on_a_hand_worked_example() -> None:
    # sorted: .001 .012 .03 .04 .2 1; times 6 5 4 3 2 1: .006 .06 .12 .12 .4 1; running maximum
    p = [0.04, 0.001, 1.0, 0.03, 0.2, 0.012]
    assert ev.holm(p) == pytest.approx([0.12, 0.006, 1.0, 0.12, 0.4, 0.06])
    assert [value < 0.05 for value in ev.holm(p)] == [False, True, False, False, False, False]
    # the step-down never lets a larger p-value have a smaller adjusted one: .03, then
    # max(.03, 2 x .011) = .03
    assert ev.holm([0.011, 0.010, 0.5]) == pytest.approx([0.03, 0.03, 0.5])
    # a test that is not evaluable enters with p = 1 and still counts in the multipliers
    assert ev.holm([0.009, 1.0, 1.0, 1.0, 1.0, 1.0]) == pytest.approx([0.054, 1, 1, 1, 1, 1])
    assert ev.holm([0.008, 1.0, 1.0, 1.0, 1.0, 1.0])[0] == pytest.approx(0.048)
    assert ev.holm([0.5, 0.5]) == [1.0, 1.0] and ev.holm([]) == []


def test_sign_flip_enumerates_every_pattern_of_a_few_episodes() -> None:
    # episode sums 3, 1, -1: the totals under the 8 sign patterns are 5, 3, 3, 1, -1, -3, -3,
    # -5; three are at least the observed 3, six are at least 3 in absolute value
    flips = ev.sign_flip(np.array([3.0, 1.0, -1.0]))
    assert flips == {
        "one_sided": 3 / 8,
        "one_sided_lower": 7 / 8,
        "two_sided": 6 / 8,
        "patterns": 8,
        "exact": True,
    }
    # all sums positive: only the observed pattern reaches the total, and its mirror image
    flips = ev.sign_flip(np.array([1.0, 2.0, 3.0, 4.0]))
    assert (flips["one_sided"], flips["one_sided_lower"], flips["two_sided"]) == (1 / 16, 1, 2 / 16)
    # a total of zero is the least extreme there is
    assert ev.sign_flip(np.array([2.0, -2.0]))["two_sided"] == 1.0
    assert ev.sign_flip(np.array([-1.0, -2.0, -3.0]))["one_sided"] == 1.0
    assert ev.sign_flip(np.array([-1.0, -2.0, -3.0]))["one_sided_lower"] == 1 / 8


def test_studentised_sign_flip_on_a_case_worked_by_hand() -> None:
    """Three episodes of 1, 2 and 1 statements whose sums are 3, 1 and -1: every one of the 8
    sign patterns is a data set, and its statistic is its mean over its cluster-robust standard
    error, worked out here one pattern at a time."""
    sums, sizes = np.array([3.0, 1.0, -1.0]), np.array([1.0, 2.0, 1.0])

    def t_of(signed: np.ndarray) -> float:
        mean = signed.sum() / 4
        se = np.sqrt(3 / 2 * ((signed - mean * sizes) ** 2).sum()) / 4
        return mean / se

    observed = t_of(sums)  # mean 3/4; residuals 2.25, -0.5, -1.75; t = 0.8464
    assert observed == pytest.approx(0.75 / (np.sqrt(1.5 * (2.25**2 + 0.5**2 + 1.75**2)) / 4))
    flipped = [t_of(np.array([a, b, c]) * sums) for c in (1, -1) for b in (1, -1) for a in (1, -1)]
    got = ev.sign_flip_t(sums, sizes)
    assert got["exact"] is True and got["patterns"] == 8
    assert got["one_sided"] == sum(t >= observed - 1e-12 for t in flipped) / 8
    assert got["one_sided_lower"] == sum(t <= observed + 1e-12 for t in flipped) / 8
    assert got["two_sided"] == sum(abs(t) >= abs(observed) - 1e-12 for t in flipped) / 8
    # the eight statistics are +-0.8464, +-0.7263, +-0.2421 and +-1.7609: two reach the observed
    # one, seven are at most it, four are as large in absolute value (the plain sign-flip test
    # on the same sums gives 3/8 one-sided)
    assert (got["one_sided"], got["one_sided_lower"], got["two_sided"]) == (2 / 8, 7 / 8, 4 / 8)
    # the same statistic as the bootstrap-t
    taken = P.cluster_draws(3, 50, ev.SEED).astype(float)
    assert ev.studentised(sums, sizes, taken)["t"] == pytest.approx(observed)
    # many episodes: 10,000 drawn patterns, the observed one counted with them
    rng = np.random.default_rng(4)
    many, counts = rng.normal(0.3, 1.0, size=20), rng.integers(1, 6, size=20).astype(float)
    drawn = ev.sign_flip_t(many, counts, draws=500)
    signs = 1 - 2 * np.random.default_rng(ev.SEED).integers(0, 2, size=(500, 20))
    stats = [t_of_many(row * many, counts) for row in signs]
    t = t_of_many(many, counts)
    assert drawn["patterns"] == 500 and drawn["exact"] is False
    assert drawn["one_sided"] == pytest.approx((1 + sum(s >= t for s in stats)) / 501)
    assert drawn["two_sided"] == pytest.approx((1 + sum(abs(s) >= abs(t) for s in stats)) / 501)
    # patterns without variance: four equal sums, whose residuals are all zero as observed and
    # with every sign flipped, give statistics of plus and minus infinity
    even = ev.sign_flip_t(np.array([1.0, 1.0, 1.0, 1.0]), np.ones(4))
    assert even["one_sided"] == 1 / 16 and even["two_sided"] == 2 / 16


def t_of_many(signed: np.ndarray, sizes: np.ndarray) -> float:
    groups, n = len(signed), sizes.sum()
    mean = signed.sum() / n
    return float(mean / (np.sqrt(groups / (groups - 1) * ((signed - mean * sizes) ** 2).sum()) / n))


def test_the_larger_of_two_procedures_side_by_side() -> None:
    bootstrap_t = {"one_sided": 0.004, "one_sided_lower": 0.997, "two_sided": 0.008}
    flips_t = {"one_sided": 0.011, "one_sided_lower": 0.990, "two_sided": 0.021}
    assert ev.larger_of(bootstrap_t, flips_t) == {
        "one_sided": 0.011,
        "one_sided_lower": 0.997,
        "two_sided": 0.022,
    }
    # the two-sided p-value comes from the larger one-sided ones, not from the two-sided ones
    assert ev.larger_of(flips_t, bootstrap_t)["two_sided"] == 0.022
    lower = {"one_sided": 0.9, "one_sided_lower": 0.6, "two_sided": 1.0}
    assert ev.larger_of(lower, lower)["two_sided"] == 1.0  # at most 1


def test_sign_flip_draws_patterns_for_many_episodes() -> None:
    rng = np.random.default_rng(5)
    sums = rng.normal(0.4, 1.0, size=14)
    flips = ev.sign_flip(sums, draws=4000, seed=ev.SEED)
    assert flips["patterns"] == 4000 and flips["exact"] is False
    # the same draws, counted by hand: the observed pattern is added to both counts
    signs = 1 - 2 * np.random.default_rng(ev.SEED).integers(0, 2, size=(4000, 14))
    totals = [float((row * sums).sum()) for row in signs]
    above = sum(total >= sums.sum() - 1e-9 for total in totals)
    beyond = sum(abs(total) >= abs(sums.sum()) - 1e-9 for total in totals)
    assert flips["one_sided"] == pytest.approx((1 + above) / 4001)
    assert flips["two_sided"] == pytest.approx((1 + beyond) / 4001)
    # and close to the exact p-value over all 2^14 patterns
    every = 1 - 2 * ((np.arange(2**14)[:, None] >> np.arange(14)) & 1)
    exact = float(((every @ sums) >= sums.sum() - 1e-9).mean())
    assert abs(flips["one_sided"] - exact) < 0.02
    # at most 13 episodes are enumerated, whatever the number of draws
    assert ev.sign_flip(sums[:13], draws=10)["patterns"] == 2**13
    assert ev.EXACT_FLIPS_UP_TO == 13 and 2**13 <= ev.DRAWS < 2**14


def by_hand_t(d: np.ndarray, clusters: list[str], taken: np.ndarray) -> dict[str, float]:
    """The bootstrap-t from its definition, one draw at a time."""
    names = sorted(set(clusters))
    members = {name: d[[c == name for c in clusters]] for name in names}

    def mean_and_se(drawn: list[np.ndarray]) -> tuple[float, float]:
        n = sum(len(part) for part in drawn)
        mean = sum(part.sum() for part in drawn) / n
        spread = sum((part.sum() - mean * len(part)) ** 2 for part in drawn)
        return mean, float(np.sqrt(len(drawn) / (len(drawn) - 1) * spread)) / n

    delta, se = mean_and_se([members[name] for name in names])
    t = delta / se
    stars = []
    for counts in taken:
        drawn = [members[name] for name, k in zip(names, counts, strict=True) for _ in range(k)]
        mean, error = mean_and_se(drawn)
        stars.append((mean - delta) / error)
    upper = (1 + sum(star >= t for star in stars)) / (len(stars) + 1)
    lower = (1 + sum(star <= t for star in stars)) / (len(stars) + 1)
    beyond = (1 + sum(abs(star) >= abs(t) for star in stars)) / (len(stars) + 1)
    low, high = np.quantile(stars, [0.025, 0.975])
    reach = np.quantile(np.abs(stars), 0.95)
    return {
        "se": se,
        "t": t,
        "one_sided": upper,
        "one_sided_lower": lower,
        "two_sided": min(1.0, 2 * min(upper, lower)),
        "two_sided_symmetric": beyond,
        "ci95": [delta - high * se, delta - low * se],
        "ci95_symmetric": [delta - reach * se, delta + reach * se],
    }


def test_studentised_bootstrap_against_its_definition() -> None:
    rng = np.random.default_rng(11)
    clusters = [
        name
        for name, size in zip("abcdefg", (2, 1, 3, 2, 5, 1, 4), strict=True)
        for _ in range(size)
    ]
    d = rng.normal(0.15, 0.3, size=len(clusters))
    sums, sizes = P.cluster_sums(d, clusters)
    taken = P.cluster_draws(len(sizes), 600, ev.SEED)
    got = ev.studentised(sums[:, 0], sizes, taken.astype(float))
    want = by_hand_t(d, clusters, taken)
    for key in ("se", "t", "one_sided", "one_sided_lower", "two_sided", "two_sided_symmetric"):
        assert got[key] == pytest.approx(want[key]), key
    assert got["ci95"] == pytest.approx(want["ci95"])
    assert got["ci95_symmetric"] == pytest.approx(want["ci95_symmetric"])
    # the symmetric p-value is not twice a tail: here it differs from the equal-tailed one
    assert got["two_sided_symmetric"] != got["two_sided"]
    # the standard error is the clustered one of the power code, and with episodes of one
    # statement each it is the usual standard error of a mean
    assert got["se"] == pytest.approx(W.clustered_variance(d, clusters)["se_clustered"])
    alone = [str(k) for k in range(len(d))]
    sums, sizes = P.cluster_sums(d, alone)
    single = ev.studentised(sums[:, 0], sizes, P.cluster_draws(len(d), 50, ev.SEED).astype(float))
    assert single["se"] == pytest.approx(d.std(ddof=1) / np.sqrt(len(d)))


def test_studentised_bootstrap_without_variance() -> None:
    sizes = np.array([2.0, 3.0, 1.0])
    taken = P.cluster_draws(3, 99, ev.SEED).astype(float)
    # every difference is 0.3: no draw is more extreme than a certain positive effect
    constant = ev.studentised(0.3 * sizes, sizes, taken)
    assert constant["se"] == 0 and constant["t"] == np.inf
    assert constant["one_sided"] == pytest.approx(1 / 100)
    assert constant["two_sided_symmetric"] == pytest.approx(1 / 100)
    assert constant["one_sided_lower"] == 1.0
    # every difference is 0: nothing to see
    nothing = ev.studentised(0.0 * sizes, sizes, taken)
    assert nothing["t"] == 0 and nothing["one_sided"] == 1.0 and nothing["two_sided"] == 1.0
    assert nothing["two_sided_symmetric"] == 1.0 and nothing["ci95_symmetric"] == [0.0, 0.0]
    # two episodes: half of the draws take one episode twice and have no variance; their
    # statistic is infinite, by the sign of the drawn mean minus the observed one
    two = ev.studentised(np.array([1.0, -3.0]), np.array([2.0, 2.0]), taken[:, :2] * 0 + [2, 0])
    assert two["t"] == pytest.approx(-0.5) and two["ci95"] is None
    assert two["one_sided"] == 1.0 and two["one_sided_lower"] == pytest.approx(1 / 100)


def test_studentised_bootstrap_on_draws_worked_by_hand() -> None:
    """Three episodes of 1, 2 and 1 statements whose sums are 3, 1 and -1 (the case of the
    studentised sign-flip test above): delta 3/4, residuals 2.25, -0.5 and -1.75, standard error
    sqrt(1.5 * 8.375) / 4 = 0.8861, t = 0.8464. Five draws, each worked out by hand:

    * the three episodes once each: the sample itself, t* = 0;
    * the first twice and the second: mean 7/4, residuals 1.25, 1.25, -2.5, se* = 0.9375,
      t* = 1 / 0.9375 = 16/15;
    * the second and the third twice: mean -1/4, residuals 1.5, -0.75, -0.75, se* = 0.5625,
      t* = -1 / 0.5625 = -16/9;
    * the first and the third twice: mean 1/3, residuals 8/3, -4/3, -4/3, se* = 4/3,
      t* = (1/3 - 3/4) / (4/3) = -5/16;
    * the first and the second twice: mean 1, residuals 2, -1, -1, se* = 0.6,
      t* = 0.25 / 0.6 = 5/12.
    """
    sums, sizes = np.array([3.0, 1.0, -1.0]), np.array([1.0, 2.0, 1.0])
    taken = np.array([[1, 1, 1], [2, 1, 0], [0, 1, 2], [1, 0, 2], [1, 2, 0]], dtype=float)
    stars = np.array([0.0, 16 / 15, -16 / 9, -5 / 16, 5 / 12])
    se = float(np.sqrt(1.5 * 8.375)) / 4
    got = ev.studentised(sums, sizes, taken)
    assert got["se"] == pytest.approx(se) and got["t"] == pytest.approx(0.75 / se)
    assert got["t"] == pytest.approx(0.8464, abs=5e-5)
    # one draw reaches the observed statistic, four are at most it, two are as large in size
    assert got["one_sided"] == pytest.approx(2 / 6)
    assert got["one_sided_lower"] == pytest.approx(5 / 6)
    assert got["two_sided"] == pytest.approx(4 / 6)  # equal-tailed: twice the smaller tail
    assert got["two_sided_symmetric"] == pytest.approx(3 / 6)
    low, high = np.quantile(stars, [0.025, 0.975])
    reach = float(np.quantile(np.abs(stars), 0.95))
    assert got["ci95"] == pytest.approx([0.75 - high * se, 0.75 - low * se])
    assert got["ci95_symmetric"] == pytest.approx([0.75 - reach * se, 0.75 + reach * se])
    assert got["ci95"] == pytest.approx([-0.1376, 2.1954], abs=5e-5)
    # two more draws without variance: the first episode three times (mean 3, above the
    # observed 3/4: plus infinity) and the third three times (mean -1: minus infinity)
    more = np.vstack([taken, [[3, 0, 0], [0, 0, 3]]])
    got = ev.studentised(sums, sizes, more)
    assert (got["one_sided"], got["one_sided_lower"]) == pytest.approx((3 / 8, 6 / 8))
    assert (got["two_sided"], got["two_sided_symmetric"]) == pytest.approx((6 / 8, 5 / 8))
    assert got["ci95"] is None and got["ci90_symmetric"] is None
    # the larger of this and the studentised sign-flip test of the same sums (2/8 and 7/8)
    flips_t = ev.sign_flip_t(sums, sizes)
    assert ev.larger_of(got, flips_t) == {
        "one_sided": pytest.approx(3 / 8),
        "one_sided_lower": pytest.approx(7 / 8),
        "two_sided": pytest.approx(6 / 8),
    }


SIZE_CHECK_NAMES = {
    "percentile": "percentile",
    "studentised": "studentised",
    "studentised_symmetric": "studentised_symmetric",
    "sign_flip_t": "sign_flip_t",
    "larger_of_studentised_and_sign_flip_t": "max_t",
    "sign_flip": "sign_flip",
}
"""Each procedure of the evaluator and its name in ``size_check.py``."""


@pytest.mark.parametrize("episodes", [2, 3, 7, 13, 14, 60])
def test_every_procedure_gives_the_p_values_of_the_size_check(episodes: int) -> None:
    """The evaluator imports nothing from ``size_check.py``; on the same paired differences
    (continuous, mostly zero, few distinct values, skewed) both give the same p-values on each
    side, with the registered draws and sign patterns. One case is left out: differences that
    cancel in a draw to a rounding error, which the evaluator counts as a zero, on both sides
    (``test_a_draw_whose_differences_cancel_counts_on_both_sides``), and the size check on the
    side of the error's sign."""
    assert set(SIZE_CHECK_NAMES) == set(ev.PROCEDURES)
    assert SC.DRAWS == SC.FLIPS == ev.DRAWS and SC.SEED == ev.SEED
    rng = np.random.default_rng(episodes)
    sizes = rng.integers(1, 25, size=episodes)
    clusters = [f"g{g:03d}" for g in range(episodes) for _ in range(sizes[g])]
    n = len(clusters)
    shapes = {
        "continuous": rng.normal(0.01, 0.2, size=n),
        "mostly zero": (rng.random(n) < 0.1) * rng.normal(0, 0.3, size=n),
        "few values": rng.choice([-0.18, 0.0, 0.07, 0.32], size=n),
        "skewed": rng.exponential(0.1, size=n) - 0.08,
    }
    sides = {"one_sided": "p_upper", "one_sided_lower": "p_lower", "two_sided": "p_two_sided"}
    for shape, d in shapes.items():
        mine = ev.contrast(d + 0.4, np.full(n, 0.4), clusters)
        theirs = SC.contrast_tests(d, clusters)
        for name, other in SIZE_CHECK_NAMES.items():
            for side, key in sides.items():
                assert mine["p_values"][name][side] == pytest.approx(
                    theirs[other][key], abs=1e-12
                ), (shape, name, side)
        assert mine["ci95"] == pytest.approx(
            [theirs["percentile"]["low"], theirs["percentile"]["high"]], abs=1e-12
        )
        if mine["studentised"]["ci95"] is not None:
            for name, ends in (
                ("ci95", "studentised"),
                ("ci95_symmetric", "studentised_symmetric"),
            ):
                assert mine["studentised"][name] == pytest.approx(
                    [theirs[ends]["low"], theirs[ends]["high"]], abs=1e-9
                )


def paired(
    effect: float, seed: int = 3, episodes: int = 30
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Losses of a comparator and a tested predictor over episodes of unequal size, the
    comparator worse by ``effect`` on average."""
    rng = np.random.default_rng(seed)
    clusters, comparator, tested = [], [], []
    for g in range(episodes):
        size = int(rng.integers(1, 12))
        shift = rng.normal(0, 0.05)
        for _ in range(size):
            loss = float(rng.uniform(0.1, 0.4))
            clusters.append(f"g{g:02d}")
            tested.append(loss)
            comparator.append(loss + effect + shift + float(rng.normal(0, 0.05)))
    return np.array(comparator), np.array(tested), clusters


def test_contrast_gives_the_registered_bootstrap_and_every_p_value() -> None:
    comparator, tested, clusters = paired(0.1)
    result = ev.contrast(comparator, tested, clusters)
    assert result["evaluable"] and (result["statements"], result["episodes"]) == (len(clusters), 30)
    assert result["delta"] == pytest.approx(float((comparator - tested).mean()))
    assert result["loss_comparator"] - result["loss_tested"] == pytest.approx(result["delta"])
    # the percentile procedure is the one of PLAN section 6, counted by hand on the draws
    draws = P.bootstrap_means(np.column_stack([comparator, tested]), clusters)
    delta = draws[:, 0] - draws[:, 1]
    below = (1 + int((delta <= 0).sum())) / 10_001
    above = (1 + int((delta >= 0).sum())) / 10_001
    assert result["p_values"]["percentile"] == {
        "one_sided": pytest.approx(below),
        "one_sided_lower": pytest.approx(above),
        "two_sided": pytest.approx(min(1.0, 2 * min(below, above))),
    }
    assert result["ci95"] == pytest.approx(list(np.quantile(delta, [0.025, 0.975])))
    assert result["ci90"] == pytest.approx(list(np.quantile(delta, [0.05, 0.95])))
    # the other procedures see the same differences, and the bootstrap-t the same draws
    sums, sizes = P.cluster_sums(comparator - tested, clusters)
    flips = ev.sign_flip(sums[:, 0])
    flips_t = ev.sign_flip_t(sums[:, 0], sizes)
    assert result["p_values"]["sign_flip"] == {key: flips[key] for key in ev.SIDES}
    assert result["p_values"]["sign_flip_t"] == {key: flips_t[key] for key in ev.SIDES}
    by_t = ev.studentised(sums[:, 0], sizes, P.cluster_draws(30, ev.DRAWS, ev.SEED).astype(float))
    assert result["p_values"]["studentised"] == {key: by_t[key] for key in ev.SIDES}
    assert result["p_values"]["studentised_symmetric"] == {
        "one_sided": by_t["one_sided"],
        "one_sided_lower": by_t["one_sided_lower"],
        "two_sided": by_t["two_sided_symmetric"],
    }
    assert result["p_values"]["larger_of_studentised_and_sign_flip_t"] == ev.larger_of(
        by_t, flips_t
    )
    assert result["studentised"]["ci95"] == by_t["ci95"]
    assert result["studentised"]["ci90_symmetric"] == by_t["ci90_symmetric"]
    assert list(result["p_values"]) == list(ev.PROCEDURES)
    # a planted effect is found by every procedure, in its direction only
    for source in ev.P_VALUE_SOURCES:
        assert ev.registered_p(result, 1, source) < 0.001, source
        assert ev.registered_p(result, 2, source) < 0.002, source
    backwards = ev.contrast(tested, comparator, clusters)
    assert backwards["delta"] == pytest.approx(-result["delta"])
    for source in ev.P_VALUE_SOURCES:
        assert ev.registered_p(backwards, 1, source) > 0.999, source
        assert ev.registered_p(backwards, 2, source) < 0.002, source


def test_contrast_does_not_find_an_effect_that_is_not_there() -> None:
    comparator, tested, clusters = paired(0.0)
    result = ev.contrast(comparator, tested, clusters)
    for source in ev.P_VALUE_SOURCES:
        assert ev.registered_p(result, 1, source) > 0.05, source
        assert ev.registered_p(result, 2, source) > 0.05, source
    assert result["ci95"][0] < 0 < result["ci95"][1]
    # identical losses: the contrast is zero in every draw, and nothing is rejected
    same = ev.contrast(tested, tested, clusters)
    assert same["delta"] == 0 and same["ci95"] == [0.0, 0.0]
    assert {
        ev.registered_p(same, sides, source) for sides in (1, 2) for source in ev.P_VALUE_SOURCES
    } == {1.0}


def test_a_draw_whose_differences_cancel_counts_on_both_sides() -> None:
    """PLAN section 6 counts a draw with a contrast of zero on both sides (``<= 0`` and ``>=
    0``). Seven episodes whose paired differences are tenths that cancel in many draws (0.3 -
    0.2 against 0.1 - 0.2, and so on): the p-values are those of the same draws counted in exact
    fractions, although in floating point most of these sums are a rounding error away from
    zero."""
    pairs = {
        "a": [("0.3", "0.2")],
        "b": [("0.1", "0.2")],
        "c": [("0.7", "0.4"), ("0.5", "0.6")],
        "d": [("0.2", "0.4")],
        "e": [("0.9", "0.3")],
        "f": [("0.1", "0.4"), ("0.1", "0.4")],
        "g": [("0.5", "0.4")],
    }
    clusters = [name for name, rows in pairs.items() for _ in rows]
    comparator = np.array([float(c) for rows in pairs.values() for c, _ in rows])
    tested = np.array([float(t) for rows in pairs.values() for _, t in rows])
    exact = [sum(Fraction(c) - Fraction(t) for c, t in rows) for rows in pairs.values()]
    assert exact == [Fraction(k, 10) for k in (1, -1, 2, -2, 6, -6, 1)]
    taken = P.cluster_draws(7, 2000, ev.SEED)
    totals = [sum(int(k) * s for k, s in zip(row, exact, strict=True)) for row in taken]
    below, above = sum(t <= 0 for t in totals), sum(t >= 0 for t in totals)
    zero = below + above - 2000
    assert zero > 50
    result = ev.contrast(comparator, tested, clusters, draws=2000)
    assert result["p_values"]["percentile"] == {
        "one_sided": (1 + below) / 2001,
        "one_sided_lower": (1 + above) / 2001,
        "two_sided": min(1.0, 2 * min(1 + below, 1 + above) / 2001),
    }
    draws = ev.drawn_deltas(comparator - tested, clusters, 2000, ev.SEED)
    assert int((draws == 0).sum()) == zero
    assert [float(d) for d in np.sign(draws)] == [float((t > 0) - (t < 0)) for t in totals]
    # the same sums in floating point: some of the zeros are off by a rounding error, which
    # would put them on one side only
    sums, _ = P.cluster_sums(comparator - tested, clusters)
    floats = taken.astype(float) @ sums[:, 0]
    assert int((floats == 0).sum()) < zero and np.abs(floats[draws == 0]).max() < 1e-14
    # a draw is not taken for zero because it is small: the same differences a million times
    # smaller cancel in the same draws and in no other
    small = ev.drawn_deltas((comparator - tested) * 1e-6, clusters, 2000, ev.SEED)
    assert int((small == 0).sum()) == zero


def test_a_draw_of_episodes_on_which_two_predictors_agree_is_a_zero() -> None:
    """The shape of H2: the two sides give the same loss wherever the model's reading is the
    rule's. A draw that takes none of the episodes where they differ has a contrast of exactly
    zero and counts on both sides, so the p-value cannot fall below the share of such draws."""
    rng = np.random.default_rng(12)
    sizes = rng.integers(1, 9, size=12)
    clusters = [f"g{g:02d}" for g in range(12) for _ in range(sizes[g])]
    tested = rng.uniform(0.05, 0.6, size=len(clusters))
    differs = np.isin(clusters, ["g03", "g07"])
    comparator = np.where(differs, tested + rng.uniform(0.05, 0.3, size=len(clusters)), tested)
    taken = P.cluster_draws(12, ev.DRAWS, ev.SEED)
    neither = int(((taken[:, 3] == 0) & (taken[:, 7] == 0)).sum())
    assert neither > 1000  # about (10/12)^12 of the draws
    result = ev.contrast(comparator, tested, clusters)
    assert result["delta"] > 0
    assert result["p_values"]["percentile"] == {
        "one_sided": (1 + neither) / 10_001,
        "one_sided_lower": 1.0,
        "two_sided": 2 * (1 + neither) / 10_001,
    }
    assert result["ci95"][0] == 0.0 and result["ci95"][1] > 0


def test_contrast_is_not_evaluable_without_two_episodes() -> None:
    one = ev.contrast([0.4, 0.5, 0.6], [0.1, 0.1, 0.1], ["g", "g", "g"])
    assert one["evaluable"] is False and one["reason"] == "fewer than two episodes"
    assert one["delta"] == pytest.approx(0.4) and "p_values" not in one
    none = ev.contrast([], [], [])
    assert none == {
        "statements": 0,
        "episodes": 0,
        "evaluable": False,
        "reason": "no scoreable statement",
    }
    assert ev.contrast([0.4, 0.5], [0.1, 0.1], ["g", "h"])["evaluable"] is True
    with pytest.raises(ValueError, match="a loss is missing"):
        ev.contrast([0.4, float("nan")], [0.1, 0.1], ["g", "h"])


def test_contrast_is_the_same_on_every_run() -> None:
    comparator, tested, clusters = paired(0.02, seed=8)
    assert ev.contrast(comparator, tested, clusters) == ev.contrast(comparator, tested, clusters)
    other = ev.contrast(comparator, tested, clusters, seed=1)
    assert other["ci95"] != ev.contrast(comparator, tested, clusters)["ci95"]
    assert (ev.SEED, ev.DRAWS) == (20261001, 10_000)


# --------------------------------------------------------------------------------------------
# The two registered constants
# --------------------------------------------------------------------------------------------


def test_the_registered_constants_are_the_plans_wording_today() -> None:
    """Both constants are set once before registration. This test holds them at the candidate
    the plan words today; changing a constant means changing it here too."""
    assert ev.P_VALUE_SOURCES == (
        "percentile",
        "studentised",
        "studentised_symmetric",
        "sign_flip_t",
        "larger_of_studentised_and_sign_flip_t",
    )
    assert ev.PROCEDURES[:-1] == ev.P_VALUE_SOURCES and ev.PROCEDURES[-1] == "sign_flip"
    assert ev.H3_COMPARATORS == ("gbm_structured", "base_rate", "better_on_dev")
    assert (ev.P_VALUE_SOURCE, ev.H3_COMPARATOR) == ("percentile", "base_rate")
    record = ev.registered_record()
    assert (record["p_value_source"], record["h3_comparator"]) == ("percentile", "base_rate")
    assert record["p_value_source_candidates"] == list(ev.P_VALUE_SOURCES)
    assert record["p_value_procedures_reported"] == list(ev.PROCEDURES)
    assert record["sign_flip_patterns"] == {"every_pattern_up_to_episodes": 13, "drawn": 10_000}
    # nothing outside this file sets either constant: no option names them and no variable of
    # the environment is read
    source = Path(ev.__file__).read_text(encoding="utf-8")
    assert "os.environ" not in source and "getenv" not in source
    for command in ("dev", "check", "confirmatory", "baselines"):
        options = set(vars(ev.arguments([command])))
        assert not [name for name in options if "source" in name or "comparator" in name]
    assert (record["familywise_alpha"], record["tests_in_the_family"]) == (0.05, 6)
    assert (record["h2_margin"], record["probe_alpha"], record["min_slice_scoreable"]) == (
        0.02,
        0.05,
        50,
    )
    assert record["cutoff_month_ends"] == {LLAMA: "2023-12-31", DEEPSEEK: "2024-12-31"}
    assert tuple(record["primaries"]) == rd.PRIMARIES == S.PRIMARY


def test_registered_p_takes_the_named_procedure() -> None:
    result = {
        "p_values": {
            name: {"one_sided": k / 100, "one_sided_lower": 0.9, "two_sided": k / 50}
            for k, name in enumerate(ev.PROCEDURES, start=1)
        }
    }
    got = [ev.registered_p(result, sides, s) for s in ev.P_VALUE_SOURCES for sides in (1, 2)]
    assert got == [0.01, 0.02, 0.02, 0.04, 0.03, 0.06, 0.04, 0.08, 0.05, 0.10]
    # the sensitivity analysis is reported, never a source of the registered p-values
    for source, sides in (("bootstrap", 1), ("percentile", 3), ("sign_flip", 1)):
        with pytest.raises(ValueError):
            ev.registered_p(result, sides, source)


def test_comparator_rules() -> None:
    structured_better = {"gbm_structured": 0.21, "base_rate": 0.24}
    base_better = {"gbm_structured": 0.24, "base_rate": 0.20}
    for losses in (structured_better, base_better):
        assert ev.comparator_choice(losses, "gbm_structured") == "gbm_structured"
        assert ev.comparator_choice(losses, "base_rate") == "base_rate"
    assert ev.comparator_choice(structured_better, "better_on_dev") == "gbm_structured"
    assert ev.comparator_choice(base_better, "better_on_dev") == "base_rate"
    tie = {"gbm_structured": 0.2, "base_rate": 0.2}
    assert ev.comparator_choice(tie, "better_on_dev") == "gbm_structured"
    with pytest.raises(ValueError, match="unknown H3 comparator rule"):
        ev.comparator_choice(tie, "the best one")
    # the same rule picks the model's best condition: the lowest loss, the earlier at a tie
    assert ev.lowest({"a": 0.3, "b": 0.2, "c": 0.25}, ev.CONDITIONS) == "b"
    assert ev.lowest({"a": 0.2, "b": 0.2, "c": 0.2}, ev.CONDITIONS) == "a"
    assert ev.lowest({"a": 0.3, "b": 0.2, "c": 0.2}, ev.CONDITIONS) == "b"


@pytest.mark.parametrize("source", ev.P_VALUE_SOURCES)
def test_the_p_value_source_in_force_enters_holm_and_the_record(
    study: SimpleNamespace,
    base: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    monkeypatch.setattr(ev, "P_VALUE_SOURCE", source)
    report, table, _ = confirm(study, tmp_path, capsys)
    assert report["registered"]["p_value_source"] == source and f"p-values: {source}." in table
    for entry, before in zip(report["family"], base.report["family"], strict=True):
        side = "one_sided" if entry["sides"] == 1 else "two_sided"
        assert entry["p"] == entry["p_values"][source][side]
        # the estimate, its intervals and every p-value do not depend on the constant
        for key in ("delta", "ci95", "ci90", "p_values"):
            assert entry[key] == before[key]
    adjusted = ev.holm([entry["p"] for entry in report["family"]])
    assert [entry["p_holm"] for entry in report["family"]] == pytest.approx(adjusted, abs=5e-6)
    assert report["probe"][LLAMA]["p"] == report["probe"][LLAMA]["p_values"][source]["one_sided"]
    two = [e for e in report["family"] if e["sides"] == 2 and e["hypothesis"] == "H2"]
    values = {e["model"]: [e["p_values"][s]["two_sided"] for s in ev.PROCEDURES] for e in two}
    assert len(set(values[DEEPSEEK])) >= 5  # the procedures do differ
    # the secondaries take the source in force too
    for model in rd.PRIMARIES:
        h3 = entry_of(report, "H3", model)
        assert (
            report["secondaries"]["delta_gbm"][model]["p"] == (h3["beside"]["gbm_structured"]["p"])
        )
        assert h3["beside"]["base_rate"]["p"] == h3["p"]


# --------------------------------------------------------------------------------------------
# Readings as predictions
# --------------------------------------------------------------------------------------------


def stored(reading: dict | None, kind: str = "predictive", **more: Any) -> dict:
    status = "ok" if reading is not None else "failed"
    return {"reading": reading, "status": status, "fallback": rd.fallback_for(kind, status), **more}


def test_predictive_readings_are_taken_as_given_and_failures_take_the_base_rate() -> None:
    first = pd.DataFrame(
        {
            "event_date": ["2024-01-15", "2024-02-15", "2024-03-15"],
            "horizon_a": ["2024-03-31", "2024-04-30", "2024-05-31"],
            "horizon_b": ["2024-06-29", "2024-07-29", "2024-08-29"],
        },
        index=["s1", "s2", "s3"],
    )
    base = pd.DataFrame(
        [[0.11, 0.22, 1, 2, 3, 4, 5], [0.33, 0.44, 6, 7, 8, 9, 10], [0.5, 0.6, 11, 12, 13, 14, 15]],
        index=first.index,
        columns=list(P.PREDICTION_COLUMNS),
        dtype=float,
    )
    asked = [
        {"a": a, "b": b, "rule": "stated_end"}
        for a, b in zip(first["horizon_a"], first["horizon_b"], strict=True)
    ]
    rows = {
        "s1": stored(forecast(0.7, 0.4, 100), horizons=asked[0]),
        "s2": stored(None, horizons=asked[1]),
        "s3": stored(forecast(0.2, 0.9, 40), horizons=asked[2]),
    }
    pred, parsed, counts = ev.predictive(rows, first, base)
    assert pred.loc["s1"].tolist() == [0.7, 0.4, 50, 100, 150, 200, 250]  # kept although b < a
    assert pred.loc["s2"].tolist() == base.loc["s2"].tolist()  # the base rate's output
    assert pred.loc["s3"].tolist() == [0.2, 0.9, 20, 40, 60, 80, 100]
    assert parsed.tolist() == [True, False, True]
    assert counts == {"replaced_by_base_rate": 1, "p_b_below_p_a": 1}
    assert ev.asked_elsewhere(rows, first) == 0
    # a row that asked about another date than the statement's horizon is counted
    rows["s3"] = stored(forecast(0.2, 0.9, 40), horizons=asked[2] | {"b": "2024-08-30"})
    rows["s2"] = stored(None, horizons=asked[1] | {"rule": "fallback"})
    assert ev.asked_elsewhere(rows, first) == 2
    del rows["s3"]  # a row that is not there is another problem, counted elsewhere
    assert ev.asked_elsewhere(rows, first) == 1
    # the probe is asked about 90 and 180 days after the statement date, whatever the notice
    probe = {
        "s1": stored(
            forecast(0.1, 0.2, 30), horizons={"a": "2024-04-14", "b": "2024-07-13", "rule": "probe"}
        ),
        "s2": stored(None, horizons={"a": "2024-05-15", "b": "2024-08-13", "rule": "probe"}),
        "s3": stored(forecast(0.1, 0.2, 30), horizons=asked[2]),
    }
    assert ev.probe_horizons("2024-01-15") == ("2024-04-14", "2024-07-13")
    assert ev.asked_elsewhere(probe, first, probe=True) == 1
    assert ev.asked_elsewhere(probe, first) == 2


def test_literal_readings_give_the_end_of_a_stated_period_or_nothing() -> None:
    first = pd.DataFrame({"event_date": ["2024-01-15"] * 7}, index=list("abcdefg"))
    rows = {
        "a": stored(literal("recovery", "2024-03-01", "2024-03-31"), "literal"),
        "b": stored(literal("next_delivery", "2024-02-01", "2024-02-10"), "literal"),
        "c": stored(literal("recovery", "", ""), "literal"),  # ABSTAIN
        "d": stored(None, "literal"),  # failed twice: counts as ABSTAIN
        "e": stored(literal("depletion", "2024-03-01", "2024-03-31"), "literal"),
        "f": stored(literal("none", "2024-03-01", "2024-03-31"), "literal"),
        "g": stored(literal("recovery", "2023-12-01", "2023-12-31"), "literal"),  # already past
    }
    days, parsed, counts = ev.literal_days(rows, first)
    assert days.tolist()[:2] == [76.0, 26.0] and days["g"] == -15.0
    assert days[["c", "d", "e", "f"]].isna().all()
    assert parsed.tolist() == [True, True, True, False, True, True, True]
    assert counts == {
        "failed_counted_as_abstain": 1,
        "abstain": 1,
        "period_of_another_statement_type": 2,
    }
    assert rows["d"]["fallback"] == "abstain" and ev.PERIOD_TYPES == ("recovery", "next_delivery")


@pytest.fixture(scope="module")
def opened(study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """The study as the confirmatory command holds it before the sealed file is read."""
    patch = pytest.MonkeyPatch()
    guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        counts = json.loads(study.paths.counts.read_text())
        found = ev.gather(
            study.paths.runs,
            D.read_table(study.paths.eligible),
            study.listed.set_index("statement_group_id"),
            counts,
            study.paths.selections,
            file_sha(study.paths.statements),
            {},
        )
        assert found.problems == []
        table = D.load_statements(study.paths.statements)
        held, sha = ev.open_study(table, study.listed, found, {})
        fitted, _ = ev.refit(P.prepare(table))
    finally:
        patch.undo()
    return SimpleNamespace(study=held, sha=sha, fitted=fitted, frame=P.prepare(table), found=found)


def test_condition_c_goes_through_the_calibrator_of_the_refit(
    study: SimpleNamespace, opened: SimpleNamespace
) -> None:
    held, ids = opened.study, list(study.filled.index)
    rows = opened.frame.loc[ids]
    rules = held.predictions["rules_plus_slip"]
    assert rules.equals(opened.fitted["rules_plus_slip"].predict(rows))
    mine = held.predictions[f"{DEEPSEEK}:c"]
    kinds = {i: answer(DEEPSEEK, "c", study.filled.loc[i].to_dict()) for i in ids}
    same = [i for i in ids if kinds[i]["statement_type"] == "next_delivery"]
    later = [
        i
        for i in ids
        if kinds[i]["statement_type"] == "recovery" and kinds[i]["interval"] != "ABSTAIN"
    ]
    none = [
        i
        for i in ids
        if kinds[i]["interval"] == "ABSTAIN" or kinds[i]["statement_type"] == "depletion"
    ]
    assert min(len(same), len(later), len(none)) > 10 and len(same) + len(later) + len(none) == 320
    # the rule's own period: exactly rules plus slip
    assert mine.loc[same].equals(rules.loc[same])
    # a period that ends 31 days later: the slip curve read 31 days earlier
    slips = opened.fitted["rules_plus_slip"]
    for item in later[:25]:
        row = rows.loc[item]
        curve = slips.basis(row["form"], row["revision"])[1].slip
        assert mine.loc[item, "p_a"] == pytest.approx(float(curve.cdf(-31.0)))
        assert mine.loc[item, "p_b"] == pytest.approx(float(curve.cdf(59.0)))
    assert (mine.loc[later, "p_a"] <= rules.loc[later, "p_a"]).all()
    # no stated period: the no-date table by listing age
    assert mine.loc[none].equals(slips.no_date.predict(rows.loc[none]))
    record = held.runs[DEEPSEEK]["c"]
    assert record["abstain"] == sum(kinds[i]["interval"] == "ABSTAIN" for i in ids)
    assert record["period_of_another_statement_type"] == sum(
        kinds[i]["statement_type"] == "depletion" for i in ids
    )


def test_failed_readings_are_replaced_and_counted(
    study: SimpleNamespace, opened: SimpleNamespace
) -> None:
    held, ids = opened.study, list(study.filled.index)
    failed = [i for i in ids if fails(LLAMA, "a", i) == 2]
    repaired = [i for i in ids if fails(LLAMA, "a", i) == 1]
    assert failed and repaired
    mine, base = held.predictions[f"{LLAMA}:a"], held.predictions["base_rate"]
    assert mine.loc[failed].equals(base.loc[failed])
    assert (mine.loc[repaired, "p_a"] == 0.9).all()  # a repaired reading is a reading
    assert held.parsed[f"{LLAMA}:a"].sum() == 320 - len(failed)
    record = held.runs[LLAMA]["a"]
    assert record["replaced_by_base_rate"] == record["by_status"]["failed"] == len(failed)
    assert record["by_status"]["repaired"] == len(repaired)
    assert record["parse_failure_rate"] == pytest.approx(len(failed) / 320)
    # condition (b) follows the outcome event by event, so its second probability is often
    # below its first; such answers are kept as given and counted
    assert held.runs[LLAMA]["b"]["p_b_below_p_a"] > 0
    given_b = given(study, LLAMA, "b")
    assert held.predictions[f"{LLAMA}:b"][["p_a", "p_b"]].equals(given_b[["p_a", "p_b"]])
    assert held.runs[LLAMA]["b"]["p_b_below_p_a"] == int((given_b["p_b"] < given_b["p_a"]).sum())
    # a failed literal reading counts as ABSTAIN
    lost = [i for i in ids if fails(LLAMA, "c", i) == 2]
    assert held.runs[LLAMA]["c"]["failed_counted_as_abstain"] == len(lost) > 0
    rows = opened.frame.loc[lost]
    no_date = opened.fitted["rules_plus_slip"].no_date.predict(rows)
    assert held.predictions[f"{LLAMA}:c"].loc[lost].equals(no_date)
    # a failed probe reading takes the base rate at the probe's horizons, 90 and 180 days
    probe_ids = held.probe_ids
    gone = [i for i in probe_ids if fails(DEEPSEEK, "probe", i) == 2]
    assert gone and held.probe[DEEPSEEK].loc[gone].equals(held.probe["base_rate"].loc[gone])
    at_90 = opened.fitted["base_rate"].predict(opened.frame.loc[gone].assign(h_a=90.0, h_b=180.0))
    assert held.probe["base_rate"].loc[gone].equals(at_90)


def test_typed_outcomes_are_those_of_the_sealed_rows(study: SimpleNamespace) -> None:
    filled = study.filled.reset_index(drop=True)
    frame = ev.typed_outcomes(filled)
    want = truth(study)
    assert frame.index.tolist() == sorted(want.index) and set(frame["period"]) == {"test"}
    assert frame["y_a"].equals(want["y_a"].loc[frame.index])
    assert frame["y_b"].equals(want["y_b"].loc[frame.index])
    assert frame["scoreable"].tolist() == D.true(study.filled["scoreable"]).tolist()
    assert set(frame["ttr_kind"]) <= set(P.TTR_KINDS)
    # a variant scores the horizon events of another bracket
    other = filled.assign(E_end_all="no", E_end90_all="yes")
    assert set(ev.typed_outcomes(other, "_all")["y_a"]) == {0.0}
    assert set(ev.typed_outcomes(other, "_all")["y_b"]) == {1.0}
    # the predictors' own frame still refuses an outcome on a test-period statement
    with pytest.raises(ValueError, match="outcome columns filled on test-period statements"):
        P.prepare(filled)


# --------------------------------------------------------------------------------------------
# The dev command
# --------------------------------------------------------------------------------------------


def selection(study: SimpleNamespace, model: str) -> dict:
    path = study.paths.selections / ev.SELECTION_NAME.format(model=model)
    return json.loads(path.read_text())


def test_dev_command_scores_the_three_conditions_and_selects(study: SimpleNamespace) -> None:
    table = study.table
    dev = table[(table["split"] == "dev") & D.true(table["scoreable"])]
    dev = dev.set_index("statement_group_id", drop=False)
    events = {"yes": 1.0, "no": 0.0}
    y = pd.DataFrame({"y_a": dev["E_end"].map(events), "y_b": dev["E_end90"].map(events)})
    for model in rd.PRIMARIES:
        record = selection(study, model)
        assert (
            record["model"] == model and record["registered"]["h3_comparator"] == ev.H3_COMPARATOR
        )
        assert record["dev"]["scoreable_statements"] == len(dev) == record["dev"]["statements_read"]
        assert record["dev"]["scoreable_by_E_end_and_E_end90"] == D.mix(dev)
        assert record["dev"]["dated_statements_not_read"] == record["dev"][
            "dated_statements"
        ] - len(dev)
        assert record["inputs"]["statements_sha256"] == file_sha(study.paths.statements)
        assert record["fitted_on"]["split"] == "fit"
        losses = {}
        for condition in ("a", "b"):
            answers = pd.DataFrame(
                [answer(model, condition, row) for row in dev.to_dict("records")], index=dev.index
            ).rename(columns={"p_by_horizon_a": "p_a", "p_by_horizon_b": "p_b"})
            losses[condition] = float(brier(answers, y).mean())
        entry = record["conditions"]
        if model == DEEPSEEK:  # every answer parsed: the loss is the one of the answers
            assert entry["a"]["primary_brier"] == pytest.approx(losses["a"], abs=1e-6)
        assert entry["b"]["primary_brier"] == pytest.approx(losses["b"], abs=1e-6)
        chosen = record["selection"]
        assert chosen["primary_brier"] == {c: entry[c]["primary_brier"] for c in ev.CONDITIONS}
        assert chosen["selected"] == ev.lowest(chosen["primary_brier"], ev.CONDITIONS)
        for condition in ev.CONDITIONS:
            low, high = entry[condition]["ci95"]
            assert low <= entry[condition]["primary_brier"] <= high
            # the dev runs read the scoreable statements only, so the bounds add nothing
            bounds = entry[condition]["bounds_statements_read"]
            assert set(bounds.values()) == {entry[condition]["primary_brier"]}
            assert entry[condition]["line"] == f"dev-{condition}" and entry[condition][
                "rows"
            ] == len(dev)
            # the selection file names the dev readings it was made from, by their hash
            read_from = run_folder(study, model, f"dev-{condition}") / "readings.jsonl"
            assert entry[condition]["readings_sha256"] == {
                read_from.parent.name: file_sha(read_from)
            }
    assert selection(study, LLAMA)["selection"]["selected"] == "b"
    planned = [fails(LLAMA, "a", item) for item in dev.index]
    status = selection(study, LLAMA)["conditions"]["a"]["by_status"]
    assert (status.get("failed", 0), status.get("repaired", 0)) == (
        planned.count(2),
        planned.count(1),
    )
    assert planned.count(2) + planned.count(1) > 0
    # the literal reading of the first primary is the rule's: condition (c) is rules plus slip
    first = selection(study, LLAMA)
    lost = first["conditions"]["c"]["failed_counted_as_abstain"]
    assert lost == [fails(LLAMA, "c", item) for item in dev.index].count(2)
    assert first["conditions"]["c"]["primary_brier"] == pytest.approx(
        first["model_free"]["rules_plus_slip"]["primary_brier"], abs=0.02 if lost else 1e-6
    )
    # the model-free losses are those of the power code on the same table
    _, rows, free = W.fit_and_predict(P.prepare(table))
    scoreable = rows[rows["scoreable"]]
    want = W.primary_losses(scoreable, free).mean()
    for name in G.PREDICTORS:
        assert first["model_free"][name]["primary_brier"] == pytest.approx(want[name], abs=1e-6)
    comparator = first["h3_comparator"]
    assert comparator["primary_brier"] == {
        name: first["model_free"][name]["primary_brier"] for name in ev.COMPARATOR_CANDIDATES
    }
    assert comparator["under_each_rule"] == {
        rule: ev.comparator_choice(comparator["primary_brier"], rule) for rule in ev.H3_COMPARATORS
    }
    assert comparator["rule"] == "base_rate" == comparator["selected"]


def run_dev(study: SimpleNamespace, out: Path, model: str = LLAMA, **replace: Any) -> int:
    names = ("statements", "counts", "out-root")
    return ev.main(["dev", "--model", model, "--out", str(out), *options(study, *names, **replace)])


def test_a_failed_dev_answer_takes_the_base_rate_of_the_fit_split(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PLAN section 4 in the dev runs: a predictive answer that fails is replaced by the output
    of the base-rate predictor, here the one fitted on the fit split, and counted."""
    table = study.table
    dev = table[(table["split"] == "dev") & D.true(table["scoreable"])]
    dev = dev.set_index("statement_group_id", drop=False)
    lost = sorted(dev.index)[:12]

    def fail(row: dict) -> dict:
        if row["item_id"] not in lost:
            return row
        return row | {"status": "failed", "reading": None, "fallback": "base_rate"}

    out = tmp_path / "selection.json"
    with rewritten(study, DEEPSEEK, "dev-a", fail):
        assert run_dev(study, out, DEEPSEEK) == 0
    capsys.readouterr()
    entry = json.loads(out.read_text())["conditions"]["a"]
    assert entry["by_status"] == {"failed": 12, "ok": len(dev) - 12}
    assert entry["replaced_by_base_rate"] == 12
    assert entry["parse_failure_rate"] == pytest.approx(12 / len(dev), abs=1e-6)
    _, _, free = W.fit_and_predict(P.prepare(table))
    events = {"yes": 1.0, "no": 0.0}
    y = pd.DataFrame({"y_a": dev["E_end"].map(events), "y_b": dev["E_end90"].map(events)})
    answers = pd.DataFrame(
        [answer(DEEPSEEK, "a", row) for row in dev.to_dict("records")], index=dev.index
    ).rename(columns={"p_by_horizon_a": "p_a", "p_by_horizon_b": "p_b"})
    answers.loc[lost, ["p_a", "p_b"]] = free["base_rate"].loc[lost, ["p_a", "p_b"]]
    assert entry["primary_brier"] == pytest.approx(float(brier(answers, y).mean()), abs=1e-6)
    # not the output of another predictor, and not the answers themselves
    other = answers.copy()
    other.loc[lost, ["p_a", "p_b"]] = free["gbm_structured"].loc[lost, ["p_a", "p_b"]]
    assert abs(float(brier(other, y).mean()) - entry["primary_brier"]) > 1e-5
    before = selection(study, DEEPSEEK)["conditions"]["a"]["primary_brier"]
    assert abs(before - entry["primary_brier"]) > 1e-5


@pytest.mark.parametrize("rule", ev.H3_COMPARATORS)
def test_the_comparator_rule_in_force_is_recorded_and_used(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rule: str,
) -> None:
    monkeypatch.setattr(ev, "H3_COMPARATOR", rule)
    for model in rd.PRIMARIES:
        assert run_dev(study, tmp_path / ev.SELECTION_NAME.format(model=model), model) == 0
    record = json.loads((tmp_path / ev.SELECTION_NAME.format(model=LLAMA)).read_text())
    losses = record["h3_comparator"]["primary_brier"]
    # on the synthetic dev split the base rate is the better of the two
    assert losses["base_rate"] < losses["gbm_structured"]
    want = {
        "gbm_structured": "gbm_structured",
        "base_rate": "base_rate",
        "better_on_dev": "base_rate",
    }
    assert record["h3_comparator"]["selected"] == want[rule]
    assert record["registered"]["h3_comparator"] == rule
    report, table, _ = confirm(
        study,
        tmp_path,
        capsys,
        selections=tmp_path,
        expect_selection_sha256=selection_args(tmp_path),
    )
    assert (
        report["registered"]["h3_comparator"] == rule and report["h3"]["comparator"] == want[rule]
    )
    for model in rd.PRIMARIES:
        entry = entry_of(report, "H3", model)
        assert entry["comparator"] == want[rule]
        assert entry["loss_comparator"] == pytest.approx(
            report["losses"][want[rule]]["primary_brier"], abs=1e-6
        )
    assert f"H3 comparator rule: {rule}." in table
    # beside H3 stand the contrasts with both predictors that read no text, whatever the rule
    entry = entry_of(report, "H3", LLAMA)
    assert list(entry["beside"]) == ["gbm_structured", "base_rate"]
    assert entry["beside"][want[rule]]["delta"] == entry["delta"]
    assert entry["beside"][want[rule]]["ci95"] == entry["ci95"]
    # the flag looks at the other one; Delta_GBM is the structured-only model's, whatever rule
    other = next(name for name in ev.COMPARATOR_CANDIDATES if name != want[rule])
    assert entry["beats_both_comparators"] is bool(
        entry["holds"] and entry["delta"] > 0 and entry["beside"][other]["ci95"][0] > 0
    )
    delta_gbm = report["secondaries"]["delta_gbm"][LLAMA]
    assert delta_gbm["comparator"] == "gbm_structured"
    assert delta_gbm["ci95"] == entry["beside"]["gbm_structured"]["ci95"]
    if rule != "base_rate":
        # the files recorded under the rule of the plan's wording are refused under another
        why = refused(study, tmp_path, capsys)
        assert "was recorded under another H3 comparator rule" in why
        named_other = "names another H3 comparator than the rule in force gives" in why
        assert named_other is (want[rule] != "base_rate")


def test_dev_command_refusals(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "selection.json"

    def stops(match: str, model: str = LLAMA, **replace: Any) -> None:
        capsys.readouterr()
        with pytest.raises(SystemExit, match=match) as stop:
            run_dev(study, out, model, **replace)
        assert str(stop.value.code).startswith("refused: ") and not out.exists()
        assert capsys.readouterr().out == ""

    stops("--model takes a primary model", model="gemma-3-27b")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ev, "P_VALUE_SOURCE", "sign_flip")  # reported, never a registered source
        stops("a registered constant has a value outside its candidates")
    with manifest_with(study, LLAMA, "dev-b", complete=False):
        stops("dev runs are not ready.*dev-b.*not finished")
    with rewritten(study, DEEPSEEK, "dev-c", lambda row: None if row["item_id"] < "S4" else row):
        stops("dev-c: the item set is not the registered list", model=DEEPSEEK)
    empty = tmp_path / "no_runs"
    empty.mkdir()
    stops("no plan of the runs", out_root=empty)
    other = tmp_path / "counts.json"
    other.write_text(json.dumps({"outputs": {D.STATEMENTS.name: {"sha256": "0" * 16}}}))
    stops("not the files the counts file", counts=other)
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "statements.csv.gz").write_bytes(study.paths.statements.read_bytes())
    stops("sealed folder", statements=sealed / "statements.csv.gz")
    # an item list of another build than the statement table
    with json_with(
        study.paths.counts,
        lambda r: r["outputs"]["items"]["dev_scoreable.jsonl"].update(sha256="0" * 16),
    ):
        stops("item file of list 'dev'")
    # nothing is overwritten
    assert run_dev(study, out) == 0
    before = out.read_bytes()
    with pytest.raises(SystemExit, match="already there, and nothing is overwritten"):
        run_dev(study, out)
    assert out.read_bytes() == before
    assert before == (study.paths.selections / ev.SELECTION_NAME.format(model=LLAMA)).read_bytes()


# --------------------------------------------------------------------------------------------
# The completeness check
# --------------------------------------------------------------------------------------------


def check(
    study: SimpleNamespace, capsys: pytest.CaptureFixture[str], *extra: str, **replace: Any
) -> tuple[int, str]:
    capsys.readouterr()
    code = ev.main(["check", *options(study, *CHECK, **replace), *extra])
    return code, capsys.readouterr().out


def test_check_says_ready_and_reads_no_outcome(
    study: SimpleNamespace, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    read: list[str] = []
    real = S.file_bytes

    def file_bytes(path: Path, what: str) -> bytes:
        read.append(what)
        return real(path, what)

    monkeypatch.setattr(S, "file_bytes", file_bytes)
    monkeypatch.setattr(ev, "refit", lambda frame: pytest.fail("check fits nothing"))
    monkeypatch.setattr(D, "attach_outcomes", lambda *a, **k: pytest.fail("check reads no outcome"))
    code, out = check(study, capsys, "--expect-eligible-sha256", study.eligible_sha)
    assert code == 0 and "nothing is missing for the confirmatory evaluation" in out
    assert "the sealed file" not in read and "missing:" not in out
    assert out.count("; ready") == 8 and "NOT ready" not in out
    assert f"{LLAMA} H3 selection: b" in out and f"{DEEPSEEK} e4-probe: 300 rows read; ready" in out
    assert "not checked here: the sealed outcome file" in out
    # the statement table is read for its first-sight columns only
    table, sha = ev.first_sight_table(study.paths.statements)
    assert list(table.columns) == list(D.FIRST_SIGHT_COLUMNS) and sha == file_sha(
        study.paths.statements
    )
    assert not set(table.columns) & set(D.OUTCOME_COLUMNS)
    # the default sealed path of the tests does not exist, and the check never looked
    assert not ev.SEALED.exists()


def watched_vault(
    study: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, list[str]]:
    """A copy of the synthetic sealed file in a folder of its own, made the default sealed
    path, and the list of every look the file system is asked for at anything in that folder
    from now on (stat, open, listing)."""
    sealed = tmp_path / "vault" / "outcomes_test.csv.gz"
    sealed.parent.mkdir()
    sealed.write_bytes(study.paths.sealed.read_bytes())
    monkeypatch.setattr(ev, "SEALED", sealed)
    touched: list[str] = []

    def watched(real: Callable[..., Any]) -> Callable[..., Any]:
        def inner(path: Any, *args: Any, **kwargs: Any) -> Any:
            if "vault" in str(path):
                touched.append(str(path))
            return real(path, *args, **kwargs)

        return inner

    for name in ("stat", "lstat", "open", "scandir", "listdir"):
        monkeypatch.setattr(os, name, watched(getattr(os, name)))
    monkeypatch.setattr(io, "open", watched(io.open))
    return sealed, touched


def test_nothing_looks_at_the_sealed_path_before_the_runs_are_complete(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The open commands, and a confirmatory command that is refused for its runs, do not read
    the sealed file, and do not ask the file system whether it is there."""
    sealed, touched = watched_vault(study, tmp_path, monkeypatch)
    assert check(study, capsys)[0] == 0
    out = tmp_path / "selection.json"
    assert run_dev(study, out) == 0
    assert ev.main(["baselines", "--out", str(tmp_path / "b.json"), *options(study, *OPEN)]) == 0
    with manifest_with(study, LLAMA, "e3-a", complete=False):
        why = refused(study, tmp_path, capsys, sealed=None)
    assert "is not finished (partial)" in why and touched == []
    # the same watch sees the sealed file when a complete study is evaluated
    report, _, _ = confirm(study, tmp_path, capsys, sealed=None)
    assert touched and report["inputs"]["sealed_outcomes_sha256"] == study.sealed_sha
    # and an open input may not be the sealed file itself, wherever it lies
    touched.clear()
    why = refused(study, tmp_path, capsys, sealed=None, statements=sealed)
    assert "--statements would be read from a sealed folder" in why and touched == []


def test_a_plan_that_names_a_sealed_file_is_not_followed(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The completeness check hashes the item files and the track records a plan names. A plan
    that names the sealed file, or anything in a sealed folder, is refused before any file it
    names is looked at, by every command."""
    sealed, touched = watched_vault(study, tmp_path, monkeypatch)
    plan = lp.plan_path(study.paths.runs)
    elsewhere = tmp_path / "sealed" / "items.jsonl"
    changes: tuple[Callable[[dict], None], ...] = (
        lambda r: r["lists"]["e3"].update(path=str(sealed)),
        lambda r: r["lists"]["dev"].update(path=str(sealed)),
        lambda r: r["tracks"]["fit+dev"].update(path=str(sealed)),
        lambda r: r["lists"]["probe"].update(path=str(elsewhere)),
        lambda r: r["options"].update(out_root=str(sealed)),
    )
    said = "the plan of the runs names a path in a sealed folder; none of its files is read"
    for change in changes:
        with json_with(plan, change):
            code, out = check(study, capsys)
            why = refused(study, tmp_path, capsys, sealed=None)
            with pytest.raises(SystemExit) as stop:
                run_dev(study, tmp_path / "selection.json")
        assert code == 3 and f"missing: {said}" in out and said in why
        assert stop.value.code == f"refused: {said}" and touched == []
    # the same for a sealed file given by its own option, wherever it lies
    other = tmp_path / "elsewhere" / "outcomes.csv.gz"
    with json_with(plan, lambda r: r["lists"]["e3"].update(path=str(other))):
        assert said in refused(study, tmp_path, capsys, sealed=other)
    # a file that is no plan is said to be none
    with changed(plan):
        plan.write_text("[1, 2")
        code, out = check(study, capsys)
        assert code == 3 and "is not a plan of launch.py" in out
        plan.write_text(json.dumps({"options": {}}))
        assert "is not a plan of launch.py" in refused(study, tmp_path, capsys, sealed=None)
    assert touched == [] and check(study, capsys)[0] == 0


def test_check_lists_what_is_missing(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with manifest_with(study, DEEPSEEK, "e3-b", complete=False):
        code, out = check(study, capsys)
    assert code == 3 and "NOT ready: no evaluation against test outcomes" in out
    assert f"missing: {DEEPSEEK} e3-b: run e3-b-{DEEPSEEK} is not finished (partial)" in out
    assert f"{DEEPSEEK} e3-b: 320 rows read; NOT ready" in out and out.count("; ready") == 7
    gone = study.paths.selections / ev.SELECTION_NAME.format(model=LLAMA)
    with changed(gone):
        gone.unlink()
        code, out = check(study, capsys)
    assert code == 3 and f"{LLAMA} H3 selection: missing" in out and "no H3 selection at" in out
    code, out = check(study, capsys, "--expect-eligible-sha256", "0" * 64)
    assert code == 3 and "the eligible list is not the file of --expect-eligible-sha256" in out
    code, out = check(study, capsys, out_root=tmp_path)
    assert code == 3 and "missing: no plan of the runs" in out
    # a primary declared not evaluable is not asked for its runs
    with manifest_with(study, DEEPSEEK, "e3-b", complete=False):
        code, out = check(study, capsys, "--not-evaluable", f"{DEEPSEEK}=its route was withdrawn")
    assert code == 0 and f"{DEEPSEEK}: not evaluable, declared on the command line: its" in out
    assert not [i for i in study.filled.index if i in out]


# --------------------------------------------------------------------------------------------
# Refusals of the confirmatory command
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
    return read


def test_a_wrong_or_missing_hash_is_refused_and_the_sealed_file_is_not_parsed(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ev, "unseal", lambda *a, **k: pytest.fail("the sealed rows were parsed"))
    sealed_bytes, real_table = study.paths.sealed.read_bytes(), ev.table_of

    def table_of(data: bytes, gzipped: bool) -> pd.DataFrame:
        assert data != sealed_bytes, "the sealed bytes were parsed"
        return real_table(data, gzipped)

    monkeypatch.setattr(ev, "table_of", table_of)
    wrong = "0" * 64
    why = refused(study, tmp_path, capsys, expect_sha256=wrong)
    assert "the sealed file is not the expected file" in why
    assert study.sealed_sha[:16] in why and "expected 0000000000000000" in why
    for value in (None, "", "abc", study.sealed_sha[:15], "z" * 64):
        why = refused(study, tmp_path, capsys, expect_sha256=value)
        assert "--expect-sha256 takes a sha256 or its first 16 or more hex characters" in why
    why = refused(study, tmp_path, capsys, expect_eligible_sha256=wrong)
    assert "the eligible list is not the expected file" in why
    why = refused(study, tmp_path, capsys, expect_eligible_sha256=None)
    assert "--expect-eligible-sha256 takes a sha256" in why
    # the hash of another file of the study does not open the sealed one
    why = refused(study, tmp_path, capsys, expect_sha256=study.eligible_sha)
    assert "the sealed file is not the expected file" in why
    # a file that is not there
    why = refused(study, tmp_path, capsys, sealed=tmp_path / "nothing.csv.gz")
    assert "the sealed file cannot be read (FileNotFoundError)" in why


def test_the_first_sixteen_characters_of_a_hash_are_enough(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    report, _, _ = confirm(
        study,
        tmp_path,
        capsys,
        expect_sha256=study.sealed_sha[:16].upper(),
        expect_eligible_sha256=study.eligible_sha[:20],
    )
    assert report["inputs"]["sealed_outcomes_sha256"] == study.sealed_sha
    assert report["family"] == base.report["family"]


def test_the_sealed_file_is_read_last_behind_everything_else(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    real_bytes, real_gather, real_open = S.file_bytes, ev.gather, ev.open_study
    real_unseal, real_evaluate = ev.unseal, ev.evaluate

    def file_bytes(path: Path, what: str) -> bytes:
        order.append(what)
        return real_bytes(path, what)

    def logged(name: str, call: Callable[..., Any]) -> Callable[..., Any]:
        def inner(*args: Any, **kwargs: Any) -> Any:
            order.append(name)
            return call(*args, **kwargs)

        return inner

    monkeypatch.setattr(S, "file_bytes", file_bytes)
    monkeypatch.setattr(ev, "gather", logged("completeness", real_gather))
    monkeypatch.setattr(ev, "open_study", logged("predictions", real_open))
    monkeypatch.setattr(ev, "unseal", logged("unseal", real_unseal))
    monkeypatch.setattr(ev, "evaluate", logged("evaluate", real_evaluate))
    confirm(study, tmp_path, capsys)
    opened_at = order.index("the sealed file")
    before = order[:opened_at]
    assert before[-2:] == ["completeness", "predictions"]
    assert set(before[:-2]) == {
        "the eligible list",
        "the statement table",
        "the events table",
        "the counts file",
    }
    assert order[opened_at + 1 : opened_at + 3] == ["unseal", "evaluate"]
    assert order.count("the sealed file") == 1


def test_an_output_that_exists_or_lies_in_a_sealed_folder_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    def stops(out: Path | None, match: str) -> None:
        args = ["confirmatory", *options(study)] + ([] if out is None else ["--out", str(out)])
        with pytest.raises(SystemExit, match=match) as stop:
            ev.main(args)
        assert str(stop.value.code).startswith("refused: ")

    stops(None, "--out is required")
    there = tmp_path / "there.json"
    there.write_text("{}")
    stops(there, "already there, and nothing is overwritten")
    assert there.read_text() == "{}"
    table = tmp_path / "new.md"
    table.write_text("kept")
    stops(tmp_path / "new.json", "already there, and nothing is overwritten")
    assert table.read_text() == "kept" and not (tmp_path / "new.json").exists()
    stops(tmp_path / "no_such_folder" / "r.json", "folder of the output does not exist")
    vault = tmp_path / "sealed"
    vault.mkdir()
    stops(vault / "r.json", "--out lies in a sealed folder")
    stops(tmp_path / "r.md", "cannot end in .md")
    assert list(vault.iterdir()) == [] and sealed_unread == []
    assert capsys.readouterr().out == ""


def test_an_open_input_in_a_sealed_folder_or_of_another_build_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    vault = tmp_path / "sealed"
    vault.mkdir()
    for name in OPEN:
        copy = vault / getattr(study.paths, name).name
        copy.write_bytes(getattr(study.paths, name).read_bytes())
        why = refused(study, tmp_path, capsys, **{name: copy})
        assert "would be read from a sealed folder; only --sealed names a sealed file" in why
    why = refused(study, tmp_path, capsys, statements=study.paths.sealed)
    assert "would be read from a sealed folder" in why
    # a statement table, or an eligible list, that the counts file does not record
    other = tmp_path / "statements.csv.gz"
    table = D.load_statements(study.paths.statements)
    other.write_bytes(F.gz_bytes(table.iloc[:-1]))
    why = refused(study, tmp_path, capsys, statements=other)
    assert (
        "not the files the counts file of the dataset builder records: the statement table" in why
    )
    with json_with(study.paths.counts, lambda r: r["inputs"].update(events_sha256="0" * 16)):
        why = refused(study, tmp_path, capsys)
    assert "records: the events table" in why
    with json_with(
        study.paths.counts,
        lambda r: r["outputs"]["items"]["subset_probe.jsonl"].update(sha256="0" * 16),
    ):
        why = refused(study, tmp_path, capsys)
    assert "the item file of list 'probe' in the plan is not the one the counts file" in why
    assert "the sealed file" not in sealed_unread


def break_row(item_index: int, **change: Any) -> Callable[[dict], dict]:
    """Change the fields of the row at a position of a stored file."""
    seen = iter(range(10**6))

    def apply(row: dict) -> dict:
        return row | change if next(seen) == item_index else row

    return apply


REFUSED_RUNS: dict[str, tuple[Callable[[SimpleNamespace], Any], str]] = {
    "a partial run": (
        lambda s: manifest_with(s, LLAMA, "e3-a", complete=False),
        "e3-a: run e3-a-llama-3.3-70b is not finished (partial)",
    ),
    "a run with no manifest": (
        lambda s: removed(run_folder(s, DEEPSEEK, "e3-c") / "run_manifest.json"),
        "e3-c: run e3-c-deepseek-v3 is not finished (none)",
    ),
    "a run that was never made": (
        lambda s: moved_away(run_folder(s, DEEPSEEK, "e4-probe")),
        "e4-probe: run e4-probe-deepseek-v3 is not finished (none)",
    ),
    "a run of another model id": (
        lambda s: manifest_with(s, LLAMA, "e3-b", model_id="meta-llama/llama-3.1-8b-instruct"),
        "e3-b: run e3-b-llama-3.3-70b is not finished (mismatch: model_id)",
    ),
    "a run pinned to another provider": (
        lambda s: manifest_with(
            s, LLAMA, "e3-b", provider_object=rd_route(LLAMA)["provider_object"] | {"order": ["x"]}
        ),
        "e3-b: run e3-b-llama-3.3-70b is not finished (mismatch: provider_object)",
    ),
    "a run under another pin of its template": (
        lambda s: manifest_with(s, LLAMA, "e3-b", template_sha256="0" * 64),
        "is not finished (mismatch: template_sha256)",
    ),
    "a run on another item file": (
        lambda s: manifest_with(s, DEEPSEEK, "e3-a", items_sha256="0" * 64),
        "is not finished (mismatch: items_sha256)",
    ),
    "a run with another track record": (
        lambda s: manifest_with(s, DEEPSEEK, "e3-b", track_record_sha256="0" * 64),
        "is not finished (mismatch: track_record_sha256)",
    ),
    "an item that was not answered": (
        lambda s: rewritten(
            s, LLAMA, "e3-c", lambda row: None if row["item_id"] == first_id(s) else row
        ),
        "e3-c: the item set is not the registered list (1 items missing, 0 not on the list)",
    ),
    "an item that is not on the list": (
        lambda s: rewritten(
            s,
            LLAMA,
            "e4-probe",
            lambda row: (
                [row, row | {"item_id": "S000000000000"}] if row["item_id"] == probe_id(s) else row
            ),
        ),
        "e4-probe: the item set is not the registered list (0 items missing, 1 not on the list)",
    ),
    "an item answered twice": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-a", lambda row: [row, row] if row["item_id"] == first_id(s) else row
        ),
        "e3-a: 1 items were answered twice",
    ),
    "a second sample of an item": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-a",
            lambda row: [row, row | {"sample": 1}] if row["item_id"] == first_id(s) else row,
        ),
        "e3-a: 2 samples per item where one is planned",
    ),
    "a reading served by another provider": (
        lambda s: rewritten(s, LLAMA, "e3-a", break_row(5, echo="mismatch")),
        "e3-a: 1 rows whose served model or provider is not ok",
    ),
    "a reading with no record of who served it": (
        lambda s: rewritten(s, LLAMA, "e3-a", break_row(5, echo="not_recorded")),
        "e3-a: 1 rows whose served model or provider is not ok",
    ),
    "a row of another model id": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-c", break_row(7, model_id="deepseek/deepseek-chat-v3.1")
        ),
        "e3-c: 1 rows with another model id or provider pin than the registered route",
    ),
    "a row of another provider pin": (
        lambda s: rewritten(s, DEEPSEEK, "e3-c", break_row(7, provider_pin="streamlake")),
        "e3-c: 1 rows with another model id or provider pin than the registered route",
    ),
    "an answer served as another model": (
        lambda s: rewritten(
            s,
            LLAMA,
            "e3-b",
            lambda row: (
                row
                | {
                    "attempts": [
                        a | {"served_model": "meta-llama/llama-3.1-8b-instruct"}
                        for a in row["attempts"]
                    ]
                }
                if row["item_id"] == first_id(s)
                else row
            ),
        ),
        "e3-b: 1 rows with an answer served as another model",
    ),
    "a row under another pin": (
        lambda s: rewritten(s, LLAMA, "e3-b", break_row(0, template_sha256="0" * 64)),
        "e3-b: 1 rows with another template or pin than the frozen one",
    ),
    "a row read with shifted dates": (
        lambda s: rewritten(s, LLAMA, "e3-b", break_row(0, shift_years=4)),
        "e3-b: 1 rows with masked names, shifted dates or a temperature above zero",
    ),
    "a reading with the outcome of its own period in context": (
        lambda s: rewritten(
            s, LLAMA, "e3-b", break_row(9, warnings=["track_record_not_before_item"])
        ),
        "e3-b: 1 rows with a track record that reaches the date of the item",
    ),
    "a failed row that carries a reading": (
        lambda s: rewritten(s, DEEPSEEK, "e3-a", break_row(3, status="failed")),
        "e3-a: 1 rows with a status, a reading and a fallback flag that contradict one another",
    ),
    "readings changed after the manifest was written": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-b", break_row(3, warnings=["edited"]), keep_manifest_hash=True
        ),
        "e3-b: the readings of run e3-b-deepseek-v3 are not those of its manifest",
    ),
    "a reading about another horizon": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-b",
            lambda row: (
                row | {"horizons": row["horizons"] | {"a": "2020-01-01"}}
                if row["item_id"] == first_id(s)
                else row
            ),
        ),
        "e3-b: 1 rows asked about other horizons than the registered",
    ),
    "a probe reading about the notice's own horizon": (
        lambda s: rewritten(
            s,
            LLAMA,
            "e4-probe",
            lambda row: (
                row | {"horizons": row["horizons"] | {"rule": "stated_end"}}
                if row["item_id"] == probe_id(s)
                else row
            ),
        ),
        "e4-probe: 1 rows asked about other horizons",
    ),
    "a plan for another list": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs), lambda r: r["lists"]["e3"].update(item_ids_sha256="0" * 64)
        ),
        "the plan's item list 'e3' is not the registered eligible list",
    ),
    "a plan for another probe subset": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs),
            lambda r: r["lists"]["probe"].update(item_ids_sha256="0" * 64),
        ),
        "the plan's item list 'probe' is not the probe subset of the eligible list",
    ),
    "a plan for another route": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs),
            lambda r: r["routes"][DEEPSEEK].update(provider="streamlake"),
        ),
        "the plan was made for another route than the registered one",
    ),
    "a plan under another pin": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs), lambda r: r["templates"].update({"probe-v1": "0" * 64})
        ),
        "the plan holds another pin of probe-v1 than the frozen one",
    ),
    "a plan for another output root": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs), lambda r: r["options"].update(out_root="/somewhere/else")
        ),
        "the plan was made for another output root than the one given",
    ),
    "a plan without the confirmatory runs of a primary": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs),
            lambda r: r.update(
                runs=[run for run in r["runs"] if (run["model"], run["line"]) != (LLAMA, "e3-c")]
            ),
        ),
        "llama-3.3-70b e3-c: the plan holds no run",
    ),
    "an item file changed since the plan": (
        lambda s: appended(s.paths.runs.parent / "items" / "e3_eligible.jsonl", "\n"),
        "is not the file the plan was made with",
    ),
    "no selection for a primary": (
        lambda s: removed(s.paths.selections / ev.SELECTION_NAME.format(model=DEEPSEEK)),
        "deepseek-v3: no H3 selection at",
    ),
    "a selection made on another statement table": (
        lambda s: json_with(
            s.paths.selections / ev.SELECTION_NAME.format(model=LLAMA),
            lambda r: r["inputs"].update(statements_sha256="0" * 64),
        ),
        "h3_selection_llama-3.3-70b.json was made on another statement table",
    ),
    "a selection of another model": (
        lambda s: json_with(
            s.paths.selections / ev.SELECTION_NAME.format(model=LLAMA),
            lambda r: r.update(model=DEEPSEEK),
        ),
        "h3_selection_llama-3.3-70b.json is not a selection for this model",
    ),
    "a selection that selects nothing": (
        lambda s: json_with(
            s.paths.selections / ev.SELECTION_NAME.format(model=LLAMA),
            lambda r: r["selection"].update(selected="d"),
        ),
        "h3_selection_llama-3.3-70b.json is not a selection for this model",
    ),
    "selections that name different comparators": (
        lambda s: json_with(
            s.paths.selections / ev.SELECTION_NAME.format(model=LLAMA),
            lambda r: r["h3_comparator"].update(selected="gbm_structured"),
        ),
        "the selection files name different H3 comparators",
    ),
    "selections that both name another comparator than the rule gives": (
        lambda s: both_selections(
            s, lambda r: r["h3_comparator"].update(selected="gbm_structured")
        ),
        "h3_selection_deepseek-v3.json names another H3 comparator than the rule in force gives",
    ),
    "a selection that is not the lowest of its own dev losses": (
        lambda s: json_with(
            s.paths.selections / ev.SELECTION_NAME.format(model=LLAMA),
            lambda r: r["selection"].update(selected="c"),
        ),
        "h3_selection_llama-3.3-70b.json does not select the condition with the lowest of its "
        "own dev losses",
    ),
    "a selection file other than the one hashed at the freeze": (
        lambda s: appended(s.paths.selections / ev.SELECTION_NAME.format(model=DEEPSEEK), "\n"),
        "h3_selection_deepseek-v3.json is not the selection file hashed at the freeze",
    ),
    "a run that showed the track record of another phase": (
        lambda s: manifest_with(s, DEEPSEEK, "e3-b", track_record_split="fit"),
        "e3-b: run e3-b-deepseek-v3 showed another track record than the fit+dev one",
    ),
    "a run planned with the track record of another phase": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs),
            lambda r: [
                run.update(track="fit") for run in r["runs"] if run["run"] == f"e3-b-{LLAMA}"
            ],
        ),
        "run e3-b-llama-3.3-70b is planned with another track record than the fit+dev one",
    ),
    "a run planned with a track record under a template that shows none": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs),
            lambda r: [
                run.update(track="fit+dev") for run in r["runs"] if run["run"] == f"e3-a-{LLAMA}"
            ],
        ),
        "run e3-a-llama-3.3-70b is planned with another track record than none",
    ),
    "an answer served by another provider than the pinned one": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-a",
            lambda row: (
                row | {"attempts": [a | {"served_provider": "Together"} for a in row["attempts"]]}
                if row["item_id"] == first_id(s)
                else row
            ),
        ),
        "e3-a: 1 rows with an answer served by another provider than the pinned one",
    ),
    "a readings file with a line that is no JSON": (
        lambda s: appended(run_folder(s, LLAMA, "e3-a") / "readings.jsonl", "{no json\n"),
        "the completeness check stopped on the plan or the stored runs (JSONDecodeError): they "
        "are not as the launcher and the harness write them",
    ),
    "a manifest that is no JSON": (
        lambda s: scribbled(run_folder(s, DEEPSEEK, "e3-b") / "run_manifest.json"),
        "the completeness check stopped on the plan or the stored runs (JSONDecodeError)",
    ),
    "a plan whose run has a template the harness lacks": (
        lambda s: json_with(
            lp.plan_path(s.paths.runs),
            lambda r: [
                run.update(template="predictive-v9")
                for run in r["runs"]
                if run["run"] == f"e3-a-{DEEPSEEK}"
            ],
        ),
        "deepseek-v3 e3-a: the plan holds runs under several templates, or one the harness lacks",
    ),
}


@contextmanager
def both_selections(study: SimpleNamespace, change: Callable[[dict], None]) -> Iterator[None]:
    """The selection files of both primaries passed through ``change``."""
    first, second = (
        study.paths.selections / ev.SELECTION_NAME.format(model=model) for model in rd.PRIMARIES
    )
    with json_with(first, change), json_with(second, change):
        yield


def rd_route(model: str) -> dict:
    return ev.registered_route(model)


def first_id(study: SimpleNamespace) -> str:
    return study.filled.index[0]


def probe_id(study: SimpleNamespace) -> str:
    return sorted(study.eligible.loc[study.eligible["probe"] == 1, "statement_group_id"])[0]


@contextmanager
def removed(path: Path) -> Iterator[None]:
    with changed(path):
        path.unlink()
        yield


@contextmanager
def moved_away(folder: Path) -> Iterator[None]:
    aside = folder.with_name(folder.name + ".aside")
    folder.rename(aside)
    try:
        yield
    finally:
        aside.rename(folder)


@contextmanager
def appended(path: Path, text: str) -> Iterator[None]:
    with changed(path):
        path.write_text(path.read_text() + text)
        yield


@contextmanager
def scribbled(path: Path, text: str = "{half a") -> Iterator[None]:
    """A file overwritten with text that is no JSON."""
    with changed(path):
        path.write_text(text)
        yield


@pytest.mark.parametrize("case", list(REFUSED_RUNS))
def test_a_run_that_is_partial_mismatched_or_of_another_set_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
    case: str,
) -> None:
    change, reason = REFUSED_RUNS[case]
    hashes = [
        part for value in study.selection_shas for part in ("--expect-selection-sha256", value)
    ]
    with change(study):
        why = refused(study, tmp_path, capsys)
        code, listed = check(study, capsys, *hashes)
    assert reason in why, why
    assert why.startswith(
        "refused: no evaluation before every confirmatory run is complete (PLAN section 6): "
    )
    assert "the sealed file" not in sealed_unread
    # no item is named in a refusal, and the check command says the same without stopping
    assert not [i for i in study.filled.index if i in why or i in listed]
    assert code == 3 and reason in listed and "NOT ready" in listed


def test_a_run_whose_manifest_is_not_complete_is_refused_twice_over(
    study: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher's test of a run and the harness's pooled record are two checks of the same
    thing; either one alone refuses a run that is not complete."""
    ids = list(study.filled.index)
    with manifest_with(study, LLAMA, "e3-a", complete=False):
        group = ev.read_group(study.plan, study.paths.runs, "confirmatory", LLAMA, "e3-a", ids)
        assert [p.split(": ", 1)[1] for p in group.problems] == [
            f"run e3-a-{LLAMA} is not finished (partial)",
            "1 runs are not complete",
        ]
        monkeypatch.setattr(lp, "run_state", lambda plan, run: "finished")
        group = ev.read_group(study.plan, study.paths.runs, "confirmatory", LLAMA, "e3-a", ids)
        assert [p.split(": ", 1)[1] for p in group.problems] == ["1 runs are not complete"]
    group = ev.read_group(study.plan, study.paths.runs, "confirmatory", LLAMA, "e3-a", ids)
    assert group.problems == () and len(group.rows) == 320 and group.template == "predictive-v1"
    # the same rows read against another list are not the registered set
    group = ev.read_group(study.plan, study.paths.runs, "confirmatory", LLAMA, "e3-a", ids[:-2])
    assert group.problems == (
        f"{LLAMA} e3-a: the item set is not the registered list (0 items missing, 2 not on the "
        "list)",
    )


def test_a_run_stored_in_several_parts_is_pooled(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    """PLAN section 6: the evaluator accepts a run stored in several parts. One confirmatory
    run is cut into the two shards the harness would make of it, each with its own manifest,
    and the plan lists the two in its place."""
    whole = run_folder(study, DEEPSEEK, "e3-a")
    rows = stored_rows(study, DEEPSEEK, "e3-a")
    manifest = json.loads((whole / "run_manifest.json").read_text())
    parts = []
    for k in range(2):
        mine = [row for row in rows if rd.shard_of(row["item_id"], 2) == k]
        folder = study.paths.runs / f"{whole.name}.s{k}"
        folder.mkdir()
        readings = folder / "readings.jsonl"
        readings.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in mine))
        record = manifest | {
            "shard": f"{k}/2",
            "items": len(mine),
            "item_ids_sha256": lp.ids_sha256(row["item_id"] for row in mine),
            "expected_rows": len(mine),
            "readings": len(mine),
            "readings_sha256": file_sha(readings),
        }
        (folder / "run_manifest.json").write_text(json.dumps(record))
        parts.append((folder, record))
    assert sum(record["items"] for _, record in parts) == 320
    assert min(record["items"] for _, record in parts) > 100

    def in_two(plan: dict) -> None:
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
            runs += shards if run["run"] == whole.name else [run]
        plan["runs"] = runs

    try:
        with json_with(lp.plan_path(study.paths.runs), in_two), moved_away(whole):
            report, _, _ = confirm(study, tmp_path, capsys)
            assert report["runs"][DEEPSEEK]["a"]["runs"] == 2
            assert report["runs"][DEEPSEEK]["a"]["rows"] == 320
            assert report["runs"][DEEPSEEK]["a"]["readings_sha256"] == {
                folder.name: record["readings_sha256"] for folder, record in parts
            }
            assert report["family"] == base.report["family"]
            # one part that is not complete, or not there, is a refusal
            second = parts[1][0] / "run_manifest.json"
            with changed(second):
                second.write_text(json.dumps(parts[1][1] | {"complete": False}))
                why = refused(study, tmp_path, capsys)
            assert f"run {parts[1][0].name} is not finished (partial)" in why
            with moved_away(parts[1][0]):
                why = refused(study, tmp_path, capsys)
            assert f"run {parts[1][0].name} is not finished (none)" in why
            assert f"({parts[1][1]['items']} items missing, 0 not on the list)" in why
            # an item answered in both parts is a duplicate
            first = parts[0][0] / "readings.jsonl"
            with changed(first, parts[0][0] / "run_manifest.json"):
                twice = (parts[1][0] / "readings.jsonl").read_text().splitlines()[0]
                first.write_text(first.read_text() + twice + "\n")
                record = parts[0][1] | {"readings_sha256": file_sha(first)}
                (parts[0][0] / "run_manifest.json").write_text(json.dumps(record))
                why = refused(study, tmp_path, capsys)
            assert "e3-a: 1 items were answered twice" in why
    finally:
        for folder, _ in parts:
            shutil.rmtree(folder)


def test_the_study_is_whole_again_after_the_refusals(
    study: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = check(study, capsys)
    assert code == 0 and "missing:" not in out
    assert not list(study.paths.runs.glob("*.aside"))


def test_a_sealed_file_of_another_build_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = D.read_table(study.paths.sealed)
    other = tmp_path / "sealed" / "outcomes_test.csv.gz"
    C.write_gz(rows.iloc[:-1], other)
    why = refused(study, tmp_path, capsys, sealed=other, expect_sha256=file_sha(other))
    assert "the sealed file and the events table are not from the same build" in why
    C.write_gz(rows.drop(columns=["outcome_B"]), other)
    why = refused(study, tmp_path, capsys, sealed=other, expect_sha256=file_sha(other))
    assert "the sealed file lacks ['outcome_B']" in why
    C.write_gz(rows.assign(period="train"), other)
    why = refused(study, tmp_path, capsys, sealed=other, expect_sha256=file_sha(other))
    assert "the sealed file is not the table of test-period outcomes" in why
    # the outcome of another statement under the display row of an eligible one
    swapped = rows.copy()
    listed = set(study.listed["event_id"])
    k = next(n for n, event in enumerate(swapped["event_id"]) if event in listed)
    swapped.loc[k, "statement_group_id"] = "S000000000000"
    C.write_gz(swapped, other)
    why = refused(study, tmp_path, capsys, sealed=other, expect_sha256=file_sha(other))
    assert "1 eligible statements have no outcome row of their display row" in why


def test_a_stop_inside_the_rules_withholds_its_message(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    recwarn: pytest.WarningsRecorder,
) -> None:
    secret, real = "recovered on 2024-05-01", D.attach_outcomes

    def stop(*args: Any, **kwargs: Any) -> None:
        raise ValueError(f"E0001: {secret}")

    monkeypatch.setattr(D, "attach_outcomes", stop)
    why = refused(study, tmp_path, capsys)
    assert why == (
        "refused: the evaluation stopped on the sealed rows (ValueError); the message is "
        "withheld because it may quote a sealed value"
    )
    assert secret not in why and "E0001" not in why

    def warn(*args: Any, **kwargs: Any) -> None:
        warnings.warn(f"odd cell: {secret}", stacklevel=1)
        raise KeyError(secret)

    monkeypatch.setattr(D, "attach_outcomes", real)
    monkeypatch.setattr(ev, "evaluate", warn)
    why = refused(study, tmp_path, capsys)
    assert "(KeyError)" in why and secret not in why
    assert not [w for w in recwarn if secret in str(w.message)]


def test_a_malformed_declaration_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    for value in ("gemma-3-27b=slow", LLAMA, f"{LLAMA}=", f"{LLAMA}= "):
        why = refused(study, tmp_path, capsys, "--not-evaluable", value)
        assert "--not-evaluable takes MODEL=REASON with a primary model" in why
    why = refused(study, tmp_path, capsys, "--by-form")
    assert "unrecognized arguments: --by-form" in why
    with pytest.raises(SystemExit) as stop:
        ev.main(["evaluate"])
    assert str(stop.value.code).startswith("refused: ")
    assert sealed_unread == []


def test_a_registered_constant_outside_its_candidates_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    sealed_unread: list[str],
) -> None:
    monkeypatch.setattr(ev, "P_VALUE_SOURCE", "wild bootstrap")
    assert "a registered constant has a value outside its candidates" in refused(
        study, tmp_path, capsys
    )
    monkeypatch.setattr(ev, "P_VALUE_SOURCE", "percentile")
    monkeypatch.setattr(ev, "H3_COMPARATOR", "gbm_text")
    assert "a registered constant has a value outside its candidates" in refused(
        study, tmp_path, capsys
    )
    assert sealed_unread == []


# --------------------------------------------------------------------------------------------
# The confirmatory results on the synthetic study
# --------------------------------------------------------------------------------------------


def test_result_file_holds_the_registered_record(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    report = base.report
    assert list(report) == [
        "about",
        "command",
        "registered",
        "inputs",
        "refit",
        "h3",
        "not_evaluable_by_declaration",
        "runs",
        "items",
        "probe",
        "item_sets",
        "family",
        "secondaries",
        "losses",
        "where_the_plan_is_silent",
        "not_computed_here",
    ]
    assert report["registered"] == json.loads(json.dumps(ev.registered_record()))
    inputs = report["inputs"]
    assert inputs["sealed_outcomes_sha256"] == study.sealed_sha
    assert inputs["eligible_sha256"] == study.eligible_sha
    assert inputs["statements_sha256"] == file_sha(study.paths.statements)
    assert inputs["events_sha256"] == file_sha(study.paths.events)
    assert inputs["plan_sha256"] == file_sha(lp.plan_path(study.paths.runs))
    assert inputs["code_sha256"]["evaluate.py"] == file_sha(Path(ev.__file__))
    assert set(inputs["code_sha256"]) >= {
        "predictors.py",
        "gbm.py",
        "power.py",
        "dataset.py",
        "forms.py",
        "read.py",
        "launch.py",
        "sealed_counts.py",
        "numpy",
        "scikit_learn",
    }
    assert inputs["baseline_predictions_checked_against_the_freeze"] is True
    truthful = truth(study)
    scoreable = truthful.dropna(subset=["y_a", "y_b"])
    assert report["items"] == {
        "eligible_statements": 320,
        "eligible_episodes": 40,
        "scoreable_statements": len(scoreable),
        "scoreable_episodes": scoreable["episode"].nunique(),
        "with_a_horizon_event_undetermined": 320 - len(scoreable),
        "scoreable_by_E_end_and_E_end90": D.mix(study.filled[D.true(study.filled["scoreable"])]),
    }
    assert report["refit"]["splits"] == "fit and dev"
    train = study.table[
        (study.table["period"] == "train") & (study.table["analysis_set"] == "dated")
    ]
    assert report["refit"]["statements_by_analysis_set"]["dated"] == len(train)
    assert report["h3"]["comparator"] == "base_rate"
    for model in rd.PRIMARIES:
        chosen = report["h3"]["selections"][model]
        path = study.paths.selections / chosen["file"]
        assert (
            chosen["sha256"] == file_sha(path)
            and chosen["selected"] == selection(study, model)["selection"]["selected"]
        )
        assert set(report["runs"][model]) == {"a", "b", "c", "probe"}
    assert [(e["hypothesis"], e["model"]) for e in report["family"]] == [
        (h, m) for m in rd.PRIMARIES for h in ("H1", "H2", "H3")
    ]
    assert len(report["not_computed_here"]) == len(ev.NOT_COMPUTED_HERE) > 5


def test_a_planted_effect_is_found_and_a_null_is_not(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"]).index
    # the first primary: (b) follows the outcome, (a) says 0.9 and 0.95 whatever happens
    planted = entry_of(base.report, "H1", LLAMA)
    assert planted["holds"] is True and planted["p_holm"] < 0.05 and planted["delta"] > 0.3
    assert planted["reading"] == "holds: the tested condition has the lower loss"
    assert (planted["comparator"], planted["tested"], planted["sides"]) == (
        f"{LLAMA}:a",
        f"{LLAMA}:b",
        1,
    )
    assert planted["items"] == ev.ALL_ITEMS
    assert (planted["statements"], planted["episodes"]) == (len(scoreable), 40)
    loss_b = brier(given(study, LLAMA, "b"), y).loc[scoreable]
    assert planted["loss_tested"] == pytest.approx(loss_b.mean(), abs=1e-6)
    # where both conditions parsed, the contrast is the one of the scripted answers
    parsed = [i for i in scoreable if fails(LLAMA, "a", i) < 2]
    loss_a = brier(given(study, LLAMA, "a"), y)
    want = float((loss_a.loc[parsed] - loss_b.loc[parsed]).mean())
    assert planted["both_sides_parsed"]["statements"] == len(parsed) < len(scoreable)
    assert planted["both_sides_parsed"]["delta"] == pytest.approx(want, abs=1e-6)
    # the second primary: (a) and (b) are the same noise around the same probabilities
    null = entry_of(base.report, "H1", DEEPSEEK)
    loss = {c: brier(given(study, DEEPSEEK, c), y).loc[scoreable] for c in ("a", "b")}
    assert null["delta"] == pytest.approx(float((loss["a"] - loss["b"]).mean()), abs=1e-6)
    assert null["loss_comparator"] == pytest.approx(float(loss["a"].mean()), abs=1e-6)
    assert null["holds"] is False and null["p"] > 0.05 and null["reading"] == "not rejected"
    assert null["ci95"][0] < 0 < null["ci95"][1]
    assert null["both_sides_parsed"]["statements"] == len(scoreable)
    assert null["both_sides_parsed"]["delta"] == pytest.approx(null["delta"], abs=1e-6)
    # the registered p-value is the one-sided percentile one, counted by hand on the draws
    pair = np.column_stack([loss["a"], loss["b"]])
    draws = P.bootstrap_means(pair, y.loc[scoreable, "episode"])
    by_hand = (1 + int((draws[:, 0] - draws[:, 1] <= 0).sum())) / 10_001
    assert null["p"] == pytest.approx(by_hand, abs=1e-6)
    assert null["ci95"] == pytest.approx(
        list(np.quantile(draws[:, 0] - draws[:, 1], [0.025, 0.975])), abs=1e-6
    )


def test_h2_reads_equivalence_from_the_ninety_percent_interval(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    same = entry_of(base.report, "H2", LLAMA)
    assert (same["comparator"], same["tested"], same["sides"]) == (
        "rules_plus_slip",
        f"{LLAMA}:c",
        2,
    )
    # the first primary's literal reading is the rule's: where it parsed, the two sides agree
    assert same["both_sides_parsed"]["delta"] == 0 and same["both_sides_parsed"]["p"] == 1.0
    assert same["holds"] is False and abs(same["delta"]) < 0.001
    assert same["equivalence"] == {"margin": 0.02, "ci90": same["ci90"], "declared": True}
    other = entry_of(base.report, "H2", DEEPSEEK)
    assert other["delta"] != 0 and other["p"] == other["p_values"]["percentile"]["two_sided"]
    low, high = other["ci90"]
    assert other["equivalence"]["declared"] is (low > -0.02 and high < 0.02)
    assert "H2 equivalence, llama-3.3-70b: declared (90% interval" in base.table
    for entry in base.report["family"]:
        assert ("equivalence" in entry) is (entry["hypothesis"] == "H2")


def test_equivalence_needs_the_interval_strictly_inside_the_margin(
    study: SimpleNamespace, opened: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = ev.typed_outcomes(study.filled.reset_index(drop=True))
    real = ev.scored

    def at(low: float, high: float) -> dict:
        def fixed(*args: Any, **kwargs: Any) -> dict:
            return real(*args, **kwargs) | {"ci90": [low, high]}

        monkeypatch.setattr(ev, "scored", fixed)
        report = ev.evaluate(opened.study, rows, {}, "percentile", draws=200)
        return entry_of(report, "H2", LLAMA)["equivalence"]

    assert at(-0.0199, 0.0199)["declared"] is True
    assert at(-0.02, 0.01)["declared"] is False  # on the margin is not inside it
    assert at(-0.01, 0.02)["declared"] is False
    assert at(-0.03, 0.0)["declared"] is False and at(0.0, 0.03)["declared"] is False


def test_h3_compares_the_selected_condition_with_the_comparator(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"]).index
    for model in rd.PRIMARIES:
        best = selection(study, model)["selection"]["selected"]
        entry = entry_of(base.report, "H3", model)
        assert (entry["comparator"], entry["tested"], entry["sides"]) == (
            "base_rate",
            f"{model}:{best}",
            2,
        )
        losses = base.report["losses"]
        assert entry["loss_comparator"] == pytest.approx(
            losses["base_rate"]["primary_brier"], abs=1e-6
        )
        assert entry["loss_tested"] == pytest.approx(
            losses[f"{model}:{best}"]["primary_brier"], abs=1e-6
        )
        assert entry["p"] == entry["p_values"]["percentile"]["two_sided"]
        # beside it: the same condition against both predictors that read no text, on the
        # same statements and the same draws
        assert list(entry["beside"]) == ["gbm_structured", "base_rate"]
        mine, other = entry["beside"]["base_rate"], entry["beside"]["gbm_structured"]
        assert (mine["delta"], mine["ci95"], mine["p"]) == (
            entry["delta"],
            entry["ci95"],
            entry["p"],
        )
        assert other["statements"] == entry["statements"] and other["delta"] == pytest.approx(
            losses["gbm_structured"]["primary_brier"] - entry["loss_tested"], abs=2e-6
        )
        assert entry["beats_both_comparators"] is bool(
            entry["holds"] and entry["delta"] > 0 and other["ci95"][0] > 0
        )
        # Delta_GBM, a registered secondary outside the family, is the same contrast
        delta_gbm = base.report["secondaries"]["delta_gbm"][model]
        assert delta_gbm == {"comparator": "gbm_structured", "tested": entry["tested"], **other}
        # the answers of the selected condition that were not parsed, among those scored
        failed = [i for i in scoreable if fails(model, best, i) == 2]
        assert entry["scoreable_not_parsed"] == {"base_rate": 0, f"{model}:{best}": len(failed)}
        with_each = base.report["secondaries"]["h3_with_each_condition"]
        assert with_each[f"{model}:{best}"]["delta"] == entry["delta"]
        assert with_each[f"{model}:{best}"]["p"] == entry["p"]
    assert list(with_each) == [f"{m}:{c}" for m in rd.PRIMARIES for c in ev.CONDITIONS]
    text = entry_of(base.report, "H3", LLAMA)
    loss_b = brier(given(study, LLAMA, "b"), y).loc[scoreable]
    assert text["loss_tested"] == pytest.approx(float(loss_b.mean()), abs=1e-6)
    assert text["holds"] is True and text["delta"] > 0 and text["beats_both_comparators"] is True
    assert text["reading"] == (
        "rejected in favour of the tested predictor; the 95% interval against gbm_structured "
        "also lies above zero"
    )
    assert f"Beside H3, {LLAMA}: gbm_structured minus {LLAMA}:b: delta" in base.table
    assert base.table.count("Beside H3, ") == 2 and "base_rate minus" not in base.table
    flags = [e["beats_both_comparators"] for e in base.report["family"] if e["hypothesis"] == "H3"]
    assert base.table.count("beats both comparators: yes") == sum(flags) >= 1
    assert base.printed.count("beside: gbm_structured minus the tested condition") == 2
    for entry in base.report["family"]:
        assert ("beside" in entry) is (entry["hypothesis"] == "H3")
        assert ("beats_both_comparators" in entry) is (entry["hypothesis"] == "H3")
        assert set(entry["scoreable_not_parsed"]) == {entry["comparator"], entry["tested"]}
    first = entry_of(base.report, "H1", LLAMA)
    lost = len([i for i in scoreable if fails(LLAMA, "a", i) == 2])
    assert first["scoreable_not_parsed"] == {f"{LLAMA}:a": lost, f"{LLAMA}:b": 0}


def test_delta_gbm_and_h3_rest_on_the_same_statements_and_draws(
    study: SimpleNamespace, base: SimpleNamespace, opened: SimpleNamespace
) -> None:
    """PLAN section 6: Delta_GBM is computed on the same statements and the same bootstrap draws
    as Delta. The three predictors are resampled together here, once, and both intervals are
    read off that one set of draws; a contrast resampled on other draws has other ends."""
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"]).index
    clusters = list(y.loc[scoreable, "episode"])
    for model in rd.PRIMARIES:
        entry = entry_of(base.report, "H3", model)
        names = ("base_rate", "gbm_structured", entry["tested"])
        losses = np.column_stack(
            [brier(opened.study.predictions[n], y).loc[scoreable] for n in names]
        )
        draws = P.bootstrap_means(losses, clusters)
        delta, delta_gbm = draws[:, 0] - draws[:, 2], draws[:, 1] - draws[:, 2]
        assert entry["ci95"] == pytest.approx(P.interval(delta), abs=1e-6)
        assert entry["p"] == pytest.approx(P.p_values(delta)["two_sided"], abs=1e-6)
        second = base.report["secondaries"]["delta_gbm"][model]
        assert second["statements"] == entry["statements"] == len(scoreable)
        assert second["ci95"] == pytest.approx(P.interval(delta_gbm), abs=1e-6)
        assert second["p"] == pytest.approx(P.p_values(delta_gbm)["two_sided"], abs=1e-6)
        # paired draw by draw: Delta_GBM minus Delta is the structured model's loss minus the
        # base rate's in every draw, so its interval is that of the model-free contrast
        gap = draws[:, 1] - draws[:, 0]
        assert np.allclose(delta_gbm - delta, gap)
        other = ev.contrast(losses[:, 1], losses[:, 2], clusters, seed=ev.SEED + 1)
        assert other["ci95"] != pytest.approx(second["ci95"], abs=1e-6)


def test_the_h3_contrast_of_each_condition_beside_the_selected_one(base: SimpleNamespace) -> None:
    with_each = base.report["secondaries"]["h3_with_each_condition"]
    for model in rd.PRIMARIES:
        entry = entry_of(base.report, "H3", model)
        for condition in ev.CONDITIONS:
            mine = with_each[f"{model}:{condition}"]
            assert mine["statements"] == entry["statements"]
            assert mine["delta"] == pytest.approx(
                base.report["losses"]["base_rate"]["primary_brier"]
                - base.report["losses"][f"{model}:{condition}"]["primary_brier"],
                abs=2e-6,
            )


def test_a_two_sided_rejection_names_the_side_it_favours() -> None:
    entry = {"evaluable": True, "holds": True, "sides": 2, "delta": -0.1}
    assert ev.reading_of(entry) == "rejected in favour of the comparator"
    assert ev.reading_of(entry | {"delta": 0.1}) == "rejected in favour of the tested predictor"
    assert ev.reading_of(entry | {"holds": False}) == "not rejected"
    assert ev.reading_of(entry | {"sides": 1}) == "holds: the tested condition has the lower loss"
    said = ev.reading_of({"evaluable": False, "reason": "why"})
    assert said == "not evaluable (why); counted as not rejected"


def h3_entry(
    delta: float, holds: bool, other: list[float] | None, comparator: str = "base_rate"
) -> dict:
    """An H3 entry as the evaluator holds it when it reads it: the contrast, whether it holds
    under Holm, and the 95% interval of the contrast with the other candidate."""
    rival = next(name for name in ev.COMPARATOR_CANDIDATES if name != comparator)
    return {
        "evaluable": True,
        "holds": holds,
        "sides": 2,
        "delta": delta,
        "comparator": comparator,
        "beside": {comparator: {"ci95": [0.01, 0.05]}, rival: {"ci95": other}},
    }


@pytest.mark.parametrize("holds", [True, False])
@pytest.mark.parametrize("delta", [0.03, 0.0, -0.03])
@pytest.mark.parametrize("low", [0.001, 0.0, -0.001])
def test_the_flag_beats_both_comparators_on_its_truth_table(
    holds: bool, delta: float, low: float
) -> None:
    """True only when H3 holds (Holm-adjusted p below 0.05), with a positive contrast, and the
    95% interval of Delta_GBM lies wholly above zero: one cell of the eighteen."""
    entry = h3_entry(delta, holds, [low, 0.05])
    assert ev.beats_both(entry) is (holds and delta > 0 and low > 0)


def test_value_beyond_both_predictors_needs_h3_and_the_second_interval() -> None:
    """PLAN section 6, "Reading": the second condition can only withhold a claim."""
    assert ev.beats_both(h3_entry(0.03, True, [0.001, 0.04])) is True
    # the other interval reaches zero, or below it: no claim beyond the comparator
    assert ev.beats_both(h3_entry(0.03, True, [0.0, 0.04])) is False
    assert ev.beats_both(h3_entry(0.03, True, [-0.01, 0.04])) is False
    assert ev.beats_both(h3_entry(0.03, True, None)) is False
    # H3 itself does not hold, or holds in favour of the comparator: never a claim
    assert ev.beats_both(h3_entry(0.03, False, [0.01, 0.04])) is False
    assert ev.beats_both(h3_entry(-0.03, True, [0.01, 0.04])) is False
    assert ev.beats_both({"evaluable": False, "holds": False}) is False
    # the same rule when the comparator in force is the other candidate
    assert ev.beats_both(h3_entry(0.03, True, [0.001, 0.04], "gbm_structured")) is True
    assert ev.beats_both(h3_entry(0.03, True, [-0.001, 0.04], "gbm_structured")) is False
    # the interval of the comparator in force is not the one that is looked at
    entry = h3_entry(0.03, True, [0.001, 0.04])
    entry["beside"]["base_rate"]["ci95"] = [-0.5, 0.5]
    assert ev.beats_both(entry) is True
    # an unadjusted p below 0.05 is not enough: the flag reads ``holds``, which is Holm's
    assert ev.beats_both(h3_entry(0.03, False, [0.001, 0.04]) | {"p": 0.01}) is False
    yes = h3_entry(0.03, True, [0.001, 0.04]) | {"beats_both_comparators": True}
    assert ev.reading_of(yes) == (
        "rejected in favour of the tested predictor; the 95% interval against gbm_structured "
        "also lies above zero"
    )
    assert ev.reading_of(yes | {"beats_both_comparators": False}) == (
        "rejected in favour of the tested predictor; the 95% interval against gbm_structured "
        "does not lie above zero"
    )
    assert ev.reading_of(yes | {"delta": -0.03, "beats_both_comparators": False}) == (
        "rejected in favour of the comparator"
    )
    assert ev.reading_of(yes | {"holds": False, "beats_both_comparators": False}) == "not rejected"


def test_holm_runs_over_the_six_registered_p_values(base: SimpleNamespace) -> None:
    family = base.report["family"]
    p = [entry["p"] for entry in family]
    for entry in family:
        side = "one_sided" if entry["hypothesis"] == "H1" else "two_sided"
        assert entry["sides"] == (1 if entry["hypothesis"] == "H1" else 2)
        assert entry["p"] == entry["p_values"]["percentile"][side]
    order = sorted(range(6), key=lambda k: p[k])
    running, want = 0.0, [0.0] * 6
    for rank, k in enumerate(order):
        running = max(running, min(1.0, (6 - rank) * p[k]))
        want[k] = running
    assert [entry["p_holm"] for entry in family] == pytest.approx(want, abs=2e-6)
    assert [entry["holds"] for entry in family] == [value < 0.05 for value in want]
    assert sum(entry["holds"] for entry in family) in range(1, 6)


def test_a_hypothesis_holds_only_below_the_familywise_level_after_holm(
    study: SimpleNamespace, opened: SimpleNamespace
) -> None:
    """PLAN section 6: a hypothesis holds when its Holm-adjusted p is below 0.05. The adjusted
    p-values are put in here, in the order of the family; 0.05 itself does not hold. The flag
    beside H3 reads the adjusted p too: the first primary's H3 has a small p, a positive
    contrast and a second interval above zero, and it carries no flag when Holm leaves it at
    0.05 or more."""
    rows = ev.typed_outcomes(study.filled.reset_index(drop=True))
    adjusted = [0.0499, 0.05, 0.0999, 0.0501, 1.0, 0.0499]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ev, "holm", lambda p: adjusted)
        report = ev.evaluate(opened.study, rows, {}, "percentile", draws=500)
    assert [entry["p_holm"] for entry in report["family"]] == adjusted
    assert [entry["holds"] for entry in report["family"]] == [
        True,
        False,
        False,
        False,
        False,
        True,
    ]
    assert ev.FAMILY_ALPHA == 0.05 and ev.TESTS == 6
    h3 = entry_of(report, "H3", LLAMA)
    assert h3["p"] < 0.05 and h3["delta"] > 0 and h3["beside"]["gbm_structured"]["ci95"][0] > 0
    assert h3["holds"] is False and h3["beats_both_comparators"] is False
    assert h3["reading"] == "not rejected"
    # under Holm's own adjustment the same entry holds and carries the flag
    report = ev.evaluate(opened.study, rows, {}, "percentile", draws=500)
    h3 = entry_of(report, "H3", LLAMA)
    assert h3["p_holm"] < 0.05 and h3["holds"] is True and h3["beats_both_comparators"] is True


def test_bounds_stand_beside_every_confirmatory_estimate(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    y = truth(study)
    a, b = given(study, DEEPSEEK, "a"), given(study, DEEPSEEK, "b")
    entry = entry_of(base.report, "H1", DEEPSEEK)["bounds"]
    assert entry["statements"] == 320
    assert entry["with_a_horizon_event_undetermined"] == int(
        y[["y_a", "y_b"]].isna().any(axis=1).sum()
    )
    for name, fill in (("undetermined_as_no", 0.0), ("undetermined_as_yes", 1.0)):
        filled = y[["y_a", "y_b"]].fillna(fill)
        loss_a, loss_b = float(brier(a, filled).mean()), float(brier(b, filled).mean())
        assert entry[name]["loss_comparator"] == pytest.approx(loss_a, abs=1e-6)
        assert entry[name]["loss_tested"] == pytest.approx(loss_b, abs=1e-6)
        assert entry[name]["delta"] == pytest.approx(loss_a - loss_b, abs=1e-6)
    for other in base.report["family"]:
        assert other["bounds"]["statements"] == 320 and "undetermined_as_yes" in other["bounds"]


def test_secondaries_and_scores(study: SimpleNamespace, base: SimpleNamespace) -> None:
    report, second = base.report, base.report["secondaries"]
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"])
    pairs = [(c["comparator"], c["tested"]) for c in second["model_free_contrasts"]]
    # PLAN section 6: the text-trained model and rules plus slip against the base rate and
    # against the structured-only model, and the structured-only model against the base rate
    assert (
        pairs
        == list(ev.MODEL_FREE_PAIRS)
        == [
            ("base_rate", "gbm_text"),
            ("base_rate", "rules_plus_slip"),
            ("gbm_structured", "gbm_text"),
            ("gbm_structured", "rules_plus_slip"),
            ("base_rate", "gbm_structured"),
        ]
    )
    for found in second["model_free_contrasts"]:
        losses = report["losses"]
        want = (
            losses[found["comparator"]]["primary_brier"] - losses[found["tested"]]["primary_brier"]
        )
        assert found["delta"] == pytest.approx(want, abs=2e-6) and found["statements"] == len(
            scoreable
        )
    # H2 on the month-and-year form alone
    month_year = study.filled.loc[scoreable.index, "form"] == "month_year"
    assert 0 < month_year.sum() < len(scoreable)
    assert set(second["h2_on_the_month_and_year_form"]) == {f"H2 {LLAMA}", f"H2 {DEEPSEEK}"}
    assert second["h2_on_the_month_and_year_form"][f"H2 {LLAMA}"]["statements"] == int(
        month_year.sum()
    )
    # the post-cutoff slice of a primary that was not switched, when it is large enough
    after = scoreable[scoreable["day"] > "2023-12-31"]
    assert set(second["post_cutoff_slice"]) == {f"{h} {LLAMA}" for h in ("H1", "H2", "H3")}
    assert second["post_cutoff_slice"][f"H1 {LLAMA}"]["statements"] == len(after)
    loss = {c: brier(given(study, DEEPSEEK, c), y) for c in ("a", "b")}
    # every statement of the synthetic study was first captured before its stated end
    assert second["first_captured_by_the_stated_end"][f"H1 {DEEPSEEK}"]["delta"] == pytest.approx(
        float((loss["a"] - loss["b"]).loc[scoreable.index].mean()), abs=1e-6
    )
    by_company = second["clusters_by_company"][f"H1 {DEEPSEEK}"]
    assert (
        by_company["episodes"] == study.filled.loc[scoreable.index, "company_name"].nunique() == 3
    )
    assert by_company["delta"] == entry_of(report, "H1", DEEPSEEK)["delta"]
    assert by_company["ci95"] != entry_of(report, "H1", DEEPSEEK)["ci95"]
    for name in ("all_covered_presentations", "any_covered_presentation", "recovery_definition_A"):
        assert len(second[name]) == 6
    # every statement has one presentation, so these two brackets are the primary one
    assert second["all_covered_presentations"] == second["first_captured_by_the_stated_end"]
    # under definition A nothing is ever resolved in the synthetic captures: all no/no
    under_a = second["recovery_definition_A"][f"H1 {DEEPSEEK}"]
    none = pd.DataFrame({"y_a": 0.0, "y_b": 0.0}, index=y.index)
    want = float(
        (brier(given(study, DEEPSEEK, "a"), none) - brier(given(study, DEEPSEEK, "b"), none)).mean()
    )
    assert under_a["statements"] == 320 and under_a["delta"] == pytest.approx(want, abs=1e-6)
    # the decomposition of E3
    parts = second["decomposition"][LLAMA]
    losses = report["losses"]
    assert list(parts) == [
        "content_value_of_the_text",
        "content_value_against_the_structured_model",
        "reading_loss",
        "trust_loss",
    ]
    assert parts["content_value_of_the_text"]["delta"] == pytest.approx(
        losses["base_rate"]["primary_brier"] - losses["rules_plus_slip"]["primary_brier"],
        abs=2e-6,
    )
    assert parts["content_value_against_the_structured_model"]["delta"] == pytest.approx(
        losses["gbm_structured"]["primary_brier"] - losses["rules_plus_slip"]["primary_brier"],
        abs=2e-6,
    )
    assert parts["reading_loss"]["delta"] == pytest.approx(
        losses[f"{LLAMA}:c"]["primary_brier"] - losses["rules_plus_slip"]["primary_brier"], abs=2e-6
    )
    assert parts["trust_loss"]["delta"] == pytest.approx(
        losses[f"{LLAMA}:a"]["primary_brier"] - losses[f"{LLAMA}:c"]["primary_brier"], abs=2e-6
    )
    # the overconfidence criterion of PLAN section 13: (a) of the first primary says 0.9
    over = second["overconfidence_of_condition_a"]
    assert over[LLAMA]["met"] is True and over[DEEPSEEK]["met"] is False
    record = losses[f"{DEEPSEEK}:a"]
    a = given(study, DEEPSEEK, "a").loc[scoreable.index]
    gap = float((a["p_a"] - scoreable["y_a"]).mean())
    assert record["calibration_in_the_large"]["E_end"]["mean_p_minus_frequency"] == pytest.approx(
        gap, abs=1e-6
    )
    assert record["mean_p_E_end"] == pytest.approx(float(a["p_a"].mean()), abs=1e-6)
    assert record["brier_E_end"] == pytest.approx(
        float(((a["p_a"] - scoreable["y_a"]) ** 2).mean()), abs=1e-6
    )
    assert record["primary_brier"] == pytest.approx(float(brier(a, scoreable).mean()), abs=1e-6)
    assert set(record["pinball_all_statements"]) == {"0.50", "0.80", "0.95"}
    assert set(losses) == {
        *G.PREDICTORS,
        *(f"{m}:{c}" for m in rd.PRIMARIES for c in ev.CONDITIONS),
    }


def test_murphy_decomposition_and_coverage_on_small_cases() -> None:
    # two bins of two: means .15 and .85 against frequencies 0 and 1
    p, y = [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]
    parts = ev.murphy(p, y, bins=2)
    assert parts == {
        "bins": 2,
        "reliability": pytest.approx(0.15**2),
        "resolution": pytest.approx(0.25),
        "uncertainty": pytest.approx(0.25),
    }
    assert ev.murphy([0.5, 0.5, 0.5], [1, 0, 1])["bins"] == 3
    assert ev.murphy([0.3] * 30, [0, 1, 1] * 10)["resolution"] == pytest.approx(0.0)
    rows = pd.DataFrame(
        {
            "ttr_kind": [
                "interval",
                "interval",
                "interval",
                "at_cap",
                "right_censored",
                "right_censored",
            ],
            "ttr_lower": [30.0, 30.0, 5.0, 365.0, 200.0, 50.0],
            "ttr_upper": [60.0, 60.0, 40.0, 365.0, np.nan, np.nan],
        }
    )
    pred = pd.DataFrame(
        {
            "q10": [20.0, 70.0, 20.0, 20.0, 20.0, 20.0],
            "q90": [80.0, 90.0, 80.0, 300.0, 150.0, 100.0],
        }
    )
    # inside; wholly below the interval; straddles its lower end; at the cap, above; censored
    # at 200, above an interval that ends at 150; censored at 50, which says nothing
    assert ev.coverage80(pred, rows) == {
        "inside": 1,
        "outside": 3,
        "bracket_straddles_the_interval": 2,
        "coverage": 0.25,
    }
    gap = ev.calibration([0.9, 0.8, 0.7, 0.6], [1, 0, 1, 0], ["g", "g", "h", "h"], 200, ev.SEED)
    assert (
        gap["mean_p_minus_frequency"] == pytest.approx(0.25)
        and gap["ci95"][0] <= 0.25 <= gap["ci95"][1]
    )
    assert ev.calibration([0.9, 0.8], [1, 0], ["g", "g"], 200, ev.SEED)["ci95"] is None


def test_parse_and_refusal_counts_are_reported_per_model_and_condition(
    study: SimpleNamespace, base: SimpleNamespace
) -> None:
    ids = list(study.filled.index)
    runs = base.report["runs"]
    for model in rd.PRIMARIES:
        for condition in ("a", "b", "c", "probe"):
            record = runs[model][condition]
            pool = (
                study.eligible.loc[study.eligible["probe"] == 1, "statement_group_id"]
                if condition == "probe"
                else ids
            )
            failed = sum(fails(model, condition, i) == 2 for i in pool)
            repaired = sum(fails(model, condition, i) == 1 for i in pool)
            assert record["rows"] == len(pool)
            assert record["by_status"].get("failed", 0) == failed
            assert record["by_status"].get("repaired", 0) == repaired
            assert record["parse_failure_rate"] == pytest.approx(failed / len(pool), abs=1e-6)
            assert record["refusal_rate"] == 0 and record["by_echo"] == {"ok": len(pool)}
            assert record["line"] == ev.LINES["confirmatory"][condition]
            # which stored readings were scored: the hash of the file of each run
            stored_at = run_folder(study, model, record["line"]) / "readings.jsonl"
            assert record["readings_sha256"] == {stored_at.parent.name: file_sha(stored_at)}
    assert (
        runs[LLAMA]["a"]["replaced_by_base_rate"] > 0
        and runs[DEEPSEEK]["probe"]["replaced_by_base_rate"] > 0
    )


def test_a_refused_reading_is_a_failure_with_the_same_fallback(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    target = study.filled.index[D.true(study.filled["scoreable"])][0]

    def refuse(row: dict) -> dict:
        if row["item_id"] != target:
            return row
        return row | {
            "status": "refused",
            "reading": None,
            "fallback": "base_rate",
            "echo": "refused",
        }

    with rewritten(study, DEEPSEEK, "e3-a", refuse):
        report, _, _ = confirm(study, tmp_path, capsys)
    record = report["runs"][DEEPSEEK]["a"]
    assert record["by_status"]["refused"] == 1 and record["refusal_rate"] == pytest.approx(
        1 / 320, abs=1e-6
    )
    assert record["replaced_by_base_rate"] == 1 and record["by_echo"] == {"ok": 319, "refused": 1}
    entry = entry_of(report, "H1", DEEPSEEK)
    assert entry["both_sides_parsed"]["statements"] == entry["statements"] - 1
    assert entry["delta"] != entry_of(base.report, "H1", DEEPSEEK)["delta"]


# --------------------------------------------------------------------------------------------
# The probe rule
# --------------------------------------------------------------------------------------------


def informed(study: SimpleNamespace) -> Callable[[dict], dict]:
    """Probe rows whose median is the midpoint of the true bracket: a reader that remembers."""
    known = study.filled["ttr_mid_days"]

    def change(row: dict) -> dict:
        if row["reading"] is None or not known[row["item_id"]]:
            return row
        days = dict.fromkeys(P.QUANTILE_KEYS, round(float(known[row["item_id"]])))
        return row | {"reading": row["reading"] | {"days_to_recovery": days}}

    return change


def test_the_probe_is_scored_against_the_base_rate(
    study: SimpleNamespace, base: SimpleNamespace, opened: SimpleNamespace
) -> None:
    filled = study.filled
    probe_ids = opened.study.probe_ids
    kept = [i for i in probe_ids if filled.loc[i, "ttr_kind"] != "right_censored"]
    target = filled.loc[kept, "ttr_mid_days"].astype(float)
    for model, median in ((LLAMA, 2.0), (DEEPSEEK, 4.0)):
        record = base.report["probe"][model]
        mine = pd.Series(median, index=kept)
        if model == DEEPSEEK:  # its failed probe readings take the base rate's median
            gone = [i for i in kept if fails(DEEPSEEK, "probe", i) == 2]
            mine.loc[gone] = opened.study.probe["base_rate"].loc[gone, "q50"]
        want = float((0.5 * (target - mine).abs()).mean())
        assert record["loss_tested"] == pytest.approx(want, abs=1e-5)
        base_q = opened.study.probe["base_rate"].loc[kept, "q50"]
        assert record["loss_comparator"] == pytest.approx(
            float((0.5 * (target - base_q).abs()).mean()), abs=1e-5
        )
        assert record["probe_statements"] == 300
        assert (
            record["left_out_right_censored"]
            == 300 - len(kept)
            == record["pinball_model"]["left_out_right_censored"]
        )
        assert record["statements"] == len(kept) and record["alpha"] == 0.05
        # a median of a few days is far worse than the base rate: no switch
        assert record["delta"] < 0 and record["p"] > 0.99 and record["beats_base_rate"] is False
        assert record["p"] == record["p_values"]["percentile"]["one_sided"]
        chosen = base.report["item_sets"][model]
        assert (
            chosen["switched"] is False and chosen["items"] == ev.ALL_ITEMS and chosen["evaluable"]
        )
    scoreable = filled[D.true(filled["scoreable"])]
    sets = base.report["item_sets"]
    assert sets[LLAMA]["slice_scoreable"] == int((scoreable["event_date"] > "2023-12-31").sum())
    assert sets[DEEPSEEK]["slice_scoreable"] == int((scoreable["event_date"] > "2024-12-31").sum())
    assert sets[LLAMA]["slice_analysed"] is True and sets[DEEPSEEK]["slice_analysed"] is False
    assert sets[LLAMA]["slice_statements"] == int((filled["event_date"] > "2023-12-31").sum())


def test_the_probe_leaves_out_a_target_censored_before_the_cap() -> None:
    index = [f"s{k}" for k in range(6)]
    rows = pd.DataFrame(
        {
            "ttr_kind": ["interval"] * 4 + ["at_cap", "right_censored"],
            "ttr_lower": [5.0, 40.0, 90.0, 190.0, 365.0, 120.0],
            "ttr_upper": [15.0, 60.0, 110.0, 210.0, 365.0, np.nan],
            "ttr_mid": [10.0, 50.0, 100.0, 200.0, 365.0, np.nan],
            "episode_id": ["g", "g", "h", "h", "k", "k"],
        },
        index=index,
    )
    base = pd.DataFrame({"q50": [100.0] * 6}, index=index)
    mine = pd.DataFrame({"q50": [10.0, 50.0, 100.0, 200.0, 365.0, 5.0]}, index=index)
    held = ev.Study(
        first=pd.DataFrame(index=index),
        probe_ids=index,
        predictions={},
        parsed={},
        probe={"base_rate": base, LLAMA: mine},
        selection={},
        comparator="",
        runs={},
        not_evaluable={},
        refit={},
    )
    record = ev.probe_test(LLAMA, held, rows, 500, ev.SEED, "percentile")
    # five targets are scored at the midpoint of their bracket; the sixth has none
    assert (record["probe_statements"], record["statements"]) == (6, 5)
    assert record["left_out_right_censored"] == 1 and record["episodes"] == 3
    assert record["loss_tested"] == 0 and record["loss_comparator"] == pytest.approx(
        0.5 * (90 + 50 + 0 + 100 + 265) / 5
    )
    assert record["delta"] == pytest.approx(50.5) and record["beats_base_rate"] is True
    assert record["p"] == pytest.approx(1 / 501) == record["p_values"]["percentile"]["one_sided"]
    # the bounds of the pinball loss keep the censored target, between its lower bound and the cap
    assert record["pinball_model"]["left_out_right_censored"] == 1
    assert record["pinball_model"]["statements"] == 5 and record["pinball_model"]["loss"] == 0
    assert record["pinball_model"]["upper_bound"] > record["pinball_model"]["lower_bound"] > 0
    # the verdict is a p-value below 0.05; 0.05 itself is not below it
    for p, verdict in ((0.0499, True), (0.05, False), (0.3, False)):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ev, "registered_p", lambda *args, p=p: p)
            again = ev.probe_test(LLAMA, held, rows, 500, ev.SEED, "percentile")
        assert again["p"] == p and again["beats_base_rate"] is verdict
    assert ev.PROBE_ALPHA == 0.05 and ev.PROBE_LEVEL == 0.5
    # the same medians as the base rate's: no difference, and no switch
    held.probe[LLAMA] = base
    same = ev.probe_test(LLAMA, held, rows, 500, ev.SEED, "percentile")
    assert same["delta"] == 0 and same["p"] == 1.0 and same["beats_base_rate"] is False


def test_a_primary_that_beats_the_base_rate_is_evaluated_on_its_slice(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    with rewritten(study, LLAMA, "e4-probe", informed(study)):
        report, table, _ = confirm(study, tmp_path, capsys)
    probe = report["probe"][LLAMA]
    assert probe["delta"] > 0 and probe["p"] < 0.05 and probe["beats_base_rate"] is True
    chosen = report["item_sets"][LLAMA]
    assert chosen["switched"] is True and chosen["items"] == ev.SLICE_ITEMS and chosen["evaluable"]
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"])
    after = scoreable[scoreable["day"] > "2023-12-31"]
    assert len(after) == chosen["slice_scoreable"] >= ev.MIN_SLICE
    loss_b = brier(given(study, LLAMA, "b"), y)
    for hypothesis in ("H1", "H2", "H3"):
        entry = entry_of(report, hypothesis, LLAMA)
        assert entry["items"] == ev.SLICE_ITEMS and entry["statements"] == len(after)
        assert entry["bounds"]["statements"] == int((y["day"] > "2023-12-31").sum())
        assert entry["delta"] != entry_of(base.report, hypothesis, LLAMA)["delta"]
    assert entry_of(report, "H1", LLAMA)["loss_tested"] == pytest.approx(
        float(loss_b.loc[after.index].mean()), abs=1e-6
    )
    # what stands beside H3 is on the same statements: Delta_GBM, H3 with each condition and
    # the decomposition
    second = report["secondaries"]
    h3 = entry_of(report, "H3", LLAMA)
    assert h3["beside"]["gbm_structured"]["statements"] == len(after)
    assert second["delta_gbm"][LLAMA]["statements"] == len(after)
    assert second["delta_gbm"][LLAMA]["delta"] == h3["beside"]["gbm_structured"]["delta"]
    assert second["delta_gbm"][DEEPSEEK]["statements"] == len(scoreable)
    for condition in ev.CONDITIONS:
        assert second["h3_with_each_condition"][f"{LLAMA}:{condition}"]["statements"] == len(after)
    assert {part["statements"] for part in second["decomposition"][LLAMA].values()} == {len(after)}
    # the slice of a switched primary is its confirmatory set, not a secondary
    assert report["secondaries"]["post_cutoff_slice"] == {}
    assert report["losses"][f"{LLAMA}:b"]["scoreable_statements"] == len(after)
    assert report["losses"]["gbm_structured"]["scoreable_statements"] == len(scoreable)
    # the other primary is untouched, and the family still has six tests
    for hypothesis in ("H1", "H2", "H3"):
        mine, before = (
            entry_of(report, hypothesis, DEEPSEEK),
            entry_of(base.report, hypothesis, DEEPSEEK),
        )
        assert (mine["delta"], mine["p"], mine["statements"]) == (
            before["delta"],
            before["p"],
            before["statements"],
        )
    assert len(report["family"]) == 6 and f"tests on: {ev.SLICE_ITEMS}." in table


def test_a_switched_primary_with_a_small_slice_is_not_evaluable(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    with rewritten(study, DEEPSEEK, "e4-probe", informed(study)):
        report, table, printed = confirm(study, tmp_path, capsys)
    chosen = report["item_sets"][DEEPSEEK]
    assert report["probe"][DEEPSEEK]["beats_base_rate"] is True and chosen["switched"] is True
    assert 0 < chosen["slice_scoreable"] < ev.MIN_SLICE and chosen["evaluable"] is False
    assert "items" not in chosen and "fewer than 50 scoreable statements" in chosen["reason"]
    for hypothesis in ("H1", "H2", "H3"):
        entry = entry_of(report, hypothesis, DEEPSEEK)
        assert entry["evaluable"] is False and entry["p"] == 1.0 and entry["p_holm"] == 1.0
        assert entry["holds"] is False and "delta" not in entry and "equivalence" not in entry
        assert entry["reading"].startswith("not evaluable (the probe beat the base rate")
        assert entry["reading"].endswith("counted as not rejected")
    # the three tests stay in the family: the other primary's p-values are still adjusted
    # over six tests
    mine = [entry_of(report, h, LLAMA) for h in ("H1", "H2", "H3")]
    before = [entry_of(base.report, h, LLAMA) for h in ("H1", "H2", "H3")]
    assert [e["p"] for e in mine] == [e["p"] for e in before]
    assert [e["p_holm"] for e in mine] == pytest.approx(
        ev.holm([*[e["p"] for e in mine], 1, 1, 1])[:3], abs=1e-6
    )
    # the two smallest p-values are multiplied by 6 and by 5, not by 3 and by 2
    assert mine[0]["p_holm"] == pytest.approx(6 * mine[0]["p"], abs=1e-6)
    assert mine[2]["p_holm"] == pytest.approx(5 * mine[2]["p"], abs=1e-6)
    assert not [
        key for key in report["secondaries"]["first_captured_by_the_stated_end"] if DEEPSEEK in key
    ]
    assert f"{DEEPSEEK}:a" not in report["losses"] and f"{LLAMA}:a" in report["losses"]
    assert "not evaluable" in table and "not evaluable" in printed


def typed_rows(
    scoreable: Sequence[bool], days: Sequence[str], episodes: Sequence[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = [f"s{k:03d}" for k in range(len(days))]
    rows = pd.DataFrame(
        {"scoreable": list(scoreable), "episode_id": list(episodes or index)}, index=index
    )
    return pd.DataFrame({"event_date": list(days)}, index=index), rows


def test_the_small_slice_rule_at_its_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    # 60 statements after the cutoff day of the first primary, 49 of them scoreable, and a
    # statement dated on the cutoff day itself, which is not after it
    days = ["2024-01-01"] * 60 + ["2023-12-31"] + ["2023-06-01"] * 20
    first, rows = typed_rows([True] * 49 + [False] * 11 + [True] * 21, days)
    ids, record = ev.item_set(LLAMA, True, first, rows)
    assert ids is None and record["slice_scoreable"] == 49 and record["slice_statements"] == 60
    assert record["evaluable"] is False and record["slice_analysed"] is False and record["switched"]
    first, rows = typed_rows([True] * 50 + [False] * 10 + [True] * 21, days)
    ids, record = ev.item_set(LLAMA, True, first, rows)
    assert list(ids) == list(rows.index[:60]) and record["items"] == ev.SLICE_ITEMS
    assert record["slice_scoreable"] == 50 and record["slice_analysed"] and record["evaluable"]
    # not beaten: every statement, whatever the slice holds
    ids, record = ev.item_set(LLAMA, False, first, rows)
    assert (
        list(ids) == list(rows.index) and record["items"] == ev.ALL_ITEMS and not record["switched"]
    )
    # a probe that could not be tested decides nothing
    ids, record = ev.item_set(LLAMA, None, first, rows)
    assert ids is None and record["reason"] == "the probe could not be tested"
    # the other primary's cutoff month ends a year later: none of these statements is after it
    ids, record = ev.item_set(DEEPSEEK, True, first, rows)
    assert ids is None and record["slice_statements"] == 0
    # a model whose cutoff month is the last of the test split has no slice
    monkeypatch.setitem(S.CUTOFF_MONTH_ENDS, LLAMA, date(2025, 12, 31))
    late_first, late_rows = typed_rows([True] * 80, ["2026-02-01"] * 80)
    ids, record = ev.item_set(LLAMA, True, late_first, late_rows)
    assert ids is None and record["slice_inside_the_test_split"] is False
    assert "has no slice inside the test split" in record["reason"]
    assert ev.MIN_SLICE == 50


def test_the_item_sets_are_fixed_by_the_probe_before_any_test(
    study: SimpleNamespace, opened: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real_probe, real_set, real_scored = ev.probe_test, ev.item_set, ev.scored

    def probe_test(*args: Any, **kwargs: Any) -> dict:
        order.append("probe")
        return real_probe(*args, **kwargs)

    def item_set(model: str, beaten: Any, first: pd.DataFrame, rows: pd.DataFrame) -> Any:
        order.append("set")
        assert beaten in (True, False, None)  # what decides the set: the probe's verdict
        return real_set(model, beaten, first, rows)

    def scored(*args: Any, **kwargs: Any) -> dict:
        order.append("test")
        return real_scored(*args, **kwargs)

    monkeypatch.setattr(ev, "probe_test", probe_test)
    monkeypatch.setattr(ev, "item_set", item_set)
    monkeypatch.setattr(ev, "scored", scored)
    rows = ev.typed_outcomes(study.filled.reset_index(drop=True))
    ev.evaluate(opened.study, rows, {}, "percentile", draws=200)
    assert order[:4] == ["probe", "probe", "set", "set"] and set(order[4:]) == {"test"}


def test_a_probe_on_one_episode_decides_nothing(
    study: SimpleNamespace, opened: SimpleNamespace
) -> None:
    rows = ev.typed_outcomes(study.filled.reset_index(drop=True))
    one = rows.assign(episode_id="the only episode")
    report = ev.evaluate(opened.study, one, {}, "percentile", draws=200)
    for model in rd.PRIMARIES:
        assert report["probe"][model]["evaluable"] is False
        assert (
            report["probe"][model]["beats_base_rate"] is None
            and report["probe"][model]["p"] is None
        )
        assert report["item_sets"][model]["reason"] == "the probe could not be tested"
    assert [entry["p"] for entry in report["family"]] == [1.0] * 6
    assert not any(entry["holds"] for entry in report["family"])
    # two episodes are enough for a test, and the test is then made
    two = rows.assign(episode_id=["g" if k % 2 else "h" for k in range(len(rows))])
    report = ev.evaluate(opened.study, two, {}, "percentile", draws=200)
    assert all(entry["evaluable"] and entry["episodes"] == 2 for entry in report["family"])


def test_a_primary_declared_not_evaluable_stays_in_the_family(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    declared = f"{DEEPSEEK}=its route was withdrawn on 2026-10-20"
    with moved_away(run_folder(study, DEEPSEEK, "e3-b")):
        # without the declaration the missing run is a refusal
        assert "is not finished (none)" in refused(study, tmp_path, capsys)
        report, table, _ = confirm(study, tmp_path, capsys, "--not-evaluable", declared)
    reason = "declared on the command line: its route was withdrawn on 2026-10-20"
    assert report["not_evaluable_by_declaration"] == {DEEPSEEK: reason}
    assert list(report["runs"]) == [LLAMA] and list(report["probe"]) == [LLAMA]
    for hypothesis in ("H1", "H2", "H3"):
        entry = entry_of(report, hypothesis, DEEPSEEK)
        assert entry["evaluable"] is False and entry["reason"] == reason
        assert (entry["p"], entry["p_holm"], entry["holds"]) == (1.0, 1.0, False)
        mine, before = entry_of(report, hypothesis, LLAMA), entry_of(base.report, hypothesis, LLAMA)
        assert (mine["delta"], mine["p"]) == (before["delta"], before["p"])
    assert len(report["family"]) == 6 and table.count("not evaluable") == 3


# --------------------------------------------------------------------------------------------
# The model-free predictions and their hash
# --------------------------------------------------------------------------------------------


def test_baselines_command_hashes_the_predictions_of_the_refit(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
    opened: SimpleNamespace,
) -> None:
    out, table = tmp_path / "baselines.json", tmp_path / "baselines.csv"
    capsys.readouterr()
    assert (
        ev.main(["baselines", "--out", str(out), "--table", str(table), *options(study, *OPEN)])
        == 0
    )
    printed = capsys.readouterr().out
    record = json.loads(out.read_text())
    sha = record["predictions_sha256"]
    assert sha == base.report["inputs"]["baseline_predictions_sha256"] == opened.sha
    assert f"sha256 of the predictions: {sha}" in printed
    assert record["predictors"] == list(G.PREDICTORS) and record["refit"] == base.report["refit"]
    assert (record["eligible_statements"], record["probe_statements"]) == (320, 300)
    written = pd.read_csv(table, index_col=0)
    assert written.shape == (320, 5 * 7) and list(written.index) == list(study.filled.index)
    assert not written.isna().any().any()
    held = opened.study.predictions
    assert written["gbm_text.p_b"].to_numpy() == pytest.approx(
        held["gbm_text"]["p_b"].to_numpy(), abs=1e-6
    )
    assert (written["face_value.p_a"] == 1).all()
    # the predictions are fixed before any outcome: nothing of the sealed file is needed
    assert "sealed" not in " ".join(record["inputs"])
    # the hash moves with any prediction
    moved = {name: frame.copy() for name, frame in held.items() if name in G.PREDICTORS}
    moved["base_rate"].iloc[0, 0] += 0.001
    assert ev.baseline_hash(moved, opened.study.probe["base_rate"]) != sha
    with pytest.raises(SystemExit, match="already there"):
        ev.main(["baselines", "--out", str(out), *options(study, *OPEN)])


def test_predictions_can_be_held_to_the_hash_of_the_freeze(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
    sealed_unread: list[str],
) -> None:
    sha = base.report["inputs"]["baseline_predictions_sha256"]
    why = refused(study, tmp_path, capsys, "--expect-baselines-sha256", "0" * 64)
    assert "the model-free predictions are not those hashed at the freeze" in why
    assert sha[:16] in why and "the sealed file" not in sealed_unread


def test_predictions_checked_against_the_freeze_are_recorded(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    sha = base.report["inputs"]["baseline_predictions_sha256"]
    assert sha == study.baselines_sha
    report, _, _ = confirm(study, tmp_path, capsys, expect_baselines_sha256=sha[:16])
    assert report["inputs"]["baseline_predictions_checked_against_the_freeze"] is True
    assert report["family"] == base.report["family"]
    for model in rd.PRIMARIES:
        chosen = report["h3"]["selections"][model]
        assert chosen["checked_against_the_freeze"] is True
        assert f"{model}={chosen['sha256']}" in study.selection_shas


def test_every_hash_of_the_freeze_is_required_before_anything_is_read(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    why = refused(study, tmp_path, capsys, expect_baselines_sha256=None)
    assert "--expect-baselines-sha256 takes a sha256" in why
    why = refused(study, tmp_path, capsys, expect_selection_sha256=None)
    assert f"--expect-selection-sha256 is required for {list(rd.PRIMARIES)}" in why
    why = refused(study, tmp_path, capsys, expect_selection_sha256=study.selection_shas[:1])
    assert f"--expect-selection-sha256 is required for {[DEEPSEEK]}" in why
    for wrong in (
        [*study.selection_shas, study.selection_shas[0]],  # twice for one model
        ["gemma-3-27b=" + "0" * 64, *study.selection_shas],
    ):
        why = refused(study, tmp_path, capsys, expect_selection_sha256=wrong)
        assert "--expect-selection-sha256 takes MODEL=SHA256, once for each primary" in why
    for wrong in ([f"{LLAMA}=abc", study.selection_shas[1]], [LLAMA, study.selection_shas[1]]):
        why = refused(study, tmp_path, capsys, expect_selection_sha256=wrong)
        assert "--expect-selection-sha256 takes a sha256 or its first 16" in why
    # nothing was read for any of these: not even the open inputs
    assert sealed_unread == []


def test_a_primary_declared_not_evaluable_needs_no_selection_hash(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its selection file is not read either: the file may be missing."""
    declared = f"{DEEPSEEK}=its route was withdrawn"
    with removed(study.paths.selections / ev.SELECTION_NAME.format(model=DEEPSEEK)):
        report, _, _ = confirm(
            study,
            tmp_path,
            capsys,
            "--not-evaluable",
            declared,
            expect_selection_sha256=study.selection_shas[:1],
        )
    assert list(report["h3"]["selections"]) == [LLAMA]
    assert report["h3"]["selections"][LLAMA]["checked_against_the_freeze"] is True
    # the other primary's hash is still asked for
    why = refused(
        study, tmp_path, capsys, "--not-evaluable", declared, expect_selection_sha256=None
    )
    assert f"--expect-selection-sha256 is required for {[LLAMA]}" in why


def test_every_primary_declared_not_evaluable_opens_nothing(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    both = [arg for m in rd.PRIMARIES for arg in ("--not-evaluable", f"{m}=no route")]
    why = refused(study, tmp_path, capsys, *both)
    assert "every primary is declared not evaluable" in why
    assert "the sealed file is not opened for the secondaries alone" in why
    assert sealed_unread == []
    code, out = check(study, capsys, *both)
    assert code == 3 and "every primary is declared not evaluable" in out


def test_an_eligible_statement_without_a_cluster_is_found_before_the_sealed_file(
    study: SimpleNamespace,
) -> None:
    counts = json.loads(study.paths.counts.read_text())
    first = study.listed.set_index("statement_group_id")
    ids = list(first.index)
    for column, value in (("company_name", ""), ("episode_id", " ")):
        blank = first.copy()
        blank.loc[ids[:3], column] = value
        found = ev.gather(
            study.paths.runs,
            D.read_table(study.paths.eligible),
            blank,
            counts,
            study.paths.selections,
            file_sha(study.paths.statements),
            {},
        )
        assert found.problems == [
            "3 eligible statements have no shortage episode or no company: the resampling has "
            "no cluster for them"
        ]
    assert ev.cluster_problems(first, ids) == []
    assert ev.CLUSTER_COLUMNS == ("episode_id", "company_name")


def test_readings_that_cannot_be_turned_into_predictions_name_no_item(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    sealed_unread: list[str],
) -> None:
    item = first_id(study)

    def broken(*args: Any, **kwargs: Any) -> None:
        raise KeyError(item)

    monkeypatch.setattr(ev, "literal_days", broken)
    why = refused(study, tmp_path, capsys)
    assert why == "refused: the readings could not be turned into predictions (KeyError)"
    assert item not in why and "the sealed file" not in sealed_unread


def test_the_refit_uses_fit_and_dev_and_is_reproducible(
    study: SimpleNamespace, opened: SimpleNamespace
) -> None:
    frame = opened.frame
    seen: list[pd.DataFrame] = []
    real = G.fit_all

    def fit_all(rows: pd.DataFrame, *args: Any) -> Any:
        seen.append(rows)
        return real(rows, *args)

    patch = pytest.MonkeyPatch()
    patch.setattr(G, "fit_all", fit_all)
    try:
        fitted, record = REAL_REFIT(frame)
    finally:
        patch.undo()
    assert set(seen[0]["split"]) == {"fit", "dev"} and set(seen[0]["period"]) == {"train"}
    assert len(seen[0]) == int((frame["period"] == "train").sum())
    assert record == {
        "splits": "fit and dev",
        "statements_by_analysis_set": {
            name: int(((frame["period"] == "train") & (frame["analysis_set"] == name)).sum())
            for name in P.SETS
        },
    }
    rows = frame.loc[list(study.filled.index)]
    again = {name: model.predict(rows) for name, model in fitted.items()}
    first = {name: opened.study.predictions[name] for name in G.PREDICTORS}
    assert ev.predictions_text(again) == ev.predictions_text(first)
    # a test-period outcome cannot enter a fit: the predictors refuse the row
    with pytest.raises(ValueError, match="fitted on train-period statements only"):
        G.fit_all(frame[frame["split"].isin(["dev", "test"])])


# --------------------------------------------------------------------------------------------
# Reproducible, and nothing about a single statement
# --------------------------------------------------------------------------------------------


def test_two_runs_write_the_same_bytes(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base: SimpleNamespace,
) -> None:
    out = fresh(tmp_path)
    assert ev.main(["confirmatory", "--out", str(out), *options(study)]) == 0
    again = json.loads(out.read_text())
    if again["inputs"]["code_sha256"] == base.report["inputs"]["code_sha256"]:
        assert out.read_text() == base.json_text
    # (a module edited between the two runs moves its recorded hash and nothing else)
    again["inputs"]["code_sha256"] = base.report["inputs"]["code_sha256"]
    assert again == base.report
    assert out.with_suffix(".md").read_text() == base.table
    printed = capsys.readouterr().out
    assert printed.splitlines()[:-1] == base.printed.splitlines()[:-1]
    assert sorted(p.name for p in out.parent.iterdir()) == [out.name, out.with_suffix(".md").name]


def leaves(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaves(item)
    else:
        yield value


def test_no_output_says_anything_about_a_single_statement(
    study: SimpleNamespace, base: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    code, listed = check(study, capsys)
    assert code == 0
    selections = "".join(
        (study.paths.selections / ev.SELECTION_NAME.format(model=m)).read_text()
        for m in rd.PRIMARIES
    )
    outputs = base.json_text + base.table + base.printed + listed + selections
    table = study.table
    for column in (
        "statement_group_id",
        "event_id",
        "thread_id",
        "episode_id",
        "generic_name",
        "presentation",
    ):
        values = set(table[column]) - {""}
        assert len(values) > 50 or column == "generic_name"
        assert not [value for value in values if value in outputs], column
    assert "NDC" not in outputs and "Estimated recovery" not in outputs
    # no date of a statement, a horizon or a bracket: the only dates are the two cutoff days
    dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", outputs))
    assert dates == {"2023-12-31", "2024-12-31"}
    # no list as long as the eligible list, the probe subset or the scoreable statements
    sizes = {320, 300, base.report["items"]["scoreable_statements"]}
    lists = [v for v in walk(base.report) if isinstance(v, list)]
    assert lists and max(len(v) for v in lists) < 30 and not sizes & {len(v) for v in lists}
    assert all(isinstance(v, str | int | float | bool | type(None)) for v in leaves(base.report))
    assert len(base.printed.splitlines()) == 2 + 6 + 2 + 1  # two lines beside H3
    assert len(base.table.splitlines()) == 6 + 6 + 1 + 3 * 2


def walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def test_the_table_has_one_row_per_test(base: SimpleNamespace) -> None:
    lines = base.table.splitlines()
    rows = [line for line in lines if line.startswith("| H")]
    assert len(rows) == 6 and lines[0] == "# Confirmatory results (PLAN.md section 6)"
    assert (
        "Holm over 6 tests at 0.05; 10000 draws by shortage episode, seed 20261001." in base.table
    )
    header = next(line for line in lines if line.startswith("| Test"))
    assert all(row.count("|") == header.count("|") for row in rows)
    for entry, row in zip(base.report["family"], rows, strict=True):
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert cells[:4] == [
            entry["hypothesis"],
            entry["model"],
            entry["comparator"],
            entry["tested"],
        ]
        assert cells[5:8] == [
            str(entry["statements"]),
            str(entry["episodes"]),
            f"{entry['delta']:.4f}",
        ]
        assert cells[9:] == [f"{entry['p']:.4f}", f"{entry['p_holm']:.4f}", entry["reading"]]
    assert sum(line.startswith("Probe, ") for line in lines) == 2


# --------------------------------------------------------------------------------------------
# The dev command on the open train-period data
# --------------------------------------------------------------------------------------------


def stand_in(pred: pd.Series) -> dict[str, Any]:
    """A model-free prediction as a predictive answer: the two probabilities as they are, the
    quantiles as whole days."""
    days = [round(float(pred[key])) for key in P.QUANTILE_KEYS]
    return {
        "p_by_horizon_a": float(pred["p_a"]),
        "p_by_horizon_b": float(pred["p_b"]),
        "days_to_recovery": dict(
            zip(P.QUANTILE_KEYS, np.maximum.accumulate(days).tolist(), strict=True)
        ),
    }


def test_dev_command_on_the_open_data_with_stand_in_readings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The dev command on the study's own open tables (train-period outcomes only). The three
    conditions are stand-ins made from model-free predictors fitted on the fit split: (a) the
    base rate, (b) the text-trained model, (c) the rule's own reading. The losses must be those
    of ``power.py``, and of ``out/dev_losses.json`` when that file is of the same build."""
    if not D.STATEMENTS.is_file():
        pytest.skip("the open statement table is not on disk")
    table = D.load_statements(D.STATEMENTS)
    frame = P.prepare(table)
    _, dev, free = W.fit_and_predict(frame)
    scoreable = dev[dev["scoreable"]]
    assert set(scoreable["period"]) == {"train"} and len(scoreable) > 100
    ids = sorted(scoreable.index)
    cells = table.set_index("statement_group_id", drop=False)
    assert (cells.loc[ids, "event_date"] < "2023-01-01").all()
    items = tmp_path / "items"
    items.mkdir()
    text = D.jsonl(D.items(table, ids))
    (items / "dev_scoreable.jsonl").write_text(text, encoding="utf-8")
    (items / "track_fit.json").write_text(json.dumps(TRACK))
    counts = tmp_path / "counts.json"
    record = {
        "outputs": {
            D.STATEMENTS.name: {"sha256": D.sha16(D.STATEMENTS.read_bytes())},
            D.ITEMS.name: {"dev_scoreable.jsonl": {"sha256": D.sha16(text.encode("utf-8"))}},
        }
    }
    counts.write_text(json.dumps(record))
    plan_options = lp.default_options(items)
    plan_options |= {"out_root": str(tmp_path / "read"), "local_root": str(tmp_path / "local")}
    plan_options["counts"] = {"e3": 100, "tbd": 10, "silent": 10, "stale": 10}
    plan = lp.make_plan(plan_options)
    lp.plan_path(tmp_path / "read").parent.mkdir(parents=True)
    lp.plan_path(tmp_path / "read").write_text(lp.plan_text(plan), encoding="utf-8")

    def entry(prompt: str) -> str:
        """The entry block of a prompt: what a reader is shown of the statement."""
        return prompt.split("\nEntry\n", 1)[1].split("\n\n", 1)[0]

    shown = rd.TEMPLATES["predictive-v1"]
    by_entry = {
        entry(rd.render_for(shown, item)): item.item_id
        for item in rd.load_items(items / "dev_scoreable.jsonl")
    }
    assert len(by_entry) == len(ids)  # no two statements of the list look the same

    def item_of(prompt: str) -> str:
        return by_entry[entry(prompt)]

    source = {"a": "base_rate", "b": "gbm_text"}

    def reply_for(condition: str) -> Callable[[str], str]:
        def reply(prompt: str) -> str:
            item = item_of(prompt)
            if condition == "c":
                row = cells.loc[item]
                return json.dumps(literal("recovery", row["stated_start"], row["stated_end"]))
            return json.dumps(stand_in(free[source[condition]].loc[item]))

        return reply

    for run in lp.select(plan, ["dev"], models=[LLAMA]):
        make_run(plan, run, reply_for(condition_of(run["line"])), tmp_path / "local")
    out = tmp_path / "selection.json"
    args = [
        "--statements",
        str(D.STATEMENTS),
        "--counts",
        str(counts),
        "--out-root",
        str(tmp_path / "read"),
    ]
    assert ev.main(["dev", "--model", LLAMA, "--out", str(out), *args]) == 0
    printed = capsys.readouterr().out
    got = json.loads(out.read_text())
    want = W.primary_losses(scoreable, free).mean()
    conditions = got["conditions"]
    assert conditions["a"]["primary_brier"] == pytest.approx(want["base_rate"], abs=1e-6)
    assert conditions["b"]["primary_brier"] == pytest.approx(want["gbm_text"], abs=1e-6)
    assert conditions["c"]["primary_brier"] == pytest.approx(want["rules_plus_slip"], abs=1e-6)
    assert got["selection"]["selected"] == ev.lowest(
        {"a": want["base_rate"], "b": want["gbm_text"], "c": want["rules_plus_slip"]}, ev.CONDITIONS
    )
    assert got["dev"]["scoreable_statements"] == len(scoreable) == got["dev"]["statements_read"]
    assert got["dev"]["scoreable_by_E_end_and_E_end90"] == W.outcome_mix(scoreable)
    assert got["dev"]["dated_statements"] == len(dev)
    for name in G.PREDICTORS:
        assert got["model_free"][name]["primary_brier"] == pytest.approx(want[name], abs=1e-6)
    assert got["h3_comparator"]["selected"] == "base_rate"
    assert got["h3_comparator"]["under_each_rule"]["better_on_dev"] == ev.lowest(
        dict(want), ev.COMPARATOR_CANDIDATES
    )
    for condition in ev.CONDITIONS:
        assert conditions[condition]["by_status"] == {"ok": len(ids)}
        assert conditions[condition]["by_echo"] == {"ok": len(ids)}
    assert not [i for i in ids if i in printed or i in out.read_text()]
    # the registered file of the power code, when it is of the same build as the table
    if not W.DEV_LOSSES.is_file():
        return
    written = json.loads(W.DEV_LOSSES.read_text())
    code = W.code_record()
    same = written["inputs"]["statements_sha256"] == D.sha16(D.STATEMENTS.read_bytes()) and all(
        written["inputs"][key] == code[key] for key in ("predictors_sha256", "gbm_sha256")
    )
    if not same:
        return
    losses = written["losses"]
    for condition, name in (("a", "base_rate"), ("b", "gbm_text"), ("c", "rules_plus_slip")):
        assert conditions[condition]["primary_brier"] == pytest.approx(
            losses[name]["primary_brier"], abs=2e-6
        )
        assert conditions[condition]["ci95"] == pytest.approx(losses[name]["ci95"], abs=2e-6)
        assert conditions[condition]["brier_E_end"] == pytest.approx(
            losses[name]["brier_E_end"], abs=2e-6
        )
    for name in G.PREDICTORS:
        assert got["model_free"][name]["primary_brier"] == pytest.approx(
            losses[name]["primary_brier"], abs=2e-6
        )
        assert got["model_free"][name]["ci95"] == pytest.approx(losses[name]["ci95"], abs=2e-6)
    assert (
        got["dev"]["scoreable_by_E_end_and_E_end90"]
        == written["dev"]["scoreable_by_E_end_and_E_end90"]
    )
    assert got["dev"]["scoreable_statements"] == written["dev"]["scoreable_statements"]
