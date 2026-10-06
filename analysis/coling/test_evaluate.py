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

Covered: Holm on a hand-worked example; every p-value procedure on cases small enough to work out by
hand, against its definition one draw at a time, on the registered draws and against
``size_check.py``; a bootstrap draw that is exactly zero, counted on both sides; the interval of the
registered test (each end against the test itself, on few and many episodes, skewed, sparse, tied
and constant differences; a value other than zero against a computation from the statements and
against ``size_check.py``; the search written out again, with another seed too; a p-value on the
level itself; unbounded ends in the file, the table and the flag beside H3, and the line that says
what such an end is); the equivalence reading by two p-values against the 90% interval, with the
margin on an end, and the three cases in which the rule and the interval part (the interval beyond a
margin that is rejected, inside one that is not, and without an end although the margin is
rejected); the counts of statements and episodes on which two losses differ, on the item set of the
test; the percentile source against numbers the evaluator gave before it had another interval; the
two registered constants and every candidate of each, from the dev command to the result file; the
decisions the result file lists where the plan is silent; the readings as predictions, with the
base-rate and ABSTAIN fallbacks and their counts; the dev command, its selection, its comparator
and its refusals; the completeness check, which reads no outcome and never looks at the sealed
path; every refusal of a partial, mismatched or wrong-set run, of a stored reading that the harness
would not have accepted, of a wrong hash, of files of another build and of a stop inside the rules
or in the texts of the results, each with nothing written and, before the evaluation, the sealed
file left unread; the probe test, the switch to the post-cutoff slice, the small-slice rule at its
boundary and a primary declared not evaluable; the six tests against a computation made here from
the scripted answers and the synthetic outcomes; bounds, secondaries and scores; the
overconfidence criterion of PLAN section 13 (each of its five readings on rows worked by hand, an
interval that holds zero or has an end on it, an event undetermined at one horizon alone, failed
answers in the main figures and out of the parsed-only ones, a reading that the parsed answers
alone would give otherwise, the parsed-only figures withheld when a few answers failed or parsed,
every interval against a loop over the registered draws, a draw that is zero up to rounding, the
base rate on the item set of a switched primary in a study built by hand, an item set without a
scoreable statement, a primary without an item set, the keys of the result file and the line of
the table and of the printout); the hash of the model-free predictions; the same result on a second
run; no statement in any output. The last test
runs the dev command on the open train-period data with stand-in readings made from the model-free
predictors and compares it with ``power.py`` (and with ``out/dev_losses.json`` when that file is of
the same build); it is skipped when the open tables are absent.

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
MEMO: dict[tuple, Any] = {}
REAL_REFIT, REAL_DEV_FIT = ev.refit, W.fit_and_predict
REAL_INTERVAL = ev.larger_of_interval
SOURCE = ev.P_VALUE_SOURCE
"""The registered p-value source, as the evaluator has it."""
LARGER = "larger_of_studentised_and_sign_flip_t"
BY_TEST = ev.interval_method(SOURCE) == ev.TEST_INTERVAL
"""Whether the confirmatory intervals are those of the registered test under ``SOURCE``."""


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


def cached_interval(
    sums: np.ndarray,
    sizes: np.ndarray,
    taken: np.ndarray,
    coverage: float,
    draws: int = ev.DRAWS,
    seed: int = ev.SEED,
) -> list[float | None]:
    """``evaluate.larger_of_interval``, searched once per contrast for the whole module (the
    search is slow and deterministic; the tests of the search itself call the real one)."""
    held = hashlib.sha256()
    for part in (sums, sizes, taken):
        held.update(np.ascontiguousarray(part, dtype=float).tobytes())
    key = ("interval", held.hexdigest(), coverage, draws, seed)
    key += (ev.INTERVAL_REACH, ev.INTERVAL_STEPS)
    if key not in MEMO:
        MEMO[key] = REAL_INTERVAL(sums, sizes, taken, coverage, draws, seed)
    return list(MEMO[key])


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
    monkeypatch.setattr(ev, "larger_of_interval", cached_interval)


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


def counts_apart(d: pd.Series, episode: pd.Series) -> dict[str, int]:
    """The counts beside H2 from the paired differences ``d`` of the statements of a test."""
    apart = d[d.abs() > 1e-12]
    held = d.groupby(episode.loc[d.index]).sum().loc[sorted(set(episode.loc[apart.index]))]
    return {
        "statements": len(apart),
        "episodes": len(held),
        "episodes_with_a_positive_sum": int((held > 1e-12).sum()),
        "episodes_with_a_negative_sum": int((held < -1e-12).sum()),
        "episodes_whose_differences_cancel": int((held.abs() <= 1e-12).sum()),
    }


def counts_line(apart: dict[str, int]) -> str:
    """The sentence of the table that gives the counts beside H2."""
    return (
        f"The two losses differ on {apart['statements']} statements in {apart['episodes']} "
        f"episodes: {apart['episodes_with_a_positive_sum']} with a positive sum, "
        f"{apart['episodes_with_a_negative_sum']} with a negative one, "
        f"{apart['episodes_whose_differences_cancel']} whose differences cancel."
    )


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
    side, with the registered draws and sign patterns. The two part only where rounding settles
    a statistic (``test_the_size_check_parts_where_rounding_settles_a_statistic``); a draw whose
    differences cancel to a rounding error is a zero for both
    (``test_a_draw_whose_differences_cancel_counts_on_both_sides``)."""
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
    # the size check takes the same draws for zero, in its own code
    theirs = SC.contrast_tests(comparator - tested, clusters, 0.0, 2000)["percentile"]
    assert [theirs[key] for key in ("p_upper", "p_lower", "p_two_sided")] == list(
        result["p_values"]["percentile"].values()
    )


def test_the_size_check_parts_where_rounding_settles_a_statistic() -> None:
    """Differences without any variance: the standard error is zero up to rounding, and the
    plan's statistic is then plus infinity (PLAN section 6, "Test statistic"), reached by one
    sign pattern in 128, whatever the sizes of the seven episodes. The size check divides
    without that tolerance, and what it gives depends on how the rounding falls."""
    theirs = []
    for sizes in ([1] * 7, [5] * 7, [3, 5, 2, 7, 4, 6, 1]):
        clusters = [f"g{g}" for g, size in enumerate(sizes) for _ in range(size)]
        d = np.full(len(clusters), 0.1)
        sums, counts, taken = summed(d, clusters, 2000)
        mine = ev.larger_of_at(sums, counts, taken, 0.0, 2000)
        assert (mine["one_sided"], mine["one_sided_lower"]) == (1 / 128, 1.0)
        theirs.append(SC.contrast_tests(d, clusters, 0.0, 2000)["max_t"]["p_upper"])
    assert theirs[2] == 1 / 128 and theirs[0] != 1 / 128 != theirs[1]


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
# The interval of the registered test, the equivalence reading and the counts beside H2
# --------------------------------------------------------------------------------------------


def differences(shape: str, episodes: int, seed: int = 0) -> tuple[np.ndarray, list[str]]:
    """Paired differences over episodes of 1 to 11 statements, of one of five shapes: ``even``
    (normal), ``skewed``, ``sparse`` (zero outside about three episodes in ten, the shape of
    H2), ``few values`` (many ties and exact zeros) and ``no variance`` (0.25 everywhere)."""
    rng = np.random.default_rng([seed, episodes])
    sizes = rng.integers(1, 12, size=episodes)
    clusters = [f"g{g:03d}" for g in range(episodes) for _ in range(sizes[g])]
    n = len(clusters)
    on = np.repeat(rng.random(episodes) < 0.3, sizes)
    shapes = {
        "even": rng.normal(0.01, 0.2, size=n),
        "skewed": rng.exponential(0.1, size=n) - 0.08,
        "sparse": on * rng.normal(0.02, 0.3, size=n),
        "few values": rng.choice([-0.18, 0.0, 0.07, 0.32], size=n),
        "no variance": np.full(n, 0.25),
    }
    return shapes[shape], clusters


def summed(d: np.ndarray, clusters: list[str], draws: int) -> tuple[np.ndarray, ...]:
    """The episode sums and sizes of paired differences, and ``draws`` bootstrap draws."""
    sums, sizes = P.cluster_sums(d, clusters)
    return sums[:, 0], sizes, P.cluster_draws(len(sizes), draws, ev.SEED).astype(float)


SHAPES = ("even", "skewed", "sparse", "few values", "no variance")


@pytest.mark.parametrize("episodes", [3, 5, 6, 13, 14, 40])
@pytest.mark.parametrize("shape", SHAPES)
def test_the_interval_of_the_registered_test_holds_the_values_it_does_not_reject(
    shape: str, episodes: int
) -> None:
    """PLAN section 6, "Intervals": at coverage ``1 - a`` the interval runs from the smallest
    value whose one-sided p-value for a larger contrast is not below ``a / 2`` to the largest
    whose one-sided p-value for a smaller contrast is not below ``a / 2``. Checked with the test
    itself (``larger_of_at``), each end on its own p-value: an end is not rejected, a value just
    inside it is not, a value just outside it is; the estimate lies inside; and an end is
    unbounded when, and only when, the test does not reject 50 standard errors away. The
    two-sided p-value (twice the smaller of the two) gives the same answers on these data."""
    draws = 400
    sums, sizes, taken = summed(*differences(shape, episodes), draws)
    delta, se, _ = ev.robust_t(sums, sizes, ev.rounding_tolerance(sums))
    flat = shape == "no variance"
    assert (se == 0) is flat and delta == pytest.approx(float(sums.sum() / sizes.sum()))
    far = 1.0 if flat else 50 * se

    def rejected(value: float, side: str, level: float) -> bool:
        found = ev.larger_of_at(sums, sizes, taken, value, draws)
        assert (found[side] < level / 2) is (found["two_sided"] < level)
        return found[side] < level / 2

    for coverage in (0.95, 0.90):
        level = 1 - coverage
        ends = REAL_INTERVAL(sums, sizes, taken, coverage, draws)
        assert len(ends) == 2 and ends == REAL_INTERVAL(sums, sizes, taken, coverage, draws)
        # the lower end rests on the p-value for a larger contrast, the upper end on the other
        for end, direction, side in zip(ends, (-1, 1), ev.SIDES[:2], strict=True):
            assert (end is not None) is rejected(delta + direction * far, side, level)
            if end is None:
                continue
            assert isinstance(end, float) and direction * (end - delta) >= 0
            assert not rejected(end, side, level)  # the end is the last value not rejected
            step = 1e-6 * far
            assert rejected(end + direction * step, side, level)
            if flat:
                assert end == delta == 0.25  # every other value has the one same p-value
            else:
                assert end != delta and not rejected(end - direction * step, side, level)
        # the smallest p-value the sign patterns can give is one in 2^episodes: with few
        # episodes nothing is ever rejected, whatever the data
        if 2.0**-episodes >= level / 2:
            assert ends == [None, None]
        elif shape != "sparse":
            assert None not in ends
    # a wider coverage never gives a narrower interval
    wide, narrow = (REAL_INTERVAL(sums, sizes, taken, c, draws) for c in (0.95, 0.90))
    for (a, b), sign in zip(zip(wide, narrow, strict=True), (-1, 1), strict=True):
        assert a is None or (b is not None and sign * (a - b) >= 0)


def test_the_interval_is_unbounded_where_too_many_draws_have_no_variance() -> None:
    """The shape of H2 with few episodes that differ, all in one direction. A bootstrap draw
    that takes neither of the two episodes has a mean of zero and no variance: its statistic is
    minus infinity, below any observed one, so the p-value for a smaller contrast never falls
    below the share of such draws and no larger value of the contrast is ever rejected. The
    interval has no upper end, and equivalence cannot be declared at any margin."""
    rng = np.random.default_rng(12)
    sizes = rng.integers(1, 9, size=12)
    clusters = [f"g{g:02d}" for g in range(12) for _ in range(sizes[g])]
    differs = np.isin(clusters, ["g03", "g07"])
    d = np.where(differs, rng.uniform(0.05, 0.3, size=len(clusters)), 0.0)
    sums, counts, taken = summed(d, clusters, ev.DRAWS)
    neither = int(((taken[:, 3] == 0) & (taken[:, 7] == 0)).sum())
    floor = (1 + neither) / (ev.DRAWS + 1)
    assert floor > 0.10
    low, high = REAL_INTERVAL(sums, counts, taken, 0.90)
    assert high is None and low is not None and low <= float(d.mean())
    for null in (0.0, 0.02, 0.5, 40.0):
        assert ev.larger_of_at(sums, counts, taken, null)["one_sided_lower"] >= floor
    assert ev.larger_of_at(sums, counts, taken, 0.5)["one_sided_lower"] == pytest.approx(floor)
    entry = ev.contrast(
        d, np.zeros(len(d)), clusters, source=LARGER, levels=["ci95", "ci90"], margin=0.5
    )
    assert entry["ci90"] == [low, None] and entry["ci95"][1] is None
    found = ev.equivalence(entry, 0.5)
    assert found["declared"] is False and found["p_smaller_at_the_margin"] == pytest.approx(floor)
    # the percentile interval of the same draws has both ends, and would have declared it
    assert entry["percentile"]["ci90"][0] == 0.0 and entry["percentile"]["ci90"][1] < 0.5
    with_ends = ev.contrast(d, np.zeros(len(d)), clusters, source="percentile")
    assert ev.equivalence(with_ends, 0.5)["declared"] is True


def by_hand_larger_of(
    d: np.ndarray,
    clusters: list[str],
    null: float,
    taken: np.ndarray,
    signs: np.ndarray,
    all_: bool,
) -> dict[str, float]:
    """The larger-of p-values for the hypothesis that the mean difference is ``null``, from the
    statements themselves: ``null`` is taken off every difference, and every bootstrap draw and
    every sign pattern is a list of episodes worked out on its own."""
    names = sorted(set(clusters))
    members = [
        np.array([x - null for x, c in zip(d, clusters, strict=True) if c == name])
        for name in names
    ]
    scale = max(1.0, max(abs(float(part.sum())) for part in members))

    def mean_of(parts: list[np.ndarray]) -> float:
        return sum(float(part.sum()) for part in parts) / sum(len(part) for part in parts)

    def t_of(parts: list[np.ndarray], centre: float) -> float:
        n, mean = sum(len(part) for part in parts), mean_of(parts)
        spread = sum((float(part.sum()) - mean * len(part)) ** 2 for part in parts)
        se = float(np.sqrt(len(parts) / (len(parts) - 1) * spread)) / n
        if se <= 1e-12 * scale:  # no variance: infinite by the sign of what is on top, or zero
            return (
                0.0
                if abs(mean - centre) <= 1e-12 * scale
                else float(np.copysign(np.inf, mean - centre))
            )
        return (mean - centre) / se

    observed = t_of(members, 0.0)
    stars = [
        t_of([members[g] for g, k in enumerate(row) for _ in range(int(k))], mean_of(members))
        for row in taken
    ]
    flipped = [
        t_of([sign * part for sign, part in zip(row, members, strict=True)], 0.0) for row in signs
    ]
    slack = 1e-9 * max([abs(t) for t in flipped if np.isfinite(t)] or [0.0])
    extra = 0 if all_ else 1
    upper = max(
        (1 + sum(star >= observed for star in stars)) / (len(stars) + 1),
        (extra + sum(t >= observed - slack for t in flipped)) / (len(flipped) + extra),
    )
    lower = max(
        (1 + sum(star <= observed for star in stars)) / (len(stars) + 1),
        (extra + sum(t <= observed + slack for t in flipped)) / (len(flipped) + extra),
    )
    return {
        "one_sided": upper,
        "one_sided_lower": lower,
        "two_sided": min(1.0, 2 * min(upper, lower)),
    }


@pytest.mark.parametrize("episodes", [5, 7, 15])
@pytest.mark.parametrize("shape", SHAPES)
def test_a_value_other_than_zero_is_tested_on_the_differences_minus_that_value(
    shape: str, episodes: int
) -> None:
    """PLAN section 6: "A value other than zero is tested in the same way on the sums ``S_g -
    delta0 n_g``." ``larger_of_at`` against a computation made here from the statements, one
    draw and one sign pattern at a time, for values on both sides of the estimate."""
    draws = 150
    d, clusters = differences(shape, episodes)
    sums, sizes, taken = summed(d, clusters, draws)
    if episodes <= ev.EXACT_FLIPS_UP_TO:
        signs = np.array(
            [[1 - 2 * ((k >> g) & 1) for g in range(episodes)] for k in range(2**episodes)]
        )
    else:
        signs = 1 - 2 * np.random.default_rng(ev.SEED).integers(0, 2, size=(draws, episodes))
    delta = float(d.mean())
    seen = set()
    for null in (0.0, -0.07, 0.013, 0.2, delta - 0.031, delta + 0.044, 3.0):
        got = ev.larger_of_at(sums, sizes, taken, null, draws)
        want = by_hand_larger_of(d, clusters, null, taken, signs, episodes <= ev.EXACT_FLIPS_UP_TO)
        assert got == pytest.approx(want, abs=1e-12), null
        assert list(got) == list(ev.SIDES)
        seen.add((got["one_sided"], got["one_sided_lower"]))
        # the two parts, each on its own, are the tests of zero on the moved sums
        moved = sums - null * sizes
        assert got == ev.larger_of(
            ev.studentised(moved, sizes, taken), ev.sign_flip_t(moved, sizes, draws)
        )
    assert len(seen) >= (2 if shape == "no variance" else 3)  # the value tested matters
    # zero is the test every contrast reports
    at_zero = ev.contrast(d, np.zeros(len(d)), clusters, draws=draws)["p_values"][LARGER]
    assert ev.larger_of_at(sums, sizes, taken, 0.0, draws) == at_zero


@pytest.mark.parametrize(("shape", "episodes"), [("skewed", 9), ("sparse", 14), ("even", 30)])
def test_a_value_other_than_zero_gives_the_p_values_of_the_size_check(
    shape: str, episodes: int
) -> None:
    """The same on the registered draws and sign patterns, against ``size_check.py``, which
    takes the value off the episode sums in its own code."""
    d, clusters = differences(shape, episodes)
    sums, sizes, taken = summed(d, clusters, ev.DRAWS)
    for null in (-0.05, 0.02, float(d.mean()) + 0.01):
        mine = ev.larger_of_at(sums, sizes, taken, null)
        theirs = SC.contrast_tests(d, clusters, null=null)["max_t"]
        assert [mine[side] for side in ev.SIDES] == pytest.approx(
            [theirs[key] for key in ("p_upper", "p_lower", "p_two_sided")], abs=1e-12
        )


def test_sign_patterns_that_are_handed_over_are_the_ones_used() -> None:
    """The search makes the sign patterns once and hands them to every test of a value. Two
    patterns in place of the registered ones: the observed signs and their mirror image."""
    d, clusters = differences("even", 7)
    sums, sizes, taken = summed(d, clusters, 150)
    usual = ev.sign_patterns(7, 150, ev.SEED)
    assert usual[0].shape == (2**7, 7) and usual[1] is True
    assert ev.sign_flip_t(sums, sizes, 150, ev.SEED, usual) == ev.sign_flip_t(sums, sizes, 150)
    two = (np.array([[1.0] * 7, [-1.0] * 7]), True)
    mirrored = ev.sign_flip_t(sums, sizes, patterns=two)
    assert mirrored["patterns"] == 2 and float(sums.sum()) > 0
    assert (mirrored["one_sided"], mirrored["one_sided_lower"]) == (0.5, 1.0)
    null = float(d.mean()) - 0.3
    default = ev.larger_of_at(sums, sizes, taken, null, 150)
    assert ev.larger_of_at(sums, sizes, taken, null, 150, ev.SEED, usual) == default
    handed = ev.larger_of_at(sums, sizes, taken, null, 150, ev.SEED, two)
    assert default["one_sided"] < 0.05 and handed["one_sided"] == 0.5


def plain_search(
    sums: np.ndarray,
    sizes: np.ndarray,
    taken: np.ndarray,
    coverage: float,
    draws: int,
    halvings: int = 60,
    reach: float = 50.0,
    not_below: bool = True,
    seed: int = ev.SEED,
) -> list[float | None]:
    """The search of PLAN section 6 written out again: from the estimate to the value ``reach``
    standard errors away, ``halvings`` times; the end is the last value not rejected. With
    ``not_below`` false a p-value that equals the level counts as rejected. The two registered
    levels are written here as the plan has them, 0.025 and 0.05, and not computed; ``seed`` is
    that of the sign patterns (``taken`` holds the bootstrap draws)."""
    half = {0.95: 0.025, 0.90: 0.05}.get(coverage, (1 - coverage) / 2)
    total = float(sizes.sum())
    delta = float(sums.sum()) / total
    residuals = sums - delta * sizes
    se = float(np.sqrt(len(sizes) / (len(sizes) - 1) * (residuals**2).sum())) / total
    found: list[float | None] = []
    for key, far in (("one_sided", delta - reach * se), ("one_sided_lower", delta + reach * se)):

        def stays(value: float, key: str = key) -> bool:
            p = ev.larger_of_at(sums, sizes, taken, value, draws, seed)[key]
            return p >= half if not_below else p > half

        if stays(far):
            found.append(None)
            continue
        kept, dropped = delta, far
        for _ in range(halvings):
            between = (kept + dropped) / 2
            kept, dropped = (between, dropped) if stays(between) else (kept, between)
        found.append(kept)
    return found


def test_the_search_is_sixty_halvings_from_fifty_standard_errors() -> None:
    """Each end is found by bisection between the estimate and the value 50 standard errors
    away, in 60 halvings. On differences moved so that the lower end falls next to zero the
    search has not closed on two neighbouring numbers by then, and one halving more or fewer,
    or another starting distance, ends on another number."""
    assert (ev.INTERVAL_REACH, ev.INTERVAL_STEPS) == (50.0, 60)
    draws, told_apart = 300, 0
    for seed in range(2, 8):
        d, clusters = differences("even", 14, seed)
        sums, sizes, taken = summed(d, clusters, draws)
        first = REAL_INTERVAL(sums, sizes, taken, 0.95, draws)
        assert first == plain_search(sums, sizes, taken, 0.95, draws) and None not in first
        sums, sizes, taken = summed(d - first[0], clusters, draws)
        ends = REAL_INTERVAL(sums, sizes, taken, 0.95, draws)
        assert ends == plain_search(sums, sizes, taken, 0.95, draws)
        assert abs(ends[0]) < 1e-15 < ends[1]
        others = [
            plain_search(sums, sizes, taken, 0.95, draws, halvings=59),
            plain_search(sums, sizes, taken, 0.95, draws, halvings=61),
            plain_search(sums, sizes, taken, 0.95, draws, reach=49.0),
        ]
        assert others[2] != ends
        told_apart += others[0] != ends and others[1] != ends
        for other in others:  # the same interval for every use, to the last few digits
            assert other == pytest.approx(ends, abs=1e-12)
    assert told_apart >= 2


def test_another_seed_gives_other_draws_and_other_sign_patterns() -> None:
    """The seed asked for reaches the bootstrap draws and the sign patterns alike, in the search
    for each end and in the two tests at the margin. Twenty episodes, so that the sign patterns
    are drawn and not enumerated: with another seed the interval and the two p-values at the
    margin are those of that seed's draws and that seed's patterns, and the registered patterns
    on the same draws give other numbers."""
    d, clusters = differences("even", 20, 5)
    draws, seed = 300, ev.SEED + 1
    sums, sizes = P.cluster_sums(d, clusters)
    sums = sums[:, 0]
    assert len(sizes) == 20 > ev.EXACT_FLIPS_UP_TO
    taken = P.cluster_draws(20, draws, seed).astype(float)
    want = plain_search(sums, sizes, taken, 0.95, draws, seed=seed)
    registered = plain_search(sums, sizes, taken, 0.95, draws)
    assert None not in want and want != registered
    margin = 0.9 * max(abs(want[0]), abs(want[1]))  # inside the far end: no p-value is tiny

    def at_the_margin(patterns_of: int) -> dict[str, float]:
        above = ev.larger_of_at(sums, sizes, taken, margin, draws, patterns_of)
        below = ev.larger_of_at(sums, sizes, taken, -margin, draws, patterns_of)
        return {
            "p_smaller_at_the_margin": above["one_sided_lower"],
            "p_larger_at_minus_the_margin": below["one_sided"],
        }

    entry = ev.contrast(
        d,
        np.zeros(len(d)),
        clusters,
        draws=draws,
        seed=seed,
        source=LARGER,
        levels=["ci95"],
        margin=margin,
    )
    assert entry["ci95"] == want == REAL_INTERVAL(sums, sizes, taken, 0.95, draws, seed)
    assert entry["at_the_margin"] == at_the_margin(seed) != at_the_margin(ev.SEED)


def test_a_p_value_that_equals_the_level_is_not_below_it() -> None:
    """The interval holds every value whose p-value is "not below" the level, and equivalence
    needs p-values "below" it. With five episodes the sign patterns give p-values in steps of
    1/32, and an interval of coverage 0.5 is cut at 8/32 exactly: the values with that p-value
    belong to the interval, and a margin among them declares nothing."""
    draws, hit, margins = 200, 0, 0
    for seed in range(12):
        d, clusters = differences("skewed", 5, seed)
        sums, sizes, taken = summed(d, clusters, draws)
        ends = REAL_INTERVAL(sums, sizes, taken, 0.5, draws)
        assert ends == plain_search(sums, sizes, taken, 0.5, draws)
        strict = plain_search(sums, sizes, taken, 0.5, draws, not_below=False)
        sides = [ev.larger_of_at(sums, sizes, taken, end, draws) for end in ends]
        on_level = [sides[0]["one_sided"] == 0.25, sides[1]["one_sided_lower"] == 0.25]
        assert None not in ends and None not in strict
        for k, outwards in ((0, -1), (1, 1)):
            assert (ends[k] != strict[k]) is on_level[k]
            assert not on_level[k] or outwards * (ends[k] - strict[k]) > 0
        hit += sum(on_level)
        if not on_level[1] or strict[1] <= 0:
            continue
        margins += 1
        # a margin between the two upper ends: its p-value is the level itself
        with pytest.MonkeyPatch.context() as patch:
            patch.setitem(ev.LEVELS, "ci90", 0.5)
            margin = (ends[1] + strict[1]) / 2
            entry = ev.contrast(
                d,
                np.zeros(len(d)),
                clusters,
                draws=draws,
                source=LARGER,
                levels=["ci90"],
                margin=margin,
            )
            found = ev.equivalence(entry, margin)
            assert entry["ci90"] == ends and found["level"] == 0.25
            assert found["p_smaller_at_the_margin"] == 0.25 and found["declared"] is False
            wide = 2 * max(abs(ends[0]), abs(ends[1]))
            entry = ev.contrast(
                d,
                np.zeros(len(d)),
                clusters,
                draws=draws,
                source=LARGER,
                levels=["ci90"],
                margin=wide,
            )
            assert ev.equivalence(entry, wide)["declared"] is True
    assert hit >= 6 and margins >= 3
    # the same far away: three episodes give no p-value below 1/8, the level of a coverage of
    # 0.75, so the search does not start and both ends are unbounded
    d, clusters = differences("even", 3)
    sums, sizes, taken = summed(d, clusters, draws)
    delta, se, _ = ev.robust_t(sums, sizes, ev.rounding_tolerance(sums))
    for side, far in (("one_sided", delta - 50 * se), ("one_sided_lower", delta + 50 * se)):
        assert ev.larger_of_at(sums, sizes, taken, far, draws)[side] == 0.125 == ev.tail_of(0.75)
    assert REAL_INTERVAL(sums, sizes, taken, 0.75, draws) == [None, None]
    assert None not in REAL_INTERVAL(sums, sizes, taken, 0.70, draws)
    assert ev.tail_of(0.5) == 0.25 and ev.tail_of(0.70) == 0.15 and ev.tail_of(0.95) == 0.025
    assert ev.tail_of(0.90) == 0.05 and ev.LEVELS == {"ci95": 0.95, "ci90": 0.90}


def test_a_p_value_on_a_registered_level_is_not_below_it() -> None:
    """The two registered levels are 0.025 and 0.05 themselves, not the floats next to them
    that ``(1 - 0.95) / 2`` and ``(1 - 0.90) / 2`` give (PLAN section 6, "Intervals": a value is
    kept when its p-value is not below ``a/2``; equivalence needs p-values below 0.05). No
    p-value of 10,000 draws, or of every sign pattern of 13 episodes or fewer, falls on either
    level; a number of draws one short of a multiple of 40 gives p-values that do.

    * 39 draws and 14 episodes: no p-value is below 1/40, so a 95% interval has no end.
    * 399 and 1,999 draws: each end of a 95% interval is a value whose p-value is 0.025
      itself, and lies further out than the end of a search that drops such values.
    * 1,999 draws: a margin whose p-value is 100/2000 declares nothing; one whose p-value is
      99/2000 declares equivalence."""
    assert (ev.tail_of(0.95), ev.tail_of(0.90)) == (0.025, 0.05)
    assert (1 - 0.95) / 2 != 0.025 and (1 - 0.90) / 2 != 0.05  # what a plain division leaves
    for seed in range(3):
        sums, sizes, taken = summed(*differences("even", 14, seed), 39)
        delta, se, _ = ev.robust_t(sums, sizes, ev.rounding_tolerance(sums))
        for side, far in (("one_sided", delta - 50 * se), ("one_sided_lower", delta + 50 * se)):
            assert ev.larger_of_at(sums, sizes, taken, far, 39)[side] == 1 / 40 == 0.025
        assert REAL_INTERVAL(sums, sizes, taken, 0.95, 39) == [None, None]
        assert None not in REAL_INTERVAL(sums, sizes, taken, 0.90, 39)
    cases = ((399, "even", 20, 0), (1999, "skewed", 20, 1), (1999, "even", 14, 0))
    for draws, shape, episodes, seed in cases:
        sums, sizes, taken = summed(*differences(shape, episodes, seed), draws)
        ends = REAL_INTERVAL(sums, sizes, taken, 0.95, draws)
        assert ends == plain_search(sums, sizes, taken, 0.95, draws) and None not in ends
        strict = plain_search(sums, sizes, taken, 0.95, draws, not_below=False)
        for end, inner, side, outwards in zip(ends, strict, ev.SIDES[:2], (-1, 1), strict=True):
            assert outwards * (end - inner) > 0
            for value in (end, (end + inner) / 2):  # every value between the two is on the level
                assert ev.larger_of_at(sums, sizes, taken, value, draws)[side] == 0.025
    # the level of the equivalence reading: differences moved so that the lower end of the 90%
    # interval lies just above zero, and minus any margin far below it
    draws = 1999
    d, clusters = differences("skewed", 20, 1)
    sums, sizes, taken = summed(d, clusters, draws)
    d = d - REAL_INTERVAL(sums, sizes, taken, 0.90, draws)[0] + 0.001
    sums, sizes, taken = summed(d, clusters, draws)
    low, high = REAL_INTERVAL(sums, sizes, taken, 0.90, draws)
    assert [low, high] == plain_search(sums, sizes, taken, 0.90, draws) and 0 < low < high
    for margin, count, verdict in ((high, 100, False), (high * (1 + 1e-9), 99, True)):
        entry = ev.contrast(
            d,
            np.zeros(len(d)),
            clusters,
            draws=draws,
            source=LARGER,
            levels=["ci90"],
            margin=margin,
        )
        found = ev.equivalence(entry, margin)
        assert entry["ci90"] == [low, high] and found["level"] == 0.05
        assert found["p_smaller_at_the_margin"] == count / 2000
        assert found["p_larger_at_minus_the_margin"] == 1 / 2000
        assert found["declared"] is verdict


EQUIVALENCE_CASES = [(shape, episodes) for episodes in (6, 13, 14, 30) for shape in SHAPES[:4]]


@pytest.mark.parametrize(("shape", "episodes"), EQUIVALENCE_CASES)
def test_equivalence_by_two_p_values_is_the_ninety_percent_interval_inside_the_margin(
    shape: str, episodes: int
) -> None:
    """PLAN section 6: under the registered test, equivalence is declared when the p-value for
    a smaller contrast at the margin and the p-value for a larger one at minus the margin are
    both below 0.05, which is the 90% interval of that test lying strictly inside the margin.
    The verdict of the evaluator against the interval it reports, for margins well inside, well
    outside, exactly on each end (where the end is the last value not rejected, so nothing is
    declared) and a billionth of the interval's reach either side of each end. Two cases have
    an interval that lacks an end, and nothing is declared for them at any margin: the draws
    that take no episode with a difference keep the p-value above 0.05 however far the margin
    lies. The episodes here are of ordinary sizes; with one that dominates the two readings can
    part (``test_with_one_dominant_episode_the_rule_and_the_interval_can_part``), and so they
    can where an end is missing although the test rejects further away
    (``test_equivalence_can_be_declared_beside_an_end_that_is_unbounded``)."""
    draws = 400
    d, clusters = differences(shape, episodes)
    d = d / 10  # differences of the size of a margin of 0.02
    sums, sizes, taken = summed(d, clusters, draws)
    zeros = np.zeros(len(d))

    def read(margin: float) -> tuple[dict, dict]:
        entry = ev.contrast(
            d, zeros, clusters, draws=draws, source=LARGER, levels=["ci95", "ci90"], margin=margin
        )
        return entry, ev.equivalence(entry, margin)

    low, high = REAL_INTERVAL(sums, sizes, taken, 0.90, draws)
    ends = [end for end in (low, high) if end is not None]
    assert (len(ends) < 2) is ((shape, episodes) in {("sparse", 6), ("sparse", 13)}) and ends
    reach = max(abs(end) for end in ends)
    nudge = 1e-9 * reach
    margins = [0.02, reach / 2, 2 * reach, 50 * reach]
    for end in ends:
        margins += [abs(end), abs(end) + nudge, max(abs(end) - nudge, nudge)]
    verdicts = []
    for margin in margins:
        entry, found = read(margin)
        assert entry["ci90"] == [low, high] and found["ci90"] == [low, high]
        assert (found["margin"], found["level"]) == (margin, 0.05)
        assert found["interval_method"] == ev.TEST_INTERVAL == entry["interval_method"]
        smaller = ev.larger_of_at(sums, sizes, taken, margin, draws)["one_sided_lower"]
        larger = ev.larger_of_at(sums, sizes, taken, -margin, draws)["one_sided"]
        assert (found["p_smaller_at_the_margin"], found["p_larger_at_minus_the_margin"]) == (
            smaller,
            larger,
        )
        assert found["declared"] is bool(smaller < 0.05 and larger < 0.05)
        # the same verdict from the interval: both ends there, and strictly inside
        inside = len(ends) == 2 and low > -margin and high < margin
        assert found["declared"] is inside, (margin, low, high)
        verdicts.append(found["declared"])
    if len(ends) < 2:
        assert not any(verdicts)
        return
    assert verdicts[:4] == [reach < 0.02, False, True, True]
    # the end further from zero decides: on the margin it declares nothing, a little inside the
    # margin it does, a little outside it does not
    outer = 4 if abs(low) > abs(high) else 7
    assert verdicts[outer : outer + 3] == [False, True, False]


def record_under(source: str) -> dict[str, Any]:
    """The record of the constants as a result file holds it with ``source`` in force."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ev, "P_VALUE_SOURCE", source)
        return ev.registered_record()


def h2_report(d: np.ndarray, clusters: list[str]) -> dict[str, Any]:
    """A report of one H2 test on the paired differences ``d`` under the registered test, as
    far as the table and the printout read one: the contrast with both intervals, its
    equivalence reading at the registered margin and the counts beside it."""
    zeros = np.zeros(len(d))
    entry = ev.contrast(
        d, zeros, clusters, source=LARGER, levels=["ci95", "ci90"], margin=ev.H2_MARGIN
    )
    entry |= {"hypothesis": "H2", "model": "m", "comparator": "rules_plus_slip", "tested": "m:c"}
    entry |= {"sides": 2, "p": ev.registered_p(entry, 2, LARGER), "p_holm": 1.0, "holds": False}
    entry["equivalence"] = ev.equivalence(entry)
    entry["losses_differ"] = ev.differing(d, zeros, clusters)
    entry["reading"] = ev.reading_of(entry)
    episodes = len(set(clusters))
    return {
        "registered": record_under(LARGER),
        "h3": {"comparator": "base_rate"},
        "items": {
            "eligible_statements": len(d),
            "eligible_episodes": episodes,
            "scoreable_statements": len(d),
            "scoreable_episodes": episodes,
        },
        "family": [entry],
        "probe": {},
        "item_sets": {},
        "secondaries": {"overconfidence_of_condition_a": {}},
    }


def h2_line(report: dict[str, Any]) -> str:
    """The line of the table on the equivalence reading of the one H2 test of ``report``."""
    (line,) = [x for x in ev.markdown(report).splitlines() if x.startswith("H2 equivalence, ")]
    return line


RULE = "by the rule, which needs both one-sided p-values below 0.05 at the margin of 0.02: "
"""How the table words the equivalence reading under the registered test, after the verdict."""
BESIDE = "(90% interval, reported beside the rule and not read for it: "


def test_with_one_dominant_episode_the_rule_and_the_interval_can_part() -> None:
    """The sign-flip p-value need not fall steadily as the value tested moves away from the
    estimate. Six episodes of 11, 5, 1, 163, 23 and 13 statements, the fourth holding three
    statements in four: the p-value for a smaller contrast is 3/64 from about 0.015 to 0.027,
    rises to 4/64 from 0.03 to 0.045 and falls to 2/64 after that. The search for the upper end
    of the 90% interval stops at the last of these changes, near 0.046, so the interval reaches
    beyond a margin of 0.02; the rule tests 0.02 itself, where both p-values are below 0.05,
    and declares equivalence. The rule is what the evaluator reports."""
    sizes = [11, 5, 1, 163, 23, 13]
    sums = [-0.0407, 0.0821, -0.079, -0.1161, -0.1536, -0.3808]
    clusters = [f"g{k}" for k, size in enumerate(sizes) for _ in range(size)]
    d = np.array([s / n + 0.0107 for s, n in zip(sums, sizes, strict=True) for _ in range(n)])
    entry = ev.contrast(
        d, np.zeros(len(d)), clusters, source=LARGER, levels=["ci95", "ci90"], margin=0.02
    )
    found = ev.equivalence(entry)
    assert found["margin"] == ev.H2_MARGIN == 0.02
    assert entry["delta"] == pytest.approx(0.007514, abs=1e-6)
    assert entry["ci90"] == pytest.approx([-0.018592, 0.045665], abs=1e-6)
    assert (found["p_smaller_at_the_margin"], found["p_larger_at_minus_the_margin"]) == (
        3 / 64,
        3 / 64,
    )
    assert found["declared"] is True
    low, high = entry["ci90"]
    assert not (low > -0.02 and high < 0.02)  # the interval is not inside the margin
    # the table leads with the rule, which decides, and gives the interval beside it, so that
    # "declared" does not stand next to an interval that reaches past the margin unexplained
    assert h2_line(h2_report(d, clusters)) == (
        f"H2 equivalence, m: declared {RULE}0.0469 at -0.02 and 0.0469 at 0.02 {BESIDE}"
        "[-0.0186, 0.0457]). The two losses differ on 216 statements in 6 episodes: 4 with a "
        "positive sum, 2 with a negative one, 0 whose differences cancel."
    )
    # the p-value for a smaller contrast, from the estimate outwards: it rises again
    total, counts, taken = summed(d, clusters, ev.DRAWS)
    assert counts[3] / counts.sum() > 0.75
    steps = {0.01: None, 0.015: 3, 0.02: 3, 0.027: 3, 0.03: 4, 0.04: 4, 0.045: 4, 0.05: 2, 0.1: 2}
    for value, sixty_fourths in steps.items():
        moved = total - value * counts
        both = ev.larger_of_at(total, counts, taken, value)["one_sided_lower"]
        flips = ev.sign_flip_t(moved, counts)["one_sided_lower"]
        if sixty_fourths is None:
            assert both > 0.2  # near the estimate nothing is rejected
            continue
        # the sign-flip part is the larger of the two here, and the bootstrap-t part falls
        assert both == flips == sixty_fourths / 64
        assert ev.studentised(moved, counts, taken)["one_sided_lower"] < 0.03
    # at 95% the test cannot reject far above at all: 2/64 is not below 0.025
    assert entry["ci95"][1] is None and entry["ci95"][0] < low


def test_with_one_dominant_episode_the_interval_can_be_inside_a_margin_not_rejected() -> None:
    """The other way round from the test above: the interval inside the margin, and nothing
    declared. Six episodes of 8, 24, 181, 6, 16 and 8 statements, the third holding three
    statements in four: the p-value for a smaller contrast falls below 0.05 near 0.009, where
    the search for the upper end of the 90% interval stops, is 2/64 and then 3/64 up to 0.019,
    rises to 4/64 from 0.02 to 0.024 and falls to 1/64 after that. The 90% interval lies
    strictly inside a margin of 0.02; the rule tests 0.02 itself, where that p-value is not
    below 0.05, and declares nothing. The rule is what the evaluator reports."""
    sizes = [8, 24, 181, 6, 16, 8]
    means = [0.0195, -0.0057, 0.003, 0.0055, -0.0153, -0.027]
    clusters = [f"g{k}" for k, size in enumerate(sizes) for _ in range(size)]
    d = np.array([mean for mean, size in zip(means, sizes, strict=True) for _ in range(size)])
    entry = ev.contrast(
        d, np.zeros(len(d)), clusters, source=LARGER, levels=["ci95", "ci90"], margin=0.02
    )
    found = ev.equivalence(entry)
    assert found["margin"] == ev.H2_MARGIN == 0.02
    assert entry["delta"] == pytest.approx(0.000553, abs=1e-6)
    assert entry["ci90"] == pytest.approx([-0.015300, 0.008925], abs=1e-6)
    low, high = entry["ci90"]
    assert low > -0.02 and high < 0.02  # the interval is strictly inside the margin
    assert (found["p_smaller_at_the_margin"], found["p_larger_at_minus_the_margin"]) == (
        4 / 64,
        2 / 64,
    )
    assert found["level"] == 0.05 and found["declared"] is False
    # the table says that the rule declares nothing, with the two p-values it read
    assert h2_line(h2_report(d, clusters)).startswith(
        f"H2 equivalence, m: not declared {RULE}{2 / 64:.4f} at -0.02 and {4 / 64:.4f} at 0.02 "
        f"{BESIDE}[-0.0153, 0.0089]). The two losses differ on 243 statements in 6 episodes: "
    )
    # the p-value for a smaller contrast, from the estimate outwards: it rises again
    total, counts, taken = summed(d, clusters, ev.DRAWS)
    assert counts[2] / counts.sum() > 0.74
    steps = {0.005: None, 0.012: 2, 0.019: 3, 0.02: 4, 0.024: 4, 0.026: 3, 0.03: 1, 0.1: 1}
    for value, sixty_fourths in steps.items():
        moved = total - value * counts
        both = ev.larger_of_at(total, counts, taken, value)["one_sided_lower"]
        flips = ev.sign_flip_t(moved, counts)["one_sided_lower"]
        if sixty_fourths is None:
            assert both > 0.1  # near the estimate nothing is rejected
            continue
        # the sign-flip part is the larger of the two here, and the bootstrap-t part falls
        assert both == flips == sixty_fourths / 64
        assert ev.studentised(moved, counts, taken)["one_sided_lower"] < 0.03


def test_equivalence_can_be_declared_beside_an_end_that_is_unbounded() -> None:
    """The second way in which the rule and the interval part: the reach of the search, with
    a p-value that falls steadily. An end is unbounded when the value 50 standard errors away
    is not rejected; the test may reject further away, and the rule tests the margin itself.

    Eight episodes of ten statements whose losses differ on one statement in each of three,
    by 0.003, 0.003 and 0.00003. A bootstrap draw that takes neither of the first two has a
    statistic that is finite and far beyond 50, so 50 standard errors above the estimate the
    p-value for a smaller contrast is still the share of such draws, 1001/10001, and the 90%
    interval has no upper end. From about 200 standard errors on it is 247/10001; the margin of
    0.02 lies 406 standard errors away, and equivalence is declared."""
    clusters = [f"g{k}" for k in range(8) for _ in range(10)]
    d = np.zeros(80)
    d[[0, 10, 20]] = 0.003, 0.003, 0.00003
    zeros = np.zeros(80)
    entry = ev.contrast(d, zeros, clusters, source=LARGER, levels=["ci95", "ci90"], margin=0.02)
    found = ev.equivalence(entry)
    low, high = entry["ci90"]
    assert low == pytest.approx(0.0, abs=1e-9) and high is None and entry["ci95"][1] is None
    sums, sizes, taken = summed(d, clusters, ev.DRAWS)
    delta, se = entry["delta"], entry["studentised"]["se"]
    assert int(((taken[:, 0] == 0) & (taken[:, 1] == 0)).sum()) == 1000
    steps = {2: 1001, 50: 1001, 100: 1001, 150: 863, 199: 590, 201: 247, 406: 247, 1000: 247}
    seen = [ev.larger_of_at(sums, sizes, taken, delta + k * se)["one_sided_lower"] for k in steps]
    assert seen == [count / 10001 for count in steps.values()]  # it never rises
    assert 406 < (0.02 - delta) / se < 407
    assert found["p_smaller_at_the_margin"] == 247 / 10001
    assert found["p_larger_at_minus_the_margin"] == 1 / 256
    assert found["declared"] is True and found["ci90"] == [low, None]
    # the table gives the verdict of the rule with its two p-values, the interval beside it,
    # and a last line on what an end that is not there means; the printout ends on that line
    report = h2_report(d, clusters)
    note = ev.unbounded_note(report["registered"], [[low, None]])
    assert len(note) == 1 and "50 standard errors from Delta" in note[0]
    assert "It may reject values further away." in note[0]
    assert h2_line(report) == (
        f"H2 equivalence, m: declared {RULE}0.0039 at -0.02 and 0.0247 at 0.02 {BESIDE}"
        "[-0.0000, inf]). The two losses differ on 3 statements in 3 episodes: 3 with a "
        "positive sum, 0 with a negative one, 0 whose differences cancel."
    )
    assert ev.markdown(report).splitlines()[-1] == note[0] == ev.summary_lines(report)[-1]
    # with the third difference as large as the other two the same search finds the end
    d[20] = 0.003
    again = ev.contrast(d, zeros, clusters, source=LARGER, levels=["ci95", "ci90"], margin=0.02)
    assert again["ci90"] == pytest.approx([0.0, 0.000225], abs=1e-8)
    assert again["ci95"][1] == pytest.approx(0.0003, abs=1e-8)
    assert ev.equivalence(again)["declared"] is True
    whole = h2_report(d, clusters)
    assert "unbounded" not in ev.markdown(whole) + "\n".join(ev.summary_lines(whole))


def test_one_large_difference_among_small_ones_leaves_the_interval_without_an_end() -> None:
    """The same at sizes like those of the eligible list, with no dominant episode: 40 episodes
    of 48 statements each, the two losses differing on one statement of the first episode by
    -0.25 and on one statement of eight more by 0.001, with either sign. The 3,569 bootstrap
    draws without the first episode keep the p-value for a larger contrast at 3570/10001 fifty
    standard errors below the estimate, so the interval has no lower end at 90% or at 95%.
    Minus the margin lies 153 standard errors below; there the p-value is 23/10001, and
    equivalence is declared. With 0.005 in place of 0.001 the statistics of those draws are
    within the reach of the search, and the interval has both ends."""
    clusters = [f"g{g:02d}" for g in range(40) for _ in range(48)]

    def read(small: float) -> tuple[np.ndarray, dict, dict]:
        d = np.zeros(len(clusters))
        d[0] = -0.25
        for k in range(1, 9):
            d[k * 48] = small if k % 2 else -small
        entry = ev.contrast(
            d, np.zeros(len(d)), clusters, source=LARGER, levels=["ci95", "ci90"], margin=0.02
        )
        return d, entry, ev.equivalence(entry)

    d, entry, found = read(0.001)
    assert entry["ci90"][0] is None and entry["ci95"][0] is None
    assert entry["ci90"][1] == pytest.approx(2.416e-05, abs=1e-8)
    sums, sizes, taken = summed(d, clusters, ev.DRAWS)
    delta, se = entry["delta"], entry["studentised"]["se"]
    assert int((taken[:, 0] == 0).sum()) == 3569
    far = ev.larger_of_at(sums, sizes, taken, delta - 50 * se)["one_sided"]
    assert far == 3570 / 10001 and 152 < (delta + 0.02) / se < 153
    assert found["p_larger_at_minus_the_margin"] == 23 / 10001
    assert found["p_smaller_at_the_margin"] == 1 / 10001 and found["declared"] is True
    report = h2_report(d, clusters)
    assert h2_line(report) == (
        f"H2 equivalence, m: declared {RULE}0.0023 at -0.02 and 0.0001 at 0.02 {BESIDE}"
        "[-inf, 0.0000]). The two losses differ on 9 statements in 9 episodes: 4 with a "
        "positive sum, 5 with a negative one, 0 whose differences cancel."
    )
    assert ev.markdown(report).splitlines()[-1].startswith("An end shown as -inf or inf is ")
    d, entry, found = read(0.005)
    assert entry["ci90"] == pytest.approx([-0.002935, 2.43e-05], abs=1e-6)
    assert entry["ci95"] == pytest.approx([-0.003254, 2.92e-05], abs=1e-6)
    assert found["declared"] is True and "unbounded" not in ev.markdown(h2_report(d, clusters))


def test_the_counts_in_the_table_add_up_with_an_episode_whose_differences_cancel() -> None:
    """PLAN section 6, "Sensitivity": an episode whose differing statements cancel is counted
    apart. Nine episodes of four statements: two statements differ by 0.01 in each of six
    episodes, and in a seventh one differs by 0.01 and one by -0.01. The table gives the three
    counts, which add up to the episodes that differ."""
    clusters = [f"g{k}" for k in range(9) for _ in range(4)]
    d = np.zeros(36)
    for k in range(6):
        d[[4 * k, 4 * k + 1]] = 0.01
    d[[24, 25]] = 0.01, -0.01
    report = h2_report(d, clusters)
    assert report["family"][0]["losses_differ"] == {
        "statements": 14,
        "episodes": 7,
        "episodes_with_a_positive_sum": 6,
        "episodes_with_a_negative_sum": 0,
        "episodes_whose_differences_cancel": 1,
    }
    assert h2_line(report).endswith(
        "). The two losses differ on 14 statements in 7 episodes: 6 with a positive sum, 0 with "
        "a negative one, 1 whose differences cancel."
    )


def test_the_line_on_an_unbounded_end_is_printed_only_when_one_is_shown() -> None:
    made = record_under(LARGER)
    assert ev.unbounded_note(made, [[-0.1, 0.2], None, [0.0, 0.0]]) == []
    assert ev.unbounded_note(made, []) == []
    for pair in ([None, 0.2], [-0.1, None], [None, None]):
        assert ev.unbounded_note(made, [[-0.1, 0.2], pair]) == [
            "An end shown as -inf or inf is unbounded: the registered test does not reject the "
            "furthest value searched on that side (50 standard errors from Delta; with a "
            "standard error of zero, one unit from Delta, or the size of Delta if that is "
            "more). It may reject values further away."
        ]
    # the reach is the one the record holds, and a percentile interval never lacks an end
    made["intervals"]["search_reach_in_standard_errors"] = 12.5
    assert "(12.5 standard errors from Delta;" in ev.unbounded_note(made, [[None, 0.2]])[0]
    assert ev.unbounded_note(record_under("percentile"), [[None, 0.2]]) == []


def test_with_four_episodes_nothing_is_declared_at_any_margin() -> None:
    """Four episodes give no p-value below 1/16, so the test rejects no value at all: both
    intervals are unbounded on both sides and nothing is declared, whatever the margin. (An
    unbounded end does not by itself keep equivalence from being declared:
    ``test_equivalence_can_be_declared_beside_an_end_that_is_unbounded``.)"""
    d, clusters = differences("even", 4)
    for margin in (0.02, 1.0, 1e6):
        entry = ev.contrast(
            d, np.zeros(len(d)), clusters, source=LARGER, levels=["ci95", "ci90"], margin=margin
        )
        assert entry["ci90"] == [None, None] == entry["ci95"]
        found = ev.equivalence(entry, margin)
        assert found["declared"] is False and found["ci90"] == [None, None]
        assert (
            min(found["p_smaller_at_the_margin"], found["p_larger_at_minus_the_margin"]) >= 1 / 16
        )


COMMITTED_CONTRASTS = {
    ("even", 6): [
        [-0.015323935498659354, 0.09474834700828498],
        [-0.005871817635877019, 0.08562517222973692],
    ],
    ("skewed", 14): [
        [0.0003220681400501168, 0.04209351015947291],
        [0.0034256998765642274, 0.03815891263775002],
    ],
    ("sparse", 13): [
        [-0.03327760010576765, 0.031873904021841384],
        [-0.025501955306295745, 0.021539256016815524],
    ],
    ("few values", 40): [
        [0.022114426302388565, 0.06058841036414566],
        [0.02591053463505347, 0.057783305439330544],
    ],
    ("no variance", 5): [[0.25, 0.25], [0.25, 0.25]],
}
"""The 95% and 90% intervals that ``contrast`` gave before it knew any interval but the
percentile one (``evaluate.py`` at sha256 f7f3b4df6f1ab58a), on ``differences`` of each shape
and number of episodes."""


@pytest.mark.parametrize("case", list(COMMITTED_CONTRASTS))
def test_under_another_source_the_intervals_are_the_percentile_intervals_of_before(
    case: tuple[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the larger-of procedure has the interval of its test. Under ``percentile``, and
    under the three other candidates, a confirmatory contrast carries the percentile intervals
    as the evaluator computed them before, at both levels, whatever levels are asked for, and
    reads equivalence from the two ends; no value is ever tested."""
    d, clusters = differences(*case)
    zeros = np.zeros(len(d))
    plain = ev.contrast(d, zeros, clusters)
    want95, want90 = COMMITTED_CONTRASTS[case]
    assert plain["ci95"] == pytest.approx(want95, abs=1e-12)
    assert plain["ci90"] == pytest.approx(want90, abs=1e-12)
    assert plain["percentile"] == {"ci95": plain["ci95"], "ci90": plain["ci90"]}
    assert plain["interval_method"] == "percentile" and "at_the_margin" not in plain

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a value was tested under a source that has percentile intervals")

    monkeypatch.setattr(ev, "larger_of_interval", never)
    monkeypatch.setattr(ev, "larger_of_at", never)
    for source in ev.P_VALUE_SOURCES:
        if source == LARGER:
            continue
        assert ev.interval_method(source) == "percentile"
        for levels in ([], ["ci95"], ["ci95", "ci90"]):
            assert (
                ev.contrast(d, zeros, clusters, source=source, levels=levels, margin=0.02) == plain
            )
        low, high = plain["ci90"]
        for margin in (0.02, 0.05, abs(low), abs(high), 1.0):
            found = ev.equivalence(plain, margin)
            assert found == {
                "margin": margin,
                "ci90": [low, high],
                "interval_method": "percentile",
                "declared": low > -margin and high < margin,
            }
    assert (
        ev.interval_method(LARGER)
        == ev.TEST_INTERVAL
        == "values_not_rejected_by_the_registered_test"
    )
    assert ev.interval_method(None) == "percentile" and ev.TEST_INTERVAL_SOURCES == (LARGER,)


def test_a_confirmatory_contrast_carries_the_levels_it_is_asked_for() -> None:
    d, clusters = differences("skewed", 14)
    zeros = np.zeros(len(d))
    sums, sizes, taken = summed(d, clusters, 300)
    plain = ev.contrast(d, zeros, clusters, draws=300)
    both = ev.contrast(
        d, zeros, clusters, draws=300, source=LARGER, levels=["ci95", "ci90"], margin=0.02
    )
    assert both["ci95"] == REAL_INTERVAL(sums, sizes, taken, 0.95, 300)
    assert both["ci90"] == REAL_INTERVAL(sums, sizes, taken, 0.90, 300)
    assert both["ci95"][0] < both["ci90"][0] < both["delta"] < both["ci90"][1] < both["ci95"][1]
    assert both["interval_method"] == ev.TEST_INTERVAL
    assert both["at_the_margin"] == {
        "p_smaller_at_the_margin": ev.larger_of_at(sums, sizes, taken, 0.02, 300)[
            "one_sided_lower"
        ],
        "p_larger_at_minus_the_margin": ev.larger_of_at(sums, sizes, taken, -0.02, 300)[
            "one_sided"
        ],
    }
    assert len(set(both["at_the_margin"].values())) == 2
    # everything else is what any contrast reports, the percentile intervals among it
    rest = {
        k: v
        for k, v in both.items()
        if k not in ("ci95", "ci90", "interval_method", "at_the_margin")
    }
    assert rest == {k: v for k, v in plain.items() if k not in ("ci95", "ci90", "interval_method")}
    assert both["percentile"] == {"ci95": plain["ci95"], "ci90": plain["ci90"]}
    assert both["ci95"] != plain["ci95"] and both["ci90"] != plain["ci90"]
    # the 95% interval alone, and no p-value at a margin that is not given
    one = ev.contrast(d, zeros, clusters, draws=300, source=LARGER, levels=["ci95"])
    assert one["ci95"] == both["ci95"] and "ci90" not in one and "at_the_margin" not in one
    # in short, for the result file: the interval with the way it was made
    assert ev.short(one, 2, LARGER) == {
        "statements": len(d),
        "episodes": 14,
        "evaluable": True,
        "delta": one["delta"],
        "ci95": one["ci95"],
        "interval_method": ev.TEST_INTERVAL,
        "p": one["p_values"][LARGER]["two_sided"],
    }
    assert ev.short(plain, 1, LARGER)["interval_method"] == "percentile"
    assert ev.short(plain, 1, LARGER)["ci95"] == plain["ci95"]
    # in short a contrast gives its 95% interval alone, also when it holds a 90% one
    assert "ci90" in plain and "ci90" in both
    for held in (plain, both):
        assert list(ev.short(held, 2, LARGER)) == list(ev.short(one, 2, LARGER))


def test_the_counts_of_statements_and_episodes_on_which_two_losses_differ() -> None:
    """Beside H2 (PLAN section 6, "Sensitivity"). Seven episodes worked by hand:

    * ``a``: the same loss on both statements;
    * ``b``: one of two statements differs, by +0.1;
    * ``c``: one statement, -0.3;
    * ``d``: two statements, +0.3 and -0.3, which cancel;
    * ``e``: 0.3 - 0.2 and 0.1 - 0.2, which cancel to a rounding error and not to zero;
    * ``f``: three statements, +0.2, -0.05 and no difference: a positive sum;
    * ``g``: 0.1 + 0.2 against 0.3, the same loss up to a rounding error: no difference.
    """
    rows = {
        "a": [(0.4, 0.4), (0.1, 0.1)],
        "b": [(0.3, 0.2), (0.25, 0.25)],
        "c": [(0.2, 0.5)],
        "d": [(0.4, 0.1), (0.1, 0.4)],
        "e": [(0.3, 0.2), (0.1, 0.2)],
        "f": [(0.5, 0.3), (0.2, 0.25), (0.6, 0.6)],
        "g": [(0.1 + 0.2, 0.3)],
    }
    clusters = [name for name, pairs in rows.items() for _ in pairs]
    comparator = [c for pairs in rows.values() for c, _ in pairs]
    tested = [t for pairs in rows.values() for _, t in pairs]
    assert (0.3 - 0.2) + (0.1 - 0.2) != 0  # the sum of episode e, in floating point
    assert (0.1 + 0.2) - 0.3 != 0  # the one difference of episode g
    assert ev.differing(comparator, tested, clusters) == {
        "statements": 8,
        "episodes": 5,
        "episodes_with_a_positive_sum": 2,
        "episodes_with_a_negative_sum": 1,
        "episodes_whose_differences_cancel": 2,
    }
    # the other way round, the signs change places
    assert ev.differing(tested, comparator, clusters) == {
        "statements": 8,
        "episodes": 5,
        "episodes_with_a_positive_sum": 1,
        "episodes_with_a_negative_sum": 2,
        "episodes_whose_differences_cancel": 2,
    }
    same = ev.differing(tested, tested, clusters)
    assert set(same.values()) == {0} and list(same) == list(ev.differing([], [], []))
    assert set(ev.differing([], [], []).values()) == {0}
    one = ev.differing([0.5, 0.2, 0.2], [0.1, 0.2, 0.2], ["g", "h", "h"])
    assert (one["statements"], one["episodes"], one["episodes_with_a_positive_sum"]) == (1, 1, 1)
    # the tolerance is that of the episode sums, not of the single differences ("1e-12 times the
    # largest absolute episode sum"): episode ``a`` sums to 100, so anything up to 1e-10 is a
    # zero, and the one difference of ``b`` is 5e-11, far above 1e-12 times the largest single
    # difference
    wide = ["a"] * 200 + ["b", "c", "c"]
    apart = np.array([0.5] * 200 + [5e-11, 0.25, -0.25])
    assert ev.differing(apart, np.zeros(len(apart)), wide) == {
        "statements": 202,
        "episodes": 2,
        "episodes_with_a_positive_sum": 1,
        "episodes_with_a_negative_sum": 0,
        "episodes_whose_differences_cancel": 1,
    }


def test_an_unbounded_end_is_null_in_the_file_and_infinite_in_the_printout() -> None:
    assert ev._interval([None, 0.03]) == "[-inf, 0.0300]"
    assert ev._interval([-0.01, None]) == "[-0.0100, inf]"
    assert ev._interval([None, None]) == "[-inf, inf]" and ev._interval(None) == "n/a"
    assert ev._interval([-0.5, 0.25]) == "[-0.5000, 0.2500]"
    assert json.loads(ev.report_text({"ci95": [None, 0.03]})) == {"ci95": [None, 0.03]}
    # the flag beside H3: a lower end that is not there does not lie above zero
    assert ev.beats_both(h3_entry(0.03, True, [None, 0.04])) is False
    assert ev.beats_both(h3_entry(0.03, True, [None, None])) is False
    assert ev.beats_both(h3_entry(0.03, True, [0.001, None])) is True


# --------------------------------------------------------------------------------------------
# The two registered constants
# --------------------------------------------------------------------------------------------


def test_the_registered_constants_are_the_plans_wording_today() -> None:
    """Both constants are set once before registration. This test holds them at the candidate
    the plan words today; changing a constant means changing it here too. Every other test
    reads the p-value source from the evaluator (``SOURCE``), so that this is the one place."""
    assert ev.P_VALUE_SOURCES == (
        "percentile",
        "studentised",
        "studentised_symmetric",
        "sign_flip_t",
        "larger_of_studentised_and_sign_flip_t",
    )
    assert ev.PROCEDURES[:-1] == ev.P_VALUE_SOURCES and ev.PROCEDURES[-1] == "sign_flip"
    assert ev.H3_COMPARATORS == ("gbm_structured", "base_rate", "better_on_dev")
    assert (ev.P_VALUE_SOURCE, ev.H3_COMPARATOR) == (LARGER, "base_rate")
    record = ev.registered_record()
    assert (record["p_value_source"], record["h3_comparator"]) == (LARGER, "base_rate")
    assert record["intervals"] == {
        "of_the_confirmatory_contrasts_and_delta_gbm": "values_not_rejected_by_the_registered_test",
        "of_the_other_contrasts_and_single_predictors_of_the_evaluator": "percentile",
        "coverage": 0.95,
        "coverage_for_the_equivalence_of_h2": 0.90,
        "sources_with_the_interval_of_their_own_test": [LARGER],
        "search_reach_in_standard_errors": 50.0,
        "search_halvings": 60,
        "an_end_that_is_null": "unbounded: the test does not reject at the reach of the search",
    }
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


def words(text: str | None) -> str:
    """A text on one line, as its words."""
    return " ".join((text or "").split())


def test_the_evaluator_describes_the_registered_test_as_it_is_today() -> None:
    """The docstrings and names of the evaluator follow the registered test. The percentile
    p-values are a sensitivity analysis and no longer "the registered" ones; the cluster
    sign-flip test is one sensitivity analysis of three; the 90% interval of H2 is reported
    beside a rule on two p-values, from which it can part in two ways; an unbounded end says
    that the test does not reject 50 standard errors away, not that it rejects nowhere; and
    the size check zeroes a cancelling draw as this file does."""
    module, source = words(ev.__doc__), words(Path(ev.__file__).read_text(encoding="utf-8"))
    left_behind = (
        "the paired cluster bootstrap of PLAN section 6 as it is worded",
        "the sensitivity analysis of PLAN section 6",
        "the registered p-values count such a draw on both sides",
        "The interval that reads the equivalence of H2",
        "That is the 90% interval of the registered test lying strictly inside",
        "are reported for every contrast under ``percentile``",
        "but for one case",
        "An end the test cannot reach",
        "or an unbounded one, goes with a margin that is not rejected",
        "the largest absolute flipped statistic",
    )
    assert not [text for text in left_behind if text in source]
    said = (
        "the percentile p-values of the draft, now a sensitivity analysis of PLAN section 6",
        "(one of the sensitivity analyses of PLAN section 6)",
        "As a rule of thumb that is the 90% interval of the registered test lying strictly inside",
        "for every contrast given in full (the six tests and the probe)",
        "but where rounding settles a statistic",
        "(it may reject further away, which the interval does not show)",
        "equivalence is then declared beside an end that is null",
        "a stored reading that the harness's own parser accepts",
        "a declaration ``--not-evaluable`` whose reason is not printable text on one line",
    )
    assert not [text for text in said if text not in module]
    # the constants: their docstrings are in the source alone
    assert "one of the sensitivity analyses of PLAN section 6, reported for every" in source
    assert "and the interval is reported beside them; under a source with percentile" in source
    for function, text in (
        (ev.drawn_deltas, "the percentile p-values count such a draw on both sides"),
        (ev.tail_of, "so that the registered levels are 0.025 and 0.05 exactly"),
        (REAL_INTERVAL, "no end within the reach, not that no value is rejected"),
        (ev.equivalence, "The two can part in two ways, and the rule decides."),
        (ev.equivalence, "equivalence is declared beside an unbounded end"),
    ):
        assert text in words(function.__doc__), text
    # the percentile p-values are the draft's: the name that holds them does not call them
    # the registered ones
    names = ev.contrast.__code__.co_varnames
    assert "draft" in names and "registered" not in names


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
    method = ev.interval_method(source)
    assert method == ("percentile" if source != LARGER else ev.TEST_INTERVAL)
    assert (
        report["registered"]["intervals"]["of_the_confirmatory_contrasts_and_delta_gbm"] == method
    )
    assert f"Intervals of the six contrasts and of Delta_GBM: {method}." in table
    for entry, before in zip(report["family"], base.report["family"], strict=True):
        side = "one_sided" if entry["sides"] == 1 else "two_sided"
        assert entry["p"] == entry["p_values"][source][side]
        # the estimate, every p-value and the percentile intervals do not depend on the constant
        for key in ("delta", "p_values", "percentile", "studentised", "sign_flip"):
            assert entry[key] == before[key]
        # the intervals do: those of the source in force, and the entry says which they are
        assert entry["interval_method"] == method
        if method == "percentile":
            assert (entry["ci95"], entry["ci90"]) == (
                before["percentile"]["ci95"],
                before["percentile"]["ci90"],
            )
        else:
            assert entry["ci95"] != entry["percentile"]["ci95"]
            assert ("ci90" in entry) is (entry["hypothesis"] == "H2")
        if method == before["interval_method"]:
            assert entry["ci95"] == before["ci95"] and entry.get("ci90") == before.get("ci90")
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


def test_a_stored_reading_is_held_to_the_parser_of_the_harness() -> None:
    """A stored row with a reading must hold one that ``read.parse_reading`` would have let
    through: the schema of its kind and the semantic checks, applied to the stored object
    itself. Its text is not parsed again, because the parser first takes a reply apart: a list
    around a good reading passes as text and is no reading."""
    good = forecast(0.7, 0.4, 100)
    period = literal("recovery", "2024-03-01", "2024-03-31")
    assert ev.reading_accepted(good, "predictive") and ev.reading_accepted(period, "literal")
    assert ev.reading_accepted(literal("depletion", "", ""), "literal")  # ABSTAIN
    assert not ev.reading_accepted(good, "literal")
    assert not ev.reading_accepted(period, "predictive")
    assert rd.parse_reading(json.dumps([good]), "predictive").ok
    assert not ev.reading_accepted([good], "predictive")
    days = good["days_to_recovery"]
    for bad in (
        good | {"p_by_horizon_a": 1.7},
        good | {"p_by_horizon_a": -0.01},
        good | {"p_by_horizon_b": "0.4"},
        good | {"p_by_horizon_b": float("nan")},
        good | {"p_by_horizon_a": True},
        good | {"days_to_recovery": dict(zip(days, (250, 200, 150, 100, 50), strict=True))},
        good | {"days_to_recovery": days | {"q95": 366}},
        good | {"days_to_recovery": days | {"q50": 100.5}},
        good | {"days_to_recovery": {k: v for k, v in days.items() if k != "q50"}},
        good | {"note": "one key more"},
        None,
        "ABSTAIN",
    ):
        assert not ev.reading_accepted(bad, "predictive"), bad
    for bad in (
        period | {"interval": {"start": "2024-03-31", "end": "2024-03-01"}},
        period | {"interval": {"start": "2024-02-30", "end": "2024-03-01"}},
        period | {"interval": {"start": "2024-03-01"}},
        period | {"interval": 7},
        period | {"interval": "abstain"},
        period | {"statement_type": "restock"},
        period | {"stale": "no"},
        {k: v for k, v in period.items() if k != "quote"},
    ):
        assert not ev.reading_accepted(bad, "literal"), bad
    # whole days given as floats are days for the harness too, and the stored reading stays
    # as it is: the check works on a copy
    whole = good | {"days_to_recovery": {k: float(v) for k, v in days.items()}}
    before = json.dumps(whole)
    assert ev.reading_accepted(whole, "predictive") and json.dumps(whole) == before
    assert rd.parse_reading(before, "predictive").ok
    # what the harness lets through with a warning is a reading here too; the evaluator scores
    # and counts such answers (a later horizon given the lower probability, an interval for no
    # statement or for an undetermined one, a stale flag without an interval)
    for kind, reading, warning in (
        ("predictive", good, "p_by_horizon_b_below_a"),
        ("literal", period | {"statement_type": "none"}, "interval_without_statement"),
        ("literal", period | {"certainty": "undetermined"}, "interval_for_undetermined"),
        ("literal", literal("recovery", "", "") | {"stale": True}, "stale_without_interval"),
    ):
        parsed = rd.parse_reading(json.dumps(reading), kind)
        assert parsed.ok and warning in parsed.warnings
        assert ev.reading_accepted(reading, kind), warning
    # the fault of a row, beside its other faults and only for a row that holds a reading
    route = rd.ROUTES[DEEPSEEK]
    served = {"model": DEEPSEEK, "model_id": route.model_id, "provider_pin": route.provider}
    for template, reading, bad in (
        ("predictive-v1", good, good | {"p_by_horizon_a": 1.7}),
        ("literal-v1", period, period | {"interval": 7}),
    ):
        kind = rd.TEMPLATES[template].kind
        pinned = served | {"template": template, "template_sha256": rd.FROZEN_SHA256[template]}
        row = pinned | stored(reading, kind)
        assert ev.row_faults(row, DEEPSEEK, template) == []
        broken = row | {"reading": bad}
        assert ev.row_faults(broken, DEEPSEEK, template) == [
            "a stored reading that the harness's parser does not accept"
        ]
        assert ev.row_faults(broken | {"status": "failed"}, DEEPSEEK, template) == [
            "a status, a reading and a fallback flag that contradict one another",
            "a stored reading that the harness's parser does not accept",
        ]
        # a row without a reading has none to hold to the parser
        assert ev.row_faults(pinned | stored(None, kind), DEEPSEEK, template) == []


def test_every_reading_the_harness_wrote_is_one_it_accepts(study: SimpleNamespace) -> None:
    """The dev and confirmatory runs of the synthetic study were written by the harness's own
    reader: none of their rows is faulted for its reading."""
    seen = 0
    for model in rd.PRIMARIES:
        for line in (*ev.LINES["dev"].values(), *ev.LINES["confirmatory"].values()):
            rows = stored_rows(study, model, line)
            kind = rd.TEMPLATES[rows[0]["template"]].kind
            parsed = [row["reading"] for row in rows if row["reading"] is not None]
            assert all(ev.reading_accepted(reading, kind) for reading in parsed)
            assert not [row for row in rows if ev.row_faults(row, model, row["template"])]
            seen += len(parsed)
    assert seen > 3000


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


def first_reading(study: SimpleNamespace, change: Callable[[dict], Any]) -> Callable[[dict], dict]:
    """Pass the stored reading of the first eligible statement through ``change``. The row
    keeps its status, its fallback flag and everything else, so the reading alone is at fault."""

    def apply(row: dict) -> dict:
        if row["item_id"] != first_id(study):
            return row
        assert row["status"] == "ok" and isinstance(row["reading"], dict)
        return row | {"reading": change(row["reading"])}

    return apply


NOT_ACCEPTED = "1 rows with a stored reading that the harness's parser does not accept"
"""The fault of a stored reading that ``read.parse_reading`` would not have let through."""
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
    # stored readings that the harness's own parser rejects: no run of this harness holds one,
    # and the hash of the readings is the one in the manifest
    "a stored probability above one": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-a", first_reading(s, lambda r: r | {"p_by_horizon_a": 1.7})
        ),
        f"e3-a: {NOT_ACCEPTED}",
    ),
    "a stored probability that is text": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-a", first_reading(s, lambda r: r | {"p_by_horizon_b": "0.4"})
        ),
        f"e3-a: {NOT_ACCEPTED}",
    ),
    "a stored probability that is no number": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-a", first_reading(s, lambda r: r | {"p_by_horizon_a": float("nan")})
        ),
        f"e3-a: {NOT_ACCEPTED}",
    ),
    "stored quantiles that decrease": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-a",
            first_reading(
                s,
                lambda r: (
                    r
                    | {
                        "days_to_recovery": dict(
                            zip(P.QUANTILE_KEYS, (50, 40, 30, 20, 10), strict=True)
                        )
                    }
                ),
            ),
        ),
        f"e3-a: {NOT_ACCEPTED}",
    ),
    "a stored reading without its median": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-a",
            first_reading(
                s,
                lambda r: (
                    r
                    | {
                        "days_to_recovery": {
                            k: v for k, v in r["days_to_recovery"].items() if k != "q50"
                        }
                    }
                ),
            ),
        ),
        f"e3-a: {NOT_ACCEPTED}",
    ),
    "a stored reading inside a list": (
        lambda s: rewritten(s, DEEPSEEK, "e3-a", first_reading(s, lambda r: [r])),
        f"e3-a: {NOT_ACCEPTED}",
    ),
    "a stored literal interval that ends before it starts": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-c",
            first_reading(
                s, lambda r: r | {"interval": {"start": "2026-03-01", "end": "2026-02-01"}}
            ),
        ),
        f"e3-c: {NOT_ACCEPTED}",
    ),
    "a stored literal interval on a day that does not exist": (
        lambda s: rewritten(
            s,
            DEEPSEEK,
            "e3-c",
            first_reading(
                s, lambda r: r | {"interval": {"start": "2026-02-30", "end": "2026-03-31"}}
            ),
        ),
        f"e3-c: {NOT_ACCEPTED}",
    ),
    "a stored literal interval that is a number": (
        lambda s: rewritten(s, DEEPSEEK, "e3-c", first_reading(s, lambda r: r | {"interval": 7})),
        f"e3-c: {NOT_ACCEPTED}",
    ),
    "a stored statement type outside the five": (
        lambda s: rewritten(
            s, DEEPSEEK, "e3-c", first_reading(s, lambda r: r | {"statement_type": "restock"})
        ),
        f"e3-c: {NOT_ACCEPTED}",
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


def test_a_stop_in_the_texts_of_the_results_is_a_refusal_that_leaves_no_file(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    base: SimpleNamespace,
) -> None:
    """Once the sealed rows are in memory every stop is one sentence and nothing is written:
    also a stop in putting the results into the text of the result file, of the table or of the
    printout, and a text that cannot be written as UTF-8. Both texts are made before either
    file exists. The evaluation itself is replaced by the results of the untouched study, so
    that the stops are those of the texts alone."""
    parts = ("items", "probe", "item_sets", "family", "secondaries", "losses")
    held = {key: base.report[key] for key in (*parts, "where_the_plan_is_silent")}
    held["not_computed_here"] = base.report["not_computed_here"]
    monkeypatch.setattr(ev, "evaluate", lambda *args, **kwargs: dict(held))
    secret = "recovered on 2024-05-01"

    def stop(*args: Any, **kwargs: Any) -> None:
        raise KeyError(secret)

    for name in ("report_text", "markdown", "summary_lines"):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ev, name, stop)
            why = refused(study, tmp_path, capsys)  # nothing printed, no file in the folder
        assert why == (
            "refused: the evaluation stopped on the sealed rows (KeyError); the message is "
            "withheld because it may quote a sealed value"
        )
    # a character that no file can hold (a byte that was no text reaches a program as one)
    real = {name: getattr(ev, name) for name in ("report_text", "markdown")}
    for name, text in real.items():
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ev, name, lambda report, text=text: text(report) + "\udce9")
            why = refused(study, tmp_path, capsys)
        assert "the evaluation stopped on the sealed rows (UnicodeEncodeError)" in why
    # without a stop the same run writes the two files of the untouched study
    report, table, printed = confirm(study, tmp_path, capsys)
    assert report["family"] == base.report["family"] and table == base.table
    assert printed.splitlines()[:-1] == base.printed.splitlines()[:-1]


def test_a_malformed_declaration_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sealed_unread: list[str],
) -> None:
    for value in ("gemma-3-27b=slow", LLAMA, f"{LLAMA}=", f"{LLAMA}= "):
        why = refused(study, tmp_path, capsys, "--not-evaluable", value)
        assert "--not-evaluable takes MODEL=REASON with a primary model" in why
    # the reason is written into the result file and the table: it must be printable text on
    # one line. A byte of the command line that was no text reaches the program as a lone
    # surrogate, which no file can hold; that is refused here, before anything is read
    assert b"\xe9".decode("utf-8", "surrogateescape") == "\udce9"
    for reason in ("its route \udce9 was withdrawn", "withdrawn\non 20 October", "with\tdrawn"):
        why = refused(study, tmp_path, capsys, "--not-evaluable", f"{DEEPSEEK}={reason}")
        assert why == "refused: --not-evaluable takes a REASON of printable text, on one line"
    reason = "la route a été retirée (経路の撤回) on 2026-10-20"  # any script is text
    assert ev.skipped_models([f"{LLAMA}={reason}"]) == {
        LLAMA: f"declared on the command line: {reason}"
    }
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
    assert ev.NOT_COMPUTED_HERE[-1] == "E2, E5 and E7"
    assert not [item for item in report["not_computed_here"] if "E6" in item]
    # the three sensitivity analyses of the recovery rule that PLAN section 6, "Evaluator",
    # leaves to secondary scorers, in one item
    (recovery,) = [item for item in report["not_computed_here"] if "recovery rule" in item]
    for analysis in ("the BL definition", "leaving the list", "the Date Discontinued cell"):
        assert analysis in recovery
    # two things that PLAN sections 13 and 5 give to a secondary scorer, each in one item: the
    # Turnbull share beside the overconfidence criterion, and the analysis by statement type
    (share,) = [item for item in report["not_computed_here"] if "Turnbull" in item]
    assert share == (
        "the mean of P(E_end) minus the Turnbull share recovered by the stated end, reported "
        "beside the overconfidence criterion (a secondary scorer)"
    )
    (by_type,) = [item for item in report["not_computed_here"] if "by statement type" in item]
    assert "the overconfidence criterion on the recovery statements" in by_type
    assert "Turnbull" not in json.dumps(report["secondaries"]) + json.dumps(report["losses"])


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
    # the registered p-value is the one-sided one of the source in force; the percentile one
    # of the draft stands beside it with its interval, counted here by hand on the draws
    assert null["p"] == null["p_values"][SOURCE]["one_sided"]
    pair = np.column_stack([loss["a"], loss["b"]])
    draws = P.bootstrap_means(pair, y.loc[scoreable, "episode"])
    by_hand = (1 + int((draws[:, 0] - draws[:, 1] <= 0).sum())) / 10_001
    assert null["p_values"]["percentile"]["one_sided"] == pytest.approx(by_hand, abs=1e-6)
    assert null["percentile"]["ci95"] == pytest.approx(
        list(np.quantile(draws[:, 0] - draws[:, 1], [0.025, 0.975])), abs=1e-6
    )
    assert (null["ci95"] == null["percentile"]["ci95"]) is (not BY_TEST)


def test_h2_carries_its_equivalence_reading_and_it_agrees_with_the_interval_on_the_synthetic_study(
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
    found = same["equivalence"]
    assert (found["margin"], found["ci90"], found["declared"]) == (0.02, same["ci90"], True)
    assert found["interval_method"] == same["interval_method"] == ev.interval_method(SOURCE)
    other = entry_of(base.report, "H2", DEEPSEEK)
    assert other["delta"] != 0 and other["p"] == other["p_values"][SOURCE]["two_sided"]
    for entry in (same, other):
        low, high = entry["ci90"]
        # the verdict and the interval agree on these data; under the registered test that is
        # not the rule, which reads the two p-values at the margin (the two can part)
        assert entry["equivalence"]["declared"] is (low > -0.02 and high < 0.02)
        # read from the two p-values at the margin under the interval of the registered test
        # (0.05 is the level at which a 90% interval is cut), from the two ends otherwise
        keys = ["margin", "ci90", "interval_method"]
        if BY_TEST:
            keys += ["p_smaller_at_the_margin", "p_larger_at_minus_the_margin", "level"]
            assert entry["equivalence"]["level"] == 0.05
        assert list(entry["equivalence"]) == [*keys, "declared"]
        assert "at_the_margin" not in entry
    how = RULE if BY_TEST else "(90% interval"
    assert f"H2 equivalence, llama-3.3-70b: declared {how}" in base.table
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


def test_h2_under_the_registered_test_reads_the_p_values_at_the_margin(
    study: SimpleNamespace, base: SimpleNamespace, opened: SimpleNamespace
) -> None:
    """The equivalence reading of the result file, worked out again from the two losses: the
    90% interval of the registered test, and the p-value for a smaller contrast at 0.02 and for
    a larger one at -0.02, on the registered draws and sign patterns."""
    if not BY_TEST:
        pytest.skip("the registered source has percentile intervals")
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"]).index
    clusters = list(y.loc[scoreable, "episode"])
    for model in rd.PRIMARIES:
        entry = entry_of(base.report, "H2", model)
        pair = [opened.study.predictions[name] for name in ("rules_plus_slip", f"{model}:c")]
        d = (brier(pair[0], y) - brier(pair[1], y)).loc[scoreable].to_numpy()
        sums, sizes, taken = summed(d, clusters, ev.DRAWS)
        found = entry["equivalence"]
        assert found["ci90"] == entry["ci90"]
        assert entry["ci90"] == pytest.approx(REAL_INTERVAL(sums, sizes, taken, 0.90), abs=1e-6)
        assert entry["ci95"] == pytest.approx(REAL_INTERVAL(sums, sizes, taken, 0.95), abs=1e-6)
        smaller = ev.larger_of_at(sums, sizes, taken, 0.02)["one_sided_lower"]
        larger = ev.larger_of_at(sums, sizes, taken, -0.02)["one_sided"]
        assert found["p_smaller_at_the_margin"] == pytest.approx(smaller, abs=1e-6)
        assert found["p_larger_at_minus_the_margin"] == pytest.approx(larger, abs=1e-6)
        assert found["declared"] is bool(smaller < 0.05 and larger < 0.05) is True
        # on the other side of the estimate the same p-values are far from any level
        assert ev.larger_of_at(sums, sizes, taken, 0.02)["one_sided"] > 0.9
        assert ev.larger_of_at(sums, sizes, taken, -0.02)["one_sided_lower"] > 0.9
        # the table leads with the rule and its two p-values; the interval stands beside it
        assert (
            f"H2 equivalence, {model}: declared {RULE}{larger:.4f} at -0.02 and {smaller:.4f} "
            f"at 0.02 {BESIDE}{ev._interval(entry['ci90'])}). The two losses differ on "
        ) in base.table
        # H2 on the month-and-year form is a secondary: described, not read for equivalence
        short = base.report["secondaries"]["h2_on_the_month_and_year_form"][f"H2 {model}"]
        assert short["interval_method"] == "percentile" and "equivalence" not in short


def test_h2_carries_the_counts_of_statements_and_episodes_that_differ(
    study: SimpleNamespace, base: SimpleNamespace, opened: SimpleNamespace
) -> None:
    y = truth(study)
    scoreable = y.dropna(subset=["y_a", "y_b"]).index
    for model in rd.PRIMARIES:
        entry = entry_of(base.report, "H2", model)
        pair = [opened.study.predictions[name] for name in ("rules_plus_slip", f"{model}:c")]
        d = (brier(pair[0], y) - brier(pair[1], y)).loc[scoreable]
        want = counts_apart(d, y["episode"])
        assert entry["losses_differ"] == want and 0 < want["statements"] < len(scoreable)
        assert want["episodes_with_a_positive_sum"] and want["episodes_with_a_negative_sum"]
        # the table gives the three kinds of episode, which add up to those that differ
        assert sum(list(want.values())[2:]) == want["episodes"]
        assert counts_line(want) in base.table
    # the first primary reads as the rule does: its losses differ only where its answer failed
    failed = [i for i in scoreable if fails(LLAMA, "c", i) == 2]
    assert entry_of(base.report, "H2", LLAMA)["losses_differ"]["statements"] <= len(failed)
    for entry in base.report["family"]:
        assert ("losses_differ" in entry) is (entry["hypothesis"] == "H2")
    assert base.table.count("The two losses differ on ") == 2


def test_the_result_file_says_how_every_interval_was_made(base: SimpleNamespace) -> None:
    report, method = base.report, ev.interval_method(SOURCE)
    assert method == (ev.TEST_INTERVAL if SOURCE == LARGER else "percentile")
    made = report["registered"]["intervals"]
    assert made["of_the_confirmatory_contrasts_and_delta_gbm"] == method
    # the key names the evaluator, whose file it is true of: the record is also written into
    # the result files of other scorers, where other contrasts carry the interval of the test.
    # And it names contrasts and single predictors, not every other interval: the bootstrap-t
    # intervals under ``studentised`` are neither percentile intervals nor those of the test
    assert made["of_the_other_contrasts_and_single_predictors_of_the_evaluator"] == "percentile"
    assert not [key for key in made if "everything" in key or "every_other_interval" in key]
    for entry in (*report["family"], *report["probe"].values()):
        by_t = entry["studentised"]["ci95"]  # null when a draw has no finite statistic
        assert by_t is None or by_t not in (entry["ci95"], entry["percentile"]["ci95"])
    assert sum(entry["studentised"]["ci95"] is not None for entry in report["family"]) >= 4
    assert f"Intervals of the six contrasts and of Delta_GBM: {method}. H3" in base.table
    assert f"; intervals of the six contrasts and of Delta_GBM: {method}; H3" in base.printed
    for entry in report["family"]:
        assert entry["interval_method"] == method
        # the sensitivity analyses beside every confirmatory p-value: each procedure on its
        # own, and the percentile intervals of the draft
        assert list(entry["p_values"]) == list(ev.PROCEDURES)
        assert all(list(entry["p_values"][name]) == list(ev.SIDES) for name in ev.PROCEDURES)
        assert list(entry["percentile"]) == ["ci95", "ci90"]
        assert entry["percentile"]["ci95"][0] < entry["delta"] < entry["percentile"]["ci95"][1]
        assert ("ci90" in entry) is (not BY_TEST or entry["hypothesis"] == "H2")
        assert (entry["ci95"] == entry["percentile"]["ci95"]) is (not BY_TEST)
        larger = entry["p_values"][LARGER]
        for side in ("one_sided", "one_sided_lower"):
            parts = [entry["p_values"][name][side] for name in ("studentised", "sign_flip_t")]
            assert larger[side] == max(parts)
        assert entry["both_sides_parsed"]["interval_method"] == "percentile"
        assert "at_the_margin" not in entry
        for beside in entry.get("beside", {}).values():
            assert beside["interval_method"] == method
        if "equivalence" in entry:
            assert entry["equivalence"]["interval_method"] == method
    second = report["secondaries"]
    for found in second["delta_gbm"].values():
        assert found["interval_method"] == method and len(found["ci95"]) == 2
    # every other contrast is described by a percentile interval, and says so
    rest = {key: value for key, value in second.items() if key != "delta_gbm"}
    others = [v for v in walk(rest) if isinstance(v, dict) and "delta" in v and "ci95" in v]
    assert len(others) > 30 and {v["interval_method"] for v in others} == {"percentile"}
    assert {probe["interval_method"] for probe in report["probe"].values()} == {"percentile"}
    said = " ".join(report["where_the_plan_is_silent"])
    assert "unbounded and written as null" in said and "strictly inside the margin" in said
    assert report["where_the_plan_is_silent"] == list(ev.WHERE_THE_PLAN_IS_SILENT)
    # no end is missing on this study, so neither text carries the line on unbounded ends
    assert "unbounded" not in base.table + base.printed
    # the intervals that carry no ``interval_method`` are those of single predictors, which the
    # list names: their losses and their calibration in the large
    single = [v for v in walk(report["losses"]) if isinstance(v, dict) and "ci95" in v]
    assert len(single) > 30 and not [v for v in single if "interval_method" in v]


DECISIONS = (
    "the largest finite absolute flipped statistic",
    "a symmetric two-sided p-value",
    "carry percentile intervals",
    "carry no such field",
    "unbounded and written as null",
    "equivalence is declared beside an end that is null",
    "needs both ends strictly inside the margin",
    "need not fall steadily",
    "a tie between the two comparators of H3",
    "an episode and a company before the sealed file is read",
    "an unbounded lower end does not lie above zero",
    "for both predictors at once",
    "ten runs of equal length",
    "definition A is one of the outcome variants",
    "an end on zero does not",
    "except in the base rate's own record",
    "a primary without an item set has no reading",
    "the horizon events of those few statements",
)
"""A phrase of every decision in ``evaluate.WHERE_THE_PLAN_IS_SILENT``."""
STATED_BY_THE_PLAN = (
    "fewer than two episodes",  # section 6, "Confirmatory runs", and E4
    "plus or minus infinity",  # "Test statistic"
    "enumerate every sign pattern",  # "Resampling"
    "the probe test takes its p-value",  # E4, "Test"
    "a contrast of exactly zero",  # "Sensitivity": a draw that sums to zero, with its tolerance
    "differences without any variance",  # "Intervals"
    "the rule on two p-values",  # "Intervals", the equivalence rule
    "further from zero than the rounding tolerance",  # "Sensitivity"
    "calibrator's no-date table",  # section 4
    "at six decimals",  # H3, the selection
    "every primary is declared not evaluable",  # "Confirmatory runs"
    "held to the hashes of the freeze",  # "Evaluator"
)
"""A phrase of every sentence the list held before the plan stated the decision itself."""


def test_the_list_of_decisions_holds_what_the_plan_does_not_say() -> None:
    """``where_the_plan_is_silent`` in every result file. Each decision is looked for by a
    phrase, in exactly one sentence, and every sentence holds one of the phrases, so that no
    sentence can be dropped or added unseen. What the plan words itself is not repeated, and
    two details are as the code and the plan have them: the slack of the sign-flip tests is
    measured on the largest finite statistic, and no sentence says that every other interval
    is a percentile interval (the bootstrap-t intervals under ``studentised`` are not)."""
    held = ev.WHERE_THE_PLAN_IS_SILENT
    for words in DECISIONS:
        assert sum(words in sentence for sentence in held) == 1, words
    assert all(any(words in sentence for words in DECISIONS) for sentence in held)
    said = " ".join(held)
    assert not [words for words in STATED_BY_THE_PLAN if words in said]
    assert "the largest absolute flipped statistic" not in said
    assert "every other interval is a percentile interval" not in said
    assert "equal-tailed and symmetric intervals under studentised" in said
    # the overconfidence criterion: its intervals are named with the others that carry no
    # ``interval_method``, and what the plan leaves open about them is said in one sentence
    assert (
        "of calibration in the large and of the overconfidence criterion (a difference of two "
        "mean probabilities among them) are percentile intervals and carry no such field"
    ) in said
    (zero,) = [sentence for sentence in held if "an end on zero does not" in sentence]
    for phrase in (
        "both of its ends lie on one side of zero",
        "a draw whose values sum to zero up to rounding counts as zero",
        "an item set of a single episode has no interval",
        "neither part is met and the reading is the fifth",
    ):
        assert phrase in zero, phrase
    # a primary without an item set: each of the three reasons, the slice on which the first
    # part could have been read, and the primary whose runs are not read
    (unread,) = [sentence for sentence in held if "has no reading" in sentence]
    for phrase in (
        "its line in the table and in the printout gives the reason",
        "the probe could not be tested",
        "the model has no slice inside the test split",
        "its post-cutoff slice holds fewer than 50 scoreable statements",
        "the criterion is not read on such a slice, although its first part uses no scoreable set",
        "a primary declared not evaluable, whose runs are not read, has no entry and no line",
    ):
        assert phrase in unread, phrase
    # the figures on the answers that parsed: when they are withheld, and why
    (few,) = [sentence for sentence in held if "those few statements" in sentence]
    for phrase in (
        "the two parts on the answers that parsed (parsed_only) are withheld",
        "their three counts apart",
        "when 1 to 4 answers of condition (a) failed on the item set, or 1 to 4 parsed",
        "with the figures over every statement they would give the horizon events",
        "the statements that both of its sides parsed (both_sides_parsed) is withheld",
        "when it leaves out or rests on 1 to 4 scoreable statements",
    ):
        assert phrase in few, phrase
    assert ev.MIN_SHOWN - 1 == 4 and ev.MIN_SLICE == 50  # the numbers the two sentences give
    # the module's docstring words the same decisions
    described = " ".join((ev.__doc__ or "").split())
    for sentence in held[-4:]:
        worded = sentence[1:].replace("base_rate", "``base_rate``")
        for key in ("parsed_only", "both_sides_parsed"):
            worded = worded.replace(f"({key})", f"(``{key}``)")
        assert worded in described, sentence


COMMITTED_FAMILY = [
    {"ci95": [0.42466, 0.503619], "ci90": [0.430223, 0.49696], "p": 0.0001, "p_holm": 0.0006},
    {"ci95": [-0.000339, 8.6e-05], "ci90": [-0.000294, 5.8e-05], "p": 0.324568, "p_holm": 1.0},
    {"ci95": [0.182611, 0.205406], "ci90": [0.184501, 0.20382], "p": 0.0002, "p_holm": 0.001},
    {"ci95": [-0.005356, 0.008157], "ci90": [-0.004054, 0.00716], "p": 0.314369, "p_holm": 1.0},
    {"ci95": [-0.002916, 0.002285], "ci90": [-0.002506, 0.001901], "p": 0.874113, "p_holm": 1.0},
    {"ci95": [-0.002879, 0.008996], "ci90": [-0.002045, 0.007995], "p": 0.338766, "p_holm": 1.0},
]
"""The six tests of the synthetic study as ``evaluate.py`` at sha256 f7f3b4df6f1ab58a wrote
them, when ``percentile`` was its p-value source and its only kind of interval. Beside them:
both equivalence readings declared; the first H3 held and carried the flag, the second did not;
and Delta_GBM had the intervals below, with p = 0.0002 for both primaries."""
COMMITTED_DELTA_GBM = {LLAMA: [0.195922, 0.239466], DEEPSEEK: [0.012487, 0.040572]}
COMMITTED_PROBE = {LLAMA: [-31.383208, -22.187679], DEEPSEEK: [-29.9206, -20.70329]}


def test_under_the_percentile_source_the_results_are_those_of_before(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``percentile`` as the registered source every interval, the equivalence reading and
    the flag beside H3 are what the evaluator gave before it knew another kind of interval, and
    no value but zero is tested."""

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a value was tested under the percentile source")

    monkeypatch.setattr(ev, "P_VALUE_SOURCE", "percentile")
    monkeypatch.setattr(ev, "larger_of_interval", never)
    monkeypatch.setattr(ev, "larger_of_at", never)
    report, table, printed = confirm(study, tmp_path, capsys)
    assert report["registered"]["p_value_source"] == "percentile"
    for entry, want in zip(report["family"], COMMITTED_FAMILY, strict=True):
        for key, value in want.items():
            assert entry[key] == pytest.approx(value, abs=2e-6), (entry["hypothesis"], key)
        assert entry["percentile"] == {"ci95": entry["ci95"], "ci90": entry["ci90"]}
        assert entry["interval_method"] == "percentile"
        assert (
            entry["p"]
            == entry["p_values"]["percentile"]["one_sided" if entry["sides"] == 1 else "two_sided"]
        )
    assert [entry["holds"] for entry in report["family"]] == [
        True,
        False,
        True,
        False,
        False,
        False,
    ]
    for model in rd.PRIMARIES:
        h2, h3 = entry_of(report, "H2", model), entry_of(report, "H3", model)
        assert h2["equivalence"] == {
            "margin": 0.02,
            "ci90": h2["ci90"],
            "interval_method": "percentile",
            "declared": True,
        }
        assert h3["beats_both_comparators"] is (model == LLAMA)
        assert h3["beside"]["base_rate"]["ci95"] == h3["ci95"]
        other = h3["beside"]["gbm_structured"]
        assert other["ci95"] == pytest.approx(COMMITTED_DELTA_GBM[model], abs=2e-6)
        assert other["p"] == pytest.approx(0.0002, abs=2e-6) and other["ci95"][0] > 0
        assert report["secondaries"]["delta_gbm"][model]["ci95"] == other["ci95"]
        probe = report["probe"][model]
        assert probe["ci95"] == pytest.approx(COMMITTED_PROBE[model], abs=2e-6)
        assert probe["p"] == 1.0 and probe["beats_base_rate"] is False
    assert (
        "Registered p-values: percentile. Intervals of the six contrasts and of Delta_GBM: percentile."
        in table
    )
    assert (
        "H2 equivalence, llama-3.3-70b: declared (90% interval [-0.0003, 0.0001], margin 0.02)."
        in table
    )
    assert (
        "H2 equivalence, deepseek-v3: declared (90% interval [-0.0025, 0.0019], margin 0.02)."
        in table
    )
    assert "delta 0.2176, 95% interval [0.1959, 0.2395]; beats both comparators: yes" in table
    assert "delta 0.0263, 95% interval [0.0125, 0.0406]; beats both comparators: no" in table
    assert "| 0.4636 | [0.4247, 0.5036] | 0.0001 | 0.0006 |" in table
    assert "delta 0.0030 [-0.0029, 0.0090] p 0.3388 Holm 1.0000: not rejected" in printed


def test_the_flag_and_the_table_read_the_interval_of_the_registered_test(
    study: SimpleNamespace, opened: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The six contrasts and the two contrasts beside each H3 are searched, at 95%, and H2 at
    90% as well: nothing else is. With the search replaced by a fixed answer, the flag beside H3
    follows the lower end it gives for Delta_GBM, an end that is not there included; under the
    percentile source the search is not made and the flag follows the percentile interval. The
    only values tested outside the search are the margin of H2 and minus that margin."""
    rows = ev.typed_outcomes(study.filled.reset_index(drop=True))
    asked: list[float] = []
    tested: list[float] = []
    real_at = ev.larger_of_at

    def at(sums: Any, sizes: Any, taken: Any, null: float, *more: Any) -> dict[str, float]:
        tested.append(null)
        return real_at(sums, sizes, taken, null, *more)

    monkeypatch.setattr(ev, "larger_of_at", at)

    def fixed(low: float | None) -> Callable[..., list[float | None]]:
        def interval(sums: Any, sizes: Any, taken: Any, coverage: float, *more: Any) -> list:
            asked.append(coverage)
            assert more == (500, ev.SEED) and taken.shape == (500, len(sizes))
            return [low, 0.9]

        return interval

    for low, flag in ((0.001, True), (0.0, False), (-0.2, False), (None, False)):
        asked.clear()
        tested.clear()
        monkeypatch.setattr(ev, "larger_of_interval", fixed(low))
        report = ev.evaluate(opened.study, rows, {}, LARGER, draws=500)
        # two primaries: H1, H2 twice over, H3, and two contrasts beside H3
        assert sorted(asked) == [0.90] * 2 + [0.95] * 10
        assert sorted(tested) == [-0.02, -0.02, 0.02, 0.02] and ev.H2_MARGIN == 0.02
        h3 = entry_of(report, "H3", LLAMA)
        assert h3["holds"] is True and h3["delta"] > 0 and h3["ci95"] == [low, 0.9]
        other = h3["beside"]["gbm_structured"]
        assert other["ci95"] == [low, 0.9] and other["interval_method"] == ev.TEST_INTERVAL
        assert report["secondaries"]["delta_gbm"][LLAMA]["ci95"] == [low, 0.9]
        assert h3["beats_both_comparators"] is flag
        # the percentile interval of the same contrast lies above zero, and is not what is read
        apart = ev.scored(rows, opened.study.predictions, "gbm_structured", h3["tested"], draws=500)
        assert apart["interval_method"] == "percentile" and apart["ci95"][0] > 0
        assert ("also lies above zero" in h3["reading"]) is flag
        for entry in report["family"]:
            assert entry["ci95"] == [low, 0.9]
            assert entry.get("ci90") == ([low, 0.9] if entry["hypothesis"] == "H2" else None)
        # every other interval is a percentile interval of its own draws
        short = report["secondaries"]["h3_with_each_condition"][h3["tested"]]
        assert short["ci95"] == h3["percentile"]["ci95"] and short["p"] == h3["p"]
        full = {"registered": record_under(LARGER), "h3": {"comparator": "base_rate"}, **report}
        table, printed = ev.markdown(full), "\n".join(ev.summary_lines(full))
        shown = "[-inf, 0.9000]" if low is None else f"[{low:.4f}, 0.9000]"
        assert table.count(f"| {shown} |") == 6 and printed.count(shown) == 6 + 2
        assert f"95% interval {shown}; beats both comparators: {'yes' if flag else 'no'}" in table
        assert table.count(f"{BESIDE}{shown}).") == 2
        # one line on what an end that is not there means, when one is shown and only then
        note = "An end shown as -inf or inf is unbounded: "
        assert table.count(note) == printed.count(note) == (1 if low is None else 0)
        written = json.loads(ev.report_text(full))
        assert entry_of(written, "H3", LLAMA)["beside"]["gbm_structured"]["ci95"] == [low, 0.9]
    # the equivalence reading is the test at the margin, whatever interval is shown beside it
    h2 = entry_of(report, "H2", LLAMA)
    assert h2["equivalence"]["ci90"] == [None, 0.9] and h2["equivalence"]["declared"] is True
    assert h2["equivalence"]["p_smaller_at_the_margin"] < 0.05
    # the table gives each of the two p-values with the value it was tested at
    found = entry_of(written, "H2", LLAMA)["equivalence"]
    found |= {"p_smaller_at_the_margin": 0.0312, "p_larger_at_minus_the_margin": 0.0011}
    line = f"declared {RULE}0.0011 at -0.02 and 0.0312 at 0.02 {BESIDE}[-inf, 0.9000])."
    assert f"H2 equivalence, {LLAMA}: {line} The two losses differ on " in ev.markdown(written)
    # a verdict the other way is worded by the rule as well, with the same two p-values
    found["declared"] = False
    assert f"H2 equivalence, {LLAMA}: not {line} The two " in ev.markdown(written)
    # the level named is the one the reading carries, at two decimals
    found["level"] = 0.1
    other_level = line.replace("below 0.05 at the margin", "below 0.10 at the margin")
    assert other_level != line and f"{LLAMA}: not {other_level} The two " in ev.markdown(written)
    found["level"] = 0.05
    # the line on unbounded ends follows what each text shows: the 95% intervals of the six
    # tests and of the contrast beside H3 in both, the 90% interval of H2 in the table alone
    note = "An end shown as -inf or inf is unbounded: "
    for entry in written["family"]:
        entry["ci95"] = [0.0, 0.9]
        if "equivalence" in entry:
            entry["equivalence"]["ci90"] = [0.0, 0.9]
        for beside in entry.get("beside", {}).values():
            beside["ci95"] = [0.0, 0.9]
    assert note not in ev.markdown(written) + "\n".join(ev.summary_lines(written))
    other = entry_of(written, "H3", DEEPSEEK)["beside"]["gbm_structured"]
    other["ci95"] = [None, 0.9]
    assert note in ev.markdown(written) and note in "\n".join(ev.summary_lines(written))
    other["ci95"], found["ci90"] = [0.0, 0.9], [0.0, None]
    assert note in ev.markdown(written) and note not in "\n".join(ev.summary_lines(written))
    found["ci90"], first = [0.0, 0.9], entry_of(written, "H1", LLAMA)
    assert note not in ev.markdown(written) + "\n".join(ev.summary_lines(written))
    first["ci95"] = [0.0, None]  # one of the six tests alone
    assert ev.markdown(written).count(note) == 1 == "\n".join(ev.summary_lines(written)).count(note)

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("an interval was searched under the percentile source")

    monkeypatch.setattr(ev, "larger_of_interval", never)
    report = ev.evaluate(opened.study, rows, {}, "percentile", draws=500)
    h3 = entry_of(report, "H3", LLAMA)
    other = h3["beside"]["gbm_structured"]
    assert other["interval_method"] == "percentile" and other["ci95"][0] > 0
    assert h3["beats_both_comparators"] is True and h3["ci95"] == h3["percentile"]["ci95"]


def test_with_few_episodes_the_intervals_of_the_registered_test_have_no_ends(
    study: SimpleNamespace, opened: SimpleNamespace
) -> None:
    """Four episodes: the sign patterns cannot give a p-value below 1/16, so no value of any
    contrast is rejected. Every confirmatory interval is unbounded on both sides, nothing is
    declared equivalent and no flag is set, and the outputs are written all the same."""
    rows = ev.typed_outcomes(study.filled.reset_index(drop=True))
    four = rows.assign(episode_id=[f"g{k % 4}" for k in range(len(rows))])
    report = ev.evaluate(opened.study, four, {}, LARGER, draws=300)
    for entry in report["family"]:
        assert entry["evaluable"] and entry["episodes"] == 4 and entry["ci95"] == [None, None]
        assert entry["p"] >= 1 / 16 and entry["holds"] is False
        assert None not in entry["percentile"]["ci95"]
    for model in rd.PRIMARIES:
        found = entry_of(report, "H2", model)["equivalence"]
        assert found["ci90"] == [None, None] and found["declared"] is False
        h3 = entry_of(report, "H3", model)
        assert h3["beats_both_comparators"] is False
        assert h3["beside"]["gbm_structured"]["ci95"] == [None, None]
    full = {"registered": record_under(LARGER), "h3": {"comparator": "base_rate"}, **report}
    table = ev.markdown(full)
    assert table.count("| [-inf, inf] |") == 6 and table.count(f"{BESIDE}[-inf, inf]).") == 2
    # nothing is declared, and the whole line says so: the rule, the two p-values it read, the
    # interval beside it and the counts
    for model in rd.PRIMARIES:
        entry = entry_of(report, "H2", model)
        found = entry["equivalence"]
        larger, smaller = found["p_larger_at_minus_the_margin"], found["p_smaller_at_the_margin"]
        assert min(larger, smaller) >= 1 / 16
        assert (
            f"H2 equivalence, {model}: not declared {RULE}{larger:.4f} at -0.02 and "
            f"{smaller:.4f} at 0.02 {BESIDE}[-inf, inf]). {counts_line(entry['losses_differ'])}"
        ) in table.splitlines()
    assert "n/a" not in table and "None" not in table
    written = json.loads(ev.report_text(full))
    assert [entry["ci95"] for entry in written["family"]] == [[None, None]] * 6
    # the last line of the table and of the printout says what an end that is not there means
    (note,) = ev.unbounded_note(full["registered"], [[None, None]])
    printed = ev.summary_lines(full)
    assert table.splitlines()[-1] == note == printed[-1]
    assert table.count(note) == 1 and sum("[-inf, inf]" in line for line in printed) == 6 + 2
    # no contrast in short holds a 90% interval or the percentile intervals
    shorts = [v for v in walk(report["secondaries"]) if isinstance(v, dict) and "delta" in v]
    assert len(shorts) > 30 and not [v for v in shorts if "ci90" in v or "percentile" in v]
    for entry in report["family"]:
        assert "ci90" not in entry["both_sides_parsed"]
        assert all("ci90" not in beside for beside in entry.get("beside", {}).values())
    # the percentile source on the same four episodes gives every interval its two ends
    before = ev.evaluate(opened.study, four, {}, "percentile", draws=300)
    for entry in before["family"]:
        assert None not in entry["ci95"] and None not in entry["ci90"]


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
        assert entry["p"] == entry["p_values"][SOURCE]["two_sided"]
        # beside it: the same condition against both predictors that read no text, on the
        # same statements and the same draws
        assert list(entry["beside"]) == ["gbm_structured", "base_rate"]
        mine, other = entry["beside"]["base_rate"], entry["beside"]["gbm_structured"]
        assert (mine["delta"], mine["ci95"], mine["p"], mine["interval_method"]) == (
            entry["delta"],
            entry["ci95"],
            entry["p"],
            entry["interval_method"],
        )
        assert other["interval_method"] == ev.interval_method(SOURCE)
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
        assert entry["percentile"]["ci95"] == pytest.approx(P.interval(delta), abs=1e-6)
        assert entry["p_values"]["percentile"]["two_sided"] == pytest.approx(
            P.p_values(delta)["two_sided"], abs=1e-6
        )
        second = base.report["secondaries"]["delta_gbm"][model]
        assert second["statements"] == entry["statements"] == len(scoreable)
        # the intervals and p-values of the source in force, from the same episode draws (and,
        # for the interval of the registered test, the same sign patterns): worked out here
        # from the three losses
        sums, sizes = P.cluster_sums(losses, clusters)
        taken = P.cluster_draws(len(sizes), ev.DRAWS, ev.SEED).astype(float)
        for found, comparator, percentile in ((entry, 0, delta), (second, 1, delta_gbm)):
            mine = sums[:, comparator] - sums[:, 2]
            want = REAL_INTERVAL(mine, sizes, taken, 0.95) if BY_TEST else P.interval(percentile)
            assert found["ci95"] == pytest.approx(want, abs=1e-6)
            at_zero = ev.contrast(losses[:, comparator], losses[:, 2], clusters)["p_values"]
            assert found["p"] == pytest.approx(at_zero[SOURCE]["two_sided"], abs=1e-6)
            assert found["interval_method"] == ev.interval_method(SOURCE)
        # paired draw by draw: Delta_GBM minus Delta is the structured model's loss minus the
        # base rate's in every draw, so its interval is that of the model-free contrast
        gap = draws[:, 1] - draws[:, 0]
        assert np.allclose(delta_gbm - delta, gap)
        other = ev.contrast(
            losses[:, 1], losses[:, 2], clusters, seed=ev.SEED + 1, source=SOURCE, levels=["ci95"]
        )
        assert other["interval_method"] == second["interval_method"]
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
        assert entry["p"] == entry["p_values"][SOURCE][side]
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
    # (the overconfidence criterion of PLAN section 13 has its own tests)
    assert list(second["overconfidence_of_condition_a"]) == list(rd.PRIMARIES)
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


# --------------------------------------------------------------------------------------------
# The overconfidence criterion (PLAN section 13)
# --------------------------------------------------------------------------------------------


PLAN = Path(ev.__file__).parent / "plan" / "PLAN.md"
EVENT_KEYS = ["E_end", "E_end90"]
LIMIT_KEYS = [
    "undetermined",
    "mean_p",
    "largest_frequency",
    "least",
    "least_ci95",
    "smallest_frequency",
    "greatest",
    "greatest_ci95",
]
"""What the result file holds of calibration in the large over every statement, per event."""
GAP_KEYS = ["mean_p_model", "mean_p_base_rate", "difference", "ci95"]
COVERAGE_KEYS = ["inside", "outside", "bracket_straddles_the_interval", "coverage"]
PART_KEYS = ["statements", "episodes", "against_outcomes", "against_base_rate"]
CRITERION_KEYS = [
    "criterion",
    *PART_KEYS,
    "reading",
    "reading_in_words",
    "met",
    "scoreable",
    "parsed_only",
    "coverage_80",
]
"""The keys of the criterion of one primary, as ``evaluate.overconfidence`` gives them; the
result file puts ``items`` before them."""


def item_rows(
    e_end: Sequence[float | None],
    e_end90: Sequence[float | None] | None = None,
    episodes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Typed rows of an item set built by hand: the two horizon events of each statement as 1,
    0 or None (undetermined; ``E_end90`` as ``E_end`` unless given), its episode (its own
    unless given), and a time to recovery between 40 and 60 days."""
    index = [f"s{k:03d}" for k in range(len(e_end))]
    rows = pd.DataFrame(
        {
            "y_a": pd.Series(list(e_end), index=index, dtype=float),
            "y_b": pd.Series(list(e_end if e_end90 is None else e_end90), index=index, dtype=float),
            "episode_id": list(episodes or index),
            "ttr_kind": "interval",
            "ttr_lower": 40.0,
            "ttr_upper": 60.0,
            "ttr_mid": 50.0,
        },
        index=index,
    )
    return rows.assign(scoreable=rows["y_a"].notna() & rows["y_b"].notna())


def stated(rows: pd.DataFrame, p_a: Any, p_b: Any = 0.5, **quantiles: float) -> pd.DataFrame:
    """Predictions for the statements of ``rows``: ``P(E_end)`` and ``P(E_end90)`` (one value
    for all, or one per statement) and quantiles from 30 to 250 days unless given."""
    days = dict(zip(P.QUANTILE_KEYS, (30.0, 100.0, 150.0, 200.0, 250.0), strict=True)) | quantiles
    return pd.DataFrame({"p_a": p_a, "p_b": p_b, **days}, index=rows.index, dtype=float)


def everyone(rows: pd.DataFrame) -> pd.Series:
    """Every answer parsed."""
    return pd.Series(True, index=rows.index)


def events_of(found: dict[str, Any], event: str = "E_end") -> tuple[dict, dict]:
    """The two parts of a criterion for one event: against outcomes, against the base rate."""
    return found["against_outcomes"][event], found["against_base_rate"][event]


def test_an_interval_excludes_zero_when_both_ends_lie_on_one_side() -> None:
    for interval, verdict in (
        ([0.001, 0.4], True),
        ([-0.4, -0.001], True),
        ([0.0, 0.4], False),  # an end on zero does not exclude it
        ([-0.4, 0.0], False),
        ([-0.1, 0.1], False),
        ([0.0, 0.0], False),
        (None, False),  # an interval that could not be made excludes nothing
    ):
        assert ev.excludes_zero(interval) is verdict, interval


def test_the_five_readings_are_tried_in_the_plans_order() -> None:
    below, above = [-0.3, -0.1], [0.1, 0.3]
    cases = [
        # the greatest value and its interval; the part against outcomes; the part against the
        # base rate; the reading
        (-0.2, below, False, False, 1),
        (-0.2, below, False, True, 1),  # underconfident, and nothing else of the list
        (-0.2, below, True, True, 1),  # the first case is tried first, whatever else is given
        (-0.2, [-0.3, 0.1], False, True, 3),  # negative, but the interval holds zero
        (-0.2, [-0.3, 0.0], False, False, 5),  # an end on zero
        (-0.2, None, False, False, 5),  # no interval
        (0.0, below, False, False, 5),  # zero is not negative
        (0.2, above, True, True, 2),  # an interval that excludes zero from above is not the first
        (0.2, above, False, True, 3),
        (0.2, above, True, False, 4),
        (0.2, above, False, False, 5),
    ]
    for greatest, interval, first, second, reading in cases:
        outcomes = {"greatest": greatest, "greatest_ci95": interval, "met": first}
        assert ev.overconfidence_reading(outcomes, {"met": second}) == reading, outcomes
    # each reading in the words the plan gives the paper (section 13, "Reading")
    plan = words(PLAN.read_text(encoding="utf-8"))
    quoted = {
        1: ["the readings are underconfident relative to outcomes"],
        2: ["overconfident relative to outcomes"],
        3: [
            "the model states higher probabilities than the base rate",
            "the captures do not decide whether it is overconfident",
        ],
        4: [
            "the model's probabilities exceed every frequency the captures allow",
            "they were not shown to exceed the base rate's",
            "the excess is not put down to the reading",
        ],
        5: ["overconfidence was not detected"],
    }
    assert list(ev.OVERCONFIDENCE_READINGS) == [1, 2, 3, 4, 5] == list(quoted)
    for number, phrases in quoted.items():
        for phrase in phrases:
            assert phrase in plan and phrase in ev.OVERCONFIDENCE_READINGS[number], phrase
    assert "and nothing else of this list" in plan  # the first reading says nothing of the rest
    assert ev.OVERCONFIDENCE_READINGS[1] == quoted[1][0]
    assert "does not write that the readings are calibrated" in plan
    assert "does not say that the readings are calibrated" in ev.OVERCONFIDENCE_READINGS[5]
    # the criterion's own words name both parts, the item set and what met means
    said = ev.OVERCONFIDENCE_CRITERION
    for phrase in (
        "every undetermined E_end counted as yes",
        "the largest frequency of E_end the captures allow",
        "the base rate by listing age on the same statements",
        "over every statement of the item set",
        "95% percentile interval by episode",
        "met: both parts hold (reading 2)",
    ):
        assert phrase in said, phrase
    # each of the two parts asks for a value above zero, in the same words; the value below zero
    # belongs to the first reading, which those words do not describe
    assert said.count("is positive with an interval that excludes zero") == 2
    assert "negative" not in said


def twenty() -> pd.DataFrame:
    """Four episodes of five statements, each with ``E_end`` yes, no, no, undetermined,
    undetermined. Of the 20 statements 4 are yes, 8 no and 8 undetermined: the largest
    frequency the captures allow is (4 + 8) / 20 = 0.6 and the smallest 4 / 20 = 0.2. The
    episodes are alike, so every draw of episodes has the same mean and an interval is the
    value itself: the verdicts follow the signs."""
    return item_rows([1, 0, 0, None, None] * 4, episodes=[e for e in "ghkm" for _ in range(5)])


def forty() -> pd.DataFrame:
    """``twenty`` twice over: eight episodes of five statements, each with ``E_end`` yes, no,
    no, undetermined, undetermined. Of the 40 statements 8 are yes and 16 undetermined: the
    largest frequency the captures allow is 24 / 40 = 0.6 and the smallest 8 / 40 = 0.2."""
    return item_rows([1, 0, 0, None, None] * 8, episodes=[e for e in "ghkmnpqr" for _ in range(5)])


BY_HAND = [
    # P(E_end) of the model (p) and of the base rate (b) on every statement; the reading; the
    # part against outcomes (the least value p - 0.6 above zero); the part against the base
    # rate (p - b above zero). The greatest value is p - 0.2.
    (0.1, 0.05, 1, False, True),  # greatest -0.1: underconfident, though 0.05 above the base rate
    (0.9, 0.25, 2, True, True),  # least 0.3, difference 0.65
    (0.5, 0.25, 3, False, True),  # least -0.1, greatest 0.3, difference 0.25
    (0.6, 0.3, 3, False, True),  # least 0.6 - 0.6: zero is not above zero
    (0.2, 0.1, 3, False, True),  # greatest 0.2 - 0.2: zero is not below zero, so not the first
    (0.9, 0.95, 4, True, False),  # least 0.3, difference -0.05: below zero is not above it
    (0.9, 0.9, 4, True, False),  # the base rate's own probabilities: a difference of zero
    (0.5, 0.5, 5, False, False),  # least -0.1, greatest 0.3, difference 0
    (0.5, 0.7, 5, False, False),  # least -0.1, greatest 0.3, difference -0.2
]


@pytest.mark.parametrize(("p", "b", "reading", "first", "second"), BY_HAND)
def test_each_reading_of_the_criterion_on_rows_worked_by_hand(
    p: float, b: float, reading: int, first: bool, second: bool
) -> None:
    rows = twenty()
    found = ev.overconfidence(rows, stated(rows, p), stated(rows, b), everyone(rows), 400, ev.SEED)
    assert list(found) == CRITERION_KEYS and found["criterion"] == ev.OVERCONFIDENCE_CRITERION
    assert (found["statements"], found["episodes"]) == (20, 4)
    outcomes, no_text = events_of(found)
    assert outcomes["undetermined"] == 8
    assert outcomes["largest_frequency"] == pytest.approx(0.6)
    assert outcomes["smallest_frequency"] == pytest.approx(0.2)
    assert outcomes["mean_p"] == pytest.approx(p) == no_text["mean_p_model"]
    assert outcomes["least"] == pytest.approx(p - 0.6)
    assert outcomes["greatest"] == pytest.approx(p - 0.2)
    assert outcomes["least_ci95"] == pytest.approx([p - 0.6] * 2, abs=1e-12)
    assert outcomes["greatest_ci95"] == pytest.approx([p - 0.2] * 2, abs=1e-12)
    assert no_text["mean_p_base_rate"] == pytest.approx(b)
    assert no_text["difference"] == pytest.approx(p - b)
    assert no_text["ci95"] == pytest.approx([p - b] * 2, abs=1e-12)
    assert outcomes["met"] is first and no_text["met"] is second
    assert found["reading"] == reading and found["met"] is (reading == 2)
    assert found["reading_in_words"] == ev.OVERCONFIDENCE_READINGS[reading]
    # the base rate's limits on the same statements stand beside the model's, without a verdict
    theirs = outcomes["base_rate"]
    assert list(outcomes) == [*LIMIT_KEYS, "met", "base_rate"] and list(theirs) == LIMIT_KEYS
    assert theirs["mean_p"] == pytest.approx(b) and theirs["undetermined"] == 8
    assert theirs["least"] == pytest.approx(b - 0.6) and theirs["greatest"] == pytest.approx(
        b - 0.2
    )
    assert list(no_text) == [*GAP_KEYS, "met"]


def test_a_value_whose_interval_holds_zero_decides_nothing() -> None:
    # two episodes of four statements: in g no E_end happened, in h every one did (4 of 8)
    rows = item_rows([0] * 4 + [1] * 4, episodes=["g"] * 4 + ["h"] * 4)
    # The model says 0.6 everywhere: 0.6 above the outcome in g, 0.4 below it in h, and
    # 0.6 - 4/8 = 0.1 above over both. A draw of two episodes takes g twice (0.6), h twice
    # (-0.4) or each once (0.1): a quarter, a quarter and a half of the draws, so the interval
    # runs from -0.4 to 0.6. The base rate says 0.2 in g and 0.8 in h: the model is 0.4 above
    # it in g, 0.2 below it in h, 0.1 above over both, with an interval from -0.2 to 0.4.
    base = stated(rows, [0.2] * 4 + [0.8] * 4)
    found = ev.overconfidence(rows, stated(rows, 0.6), base, everyone(rows), 2000, ev.SEED)
    outcomes, no_text = events_of(found)
    assert outcomes["undetermined"] == 0  # so the least value is also the greatest
    assert outcomes["least"] == pytest.approx(0.1) == outcomes["greatest"]
    assert outcomes["least_ci95"] == pytest.approx([-0.4, 0.6]) == outcomes["greatest_ci95"]
    assert no_text["difference"] == pytest.approx(0.1) and no_text["ci95"] == pytest.approx(
        [-0.2, 0.4]
    )
    assert (outcomes["met"], no_text["met"]) == (False, False)
    assert found["reading"] == 5 and found["met"] is False
    # the mirror image: 0.4 is 0.1 below the frequency with an interval from -0.6 to 0.4, which
    # holds zero, so the readings are not called underconfident
    low = ev.overconfidence(rows, stated(rows, 0.4), stated(rows, 0.4), everyone(rows), 2000, 5)
    assert events_of(low)[0]["greatest"] == pytest.approx(-0.1)
    assert events_of(low)[0]["greatest_ci95"] == pytest.approx([-0.6, 0.4])
    assert low["reading"] == 5
    # one episode: no interval can be made, no part is met and the reading is the fifth,
    # however far the values are from zero (0.99 - 0.5 and 0.99 - 0.01)
    one = rows.assign(episode_id="g")
    alone = ev.overconfidence(one, stated(one, 0.99), stated(one, 0.01), everyone(one), 2000, 5)
    outcomes, no_text = events_of(alone)
    assert alone["episodes"] == 1 and outcomes["least"] == pytest.approx(0.49)
    assert outcomes["least_ci95"] is None and outcomes["greatest_ci95"] is None
    assert no_text["difference"] == pytest.approx(0.98) and no_text["ci95"] is None
    assert (outcomes["met"], no_text["met"], alone["reading"]) == (False, False, 5)
    assert outcomes["base_rate"]["least_ci95"] is None
    assert alone["scoreable"]["E_end"]["ci95"] is None
    assert alone["scoreable"]["E_end"]["against_base_rate"]["ci95"] is None
    # nor is a model far below every frequency called underconfident without an interval
    under = ev.overconfidence(one, stated(one, 0.01), stated(one, 0.01), everyone(one), 2000, 5)
    assert events_of(under)[0]["greatest"] == pytest.approx(-0.49) and under["reading"] == 5
    assert ev.MIN_EPISODES == 2


def test_an_undetermined_event_is_counted_at_its_own_horizon_alone() -> None:
    # Six statements in three episodes, E_end / E_end90:
    #   s000 undetermined / yes   (E_end is open and E_end90 is not)
    #   s001 no / undetermined    (the reverse)
    #   s002 yes / yes   s003 no / yes   s004 no / no   s005 undetermined / undetermined
    rows = item_rows([None, 0, 1, 0, 0, None], [1, None, 1, 1, 0, None], episodes=list("gghhkk"))
    assert rows["scoreable"].tolist() == [False, False, True, True, True, False]
    pred, base = stated(rows, 0.7, 0.8), stated(rows, 0.3, 0.5)
    found = ev.overconfidence(rows, pred, base, everyone(rows), 400, ev.SEED)
    # E_end: 1 yes, 3 no, 2 undetermined. Largest frequency (1 + 2) / 6 = 0.5, smallest 1 / 6.
    # s001 is not scoreable, and its E_end is still the no that was seen: had the three
    # statements that are not scoreable been counted as open, the largest would be 4 / 6.
    outcomes, no_text = events_of(found)
    assert outcomes["undetermined"] == 2
    assert outcomes["largest_frequency"] == pytest.approx(3 / 6)
    assert outcomes["smallest_frequency"] == pytest.approx(1 / 6)
    assert outcomes["least"] == pytest.approx(0.7 - 3 / 6)
    assert outcomes["greatest"] == pytest.approx(0.7 - 1 / 6)
    assert outcomes["base_rate"]["least"] == pytest.approx(0.3 - 3 / 6)
    assert outcomes["base_rate"]["greatest"] == pytest.approx(0.3 - 1 / 6)
    assert no_text["difference"] == pytest.approx(0.7 - 0.3)
    # E_end90: 3 yes, 1 no, 2 undetermined. Largest (3 + 2) / 6, smallest 3 / 6: the yes of
    # s000 is counted in both, although its E_end is open.
    later, apart = events_of(found, "E_end90")
    assert later["undetermined"] == 2 and later["mean_p"] == pytest.approx(0.8)
    assert later["largest_frequency"] == pytest.approx(5 / 6)
    assert later["smallest_frequency"] == pytest.approx(3 / 6)
    assert later["least"] == pytest.approx(0.8 - 5 / 6)
    assert later["greatest"] == pytest.approx(0.8 - 3 / 6)
    assert later["base_rate"]["least"] == pytest.approx(0.5 - 5 / 6)
    assert later["base_rate"]["greatest"] == pytest.approx(0.0)
    assert apart["mean_p_base_rate"] == pytest.approx(0.5)
    assert apart["difference"] == pytest.approx(0.8 - 0.5)
    # beside the criterion, the scoreable statements (s002, s003, s004: E_end 1 of 3, E_end90
    # 2 of 3), where the two predictors stand against one frequency
    scoreable = found["scoreable"]
    assert list(scoreable) == ["statements", "episodes", *EVENT_KEYS]
    assert (scoreable["statements"], scoreable["episodes"]) == (3, 2)
    assert list(scoreable["E_end"]) == [
        "mean_p_minus_frequency",
        "ci95",
        "base_rate",
        "against_base_rate",
    ]
    assert scoreable["E_end"]["mean_p_minus_frequency"] == pytest.approx(0.7 - 1 / 3)
    assert scoreable["E_end"]["base_rate"]["mean_p_minus_frequency"] == pytest.approx(0.3 - 1 / 3)
    assert list(scoreable["E_end"]["base_rate"]) == ["mean_p_minus_frequency", "ci95"]
    assert list(scoreable["E_end"]["against_base_rate"]) == GAP_KEYS
    assert scoreable["E_end"]["against_base_rate"]["difference"] == pytest.approx(0.4)
    assert scoreable["E_end90"]["mean_p_minus_frequency"] == pytest.approx(0.8 - 2 / 3)
    assert scoreable["E_end90"]["base_rate"]["mean_p_minus_frequency"] == pytest.approx(0.5 - 2 / 3)
    assert scoreable["E_end90"]["against_base_rate"]["difference"] == pytest.approx(0.3)
    held = ev.calibration(pred.loc[rows["scoreable"], "p_a"], [1, 0, 0], list("hhk"), 400, ev.SEED)
    assert {key: scoreable["E_end"][key] for key in held} == held
    # the limits on their own: the same numbers, and nothing without a statement
    limits = ev.calibration_limits([0.7] * 6, rows["y_a"], list("gghhkk"), 400, ev.SEED)
    assert limits == {key: outcomes[key] for key in LIMIT_KEYS}
    assert ev.calibration_limits([], [], [], 400, ev.SEED) == {
        "undetermined": 0,
        **dict.fromkeys(LIMIT_KEYS[1:]),
    }
    assert ev.probability_gap([], [], [], 400, ev.SEED) == dict.fromkeys(GAP_KEYS)
    # no statement is scoreable: the block holds its counts and nothing else
    open_rows = item_rows([None, 0], [1, None])
    bare = ev.overconfidence(
        open_rows, stated(open_rows, 0.7), stated(open_rows, 0.3), everyone(open_rows), 400, 5
    )
    assert bare["scoreable"] == {"statements": 0, "episodes": 0}
    assert events_of(bare)[0]["least"] == pytest.approx(0.7 - 1 / 2)


def test_failed_answers_are_in_the_criterion_and_out_of_the_parsed_only_figures() -> None:
    # Three times over, six statements in three episodes of two: E_end yes, no, undetermined,
    # no, yes, undetermined. 18 statements in nine episodes, so that neither the answers that
    # failed nor those that parsed are few enough for the parsed-only figures to be withheld.
    rows = item_rows(
        [1, 0, None, 0, 1, None] * 3, episodes=[e for e in "ghkmnpqrt" for _ in range(2)]
    )
    base = stated(rows, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6] * 3, [0.2, 0.3, 0.4, 0.5, 0.6, 0.7] * 3)
    # the model answers 0.8 (0.9 for E_end90) with an 80% interval from 50 to 200 days on the
    # first four of each six; its other two answers failed and are replaced by the base rate's
    # output
    fourth = [k % 6 < 4 for k in range(18)]
    answers = {
        item: stored(forecast(0.8, 0.9, 100) if given else None)
        for item, given in zip(rows.index, fourth, strict=True)
    }
    pred, parsed, counts = ev.predictive(answers, rows, base)
    assert counts["replaced_by_base_rate"] == 6 and parsed.tolist() == fourth
    assert pred["p_a"].tolist() == [0.8, 0.8, 0.8, 0.8, 0.5, 0.6] * 3
    found = ev.overconfidence(rows, pred, base, parsed, 400, ev.SEED)
    # The main figures hold every statement. In each six, mean P(E_end) is (4 * 0.8 + 0.5 +
    # 0.6) / 6 = 4.3 / 6 for the model and 2.1 / 6 for the base rate, a difference of 2.2 / 6.
    # E_end is yes on 2 and undetermined on 2 of 6: largest frequency 4 / 6, smallest 2 / 6.
    outcomes, no_text = events_of(found)
    assert (found["statements"], found["episodes"]) == (18, 9)
    assert outcomes["mean_p"] == pytest.approx(4.3 / 6) == no_text["mean_p_model"]
    assert outcomes["least"] == pytest.approx(4.3 / 6 - 4 / 6)
    assert outcomes["greatest"] == pytest.approx(4.3 / 6 - 2 / 6)
    assert no_text["mean_p_base_rate"] == pytest.approx(2.1 / 6)
    assert no_text["difference"] == pytest.approx(2.2 / 6)
    assert outcomes["base_rate"]["least"] == pytest.approx(2.1 / 6 - 4 / 6)
    # Parsed only: the first four statements of each six, in two of its three episodes. Mean
    # P(E_end) 0.8 against the base rate's (0.1 + 0.2 + 0.3 + 0.4) / 4 = 0.25. E_end is yes on
    # 1 and undetermined on 1 of 4: largest frequency 2 / 4, smallest 1 / 4.
    kept = found["parsed_only"]
    assert list(kept) == ["not_parsed", *PART_KEYS]
    assert (kept["not_parsed"], kept["statements"], kept["episodes"]) == (6, 12, 6)
    outcomes, no_text = events_of(kept)
    assert outcomes["undetermined"] == 3 and outcomes["mean_p"] == pytest.approx(0.8)
    assert outcomes["least"] == pytest.approx(0.8 - 2 / 4)
    assert outcomes["greatest"] == pytest.approx(0.8 - 1 / 4)
    assert outcomes["base_rate"]["mean_p"] == pytest.approx(0.25)
    assert outcomes["base_rate"]["least"] == pytest.approx(0.25 - 2 / 4)
    assert outcomes["base_rate"]["greatest"] == pytest.approx(0.0)
    assert no_text["mean_p_base_rate"] == pytest.approx(0.25)
    assert no_text["difference"] == pytest.approx(0.55)
    assert list(kept["against_outcomes"]) == EVENT_KEYS == list(kept["against_base_rate"])
    later, apart = events_of(kept, "E_end90")
    assert later["mean_p"] == pytest.approx(0.9) and apart["mean_p_base_rate"] == pytest.approx(
        0.35
    )
    # with every answer parsed the two sets are the same
    whole = ev.overconfidence(rows, pred, base, everyone(rows), 400, ev.SEED)
    assert whole["parsed_only"] == {"not_parsed": 0} | {key: whole[key] for key in PART_KEYS}
    # and with none there is nothing to give
    nobody = ev.overconfidence(rows, pred, base, ~everyone(rows), 400, ev.SEED)["parsed_only"]
    assert list(nobody) == ["not_parsed", *PART_KEYS]
    assert (nobody["not_parsed"], nobody["statements"], nobody["episodes"]) == (18, 0, 0)
    assert nobody["against_outcomes"]["E_end"]["least"] is None
    assert nobody["against_base_rate"]["E_end"] == {**dict.fromkeys(GAP_KEYS), "met": False}
    assert nobody["against_outcomes"]["E_end"]["met"] is False
    # the coverage of the 80% interval, for both predictors on every statement: the bracket
    # of 40 to 60 days straddles the lower end of the model's twelve intervals (50 to 200) and
    # lies inside the base rate's (30 to 200), which the six failed answers took
    assert found["coverage_80"] == {
        "inside": 6,
        "outside": 0,
        "bracket_straddles_the_interval": 12,
        "coverage": 1.0,
        "base_rate": {
            "inside": 18,
            "outside": 0,
            "bracket_straddles_the_interval": 0,
            "coverage": 1.0,
        },
    }
    assert list(found["coverage_80"]) == [*COVERAGE_KEYS, "base_rate"]


def test_the_parsed_only_figures_are_withheld_when_they_would_give_back_a_few_statements() -> None:
    """Beside the figures over every statement, those over the answers that parsed give the
    horizon events of the statements between the two sets: the counts of undetermined events
    subtract, and so do the frequencies times the numbers of statements. Which answers failed
    can be told from the stored runs, so with 1 to 4 failed answers the block holds its counts
    alone; and so it does over 1 to 4 parsed answers, whose events it would give outright."""
    rows = forty()  # each episode: E_end yes, no, no, undetermined, undetermined
    base, said = stated(rows, 0.5), stated(rows, 0.9)

    def with_failed(failed: Sequence[int]) -> dict[str, Any]:
        parsed = pd.Series([k not in failed for k in range(40)], index=rows.index)
        pred = said.where(parsed, base, axis=0)
        return ev.overconfidence(rows, pred, base, parsed, 300, ev.SEED)

    # five failed answers, the first episode: the figures are given, and what they give by
    # subtraction is a count over those five statements (E_end yes on 1, undetermined on 2)
    found = with_failed(range(5))
    kept = found["parsed_only"]
    assert list(kept) == ["not_parsed", *PART_KEYS]
    assert (kept["not_parsed"], kept["statements"], kept["episodes"]) == (5, 35, 7)
    whole, part = events_of(found)[0], events_of(kept)[0]
    assert whole["undetermined"] - part["undetermined"] == 2
    assert round(whole["smallest_frequency"] * 40) - round(part["smallest_frequency"] * 35) == 1
    # one failed answer, whose E_end is yes (s000), no (s001) or undetermined (s003); then two
    # and four: the same subtraction would give the event of one statement, or of a few, and
    # there is nothing left to subtract
    for failed in ([0], [1], [3], [0, 3], [0, 1, 2, 3]):
        found = with_failed(failed)
        assert found["parsed_only"] == {
            "not_parsed": len(failed),
            "statements": 40 - len(failed),
            "episodes": 8,
            "withheld": True,
        }
        # the criterion and what else stands beside it are on every statement, as before
        assert list(found) == CRITERION_KEYS and found["statements"] == 40
        outcomes, no_text = events_of(found)
        assert outcomes["undetermined"] == 16
        assert outcomes["largest_frequency"] == pytest.approx(0.6)
        assert no_text["mean_p_model"] == pytest.approx(0.9 - 0.4 * len(failed) / 40)
        assert found["reading"] == 2 and found["scoreable"]["statements"] == 24
    # four answers parsed, or one: the figures over them would be their events themselves
    for given in (1, 4):
        found = with_failed(range(given, 40))
        assert found["parsed_only"] == {
            "not_parsed": 40 - given,
            "statements": given,
            "episodes": 1,
            "withheld": True,
        }
    # five parsed, in one episode: given, without an interval
    kept = with_failed(range(5, 40))["parsed_only"]
    assert list(kept) == ["not_parsed", *PART_KEYS]
    assert (kept["not_parsed"], kept["statements"], kept["episodes"]) == (35, 5, 1)
    assert events_of(kept)[0]["greatest"] == pytest.approx(0.9 - 1 / 5)
    assert events_of(kept)[0]["greatest_ci95"] is None
    # none failed, or none parsed: no statement lies between the two sets, nothing is withheld
    assert list(with_failed([])["parsed_only"]) == ["not_parsed", *PART_KEYS]
    assert list(with_failed(range(40))["parsed_only"]) == ["not_parsed", *PART_KEYS]
    assert ev.MIN_SHOWN == 5
    assert [ev.few(count) for count in (0, 1, 4, 5, 40)] == [False, True, True, False, False]


def test_the_reading_is_that_of_every_statement_not_of_the_answers_that_parsed() -> None:
    # The model says 0.9 on the first statement of each episode, whose E_end is yes; its other
    # answers failed and hold the base rate's 0.5.
    rows = forty()
    base = stated(rows, 0.5)
    parsed = pd.Series([True, False, False, False, False] * 8, index=rows.index)
    pred = stated(rows, 0.9).where(parsed, base, axis=0)
    found = ev.overconfidence(rows, pred, base, parsed, 400, ev.SEED)
    # Every statement: mean (8 * 0.9 + 32 * 0.5) / 40 = 0.58. Least 0.58 - 0.6, which is not
    # above zero; greatest 0.58 - 0.2; 0.08 above the base rate: the third reading.
    outcomes, no_text = events_of(found)
    assert outcomes["mean_p"] == pytest.approx(0.58)
    assert outcomes["least"] == pytest.approx(-0.02)
    assert outcomes["greatest"] == pytest.approx(0.38)
    assert no_text["difference"] == pytest.approx(0.08)
    assert (outcomes["met"], no_text["met"], found["reading"]) == (False, True, 3)
    assert found["reading_in_words"] == ev.OVERCONFIDENCE_READINGS[3] and found["met"] is False
    # The eight answers that parsed: 0.9 against E_end yes on all eight, so that the least and
    # the greatest value are both -0.1 with an interval on it. Read on these alone, the model
    # would be called underconfident, which is the first reading.
    kept = found["parsed_only"]
    assert (kept["not_parsed"], kept["statements"], kept["episodes"]) == (32, 8, 8)
    outcomes, no_text = events_of(kept)
    assert outcomes["undetermined"] == 0 and outcomes["largest_frequency"] == 1.0
    assert outcomes["greatest"] == pytest.approx(-0.1)
    assert outcomes["greatest_ci95"] == pytest.approx([-0.1, -0.1])
    assert no_text["difference"] == pytest.approx(0.4) and no_text["met"] is True
    assert ev.overconfidence_reading(outcomes, no_text) == 1


def loop_interval(values: Sequence[float], episodes: Sequence[str]) -> list[float]:
    """The 95% percentile interval of a mean on the registered draws, one draw at a time:
    10,000 draws with seed 20261001, each of as many episodes as there are, with replacement;
    the mean of a draw is the sum of the values of the episodes it takes, each as often as it
    is taken, over the number of their statements."""
    names = sorted(set(episodes))
    rng = np.random.default_rng(20261001)
    taken = rng.multinomial(len(names), [1.0 / len(names)] * len(names), size=10_000)
    totals = [sum(v for v, e in zip(values, episodes, strict=True) if e == name) for name in names]
    sizes = [sum(e == name for e in episodes) for name in names]
    means = []
    for draw in taken.tolist():
        total = sum(times * value for times, value in zip(draw, totals, strict=True))
        count = sum(times * size for times, size in zip(draw, sizes, strict=True))
        means.append(total / count)
    low, high = np.quantile(means, [0.025, 0.975])
    return [float(low), float(high)]


def thirty() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Thirty statements in seven episodes of two to seven, with the predictions of a model
    and of the base rate and the answers that parsed (all but five, which is enough for the
    parsed-only figures to be given: ``evaluate.few``). Events and probabilities follow cycles
    of different lengths, so that no two episodes are alike and an interval moves with the
    draws. The two statements of the first episode have ``E_end`` undetermined: the scoreable
    statements lie in fewer episodes than the item set."""
    sizes = {"e1": 2, "e2": 3, "e3": 4, "e4": 4, "e5": 5, "e6": 5, "e7": 7}
    episodes = [name for name, size in sizes.items() for _ in range(size)]
    first = [None, None, 1, 0, 1, 0, 0, None, 1, 0]
    second = [1, 1, None, 0, 1, None, 1, 0, 1, 1, 0]
    rows = item_rows(
        [first[k % 10] for k in range(30)], [second[k % 11] for k in range(30)], episodes
    )
    p_a = [0.30 + 0.05 * (k % 9) for k in range(30)]
    pred = stated(rows, p_a, [min(0.95, p + 0.1 + 0.02 * (k % 4)) for k, p in enumerate(p_a)])
    base = stated(
        rows, [0.15 + 0.04 * (k % 6) for k in range(30)], [0.35 + 0.03 * (k % 7) for k in range(30)]
    )
    parsed = pd.Series([k not in (3, 11, 12, 19, 26) for k in range(30)], index=rows.index)
    return rows, pred, base, parsed


def test_the_intervals_of_the_criterion_are_on_the_registered_draws() -> None:
    """Every interval of the criterion against a loop over the registered draws written here:
    both limits and the difference from the base rate, for both events, on every statement, on
    the answers that parsed and on the scoreable statements (whose episodes are fewer, so that
    their draws are others)."""
    assert (ev.DRAWS, ev.SEED) == (10_000, 20261001)
    rows, pred, base, parsed = thirty()
    found = ev.overconfidence(rows, pred, base, parsed)  # the registered draws and seed

    def by_loop(keep: pd.Series, p: str, y: str) -> dict[str, Any]:
        part, mine, theirs = rows[keep], pred.loc[keep, p].tolist(), base.loc[keep, p].tolist()
        groups, event = list(part["episode_id"]), part[y].tolist()
        out: dict[str, Any] = {"model": {}, "base_rate": {}}
        for name, given_p in (("model", mine), ("base_rate", theirs)):
            for limit, counted_as in (("least", 1.0), ("greatest", 0.0)):
                gap = [
                    q - (counted_as if e != e else e) for q, e in zip(given_p, event, strict=True)
                ]
                out[name][limit] = sum(gap) / len(gap)
                out[name][f"{limit}_ci95"] = loop_interval(gap, groups)
        apart = [q - b for q, b in zip(mine, theirs, strict=True)]
        out["difference"], out["ci95"] = sum(apart) / len(apart), loop_interval(apart, groups)
        return out

    assert 0 < int(rows["scoreable"].sum()) < int(parsed.sum()) < 30
    assert rows.loc[rows["scoreable"], "episode_id"].nunique() < 7 == rows["episode_id"].nunique()
    for block, keep in ((found, everyone(rows)), (found["parsed_only"], parsed)):
        for event, p, y in (("E_end", "p_a", "y_a"), ("E_end90", "p_b", "y_b")):
            want = by_loop(keep, p, y)
            outcomes, no_text = events_of(block, event)
            for key, value in want["model"].items():
                assert outcomes[key] == pytest.approx(value, abs=1e-12), (event, key)
            for key, value in want["base_rate"].items():
                assert outcomes["base_rate"][key] == pytest.approx(value, abs=1e-12), (event, key)
            assert no_text["difference"] == pytest.approx(want["difference"], abs=1e-12)
            assert no_text["ci95"] == pytest.approx(want["ci95"], abs=1e-12)
            assert outcomes["least_ci95"][0] < outcomes["least"] < outcomes["least_ci95"][1]
    # on the scoreable statements the events are all determined, so that the two limits of the
    # loop are one value: calibration in the large, for each predictor, and their difference
    for event, p, y in (("E_end", "p_a", "y_a"), ("E_end90", "p_b", "y_b")):
        want = by_loop(rows["scoreable"], p, y)
        got = found["scoreable"][event]
        assert want["model"]["least"] == want["model"]["greatest"]
        assert got["mean_p_minus_frequency"] == pytest.approx(want["model"]["least"], abs=1e-12)
        assert got["ci95"] == pytest.approx(want["model"]["least_ci95"], abs=1e-12)
        theirs = got["base_rate"]
        assert theirs["mean_p_minus_frequency"] == pytest.approx(want["base_rate"]["least"])
        assert theirs["ci95"] == pytest.approx(want["base_rate"]["least_ci95"], abs=1e-12)
        assert got["against_base_rate"]["difference"] == pytest.approx(want["difference"])
        assert got["against_base_rate"]["ci95"] == pytest.approx(want["ci95"], abs=1e-12)
        # one frequency on both sides: the difference of the two calibrations is this one
        assert got["against_base_rate"]["difference"] == pytest.approx(
            got["mean_p_minus_frequency"] - theirs["mean_p_minus_frequency"]
        )
    # other draws or another seed give other intervals around the same values
    for other in (
        ev.overconfidence(rows, pred, base, parsed, 500, ev.SEED),
        ev.overconfidence(rows, pred, base, parsed, ev.DRAWS, ev.SEED + 1),
    ):
        mine, theirs = events_of(other), events_of(found)
        assert mine[0]["least"] == theirs[0]["least"]
        assert mine[0]["least_ci95"] != theirs[0]["least_ci95"]
        assert mine[0]["greatest_ci95"] != theirs[0]["greatest_ci95"]
        assert mine[0]["base_rate"]["least_ci95"] != theirs[0]["base_rate"]["least_ci95"]
        assert mine[1]["ci95"] != theirs[1]["ci95"]
        assert other["scoreable"]["E_end"]["ci95"] != found["scoreable"]["E_end"]["ci95"]
        assert (
            other["scoreable"]["E_end"]["against_base_rate"]["ci95"]
            != found["scoreable"]["E_end"]["against_base_rate"]["ci95"]
        )
        assert (
            events_of(other["parsed_only"])[1]["ci95"] != events_of(found["parsed_only"])[1]["ci95"]
        )


def test_a_draw_that_sums_to_zero_up_to_rounding_is_on_zero() -> None:
    """Three episodes of five statements, E_end yes on two of five in each, and a model that
    says 0.4 everywhere: calibration in the large is 0.4 - 2/5, which is zero, in every draw.
    The base rate says 0.3, 0.3, 0.6, 0.4, 0.4 in each episode, 0.4 on average: the difference
    is zero in every draw too. In floating point both sums leave a hair above zero, which is
    no evidence of anything: the intervals are on zero and no part is met."""
    rows = item_rows([1, 1, 0, 0, 0] * 3, episodes=[e for e in "ghk" for _ in range(5)])
    pred, base = stated(rows, 0.4), stated(rows, [0.3, 0.3, 0.6, 0.4, 0.4] * 3)
    clusters = list(rows["episode_id"])
    for gap in (pred["p_a"] - rows["y_a"], pred["p_a"] - base["p_a"]):
        plain = P.interval(P.bootstrap_means(gap.to_numpy(), clusters, 300, ev.SEED)[:, 0], 0.95)
        assert 0 < plain[0] <= plain[1] < 1e-15 and 0 < float(gap.mean()) < 1e-15
    found = ev.overconfidence(rows, pred, base, everyone(rows), 300, ev.SEED)
    outcomes, no_text = events_of(found)
    assert outcomes["least_ci95"] == [0.0, 0.0] == outcomes["greatest_ci95"]
    assert no_text["ci95"] == [0.0, 0.0]
    assert (outcomes["met"], no_text["met"], found["reading"]) == (False, False, 5)
    # each column has its own tolerance: a hair in the first, a value that is not zero in the
    # second, which keeps its interval however large the sums of the third are
    columns = np.array([[0.1, 0.2, -0.3] * 2, [1e-9] * 6, [1e6, 2e6, 3e6] * 2]).T
    hair, near, far = ev.episode_intervals(columns, list("ggghhh"), 300, ev.SEED)
    assert hair == [0.0, 0.0] and far == pytest.approx([2e6, 2e6])
    assert near == pytest.approx([1e-9, 1e-9], rel=1e-6) and ev.excludes_zero(near)
    assert ev.episode_intervals(columns, list("gggggg"), 300, ev.SEED) == [None, None, None]


def test_a_predictors_record_holds_the_limits_over_every_statement() -> None:
    # the statements of the test of undetermined events: E_end 1 yes, 3 no, 2 undetermined;
    # E_end90 3 yes, 1 no, 2 undetermined; three of the six are scoreable
    rows = item_rows([None, 0, 1, 0, 0, None], [1, None, 1, 1, 0, None], episodes=list("gghhkk"))
    pred, base = stated(rows, 0.7, 0.8), stated(rows, 0.3, 0.5)
    clusters = list(rows["episode_id"])
    record = ev.predictor_record(rows, pred, 300, ev.SEED)
    assert (record["statements"], record["scoreable_statements"]) == (6, 3)
    order = list(record)
    assert order.index("calibration_all_statements") == order.index("calibration_in_the_large") + 1
    limits = record["calibration_all_statements"]
    assert list(limits) == EVENT_KEYS and list(limits["E_end"]) == LIMIT_KEYS
    assert limits["E_end"] == ev.calibration_limits(
        pred["p_a"], rows["y_a"], clusters, 300, ev.SEED
    )
    assert limits["E_end90"] == ev.calibration_limits(
        pred["p_b"], rows["y_b"], clusters, 300, ev.SEED
    )
    assert limits["E_end"]["least"] == pytest.approx(0.7 - 3 / 6)
    assert limits["E_end"]["greatest"] == pytest.approx(0.7 - 1 / 6)
    assert limits["E_end90"]["least"] == pytest.approx(0.8 - 5 / 6)
    assert limits["E_end90"]["greatest"] == pytest.approx(0.8 - 3 / 6)
    # the value on the scoreable statements is as it was: 1 of 3 and 2 of 3
    large = record["calibration_in_the_large"]
    assert large["E_end"]["mean_p_minus_frequency"] == pytest.approx(0.7 - 1 / 3)
    assert large["E_end90"]["mean_p_minus_frequency"] == pytest.approx(0.8 - 2 / 3)
    assert list(large["E_end"]) == ["mean_p_minus_frequency", "ci95"]
    # beside it, the base rate's on the same statements; the record given is left as it was
    both = ev.beside_base_rate(record, rows, base, 300, ev.SEED)
    theirs = ev.predictor_record(rows, base, 300, ev.SEED)
    assert list(both) == order
    for key in ("calibration_in_the_large", "calibration_all_statements"):
        for event in EVENT_KEYS:
            assert "base_rate" not in record[key][event]
            assert both[key][event] == record[key][event] | {"base_rate": theirs[key][event]}
            assert list(both[key][event])[-1] == "base_rate"
    assert both["calibration_all_statements"]["E_end"]["base_rate"]["least"] == pytest.approx(
        0.3 - 3 / 6
    )
    assert both["calibration_in_the_large"]["E_end90"]["base_rate"][
        "mean_p_minus_frequency"
    ] == pytest.approx(0.5 - 2 / 3)
    rest = [key for key in order if not key.startswith("calibration_")]
    assert {key: both[key] for key in rest} == {key: record[key] for key in rest}
    # without other draws given, the registered ones (on statements whose intervals move with
    # the draws)
    rows, pred, base, _ = thirty()
    registered = ev.calibration_scores(rows, base, ev.DRAWS, ev.SEED)
    assert ev.calibration_scores(rows, base) == registered
    assert ev.calibration_scores(rows, base, 300, ev.SEED) != registered
    assert ev.calibration_scores(rows, base, ev.DRAWS, ev.SEED + 1) != registered
    record = ev.predictor_record(rows, pred)
    assert {key: record[key] for key in registered} == ev.calibration_scores(rows, pred)
    again = ev.beside_base_rate(record, rows, base)
    for key, events in registered.items():
        for event in EVENT_KEYS:
            assert again[key][event]["base_rate"] == events[event]
    fewer = ev.beside_base_rate(record, rows, base, 300, ev.SEED)["calibration_all_statements"]
    assert fewer["E_end"]["base_rate"] != registered["calibration_all_statements"]["E_end"]
    # no scoreable statement: the count alone, with nothing to stand beside
    open_rows = item_rows([None, 0], [1, None])
    empty = ev.predictor_record(open_rows, stated(open_rows, 0.7), 300, ev.SEED)
    assert empty == {"scoreable_statements": 0}
    assert ev.beside_base_rate(empty, open_rows, stated(open_rows, 0.3), 300, ev.SEED) == empty


def small_study(switched: Sequence[str] = (LLAMA,)) -> tuple[ev.Study, pd.DataFrame]:
    """A study built by hand, as ``evaluate.evaluate`` takes it. 160 statements in 16 episodes
    of ten: eight episodes dated before the cutoff days of both primaries and eight after the
    first primary's alone.

    * Before: in each episode ``E_end`` is yes on 5 and no on 5; ``E_end90`` yes on 8, no on 2.
    * After: in each episode ``E_end`` is yes on 2, no on 6, undetermined on 2; ``E_end90`` yes
      on 4, no on 4 and undetermined on the same 2.
    * The base rate says 0.2 before and 0.6 after for ``E_end`` (0.5 and 0.7 for ``E_end90``)
      on average. By episode it adds 0, 1, -1, 2, -2, 3, -3 and 0 times 0.0004 in each period,
      which leaves the two means as they are and lets its intervals move with the draws.
    * Condition (a) of the first primary says 0.7 (0.8); its answers failed on the first
      episode before and on the first episode after, where it holds the base rate's output
      (0.2 and 0.6, and 0.5 and 0.7: those two episodes add nothing).
    * Condition (a) of the second primary says 0.41 on average (0.8), from 0.407 in the first
      episode to 0.413 in the last in equal steps, so that no two episodes are alike. All its
      answers parsed.
    * A primary of ``switched`` has probe medians on the midpoint of every bracket, so that it
      beats the base rate and is evaluated on its slice; the other's are the base rate's."""
    index = [f"s{k:03d}" for k in range(160)]
    late, spot = np.arange(160) >= 80, np.arange(160) % 10
    y_a = np.where(late, np.where(spot < 2, 1.0, np.where(spot < 8, 0.0, np.nan)), spot < 5)
    y_b = np.where(late, np.where(spot < 4, 1.0, np.where(spot < 8, 0.0, np.nan)), spot < 8)
    rows = pd.DataFrame(
        {
            "episode_id": [f"e{k // 10:02d}" for k in range(160)],
            "company": [f"c{k % 3}" for k in range(160)],
            "y_a": y_a,
            "y_b": y_b,
            "scoreable": ~np.isnan(y_a),
            "ttr_kind": "interval",
            "ttr_lower": 40.0,
            "ttr_upper": 60.0,
            "ttr_mid": 50.0,
        },
        index=index,
    )
    first = pd.DataFrame(
        {
            "event_date": np.where(late, "2024-06-01", "2023-06-01"),
            "form": "month_year",
            "delayed_entry": "False",
        },
        index=index,
    )
    predictions = {
        name: stated(rows, 0.3 + 0.01 * k, 0.5 + 0.01 * k) for k, name in enumerate(G.PREDICTORS)
    }
    episode = np.arange(160) // 10
    step = 0.0004 * np.array([0, 1, -1, 2, -2, 3, -3, 0])[episode % 8]
    base = stated(rows, np.where(late, 0.6, 0.2) + step, np.where(late, 0.7, 0.5) + step)
    predictions["base_rate"] = base
    kept = pd.Series(episode % 8 != 0, index=index)  # all but the first episode of each period
    parsed = {}
    for model, p_a in ((LLAMA, 0.7), (DEEPSEEK, 0.41 + 0.0004 * (episode - 7.5))):
        for condition in ev.CONDITIONS:
            answers = stated(rows, p_a, 0.8) if condition == "a" else stated(rows, 0.4, 0.6)
            name = f"{model}:{condition}"
            parsed[name] = everyone(rows)
            if name == f"{LLAMA}:a":
                answers, parsed[name] = answers.where(kept, base, axis=0), kept
            predictions[name] = answers
    probe_ids = index[::2]
    probe = {"base_rate": stated(rows, 0.5).loc[probe_ids]}
    for model in rd.PRIMARIES:
        median = 50.0 if model in switched else 100.0
        probe[model] = probe["base_rate"].assign(q50=median)
    held = ev.Study(
        first=first,
        probe_ids=probe_ids,
        predictions=predictions,
        parsed=parsed,
        probe=probe,
        selection=dict.fromkeys(rd.PRIMARIES, "b"),
        comparator="base_rate",
        runs={},
        not_evaluable={},
        refit={},
    )
    return held, rows


def full_report(report: dict[str, Any]) -> dict[str, Any]:
    """The results of ``evaluate.evaluate`` as the table and the printout read them."""
    return {"registered": ev.registered_record(), "h3": {"comparator": "base_rate"}, **report}


def criterion_line(model: str, entry: dict[str, Any]) -> str:
    """The line of the table and of the printout on the criterion of one primary, written out
    from the entry of the result file."""
    first, second = events_of(entry)
    met = {True: "part met", False: "part not met"}

    def shown(pair: list[float]) -> str:
        return f"[{pair[0]:.4f}, {pair[1]:.4f}]"

    return (
        f"Overconfidence of condition (a), {model}: reading {entry['reading']} of 5: "
        f"{entry['reading_in_words']}. P(E_end) on {entry['items']} ({entry['statements']} "
        f"statements in {entry['episodes']} episodes, {first['undetermined']} with E_end "
        f"undetermined): mean {first['mean_p']:.4f}. Against outcomes: least value of "
        f"calibration in the large {first['least']:.4f} {shown(first['least_ci95'])} (every "
        f"undetermined E_end counted as yes: frequency {first['largest_frequency']:.4f}), "
        f"greatest {first['greatest']:.4f} {shown(first['greatest_ci95'])} (counted as no: "
        f"frequency {first['smallest_frequency']:.4f}); {met[first['met']]}. Against the base "
        f"rate (mean P(E_end) {second['mean_p_base_rate']:.4f}): difference "
        f"{second['difference']:.4f} {shown(second['ci95'])}; {met[second['met']]}."
    )


def test_the_criterion_of_a_switched_primary_is_read_on_its_slice() -> None:
    """The item set the probe fixed holds the criterion, for the model and for the base rate:
    the first primary is switched to its slice of 80 statements, where the base rate says 0.6
    and not the 0.4 it says over all 160; the second stays on every eligible statement."""
    held, rows = small_study()
    report = ev.evaluate(held, rows, {}, "percentile", draws=300)
    sets = report["item_sets"]
    assert sets[LLAMA]["items"] == ev.SLICE_ITEMS and sets[DEEPSEEK]["items"] == ev.ALL_ITEMS
    over = report["secondaries"]["overconfidence_of_condition_a"]
    assert list(over) == [LLAMA, DEEPSEEK]
    for entry in over.values():
        assert list(entry) == ["items", *CRITERION_KEYS]
        for block in (entry, entry["parsed_only"]):
            assert list(block["against_outcomes"]) == EVENT_KEYS
            assert list(block["against_base_rate"]) == EVENT_KEYS
            for event in EVENT_KEYS:
                outcomes, no_text = events_of(block, event)
                assert list(outcomes) == [*LIMIT_KEYS, "met", "base_rate"]
                assert list(outcomes["base_rate"]) == LIMIT_KEYS and list(no_text) == [
                    *GAP_KEYS,
                    "met",
                ]
        assert list(entry["scoreable"]) == ["statements", "episodes", *EVENT_KEYS]
        assert list(entry["parsed_only"]) == ["not_parsed", *PART_KEYS]
        assert list(entry["coverage_80"]) == [*COVERAGE_KEYS, "base_rate"]
        assert list(entry["coverage_80"]["base_rate"]) == COVERAGE_KEYS
        assert entry["criterion"] == ev.OVERCONFIDENCE_CRITERION
    # The first primary on its slice: 80 statements in 8 episodes, 16 yes and 16 undetermined,
    # so the largest frequency is 32 / 80 = 0.4 and the smallest 16 / 80 = 0.2. Its ten failed
    # answers hold the base rate's 0.6: mean P(E_end) (70 * 0.7 + 10 * 0.6) / 80 = 0.6875.
    mine = over[LLAMA]
    outcomes, no_text = events_of(mine)
    assert (mine["items"], mine["statements"], mine["episodes"]) == (ev.SLICE_ITEMS, 80, 8)
    assert outcomes["undetermined"] == 16
    assert outcomes["largest_frequency"] == pytest.approx(0.4)
    assert outcomes["smallest_frequency"] == pytest.approx(0.2)
    assert outcomes["mean_p"] == pytest.approx(0.6875)
    assert outcomes["least"] == pytest.approx(0.6875 - 0.4)
    assert outcomes["greatest"] == pytest.approx(0.6875 - 0.2)
    # the base rate on the same 80 statements says 0.6: least 0.2, greatest 0.4. Over all 160
    # it says (80 * 0.2 + 80 * 0.6) / 160 = 0.4 against frequencies of 0.45 and 0.35.
    assert outcomes["base_rate"]["mean_p"] == pytest.approx(0.6) == no_text["mean_p_base_rate"]
    assert outcomes["base_rate"]["least"] == pytest.approx(0.2)
    assert outcomes["base_rate"]["greatest"] == pytest.approx(0.4)
    assert no_text["difference"] == pytest.approx(0.6875 - 0.6)
    assert (outcomes["met"], no_text["met"], mine["reading"], mine["met"]) == (True, True, 2, True)
    # the intervals are those of the draws the evaluation was given, on the slice's episodes
    part = rows[rows.index >= "s080"]
    clusters = list(part["episode_id"])
    p_a = held.predictions[f"{LLAMA}:a"].loc[part.index, "p_a"]
    limits = ev.calibration_limits(p_a, part["y_a"], clusters, 300, ev.SEED)
    assert {key: outcomes[key] for key in LIMIT_KEYS} == limits
    assert limits["least_ci95"][0] > 0 and limits["least_ci95"][0] < limits["least_ci95"][1]
    base_p = held.predictions["base_rate"].loc[part.index, "p_a"]
    gap = ev.probability_gap(p_a, base_p, clusters, 300, ev.SEED)
    assert {key: no_text[key] for key in GAP_KEYS} == gap and gap["ci95"][0] > 0
    # E_end90 beside it: yes on 32 and undetermined on 16 of 80; mean (70 * 0.8 + 10 * 0.7) / 80
    later, apart = events_of(mine, "E_end90")
    assert later["mean_p"] == pytest.approx(0.7875) and later["undetermined"] == 16
    assert later["least"] == pytest.approx(0.7875 - 48 / 80)
    assert later["greatest"] == pytest.approx(0.7875 - 32 / 80)
    assert apart["mean_p_base_rate"] == pytest.approx(0.7)
    assert apart["difference"] == pytest.approx(0.0875)
    # the answers that parsed: 70 of the slice (the ten failed answers before the cutoff are
    # not in the item set). 0.7 against 28 / 70 and 14 / 70, and against the base rate's 0.6.
    kept = mine["parsed_only"]
    assert (kept["not_parsed"], kept["statements"], kept["episodes"]) == (10, 70, 7)
    outcomes, no_text = events_of(kept)
    assert outcomes["mean_p"] == pytest.approx(0.7) and outcomes["undetermined"] == 14
    assert outcomes["least"] == pytest.approx(0.7 - 0.4)
    assert outcomes["greatest"] == pytest.approx(0.7 - 0.2)
    assert outcomes["base_rate"]["least"] == pytest.approx(0.2)
    assert no_text["difference"] == pytest.approx(0.1) and no_text["met"] is True
    # the scoreable statements of the slice: 64, with E_end yes on 16; mean P(E_end)
    # (56 * 0.7 + 8 * 0.6) / 64 = 0.6875 again, against 0.25; the base rate 0.6 - 0.25
    scoreable = mine["scoreable"]
    assert (scoreable["statements"], scoreable["episodes"]) == (64, 8)
    assert scoreable["E_end"]["mean_p_minus_frequency"] == pytest.approx(0.6875 - 0.25)
    assert scoreable["E_end"]["base_rate"]["mean_p_minus_frequency"] == pytest.approx(0.35)
    assert scoreable["E_end"]["against_base_rate"]["difference"] == pytest.approx(0.0875)
    assert scoreable["E_end"]["against_base_rate"]["mean_p_base_rate"] == pytest.approx(0.6)
    # it is the calibration in the large of the predictor's own record, which is on the slice
    record = report["losses"][f"{LLAMA}:a"]
    assert record["statements"] == 80 and record["scoreable_statements"] == 64
    for event in EVENT_KEYS:
        large = record["calibration_in_the_large"][event]
        assert list(large) == ["mean_p_minus_frequency", "ci95", "base_rate"]
        for key in ("mean_p_minus_frequency", "ci95"):
            assert scoreable[event][key] == large[key]
            assert scoreable[event]["base_rate"][key] == large["base_rate"][key]
        everywhere = record["calibration_all_statements"][event]
        assert list(everywhere) == [*LIMIT_KEYS, "base_rate"]
        outcomes = mine["against_outcomes"][event]
        assert everywhere == {key: outcomes[key] for key in [*LIMIT_KEYS, "base_rate"]}
    assert mine["coverage_80"] == record["coverage_80"] | {
        "base_rate": ev.coverage80(held.predictions["base_rate"].loc[part.index], part)
    }
    # every condition of the switched primary has the base rate of its slice beside it
    for condition in ev.CONDITIONS:
        beside = report["losses"][f"{LLAMA}:{condition}"]["calibration_all_statements"]["E_end"]
        assert beside["base_rate"]["mean_p"] == pytest.approx(0.6)
        assert beside["base_rate"] == mine["against_outcomes"]["E_end"]["base_rate"]
    # The second primary on every eligible statement: 160 in 16 episodes, 56 yes and 16
    # undetermined, so the largest frequency is 72 / 160 = 0.45 and the smallest 0.35. It says
    # 0.41 on average: least -0.04, greatest 0.06; the base rate says 0.4 on average, a
    # difference of 0.01.
    other = over[DEEPSEEK]
    outcomes, no_text = events_of(other)
    assert (other["items"], other["statements"], other["episodes"]) == (ev.ALL_ITEMS, 160, 16)
    assert outcomes["mean_p"] == pytest.approx(0.41)
    assert outcomes["least"] == pytest.approx(0.41 - 0.45)
    assert outcomes["greatest"] == pytest.approx(0.41 - 0.35)
    assert no_text["mean_p_base_rate"] == pytest.approx(0.4)
    assert no_text["difference"] == pytest.approx(0.01)
    assert outcomes["base_rate"]["least"] == pytest.approx(0.4 - 0.45)
    # the intervals are on the draws and the seed the evaluation was given, not on others
    every = list(rows["episode_id"])
    said, base_all = held.predictions[f"{DEEPSEEK}:a"]["p_a"], held.predictions["base_rate"]["p_a"]
    wide = ev.calibration_limits(said, rows["y_a"], every, 300, ev.SEED)
    apart = ev.probability_gap(said, base_all, every, 300, ev.SEED)
    assert {key: outcomes[key] for key in LIMIT_KEYS} == wide
    assert {key: no_text[key] for key in GAP_KEYS} == apart
    for draws, seed in ((ev.DRAWS, ev.SEED), (300, ev.SEED + 1)):
        elsewhere = ev.calibration_limits(said, rows["y_a"], every, draws, seed)
        assert elsewhere["least_ci95"] != wide["least_ci95"]
        assert elsewhere["greatest_ci95"] != wide["greatest_ci95"]
        assert ev.probability_gap(said, base_all, every, draws, seed)["ci95"] != apart["ci95"]
    reseeded = ev.evaluate(held, rows, {}, "percentile", draws=300, seed=ev.SEED + 1)
    again = reseeded["secondaries"]["overconfidence_of_condition_a"][DEEPSEEK]
    elsewhere = ev.calibration_limits(said, rows["y_a"], every, 300, ev.SEED + 1)
    assert {key: events_of(again)[0][key] for key in LIMIT_KEYS} == elsewhere
    assert events_of(again)[1]["ci95"] != no_text["ci95"]
    assert again["scoreable"]["E_end"]["ci95"] != other["scoreable"]["E_end"]["ci95"]
    assert events_of(again["parsed_only"])[1]["ci95"] != events_of(other["parsed_only"])[1]["ci95"]
    moved = reseeded["losses"][f"{DEEPSEEK}:a"]["calibration_all_statements"]["E_end"]
    assert moved == elsewhere | {"base_rate": moved["base_rate"]}
    assert (
        moved["base_rate"] != report["losses"]["base_rate"]["calibration_all_statements"]["E_end"]
    )
    # its least value is below zero with an interval that excludes zero: that is no excess.
    # Its greatest value and its difference from the base rate have intervals that hold zero
    assert outcomes["least_ci95"][1] < 0 and outcomes["met"] is False
    assert outcomes["greatest_ci95"][0] < 0 < outcomes["greatest_ci95"][1]
    assert no_text["ci95"][0] < 0 < no_text["ci95"][1] and no_text["met"] is False
    assert (other["reading"], other["met"]) == (5, False)
    assert other["parsed_only"] == {"not_parsed": 0} | {key: other[key] for key in PART_KEYS}
    # the model-free predictors are scored on every eligible statement, with the base rate of
    # those statements beside them; the base rate's own record has nothing beside it
    losses = report["losses"]
    whole = losses["base_rate"]["calibration_all_statements"]["E_end"]
    assert list(whole) == LIMIT_KEYS and whole["mean_p"] == pytest.approx(0.4)
    assert whole == other["against_outcomes"]["E_end"]["base_rate"]
    assert list(losses["base_rate"]["calibration_in_the_large"]["E_end"]) == [
        "mean_p_minus_frequency",
        "ci95",
    ]
    for name in (*(n for n in G.PREDICTORS if n != "base_rate"), f"{DEEPSEEK}:b"):
        for key in ("calibration_all_statements", "calibration_in_the_large"):
            for event in EVENT_KEYS:
                assert losses[name][key][event]["base_rate"] == losses["base_rate"][key][event]
    # one line for each primary in the table and in the printout, after the probe lines
    full = full_report(report)
    table, printed = ev.markdown(full).splitlines(), ev.summary_lines(full)
    lines = [criterion_line(model, over[model]) for model in rd.PRIMARIES]
    assert table[-2:] == lines and table[-3].startswith(f"Probe, {DEEPSEEK}: ")
    assert printed[-2:] == [f"  {line}" for line in lines]
    assert lines[0].startswith(
        f"Overconfidence of condition (a), {LLAMA}: reading 2 of 5: the readings are "
        "overconfident relative to outcomes. P(E_end) on the post-cutoff slice (80 statements "
        "in 8 episodes, 16 with E_end undetermined): mean 0.6875. Against outcomes: least value "
        "of calibration in the large 0.2875 ["
    )
    assert "counted as yes: frequency 0.4000), greatest 0.4875 [" in lines[0]
    assert (
        "(counted as no: frequency 0.2000); part met. Against the base rate (mean P(E_end) "
        in lines[0]
    )
    assert "0.6000): difference 0.0875 [" in lines[0] and lines[0].endswith("]; part met.")
    assert lines[1].startswith(
        f"Overconfidence of condition (a), {DEEPSEEK}: reading 5 of 5: overconfidence was not "
        "detected, which does not say that the readings are calibrated. P(E_end) on every "
        "eligible statement (160 statements in 16 episodes, 16 with E_end undetermined): mean "
        "0.4100. Against outcomes: least value of calibration in the large -0.0400 ["
    )
    assert "greatest 0.0600 [" in lines[1] and "; part not met. Against the base rate" in lines[1]
    assert "(mean P(E_end) 0.4000): difference 0.0100 [" in lines[1]
    assert lines[1].endswith("]; part not met.")
    # the text of the result file holds the same entry
    written = json.loads(ev.report_text(full))["secondaries"]["overconfidence_of_condition_a"]
    assert list(written[LLAMA]) == ["items", *CRITERION_KEYS] and written[LLAMA]["reading"] == 2
    assert written[LLAMA]["met"] is True and written[DEEPSEEK]["met"] is False


def test_a_primary_without_an_item_set_has_no_reading() -> None:
    """The second primary beats the base rate in its probe and has no statement after its
    cutoff day: its tests are not evaluable, the criterion has no item set to be read on, and
    its line says so. The first primary is then read on every eligible statement."""
    held, rows = small_study(switched=(DEEPSEEK,))
    report = ev.evaluate(held, rows, {}, "percentile", draws=300)
    sets = report["item_sets"]
    assert sets[DEEPSEEK]["evaluable"] is False and sets[LLAMA]["items"] == ev.ALL_ITEMS
    over = report["secondaries"]["overconfidence_of_condition_a"]
    assert list(over) == [LLAMA] and over[LLAMA]["items"] == ev.ALL_ITEMS
    # on all 160 statements: 20 failed answers hold the base rate's 0.2 and 0.6, so the mean
    # is (140 * 0.7 + 10 * 0.2 + 10 * 0.6) / 160 = 0.6625 against the base rate's 0.4
    outcomes, no_text = events_of(over[LLAMA])
    assert (over[LLAMA]["statements"], over[LLAMA]["episodes"]) == (160, 16)
    assert outcomes["mean_p"] == pytest.approx(0.6625)
    assert outcomes["least"] == pytest.approx(0.6625 - 0.45)
    assert no_text["mean_p_base_rate"] == pytest.approx(0.4)
    assert over[LLAMA]["parsed_only"]["not_parsed"] == 20
    assert f"{DEEPSEEK}:a" not in report["losses"]
    full = full_report(report)
    why = sets[DEEPSEEK]["reason"]
    assert why.startswith("the probe beat the base rate and the post-cutoff slice holds fewer")
    line = f"Overconfidence of condition (a), {DEEPSEEK}: no reading ({why})."
    table, printed = ev.markdown(full).splitlines(), ev.summary_lines(full)
    assert table[-2:] == [criterion_line(LLAMA, over[LLAMA]), line]
    assert printed[-2:] == [f"  {criterion_line(LLAMA, over[LLAMA])}", f"  {line}"]


def test_an_item_set_without_a_scoreable_statement_still_has_its_reading() -> None:
    """``E_end90`` is undetermined on every statement and ``E_end`` is as it was: no statement
    is scoreable and no test is evaluable. The criterion uses no scoreable set, so each primary
    with an item set has its entry and its line all the same."""
    held, rows = small_study(switched=())
    rows = rows.assign(y_b=np.nan, scoreable=False)
    report = ev.evaluate(held, rows, {}, "percentile", draws=300)
    assert report["items"]["scoreable_statements"] == 0
    assert not [entry for entry in report["family"] if entry["evaluable"]]
    assert {sets["items"] for sets in report["item_sets"].values()} == {ev.ALL_ITEMS}
    over = report["secondaries"]["overconfidence_of_condition_a"]
    assert list(over) == [LLAMA, DEEPSEEK]
    for model, reading in ((LLAMA, 2), (DEEPSEEK, 5)):
        entry = over[model]
        assert list(entry) == ["items", *CRITERION_KEYS]
        assert (entry["statements"], entry["episodes"], entry["reading"]) == (160, 16, reading)
        # nothing on the scoreable statements but their number, here and in the model's record
        assert entry["scoreable"] == {"statements": 0, "episodes": 0}
        assert report["losses"][f"{model}:a"] == {"scoreable_statements": 0}
        # E_end90 beside it: open everywhere, so its two limits are the mean minus one and the
        # mean itself
        later = events_of(entry, "E_end90")[0]
        assert later["undetermined"] == 160
        assert (later["largest_frequency"], later["smallest_frequency"]) == (1.0, 0.0)
        assert later["least"] == pytest.approx(later["mean_p"] - 1)
        assert later["greatest"] == pytest.approx(later["mean_p"])
    # E_end on all 160 statements, as with the scoreable ones in place: 0.6625 for the first
    # primary against a largest frequency of 0.45 and the base rate's 0.4
    outcomes, no_text = events_of(over[LLAMA])
    assert outcomes["least"] == pytest.approx(0.6625 - 0.45) and outcomes["met"] is True
    assert no_text["difference"] == pytest.approx(0.2625) and no_text["met"] is True
    full = full_report(report)
    table, printed = ev.markdown(full).splitlines(), ev.summary_lines(full)
    lines = [criterion_line(model, over[model]) for model in rd.PRIMARIES]
    assert table[-2:] == lines and printed[-2:] == [f"  {line}" for line in lines]
    assert sum(line.startswith("Overconfidence of ") for line in table) == 2
    assert not [line for line in table + printed if "no reading" in line]
    written = json.loads(ev.report_text(full))["secondaries"]["overconfidence_of_condition_a"]
    assert [written[model]["reading"] for model in rd.PRIMARIES] == [2, 5]


def test_a_primary_whose_tests_are_not_evaluable_has_no_reading_of_the_criterion() -> None:
    """The first part of the criterion uses no scoreable set, and the criterion is still not
    read for a primary without an item set: one whose slice holds many statements and fewer
    than 50 scoreable ones, and one whose probe could not be tested."""
    # The first primary is switched to its slice of 80 statements. E_end90 is left open on
    # every statement of the slice but the first four of each episode: E_end is determined on
    # 64 of the 80 as before, and 32 are scoreable.
    held, rows = small_study()
    late = np.arange(160) >= 80
    left_open = late & (np.arange(160) % 10 >= 4)
    rows = rows.assign(y_b=rows["y_b"].where(~left_open), scoreable=rows["scoreable"] & ~left_open)
    assert int(rows.loc[late, "y_a"].notna().sum()) == 64
    report = ev.evaluate(held, rows, {}, "percentile", draws=300)
    chosen = report["item_sets"][LLAMA]
    assert (chosen["slice_statements"], chosen["slice_scoreable"]) == (80, 32)
    assert chosen["switched"] is True and chosen["evaluable"] is False and "items" not in chosen
    why = "the probe beat the base rate and the post-cutoff slice holds fewer than 50 scoreable"
    assert chosen["reason"] == f"{why} statements"
    over = report["secondaries"]["overconfidence_of_condition_a"]
    assert list(over) == [DEEPSEEK] and over[DEEPSEEK]["items"] == ev.ALL_ITEMS
    full = full_report(report)
    line = f"Overconfidence of condition (a), {LLAMA}: no reading ({chosen['reason']})."
    lines = [line, criterion_line(DEEPSEEK, over[DEEPSEEK])]
    assert ev.markdown(full).splitlines()[-2:] == lines
    assert ev.summary_lines(full)[-2:] == [f"  {line}" for line in lines]
    # every statement in one episode: no probe can be tested, no switch is decided, and neither
    # primary has an item set
    held, rows = small_study(switched=())
    report = ev.evaluate(held, rows.assign(episode_id="e00"), {}, "percentile", draws=300)
    assert [sets["evaluable"] for sets in report["item_sets"].values()] == [False, False]
    assert report["secondaries"]["overconfidence_of_condition_a"] == {}
    full = full_report(report)
    lines = [
        f"Overconfidence of condition (a), {model}: no reading (the probe could not be tested)."
        for model in rd.PRIMARIES
    ]
    assert ev.markdown(full).splitlines()[-2:] == lines
    assert ev.summary_lines(full)[-2:] == [f"  {line}" for line in lines]


def test_one_failed_answer_is_not_given_back_by_the_result_file() -> None:
    """One answer of condition (a) failed, on a statement whose ``E_end`` is yes (s080) or
    undetermined (s088). Beside the criterion over all 160 statements, the figures over the 159
    answers that parsed would give that statement's two horizon events by subtraction: the
    result file holds their counts alone, and its figures on outcomes are the same whichever
    statement it was."""
    seen = {}
    for failed in ("s080", "s088"):
        held, rows = small_study(switched=())
        name = f"{LLAMA}:a"
        base = held.predictions["base_rate"]
        parsed = everyone(rows)
        parsed[failed] = False
        held.predictions[name] = stated(rows, 0.7, 0.8).where(parsed, base, axis=0)
        held.parsed[name] = parsed
        full = full_report(ev.evaluate(held, rows, {}, "percentile", draws=300))
        written = json.loads(ev.report_text(full))
        entry = written["secondaries"]["overconfidence_of_condition_a"][LLAMA]
        assert list(entry) == ["items", *CRITERION_KEYS]
        assert (entry["statements"], entry["reading"]) == (160, 2)
        assert entry["parsed_only"] == {
            "not_parsed": 1,
            "statements": 159,
            "episodes": 16,
            "withheld": True,
        }
        # the second primary, all of whose answers parsed, keeps its figures
        other = written["secondaries"]["overconfidence_of_condition_a"][DEEPSEEK]
        assert list(other["parsed_only"]) == ["not_parsed", *PART_KEYS]
        assert criterion_line(LLAMA, entry) in ev.markdown(full).splitlines()
        seen[failed] = entry
    assert rows.loc["s080", "y_a"] == 1 and np.isnan(rows.loc["s088", "y_a"])
    for event in EVENT_KEYS:
        first, second = (events_of(seen[failed], event)[0] for failed in seen)
        for key in ("undetermined", "largest_frequency", "smallest_frequency"):
            assert first[key] == second[key]
            assert first["base_rate"][key] == second["base_rate"][key]


def test_the_result_file_holds_the_criterion_for_each_primary(
    study: SimpleNamespace, base: SimpleNamespace, opened: SimpleNamespace
) -> None:
    """The criterion on the synthetic study, against the scripted answers and the synthetic
    outcomes: no primary is switched, so each is read on the 320 eligible statements."""
    y = truth(study)
    over = base.report["secondaries"]["overconfidence_of_condition_a"]
    assert list(over) == list(rd.PRIMARIES)
    base_p = opened.study.predictions["base_rate"]
    for model in rd.PRIMARIES:
        entry = over[model]
        assert list(entry) == ["items", *CRITERION_KEYS]
        assert (entry["items"], entry["statements"], entry["episodes"]) == (ev.ALL_ITEMS, 320, 40)
        pred = opened.study.predictions[f"{model}:a"]
        parsed = opened.study.parsed[f"{model}:a"]
        failed = [i for i in y.index if fails(model, "a", i) == 2]
        assert entry["parsed_only"]["not_parsed"] == len(failed) == int((~parsed).sum())
        assert entry["parsed_only"]["statements"] == 320 - len(failed)
        for block, ids in ((entry, y.index), (entry["parsed_only"], parsed.index[parsed])):
            for event, p, e in (("E_end", "p_a", "y_a"), ("E_end90", "p_b", "y_b")):
                outcomes, no_text = events_of(block, event)
                mine, theirs, seen = pred.loc[ids, p], base_p.loc[ids, p], y.loc[ids, e]
                assert outcomes["undetermined"] == int(seen.isna().sum())
                assert outcomes["mean_p"] == pytest.approx(float(mine.mean()), abs=1e-6)
                assert outcomes["least"] == pytest.approx(
                    float((mine - seen.fillna(1.0)).mean()), abs=1e-6
                )
                assert outcomes["greatest"] == pytest.approx(
                    float((mine - seen.fillna(0.0)).mean()), abs=1e-6
                )
                assert outcomes["base_rate"]["least"] == pytest.approx(
                    float((theirs - seen.fillna(1.0)).mean()), abs=1e-6
                )
                assert no_text["difference"] == pytest.approx(
                    float((mine - theirs).mean()), abs=1e-6
                )
                assert no_text["mean_p_base_rate"] == pytest.approx(float(theirs.mean()), abs=1e-6)
                assert outcomes["least_ci95"][0] < outcomes["least"] < outcomes["least_ci95"][1]
                assert outcomes["met"] is (outcomes["least_ci95"][0] > 0)
                assert no_text["met"] is (no_text["ci95"][0] > 0)
        outcomes, no_text = events_of(entry)
        assert entry["reading"] == ev.overconfidence_reading(outcomes, no_text)
        assert entry["reading_in_words"] == ev.OVERCONFIDENCE_READINGS[entry["reading"]]
        assert entry["met"] is (outcomes["met"] and no_text["met"])
        # the registered draws: 10,000 by shortage episode, seed 20261001
        limits = ev.calibration_limits(
            pred.loc[y.index, "p_a"], y["y_a"], list(y["episode"]), ev.DRAWS, ev.SEED
        )
        assert outcomes["least_ci95"] == pytest.approx(limits["least_ci95"], abs=1e-6)
        assert outcomes["greatest_ci95"] == pytest.approx(limits["greatest_ci95"], abs=1e-6)
        # beside it: the scoreable statements, as in the predictor's own record
        record = base.report["losses"][f"{model}:a"]
        for event in EVENT_KEYS:
            large = record["calibration_in_the_large"][event]
            assert (
                entry["scoreable"][event]["mean_p_minus_frequency"]
                == large["mean_p_minus_frequency"]
            )
            assert entry["scoreable"][event]["ci95"] == large["ci95"]
            assert entry["scoreable"][event]["base_rate"] == large["base_rate"]
            everywhere = record["calibration_all_statements"][event]
            assert everywhere == {
                key: entry["against_outcomes"][event][key] for key in [*LIMIT_KEYS, "base_rate"]
            }
        assert entry["scoreable"]["statements"] == record["scoreable_statements"]
        assert {key: entry["coverage_80"][key] for key in COVERAGE_KEYS} == record["coverage_80"]
        assert (
            entry["coverage_80"]["base_rate"] == base.report["losses"]["base_rate"]["coverage_80"]
        )
        line = criterion_line(model, entry)
        assert base.table.splitlines().count(line) == 1 and f"  {line}" in base.printed.splitlines()
    # condition (a) of the first primary says 0.9 where it parsed, far above every frequency
    # the captures allow and above the base rate: overconfident relative to outcomes
    assert (over[LLAMA]["reading"], over[LLAMA]["met"]) == (2, True)
    assert events_of(over[LLAMA])[0]["least_ci95"][0] > 0.2
    # condition (a) of the second says about 0.3, inside the frequencies the captures allow
    # and below the base rate, with an interval that excludes zero on the wrong side: neither
    # part is met, and nothing says that it is underconfident either
    outcomes, no_text = events_of(over[DEEPSEEK])
    assert outcomes["least"] < 0 < outcomes["greatest"] and outcomes["greatest_ci95"][0] < 0
    assert no_text["difference"] < 0 and no_text["ci95"][1] < 0 and no_text["met"] is False
    assert (over[DEEPSEEK]["reading"], over[DEEPSEEK]["met"]) == (5, False)
    assert sum(line.startswith("Overconfidence of ") for line in base.table.splitlines()) == 2


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
    # the contrast without that one statement is withheld: beside the contrast on every
    # scoreable statement it would give the loss difference, and so the events, of the one
    assert entry["both_sides_parsed"] == {
        "statements": entry["statements"] - 1,
        "episodes": entry["both_sides_parsed"]["episodes"],
        "withheld": True,
    }
    # a contrast that leaves no statement out, or leaves out five or more, is given
    whole = entry_of(base.report, "H1", DEEPSEEK)["both_sides_parsed"]
    assert "withheld" not in whole and whole["delta"] is not None
    planted = entry_of(base.report, "H1", LLAMA)
    left_out = planted["statements"] - planted["both_sides_parsed"]["statements"]
    assert left_out >= ev.MIN_SHOWN and "withheld" not in planted["both_sides_parsed"]
    assert not ev.few(0) and ev.few(1) and ev.few(ev.MIN_SHOWN - 1) and not ev.few(ev.MIN_SHOWN)


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
        assert record["p"] == record["p_values"][SOURCE]["one_sided"]
        # the probe is a rule on a p-value: its intervals are descriptions
        assert record["interval_method"] == "percentile"
        assert record["ci95"] == record["percentile"]["ci95"]
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
    opened: SimpleNamespace,
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
    # the counts beside H2 are of the statements of the test, which are fewer than before
    pair = [opened.study.predictions[name] for name in ("rules_plus_slip", f"{LLAMA}:c")]
    apart = counts_apart((brier(pair[0], y) - brier(pair[1], y)).loc[after.index], y["episode"])
    assert entry_of(report, "H2", LLAMA)["losses_differ"] == apart
    before = entry_of(base.report, "H2", LLAMA)["losses_differ"]
    assert 0 < apart["statements"] < before["statements"]
    assert counts_line(apart) in table and counts_line(before) not in table
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
    # the overconfidence criterion is read on the slice too, for the model and for the base
    # rate, whose mean probability there is not its mean over the eligible list
    over, before = (
        found["secondaries"]["overconfidence_of_condition_a"] for found in (report, base.report)
    )
    inside = y.index[y["day"] > "2023-12-31"]
    assert (over[LLAMA]["items"], over[LLAMA]["statements"]) == (ev.SLICE_ITEMS, len(inside))
    base_p = opened.study.predictions["base_rate"]["p_a"]
    assert abs(float(base_p.loc[inside].mean()) - float(base_p.mean())) > 0.001
    for block in (events_of(over[LLAMA])[1], events_of(over[LLAMA])[0]["base_rate"]):
        key = "mean_p_base_rate" if "mean_p_base_rate" in block else "mean_p"
        assert block[key] == pytest.approx(float(base_p.loc[inside].mean()), abs=1e-6)
    assert events_of(before[LLAMA])[1]["mean_p_base_rate"] == pytest.approx(
        float(base_p.mean()), abs=1e-6
    )
    assert over[DEEPSEEK] == before[DEEPSEEK] and over[DEEPSEEK]["items"] == ev.ALL_ITEMS
    assert criterion_line(LLAMA, over[LLAMA]) in table.splitlines()
    assert criterion_line(LLAMA, before[LLAMA]) not in table.splitlines()
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
    # no item set, no reading of the overconfidence criterion: the line says why
    assert list(report["secondaries"]["overconfidence_of_condition_a"]) == [LLAMA]
    line = f"Overconfidence of condition (a), {DEEPSEEK}: no reading ({chosen['reason']})."
    assert line in table.splitlines() and f"  {line}" in printed.splitlines()


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
    # its runs were not read: the overconfidence criterion is the other primary's alone
    assert list(report["secondaries"]["overconfidence_of_condition_a"]) == [LLAMA]
    assert sum(line.startswith("Overconfidence of ") for line in table.splitlines()) == 1


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
    # a hash given wrongly after its sixteenth character: the two are shown at the length of
    # the one given, so that they can be told apart (sixteen characters of each are the same)
    given = sha[:16] + ("0" if sha[16] != "0" else "1")
    why = refused(study, tmp_path, capsys, "--expect-baselines-sha256", given)
    assert f"their sha256 starts with {sha[:17]}, expected {given}" in why
    why = refused(study, tmp_path, capsys, "--expect-baselines-sha256", "0" * 16)
    assert f"their sha256 starts with {sha[:16]}, expected {'0' * 16}" in why
    # the same for the selection file of a primary
    model, _, chosen = study.selection_shas[0].partition("=")
    given = chosen[:30] + ("0" if chosen[30] != "0" else "1")
    hashes = [f"{model}={given}", study.selection_shas[1]]
    why = refused(study, tmp_path, capsys, expect_selection_sha256=hashes)
    assert "is not the selection file hashed at the freeze" in why
    assert f"(its sha256 starts with {chosen[:31]}, expected {given})" in why
    assert "the sealed file" not in sealed_unread


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
    # two lines beside H3 and two on the overconfidence criterion, one for each primary
    assert len(base.printed.splitlines()) == 2 + 6 + 2 + 2 + 1
    assert len(base.table.splitlines()) == 6 + 6 + 1 + 4 * 2


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
