"""Tests for :mod:`analysis.coling.launch`, with the harness's dry run and a scripted client only:
no call leaves the machine and no tmux server is started.

Every test runs behind the fixture ``sealed_off`` (as in ``test_read.py``): a network connection
or a key lookup fails the test, and the harness's repository is a folder that is not one. Live
lanes run the harness's own command line in this process, around a scripted SDK client, in a
temporary repository that carries the tags a test needs.

Usage (from the repository root)::

    python -m pytest analysis/coling/test_launch.py -p no:cacheprovider -q
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import socket
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import analysis.coling.launch as lp
import analysis.coling.read as rd
from collie.llm.client import EndpointConfig

RealClient = rd.RouteCheckedClient
OPENROUTER = tuple(m for m in rd.STUDY_MODELS if lp.lane_of(m) == "openrouter")
PINNED = {
    model: rd.Route(rd.ROUTES[model].model_id, "deepinfra/fp8", "fp8", (0.10, 0.30, "2026-10-01"))
    for model in OPENROUTER
}
ANSWER_MARK = "ZEBRA-ANSWER"
TEXT_MARK = "QUAGGA-NOTICE"
LITERAL_OK = json.dumps(
    {
        "statement_type": "recovery",
        "interval": "ABSTAIN",
        "certainty": "estimated",
        "stale": False,
        "quote": ANSWER_MARK,
    }
)
PREDICTIVE_OK = json.dumps(
    {
        "p_by_horizon_a": 0.3,
        "p_by_horizon_b": 0.6,
        "days_to_recovery": {"q10": 20, "q50": 80, "q80": 150, "q90": 200, "q95": 365},
    }
)
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
SIZES = {
    "dev_prompt": (3, "2021-03-02"),
    "dev_scoreable": (5, "2021-05-04"),
    "e3_eligible": (8, "2024-02-06"),
    "e3_tbd": (2, "2024-03-05"),
    "e3_silent": (2, "2024-04-09"),
    "e3_stale": (1, "2024-05-07"),
    "subset_probe": (3, "2024-02-06"),
    "subset_samples20": (2, "2024-02-06"),
    "subset_paraphrase": (2, "2024-02-06"),
    "subset_twobytwo": (2, "2024-02-06"),
    "literal_items": (3, "2026-02-03"),
    "e5_pairs": (2, "2021-06-01"),
}
"""The synthetic item files: items per file and their statement date (dev files in the train
period, the others in the test or late period)."""


@pytest.fixture(autouse=True)
def sealed_off(tmp_path_factory, monkeypatch) -> None:
    """What no test may do, made impossible for every test: open a network connection, read an
    API key, start the harness as a child process or a tmux server, or use the real repository."""

    def no_network(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")

    def no_key(self):
        raise AssertionError("a test tried to read an API key")

    def no_child(*args, **kwargs):
        raise AssertionError("a test tried to start the harness or tmux as a child process")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(EndpointConfig, "resolve_key", no_key)
    monkeypatch.setattr(lp, "harness_runner", no_child)
    monkeypatch.setattr(lp, "tmux_call", no_child)
    for name in list(os.environ):
        if name.endswith("_API_KEY") or name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(rd, "REPO", tmp_path_factory.mktemp("not-a-repository"))


def git(repo: Path, *args: str) -> None:
    quiet = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "gpg.format=openpgp"]
    quiet += ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    subprocess.run(["git", *quiet, *args], cwd=repo, check=True, capture_output=True, env=env)


def make_repo(path: Path, *tags: str) -> Path:
    """A temporary git repository with one commit and the given tags on it."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "-q", "--allow-empty", "-m", "one")
    for tag in tags:
        git(path, "tag", tag)
    return path


def item(stem: str, n: int, day: str) -> dict:
    row = {
        "item_id": f"{stem[:3]}{stem[-3:]}{n:03d}".replace("_", "x"),
        "generic_name": "Anagrelide Hydrochloride Capsules",
        "company_name": "Teva Pharmaceuticals",
        "presentation": f"{n + 1} MG 100 Capsules",
        "therapeutic_category": "Hematology",
        "initial_posting_date": "2019-11-22",
        "date_of_update": day,
    }
    if stem == "subset_probe":
        return row
    return row | {
        "type_of_update": "Reverified",
        "availability_information": f"Product on backorder {TEXT_MARK}",
        "related_information": "Expected recovery soon.",
        "reason_for_shortage": "Demand increase for the drug",
        "stated_end": f"{int(day[:4]) + (day[5:7] == '12')}-{int(day[5:7]) % 12 + 1:02d}-28",
        "form": "a month and year",
        "revision": "first",
    }


def item_ids(path: Path) -> list[str]:
    return [json.loads(line)["item_id"] for line in path.read_text().splitlines()]


def write_files(folder: Path, sizes: dict[str, tuple[int, str]] = SIZES) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for stem, (n, day) in sizes.items():
        rows = [item(stem, k, day) for k in range(n)]
        (folder / f"{stem}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (folder / "track_fit.json").write_text(json.dumps(TRACK, indent=1))
    both = TRACK | {"split": "fit+dev", "through": "2022-12-31"}
    (folder / "track_fit_dev.json").write_text(json.dumps(both, indent=1))
    return folder


def options_for(tmp_path: Path, **changes) -> dict:
    options = lp.default_options(tmp_path / "items")
    options |= {"out_root": str(tmp_path / "out"), "local_root": str(tmp_path / "local")}
    return options | changes


class ScriptedSDK:
    """Stands in for the SDK client inside the real :class:`rd.RouteCheckedClient`: it echoes
    the model it was asked for and answers by the kind of the prompt. ``reply`` may replace the
    answer (it gets the model and the prompt) or raise."""

    def __init__(self, reply=None) -> None:
        self.reply = reply
        self.tokens = (500, 60)
        self.calls: list[tuple[str, str]] = []
        self.chat = self.completions = self

    def create(self, **kwargs):
        model, prompt = kwargs["model"], kwargs["messages"][-1]["content"]
        self.calls.append((model, prompt))
        text = self.reply(model, prompt) if self.reply else None
        if text is None:
            text = LITERAL_OK if "statement_type" in prompt else PREDICTIVE_OK
        return SimpleNamespace(
            model=model,
            provider="DeepInfra",
            openrouter_metadata=None,
            usage=SimpleNamespace(
                prompt_tokens=self.tokens[0],
                completion_tokens=self.tokens[1],
                total_tokens=sum(self.tokens),
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        )


class Harness:
    """Runs a launcher command in this process, through the harness's own command line."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str], output: Path) -> int:
        assert list(command[1:3]) == ["-m", "analysis.coling.read"]
        self.commands.append(list(command))
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            code, said = rd.main(list(command[3:])), ""
        except SystemExit as exc:
            code, said = (exc.code, "") if isinstance(exc.code, int) else (1, str(exc.code))
        except Exception as exc:
            code, said = 1, f"{type(exc).__name__}: {exc}"
        with output.open("a", encoding="utf-8") as handle:
            handle.write(said + "\n")
        return code

    def runs(self) -> list[str]:
        """The run names of the live commands, in the order they were started."""
        return [c[c.index("--run-name") + 1] for c in self.commands if "--run-name" in c]


@pytest.fixture
def study(tmp_path: Path, monkeypatch) -> SimpleNamespace:
    """A study that is ready for every phase, with no network: the item files, a repository with
    both tags, six pinned routes, the pilot sentences settled, and a scripted client."""
    write_files(tmp_path / "items")
    repo = make_repo(tmp_path / "repo", rd.REGISTRATION_TAG, rd.F1_TAG)
    monkeypatch.setattr(rd, "REPO", repo)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": "", "D3": ""})
    sdk = ScriptedSDK()
    monkeypatch.setattr(
        rd,
        "RouteCheckedClient",
        lambda endpoint, served_as, **kw: RealClient(
            endpoint, served_as, route=kw["route"], sdk=sdk
        ),
    )
    plan = lp.make_plan(options_for(tmp_path))
    return SimpleNamespace(
        plan=plan, sdk=sdk, repo=repo, out=tmp_path / "out", items=tmp_path / "items"
    )


def log_rows(plan: dict, event: str | None = None) -> list[dict]:
    rows = lp.read_jsonl(lp.launch_dir(plan) / lp.RUN_LOG)
    return [row for row in rows if event is None or row["event"] == event]


def names(plan: dict, *args, **kwargs) -> list[str]:
    return [run["run"] for run in lp.select(plan, *args, **kwargs)]


PRIMARIES = list(rd.PRIMARIES)


def test_no_test_can_reach_a_key_the_network_a_child_process_or_the_real_repository() -> None:
    with pytest.raises(AssertionError, match="read an API key"):
        RealClient(rd.route_endpoint("gemini-3.8-flash"), ("gemini-3.8-flash",))
    with pytest.raises(AssertionError, match="network connection"):
        socket.create_connection(("example.invalid", 443), timeout=1)
    with pytest.raises(AssertionError, match="child process"):
        lp.tmux_call(["list-sessions"])
    with pytest.raises(AssertionError, match="child process"):
        lp.harness_runner(["python", "-m", "analysis.coling.read"], Path("nowhere"))
    checkout = Path(rd.__file__).resolve().parents[2]
    assert checkout != rd.REPO and checkout not in rd.REPO.parents
    assert len(rd.paid_call_refusals(["test"])) == 2


# --- the plan ---------------------------------------------------------------------------------


def test_the_launcher_has_a_rule_for_every_line_of_the_run_sheet(monkeypatch) -> None:
    lp.check_rules()
    # only the cost trial and the dev runs come before F1
    assert [phase for phase in lp.PHASES if phase not in lp.SEALED_PHASES] == ["trial", "dev"]
    checkout = Path(rd.__file__).resolve().parents[2]  # the default roots are the harness's
    assert (checkout / lp.OUT_ROOT, checkout / lp.LOCAL_ROOT) == (rd.OUT_ROOT, rd.LOCAL_ROOT)
    planned = set(lp.PARTS) | {"e6", "e3-paraphrases"}
    assert planned == {line.name for line in rd.RUN_SHEET}
    assert {spec.count for spec in lp.LISTS} == set(rd.SHEET_COUNTS)
    # the file stems are those the dataset builder writes, for the lists it writes: its item
    # lists and the cost-trial file, which holds what the launcher's limit would read
    from analysis.coling import dataset

    stems = {spec.stem for spec in lp.LISTS if spec.source == "dataset.py --items"}
    written = {"e3_eligible", "e3_tbd", "e3_silent", "e3_stale", "dev_scoreable", dataset.TRIAL}
    written |= {f"subset_{s.name}" for s in dataset.SUBSETS if s.name != "reference_check"}
    assert stems == written
    assert lp.LIST_BY_KEY["trial"].limit == dataset.TRIAL_SIZE == lp.LIST_BY_KEY["trial"].planned
    # the two lists that other modules write elsewhere say where, and how to name the file
    for key, place in (("e2", "out/audit/literal_items.jsonl"), ("e5", "out/e5/e5_pairs.jsonl")):
        assert place in lp.LIST_BY_KEY[key].source
        assert f"--items-file {key}=PATH" in lp.LIST_BY_KEY[key].source
    # a line the launcher does not know, or one whose calls per item moved, stops the plan
    extra = rd.SheetLine("e9", "E9", "literal-v1", "e2", rd.STUDY_MODELS)
    monkeypatch.setattr(rd, "RUN_SHEET", (*rd.RUN_SHEET, extra))
    with pytest.raises(SystemExit, match="no rule for: 'e9'"):
        lp.check_rules()
    moved = tuple(
        rd.SheetLine(**{**line.__dict__, "per_item": 4}) if line.name == "e4-2x2" else line
        for line in rd.RUN_SHEET[:-1]
    )
    monkeypatch.setattr(rd, "RUN_SHEET", moved)
    with pytest.raises(SystemExit, match=r"e4-2x2.*disagree"):
        lp.check_rules()


def test_plan_orders_the_runs_by_phase_lane_and_cost(study) -> None:
    plan, runs = study.plan, study.plan["runs"]
    assert [run["n"] for run in runs] == list(range(1, len(runs) + 1))
    keys = [(lp.PHASES.index(run["phase"]), lp.LANES.index(run["lane"])) for run in runs]
    assert keys == sorted(keys)
    for phase in lp.PHASES:
        for lane in lp.LANES:
            costs = [run["usd_typical"] for run in lp.select(plan, [phase], [lane])]
            assert costs == sorted(costs)  # cheapest first inside a phase and a lane
    assert all(rd._RUN_NAME.match(run["run"]) for run in runs)
    assert len({run["run"] for run in runs}) == len(runs)
    assert {run["lane"] for run in runs if run["model"] == "gemini-3.8-flash"} == {"google"}
    assert {run["lane"] for run in runs if run["model"] == "grok-4.20"} == {"xai"}
    assert {run["model"] for run in lp.select(plan, lanes=["openrouter"])} == set(OPENROUTER)
    # the phases hold what the plan says they hold
    by_phase = {phase: lp.select(plan, [phase]) for phase in lp.PHASES}
    assert {run["line"] for run in by_phase["trial"]} == {
        "trial-literal",
        "trial-literal-free",
        "trial-a",
        "trial-b",
        "trial-probe",
    }
    assert len(by_phase["trial"]) == 5 * 8 - 1  # gemini-3.8-flash has no probe to try
    assert {(r["line"], r["model"]) for r in by_phase["dev"]} == {
        (line, model) for line in ("dev-a", "dev-b", "dev-c") for model in rd.PRIMARIES
    }
    assert {(r["line"], r["model"]) for r in by_phase["confirmatory"]} == {
        (line, model) for line in lp.CONFIRMATORY_LINES for model in rd.PRIMARIES
    }
    assert {r["list"] for r in by_phase["confirmatory"]} == {"e3", "probe"}
    rest = by_phase["rest"]
    assert {r["line"] for r in rest if r["model"] == "gemini-3.8-flash"} == {
        "e2-literal",
        "e2-literal-free",
        "e3-a",
        "e3-b",
        "e3-c",
    }
    assert {r["model"] for r in rest if r["line"] == "e3-samples"} == set(rd.PRIMARIES)
    confirmatory = [r for r in rest if r["line"] in lp.CONFIRMATORY_LINES]
    assert confirmatory and not {r["model"] for r in confirmatory} & set(rd.PRIMARIES)
    # the calls of every model are those of the harness's sheet, less what is held back
    sheet = rd.run_sheet(plan["counts"])
    for model in rd.STUDY_MODELS:
        held = sum(r["calls"] for r in plan["reserved"] if r["model"] == model)
        calls = sum(run["calls"] for run in runs if run["model"] == model)
        assert calls + held == sheet["models"][model]["calls"]
    assert {r["line"] for r in plan["reserved"]} == {"e3-paraphrases"}  # not written yet


def test_plan_gives_every_run_the_flags_of_its_condition(study) -> None:
    plan = study.plan
    by_name = {run["run"]: run for run in plan["runs"]}
    for run in plan["runs"]:
        sealed = run["phase"] in lp.SEALED_PHASES
        assert run["allow_test_items"] == (sealed and run["list"] != "e5")
        needs = rd.TEMPLATES[run["template"]].needs_track
        assert run["track"] == (("fit+dev" if sealed else "fit") if needs else None)
        args = lp.harness_args(plan, run, "live")
        assert ("--allow-test-items" in args) == run["allow_test_items"]
        assert args[args.index("--spend-cap-usd") + 1] == f"{run['cap_usd']:.6f}"
        assert float(args[args.index("--spend-cap-usd") + 1]) == run["cap_usd"]
        assert "--allow-live" in args and "--dry-run" not in args
        dry = lp.harness_args(plan, run, "rehearsal")
        assert "--dry-run" in dry and not {"--allow-live", "--run-name"} & set(dry)
    cells = [by_name[f"e4-2x2-{cell}-llama-3.3-70b"] for cell in ("mask", "shift", "mask-shift")]
    assert [(c["mask_names"], c["shift_years"]) for c in cells] == [
        (True, 0),
        (False, 4),
        (True, 4),
    ]
    args = lp.harness_args(plan, cells[2], "live")
    assert "--mask-names" in args and args[args.index("--shift-years") + 1] == "4"
    samples = by_name["e3-samples-deepseek-v3"]
    assert (samples["samples"], samples["temperature"], samples["calls"]) == (20, 1.0, 40)
    args = lp.harness_args(plan, samples, "live")
    assert (
        args[args.index("--samples") + 1] == "20" and args[args.index("--temperature") + 1] == "1"
    )
    track = lp.harness_args(plan, by_name["dev-b-llama-3.3-70b"], "live")
    assert track[track.index("--track-record") + 1].endswith("track_fit.json")
    track = lp.harness_args(plan, by_name["e3-b-llama-3.3-70b"], "live")
    assert track[track.index("--track-record") + 1].endswith("track_fit_dev.json")
    assert {by_name[f"e3-{k}-c-llama-3.3-70b"]["list"] for k in ("tbd", "silent", "stale")} == {
        "tbd",
        "silent",
        "stale",
    }


def test_trial_reads_the_first_twenty_of_a_longer_file_and_dev_lists_stay_in_the_train_period(
    tmp_path: Path,
) -> None:
    write_files(tmp_path / "items", SIZES | {"dev_prompt": (60, "2021-03-02")})
    plan = lp.make_plan(options_for(tmp_path))
    trial = lp.select(plan, ["trial"])
    assert {run["limit"] for run in trial} == {20} and {run["calls"] for run in trial} == {20}
    assert plan["lists"]["trial"]["items"] == 20 and plan["lists"]["trial"]["items_in_file"] == 60
    first = item_ids(tmp_path / "items" / "dev_prompt.jsonl")
    assert trial[0]["item_ids_sha256"] == rd._ids_sha256(first[:20])
    args = lp.harness_args(plan, trial[0], "live")
    assert args[args.index("--limit") + 1] == "20" and "--allow-test-items" not in args
    write_files(tmp_path / "items", SIZES | {"dev_scoreable": (5, "2023-01-01")})
    with pytest.raises(SystemExit, match=r"train-period items only.*'dev'"):
        lp.make_plan(options_for(tmp_path))


def units(runs: list[dict]) -> int:
    return sum(round(run["cap_usd"] * lp.MICRO) for run in runs)


def test_caps_of_a_models_runs_sum_to_its_cap(study, tmp_path: Path, monkeypatch) -> None:
    assert lp.split_units(10, [1, 1, 1]) == [4, 3, 3] and lp.split_units(7, [0, 5, 2]) == [0, 5, 2]
    assert sum(lp.split_units(1_000_003, [2585, 373, 550, 15])) == 1_000_003
    with pytest.raises(ValueError):
        lp.split_units(5, [0, 0])
    plan = study.plan
    sheet = rd.run_sheet(plan["counts"])
    for model in rd.STUDY_MODELS:
        runs = [run for run in plan["runs"] if run["model"] == model]
        held = [r for r in plan["reserved"] if r["model"] == model]
        assert all(run["cap_usd"] > 0 for run in runs)
        assert units(runs) + units(held) == round(rd.MODEL_CAPS_USD[model] * lp.MICRO)
        assert plan["models"][model]["run_caps_usd"] * lp.MICRO == pytest.approx(units(runs))
        # every line keeps the harness's suggested cap; the largest also takes the rounding
        lines = sheet["models"][model]["lines"]
        top = max(lines, key=lambda name: lines[name]["cap_usd"])
        for name, entry in lines.items():
            got = units([r for r in [*runs, *held] if r["line"] == name])
            spare = got - round(entry["cap_usd"] * lp.MICRO)
            assert spare == 0 or (name == top and 0 < spare < lp.MICRO // 100)
        # the harness's ledger takes the caps of all the model's runs at once
        for run in runs:
            rd.declare_run(study.out, run=run["run"], model=model, cap_usd=run["cap_usd"])
    assert sum(units(lp.select(plan, models=[m])) for m in rd.STUDY_MODELS) <= 169 * lp.MICRO
    # a secondary line is split over its three lists in proportion to their items
    parts = {r["list"]: r for r in plan["runs"] if r["line"] == "e3-secondary-a"}
    parts = {k: r for k, r in parts.items() if r["model"] == "llama-3.3-70b"}
    assert [parts[k]["calls"] for k in ("tbd", "silent", "stale")] == [2, 2, 1]
    assert parts["tbd"]["cap_usd"] == pytest.approx(2 * parts["stale"]["cap_usd"], abs=2e-6)
    # with the three paraphrases in the harness nothing is held back, and the sum still holds
    base = rd.TEMPLATES["predictive-track-v1"]
    more = {
        f"predictive-track-p{n}-v1": rd.PromptTemplate(
            f"predictive-track-p{n}-v1", "predictive", base.text, needs_track=True
        )
        for n in (1, 2, 3)
    }
    monkeypatch.setattr(rd, "TEMPLATES", rd.TEMPLATES | more)
    full = lp.make_plan(options_for(tmp_path, shards={"openrouter": 2, "google": 3}))
    assert not full["reserved"]
    para = [run for run in full["runs"] if run["line"] == "e3-paraphrases"]
    assert sorted({run["template"] for run in para}) == sorted(more) and len(para) == 6
    for model in rd.STUDY_MODELS:
        assert units(lp.select(full, models=[model])) == round(rd.MODEL_CAPS_USD[model] * lp.MICRO)
    # a sheet whose caps for a model are not its cap less the harness's rounding stops the plan:
    # the remainder is only ever the rounding, under one cent
    sheet_of = rd.run_sheet
    for moved, shown in ((-0.02, "29.97"), (0.02, "30.01")):

        def other_sheet(*args, moved: float = moved, **kwargs) -> dict:
            sheet = sheet_of(*args, **kwargs)
            sheet["models"]["grok-4.20"]["lines"]["e3-a"]["cap_usd"] += moved
            return sheet

        monkeypatch.setattr(rd, "run_sheet", other_sheet)
        with pytest.raises(SystemExit, match=rf"grok-4.20 sum to \${shown}\d\d, which is not its"):
            lp.make_plan(options_for(tmp_path))


def test_plan_is_deterministic_and_notices_a_changed_input(study, tmp_path: Path, capsys) -> None:
    options = options_for(tmp_path, shards={"google": 2})
    first = lp.plan_text(lp.make_plan(options))
    again = lp.plan_text(lp.make_plan(json.loads(json.dumps(options))))
    assert first == again and first.endswith(" ]\n}\n")
    assert json.loads(first)["runs"] == lp.make_plan(options)["runs"]
    body = first.splitlines()
    start = body.index(' "runs": [')
    assert all(line.startswith('  {"n": ') for line in body[start + 1 : -2])  # one run per line
    assert len(body[start + 1 : -2]) == len(json.loads(first)["runs"])
    # the command writes the same bytes twice, and --check compares without writing
    args = ["plan", "--items-dir", str(study.items), "--out-root", str(study.out)]
    args += ["--local-root", str(tmp_path / "local"), "--shards", "google=2"]
    assert lp.main(args) == 0
    path = lp.plan_path(study.out)
    written = path.read_text()
    assert written == first and lp.main(args) == 0 and path.read_text() == written
    assert lp.main([*args, "--check"]) == 0 and "up to date" in capsys.readouterr().out
    plan = lp.load_plan(study.out)
    assert not lp.plan_is_stale(plan)
    # an item file that changed makes the plan on disk stale
    target = study.items / "e3_eligible.jsonl"
    target.write_text(target.read_text() + json.dumps(item("e3_eligible", 99, "2024-02-06")) + "\n")
    assert lp.plan_is_stale(plan) and lp.main([*args, "--check"]) == 1
    assert "differs from a fresh plan" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="unknown item lists \\['e33'\\]"):
        lp.make_plan(options_for(tmp_path, counts={"e33": 5}))
    with pytest.raises(SystemExit, match="holds 9 items, not --count 8"):
        lp.make_plan(options_for(tmp_path, counts={"e3": 8}))
    # a plan belongs to the output root it was made for: a copy under another root is refused
    moved = tmp_path / "moved"
    shutil.copytree(study.out / lp.LAUNCH_DIR, moved / lp.LAUNCH_DIR)
    for command in ("status", "check", "blocked"):
        with pytest.raises(SystemExit, match="was made for the output root"):
            lp.main([command, "--out-root", str(moved)])


def test_a_list_that_is_not_on_disk_is_planned_at_its_fixed_size_or_stops_the_plan(
    tmp_path: Path,
) -> None:
    sizes = {k: v for k, v in SIZES.items() if k not in ("literal_items", "e5_pairs")}
    write_files(tmp_path / "items", sizes)
    plan = lp.make_plan(options_for(tmp_path))
    assert plan["counts"]["e2"] == 120 and plan["counts"]["e5"] == 800
    assert plan["lists"]["e2"]["on_disk"] is False and plan["lists"]["e2"]["sha256"] is None
    e2 = [run for run in plan["runs"] if run["list"] == "e2"]
    assert len(e2) == 16 and {run["calls"] for run in e2} == {120}
    assert {run["item_ids_sha256"] for run in e2} == {None}
    assert lp.plan_gaps(plan, e2[0]) == [
        f"the item file of list 'e2' is not on disk: {tmp_path / 'items' / 'literal_items.jsonl'}"
    ]
    assert not lp.file_problems(plan, e2[0])
    # a trial list that is not there yet is planned at 20 items, and never with the flag that
    # lets a run read test-period items
    (tmp_path / "items" / "dev_prompt.jsonl").unlink()
    early = lp.select(lp.make_plan(options_for(tmp_path)), ["trial", "dev"])
    assert {run["calls"] for run in early if run["phase"] == "trial"} == {20}
    assert not any(run["allow_test_items"] for run in early)
    (tmp_path / "items" / "e3_eligible.jsonl").unlink()
    with pytest.raises(SystemExit, match=r"list 'e3'.*not on disk.*--count e3=N"):
        lp.make_plan(options_for(tmp_path))
    counted = lp.make_plan(options_for(tmp_path, counts={"e3": 2585, "e5": 0}))
    assert counted["counts"]["e3"] == 2585 and not [r for r in counted["runs"] if r["list"] == "e5"]


def test_shards_split_a_run_its_items_and_its_cap(study, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lp, "SHARD_MIN_CALLS", 2)
    plan = lp.make_plan(options_for(tmp_path, shards={"google": 3}))
    whole = {run["run"]: run for run in study.plan["runs"]}
    shards = [run for run in plan["runs"] if run["run"].startswith("e3-a-gemini-3.8-flash.s")]
    assert [run["shard"] for run in shards] == [f"{run['worker']}/3" for run in shards]
    ids = [f"e3xble{n:03d}" for n in range(8)]
    for run in shards:
        mine = [i for i in ids if rd.shard_of(i, 3) == run["worker"]]
        assert run["calls"] == len(mine) > 0 and run["item_ids_sha256"] == rd._ids_sha256(mine)
        assert run["run"] == f"e3-a-gemini-3.8-flash.s{run['worker']}"
    assert sum(run["calls"] for run in shards) == 8
    assert units(shards) == units([whole["e3-a-gemini-3.8-flash"]])  # the run's cap, split
    sizes = [run["calls"] for run in shards]
    assert len(set(sizes)) > 1  # in proportion to the items of each shard, not evenly
    assert [units([run]) for run in shards] == lp.split_units(units(shards), sizes)
    # a run too small to split stays whole and goes to the first worker; other lanes are whole
    small = [run for run in plan["runs"] if run["line"] == "e2-literal" and run["lane"] == "google"]
    assert [(run["shard"], run["worker"]) for run in small] == [(None, 0)]
    assert {run["shard"] for run in lp.select(plan, lanes=["xai", "openrouter"])} == {None}
    assert {run["shard"] for run in lp.select(plan, ["trial"])} == {None}
    with pytest.raises(SystemExit, match="--shards takes LANE=N"):
        lp.make_plan(options_for(tmp_path, shards={"azure": 2}))


# --- guards -----------------------------------------------------------------------------------


def test_default_prints_the_commands_and_starts_nothing(study, capsys) -> None:
    lp.plan_path(study.out).parent.mkdir(parents=True)
    lp.plan_path(study.out).write_text(lp.plan_text(study.plan))
    # ``sealed_off`` fails the test if tmux or the harness is started
    assert lp.main(["run", "--phase", "trial", "--out-root", str(study.out)]) == 0
    out = capsys.readouterr().out
    assert out.count("--allow-live") == 39 and "trial-a-gemini-3.8-flash" in out
    assert "lane google: 4 runs, 0 finished, 1 workers" in out
    assert "new-session -d -s coling-google" in out and "--worker 0" in out
    assert out.count("--phase trial --live") == 3 and "--rehearse" not in out
    assert not (study.out / rd.LEDGER_NAME).exists() and not study.sdk.calls
    assert not (lp.launch_dir(study.plan) / lp.RUN_LOG).exists()


def test_no_live_start_before_the_registration_tag(study, monkeypatch, capsys) -> None:
    monkeypatch.setattr(rd, "REPO", make_repo(study.repo.parent / "unregistered"))
    harness, tmux = Harness(), []
    assert lp.start(study.plan, ["trial"], mode="live", tmux=lambda a: tmux.append(a) or 1) == 3
    out = capsys.readouterr().out
    assert out.count("no paid call before the registration") == 3  # once per lane
    assert not [a for a in tmux if a[0] != "has-session"]
    assert lp.run_lane(study.plan, "google", phases=["trial"], mode="live", runner=harness) == 3
    assert not harness.commands and not study.sdk.calls
    [stop] = log_rows(study.plan, "stop")
    assert stop["run"] == "trial-a-gemini-3.8-flash" and "coling-registration" in stop["reason"]


def test_no_confirmatory_or_rest_start_without_the_f1_tag(study, monkeypatch, capsys) -> None:
    repo = make_repo(study.repo.parent / "registered", rd.REGISTRATION_TAG)
    monkeypatch.setattr(rd, "REPO", repo)
    harness, tmux = Harness(), []

    def fake_tmux(args: Sequence[str]) -> int:
        tmux.append(list(args))
        return 1 if args[0] == "has-session" else 0

    # the trial and the dev runs need the registration only
    assert lp.run_lane(study.plan, "google", phases=["trial"], mode="live", runner=harness) == 0
    assert lp.run_lane(study.plan, "xai", phases=["trial"], mode="live", runner=harness) == 0
    done = len(harness.commands)
    assert done == 9
    for phase in ("confirmatory", "rest"):
        assert lp.phase_refusals(phase) and not lp.phase_refusals("dev")
    # no lane starts a later phase, by the start command ...
    assert lp.start(study.plan, ["rest"], ["google", "xai"], mode="live", tmux=fake_tmux) == 3
    out = capsys.readouterr().out
    assert out.count("phase rest: no call on late or test-period items before F1") == 2
    assert "'coling-f1' does not exist" in out
    assert not [a for a in tmux if a[0] != "has-session"]
    # ... or by a lane command given directly
    for lane, phase in (("google", "rest"), ("openrouter", "confirmatory")):
        assert lp.run_lane(study.plan, lane, phases=[phase], mode="live", runner=harness) == 3
    assert len(harness.commands) == done
    reasons = [row["reason"] for row in log_rows(study.plan, "stop")]
    assert len(reasons) == 2 and all("coling-f1" in reason for reason in reasons)
    # every run of a later phase is held, also one whose items are all in the train period
    e5 = next(run for run in study.plan["runs"] if run["list"] == "e5")
    assert e5["phase"] == "rest" and not e5["allow_test_items"]
    # with the tag the same lane goes through
    git(repo, "tag", rd.F1_TAG)
    assert lp.run_lane(study.plan, "google", phases=["rest"], mode="live", runner=harness) == 0
    assert len(harness.commands) == done + 5
    # a phase whose runs are all finished asks for no tag: there is nothing left to refuse
    monkeypatch.setattr(rd, "REPO", make_repo(study.repo.parent / "untagged"))
    assert lp.phase_refusals("trial") and lp.phase_refusals("rest")
    assert not lp.lane_refusals(study.plan, "google", ["trial", "rest"], [])
    assert lp.lane_refusals(study.plan, "xai", ["rest"], [])  # its rest runs are still to read
    capsys.readouterr()
    assert lp.start(study.plan, ["trial", "rest"], ["google"]) == 0
    assert "would be refused" not in capsys.readouterr().out


def test_a_phase_waits_for_the_earlier_phases_of_its_lane(study, capsys) -> None:
    plan, harness, tmux = study.plan, Harness(), []
    first = names(plan, ["trial"], ["openrouter"], PRIMARIES)[0]
    # dev comes after the trial of the same models, in the same lane
    assert lp.start(plan, ["dev"], ["openrouter"], PRIMARIES, mode="live", tmux=tmux.append) == 3
    out = capsys.readouterr().out
    assert (
        f"phase dev comes after 10 runs of this lane that are not finished (first: {first})" in out
    )
    assert not [a for a in tmux if a[0] != "has-session"]
    code = lp.run_lane(
        plan, "openrouter", phases=["dev"], models=PRIMARIES, mode="live", runner=harness
    )
    assert code == 3 and not harness.commands
    assert "comes after 10 runs" in log_rows(plan, "stop")[-1]["reason"]
    # queued together they run in order, and the later phase alone is then free to start
    code = lp.run_lane(
        plan, "openrouter", phases=["dev", "trial"], models=PRIMARIES, mode="live", runner=harness
    )
    assert code == 0
    assert harness.runs() == names(plan, ["trial", "dev"], ["openrouter"], PRIMARIES)
    assert not lp.lane_refusals(plan, "openrouter", ["confirmatory"], PRIMARIES)
    # the other models of the lane have not had their trial: asked for, they hold the phase
    assert lp.lane_refusals(plan, "openrouter", ["rest"], [])
    # a lane with no run in the earlier phases is held by nothing but the tags
    lp.run_lane(plan, "google", phases=["trial"], mode="live", runner=harness)
    assert not lp.lane_refusals(plan, "google", ["confirmatory", "rest"], [])


def no_nap(seconds: float) -> None:
    raise AssertionError("a lane waited where it had nothing to wait for")


def test_a_worker_waits_for_the_other_workers_of_its_lane_at_a_phase_boundary(
    study, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(lp, "SHARD_MIN_CALLS", 2)
    plan = lp.make_plan(options_for(tmp_path, shards={"openrouter": 2}))
    folder, harness, naps = lp.launch_dir(plan), Harness(), []
    mine = [run for run in lp.select(plan, ["dev"], ["openrouter"], PRIMARIES) if run["worker"]]
    assert len(mine) == 6  # the second shard of each dev run
    other = lp.lane_lock(folder, "openrouter", 0)
    other.__enter__()

    def nap(seconds: float) -> None:
        naps.append(seconds)
        if len(naps) == 2:  # the other worker ends without finishing the trial runs
            other.__exit__(None, None, None)

    assert lp.workers_alive(folder, "openrouter", but=1) == [0]
    code = lp.run_lane(
        plan, "openrouter", 1, ["trial", "dev"], PRIMARIES, mode="live", runner=harness, sleep=nap
    )
    # it waited while the other worker was alive, and once more after it was gone
    assert code == 3 and naps == [lp.WAIT_S] * 3 and not harness.commands
    assert "phase dev comes after 10 runs" in log_rows(plan, "stop")[-1]["reason"]
    assert lp.workers_alive(folder, "openrouter") == []
    [waited] = log_rows(plan, "wait")  # said once, however long the wait
    assert (waited["run"], waited["worker"], waited["left"]) == (mine[0]["run"], 1, 10)
    # once the first worker has finished the trial, the second goes on without waiting
    args = (["trial", "dev"], PRIMARIES)
    assert lp.run_lane(plan, "openrouter", 0, *args, mode="live", runner=harness, sleep=nap) == 0
    done = len(harness.commands)
    assert lp.run_lane(plan, "openrouter", 1, *args, mode="live", runner=harness, sleep=no_nap) == 0
    assert harness.runs()[done:] == [run["run"] for run in mine]
    # a lane with one worker never waits: the reason comes at once
    code = lp.run_lane(
        study.plan, "xai", phases=["rest"], mode="live", runner=harness, sleep=no_nap
    )
    assert code == 3 and "phase rest comes after 5 runs" in log_rows(plan, "stop")[-1]["reason"]
    with lp.lane_lock(folder, "google", 0), pytest.raises(SystemExit, match="already running"):
        lp.run_lane(plan, "google", phases=["trial"], mode="live", runner=harness)


def test_workers_do_not_wait_for_runs_that_their_start_will_not_finish(
    study, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(lp, "SHARD_MIN_CALLS", 2)
    # the cost-trial file is not there when the plan is made: its runs are left, by worker 0
    (study.items / "dev_prompt.jsonl").unlink()
    plan = lp.make_plan(options_for(tmp_path, shards={"openrouter": 2}))
    folder, harness = lp.launch_dir(plan), Harness()
    trial = lp.select(plan, ["trial"], ["openrouter"], PRIMARIES)
    assert len(trial) == 10 and {run["worker"] for run in trial} == {0}
    args = (["trial", "dev"], PRIMARIES)
    # worker 0 is alive, and waits itself at its own dev shard: each gives the reason at once,
    # where two workers that waited for each other would never end
    with lp.lane_lock(folder, "openrouter", 0):
        code = lp.run_lane(plan, "openrouter", 1, *args, mode="live", runner=harness, sleep=no_nap)
    assert code == 3 and not harness.commands
    assert "phase dev comes after 10 runs" in log_rows(plan, "stop")[-1]["reason"]
    with lp.lane_lock(folder, "openrouter", 1):
        code = lp.run_lane(plan, "openrouter", 0, *args, mode="live", runner=harness, sleep=no_nap)
    assert code == 3 and not harness.commands
    assert [row["run"] for row in log_rows(plan, "blocked")] == [run["run"] for run in trial]
    assert log_rows(plan, "stop")[-1]["worker"] == 0 and not log_rows(plan, "wait")
    # a run of the other worker that has its file is waited for; one without it ends the wait,
    # also when it stands beside one that would come
    write_files(study.items)
    (study.items / "track_fit.json").unlink()
    plan = lp.make_plan(options_for(tmp_path, shards={"openrouter": 2}))
    held = [run["run"] for run in lp.select(plan, ["trial"], ["openrouter"], PRIMARIES)]
    assert sum("trial-b-" in name for name in held) == 2 and len(held) == 10
    with lp.lane_lock(folder, "openrouter", 0):
        code = lp.run_lane(plan, "openrouter", 1, *args, mode="live", runner=harness, sleep=no_nap)
    assert code == 3 and not harness.commands and not log_rows(plan, "wait")
    # a phase that is not queued in the start is not waited for either
    write_files(study.items)
    plan = lp.make_plan(options_for(tmp_path, shards={"openrouter": 2}))
    with lp.lane_lock(folder, "openrouter", 0):
        code = lp.run_lane(
            plan, "openrouter", 1, ["dev"], PRIMARIES, mode="live", runner=harness, sleep=no_nap
        )
    assert code == 3 and not harness.commands and not log_rows(plan, "wait")
    assert len(log_rows(plan, "stop")) == 4
    # a worker that is alive and owns none of the runs that are left is not waited for: the
    # worker that owns them is gone, and after the one more look the reason comes
    write_files(study.items, SIZES | {"dev_scoreable": (12, "2021-05-04")})
    plan = lp.make_plan(options_for(tmp_path, shards={"openrouter": 3}))
    mine = [
        run for run in lp.select(plan, ["dev"], ["openrouter"], PRIMARIES) if run["worker"] == 1
    ]
    assert mine and {run["worker"] for run in lp.select(plan, ["trial"], ["openrouter"])} == {0}
    naps = []

    def nap(seconds: float) -> None:
        naps.append(seconds)
        assert len(naps) < 4, "the worker waits for a worker that has nothing to finish"

    with lp.lane_lock(folder, "openrouter", 2):
        code = lp.run_lane(plan, "openrouter", 1, *args, mode="live", runner=harness, sleep=nap)
    assert code == 3 and naps == [lp.WAIT_S] and not harness.commands
    assert [(row["run"], row["left"]) for row in log_rows(plan, "wait")] == [(mine[0]["run"], 10)]


def test_a_worker_takes_its_lock_although_a_look_at_it_holds_it_for_an_instant(
    study, monkeypatch
) -> None:
    folder = lp.launch_dir(study.plan)
    path = lp.lock_path(folder, "xai", 0)
    path.parent.mkdir(parents=True)
    pauses = []
    with path.open("a") as look:
        fcntl.flock(look, fcntl.LOCK_EX)  # what workers_alive does while it looks

        def pause(seconds: float) -> None:
            pauses.append(seconds)
            fcntl.flock(look, fcntl.LOCK_UN)

        monkeypatch.setattr(lp.time, "sleep", pause)
        with lp.lane_lock(folder, "xai", 0):
            assert lp.workers_alive(folder, "xai") == [0]
        assert pauses == [lp.LOCK_PAUSE_S]
    # a worker that runs holds it throughout: every try fails, and the second worker is refused
    pauses.clear()
    monkeypatch.setattr(lp.time, "sleep", pauses.append)
    again = lp.lane_lock(folder, "xai", 0)
    with lp.lane_lock(folder, "xai", 0), pytest.raises(SystemExit, match="worker 0 is already"):
        again.__enter__()
    assert pauses == [lp.LOCK_PAUSE_S] * (lp.LOCK_TRIES - 1)


# --- lanes ------------------------------------------------------------------------------------


def test_lanes_do_not_wait_for_each_other(study, monkeypatch, capsys) -> None:
    plan, harness, tmux = study.plan, Harness(), []

    def fake_tmux(args: Sequence[str]) -> int:
        tmux.append(list(args))
        return 1 if args[0] == "has-session" else 0

    # a lane runs its own runs and nothing else
    assert lp.run_lane(plan, "google", phases=["trial"], mode="live", runner=harness) == 0
    assert harness.runs() == names(plan, ["trial"], ["google"])
    assert {model for model, _ in study.sdk.calls} == {"gemini-3.8-flash"}
    # after F1 the Google lane starts its test-period runs although the OpenRouter lane, which
    # still owes its trial and dev runs, is refused; and it is started first
    code = lp.start(plan, ["confirmatory", "rest"], mode="live", tmux=fake_tmux)
    out = capsys.readouterr().out
    assert code == 3
    assert "lane google started (live): tmux -L coling attach -t coling-google" in out
    assert "lane openrouter not started: phase confirmatory comes after" in out
    assert "lane xai not started: phase rest comes after 5 runs" in out
    started = [a for a in tmux if a[0] == "new-session"]
    assert [a[a.index("-s") + 1] for a in started] == ["coling-google"]
    shell = started[0][-1]
    assert "analysis.coling.launch lane" in shell and "--lane google --worker 0" in shell
    assert "--phase confirmatory --phase rest --live" in shell and "tee -a" in shell
    assert shell.count("--lane") == 1 and "openrouter" not in shell
    # asked for the confirmatory phase alone, the lane with nothing in it says where its runs are
    lp.start(plan, ["confirmatory"], ["google"], mode="live", tmux=fake_tmux)
    assert "lane google: no run in confirmatory; its runs are in: trial, rest" in (
        capsys.readouterr().out
    )
    # a lane that stops leaves the others alone
    unset = rd.Route(rd.ROUTES["deepseek-v3"].model_id, rd.UNSET)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | {"deepseek-v3": unset})
    plan = lp.make_plan(plan["options"])  # the sheet is priced on the routes
    code = lp.run_lane(
        plan, "openrouter", phases=["trial"], models=PRIMARIES, mode="live", runner=harness
    )
    assert code == 3
    assert lp.stop_path(lp.launch_dir(plan), "openrouter").is_file()
    assert not lp.stop_path(lp.launch_dir(plan), "google").exists()
    before = len(harness.commands)
    assert lp.run_lane(plan, "google", phases=["rest"], mode="live", runner=harness) == 0
    assert harness.runs()[before:] == names(plan, ["rest"], ["google"])
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness) == 0


def test_start_puts_every_lane_under_tmux_on_its_own_and_every_worker_in_a_window(
    study, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(lp, "SHARD_MIN_CALLS", 2)
    plan = lp.make_plan(options_for(tmp_path, shards={"google": 3}))
    tmux, busy = [], set()

    def fake_tmux(args: Sequence[str]) -> int:
        tmux.append(list(args))
        if args[0] == "has-session":
            return 0 if args[-1] in busy else 1
        return 0

    assert lp.start(plan, ["trial", "rest"], mode="rehearsal", tmux=fake_tmux) == 0
    made = [a for a in tmux if a[0] in ("new-session", "new-window")]
    assert [a[:4] for a in made if a[0] == "new-session"] == [
        ["new-session", "-d", "-s", f"coling-{lane}"] for lane in ("google", "xai", "openrouter")
    ]
    assert made[0][3] == "coling-google"  # the Google lane is started before any other
    windows = [a for a in made if a[0] == "new-window"]
    assert [a[1:4] for a in windows] == [["-d", "-t", "coling-google:"]] * 2
    assert [a[a.index("-n") + 1] for a in made[:3]] == ["w0", "w1", "w2"]
    assert all("--rehearse" in a[-1] and "--live" not in a[-1] for a in made)
    assert all(f"--worker {n}" in made[n][-1] for n in range(3))
    ids = {a[-1].split("--launch-id ")[1].split()[0] for a in made}
    assert len(ids) == 1  # the workers of one start share its id
    launches = log_rows(plan, "launch")
    assert [row["lane"] for row in launches] == list(lp.LANES)
    # the server was asked once whether it was up before the first lane, and it was not
    assert [a for a in tmux if a == ["has-session"]] == [["has-session"]]
    assert tmux.index(["has-session"]) < tmux.index(made[0])
    assert lp.SERVER_UP not in capsys.readouterr().out
    # a lane that is still there under tmux, or whose worker holds its lock, is not started; the
    # lane that is started lands on the server of the other, and is told whose environment it gets
    tmux.clear()
    busy.update({"=coling-xai", "has-session"})
    with lp.lane_lock(lp.launch_dir(plan), "openrouter", 0):
        assert lp.start(plan, ["trial"], mode="rehearsal", tmux=fake_tmux) == 3
    out = capsys.readouterr().out
    assert out.count("the lane is running") == 2 and out.count(lp.SERVER_UP) == 1
    assert out.index(lp.SERVER_UP) < out.index("lane google started")
    assert [a[3] for a in tmux if a[0] == "new-session"] == ["coling-google"]
    # no variable of the shell is handed over on a command line of tmux, where it could be read
    assert not [a for a in tmux if "-e" in a or a[0] in ("set-environment", "setenv")]
    assert "API_KEY" not in (lp.launch_dir(plan) / lp.RUN_LOG).read_text()
    # a live start is refused when the plan is no longer what its inputs give
    target = study.items / "dev_prompt.jsonl"
    target.write_text(target.read_text() + json.dumps(item("dev_prompt", 77, "2021-03-02")) + "\n")
    tmux.clear()
    busy.clear()
    assert lp.start(plan, ["trial"], mode="live", tmux=fake_tmux) == 3
    assert capsys.readouterr().out.count(lp.STALE) == 3
    assert not [a for a in tmux if a[0] != "has-session"]
    assert lp.run_lane(plan, "google", phases=["trial"], mode="live", runner=Harness()) == 3


# --- running, stopping and resuming -----------------------------------------------------------


def test_a_lane_logs_every_command_with_its_start_end_and_exit_status(study) -> None:
    plan, harness = study.plan, Harness()
    assert lp.run_lane(plan, "google", phases=["trial"], mode="live", runner=harness) == 0
    wanted = names(plan, ["trial"], ["google"])
    starts, ends = log_rows(plan, "start"), log_rows(plan, "end")
    assert [row["run"] for row in starts] == [row["run"] for row in ends] == wanted
    assert [row["command"] for row in starts] == harness.commands
    assert all(row["exit"] == 0 and row["reason"] is None for row in ends)
    assert all(row["ts"] and row["lane"] == "google" and row["mode"] == "live" for row in starts)
    events = [row["event"] for row in log_rows(plan)]
    assert events == ["lane-start", *["start", "end"] * 4, "lane-end"]
    # the harness made the runs: a manifest each, the caps in its ledger, one call per item
    for run in lp.select(plan, ["trial"], ["google"]):
        manifest = lp.manifest_of(plan, run)
        assert manifest["complete"] and manifest["spend_cap_usd"] == run["cap_usd"]
        assert manifest["item_ids_sha256"] == run["item_ids_sha256"]
        assert lp.run_state(plan, run) == "finished"
        assert (lp.launch_dir(plan) / "output" / f"{run['run']}.log").is_file()
    held = rd.held_by_run(study.out)
    assert set(held) == set(wanted) and not any(entry["open"] for entry in held.values())
    assert len(study.sdk.calls) == 4 * 3


def test_a_run_is_not_taken_as_finished_on_its_exit_status(study) -> None:
    plan, seen = study.plan, []

    def idle(command: Sequence[str], output: Path) -> int:
        seen.append(list(command))
        return 0  # and nothing was read

    assert lp.run_lane(plan, "google", phases=["trial"], mode="live", runner=idle) == 3
    assert len(seen) == 1  # the lane stops at its first run
    end, stop = log_rows(plan, "end")[-1], log_rows(plan, "stop")[-1]
    assert end["exit"] == 0 and end["reason"] == stop["reason"]
    assert stop["reason"] == "the harness returned 0 and its manifest is not complete for this run"
    assert lp.unfinished(plan, lp.select(plan, ["trial"], ["google"])) == names(
        plan, ["trial"], ["google"]
    )
    # a rehearsal writes no manifest, and its exit status is all there is
    assert lp.run_lane(plan, "google", phases=["trial"], mode="rehearsal", runner=idle) == 0
    assert len(seen) == 1 + 4


def test_a_rerun_skips_what_the_harness_finished_and_nothing_else(study) -> None:
    plan, harness = study.plan, Harness()
    wanted = names(plan, ["trial"], ["xai"])
    broken = wanted[2]

    def reply(model: str, prompt: str) -> str | None:
        if len(harness.commands) == 3 and len(study.sdk.calls) % 3 == 2:
            raise RuntimeError("the provider fell over")
        return None

    study.sdk.reply = reply
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness) == 3
    assert harness.runs() == wanted[:3]
    by_name = {run["run"]: run for run in plan["runs"]}
    assert [lp.run_state(plan, by_name[name]) for name in wanted] == [
        "finished",
        "finished",
        "partial",
        "none",
        "none",
    ]
    # the stopped run left a folder, a spend log, readings and a manifest: none of them makes it
    # finished, only a manifest that says complete
    folder = study.out / broken
    assert (folder / "readings.jsonl").is_file() and (folder / "spend_log.jsonl").is_file()
    assert lp.manifest_of(plan, by_name[broken])["complete"] is False
    study.sdk.reply = None
    calls = len(study.sdk.calls)
    again = Harness()
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=again) == 0
    assert again.runs() == wanted[2:]
    assert [row["run"] for row in log_rows(plan, "skip")] == wanted[:2]
    assert len(study.sdk.calls) - calls == 2 + 3 + 3  # the stopped run resumes from its cache
    assert not lp.unfinished(plan, lp.select(plan, ["trial"], ["xai"]))
    third = Harness()
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=third) == 0
    assert not third.commands and len(log_rows(plan, "skip")) == 2 + 5
    # a run whose folder is gone is read again, from the cache: rows done, no call paid
    shutil.rmtree(study.out / wanted[0])
    calls = len(study.sdk.calls)
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=third) == 0
    assert third.runs() == wanted[:1] and len(study.sdk.calls) == calls
    counts = lp.run_counts(plan, by_name[wanted[0]], log_rows(plan))
    assert (counts["state"], counts["done"], counts["left"]) == ("finished", 3, 0)
    assert (counts["paid"], counts["spent"]) == (0, 0)
    third.commands.clear()
    # a manifest that is complete under another pin of the template, for another model id or
    # under another provider pin is not the plan's run
    target = study.out / wanted[1] / "run_manifest.json"
    manifest = json.loads(target.read_text())
    assert manifest["template_sha256"] == plan["templates"][by_name[wanted[1]]["template"]]
    assert manifest["route"] == plan["routes"]["grok-4.20"]
    assert manifest["model_id"] == plan["routes"]["grok-4.20"]["model_id"]
    assert manifest["provider_object"] is None  # a direct route sends no pin
    pinned = {"order": ["deepinfra/fp8"], "allow_fallbacks": False}
    for change in (
        {"template_sha256": "0" * 64},
        {"model_id": "grok-5"},
        {"provider_object": pinned},
        {"model": "grok-5"},
        {"template": "literal-v1"},
        {"shard": "0/2"},
        {"limit": 2},
        {"samples": 2},
        {"temperature": 1.0},
        {"mask_names": True},
        {"shift_years": 4},
        {"track_record_sha256": "0" * 64},
        {"items_sha256": "0" * 64},
        {"item_ids_sha256": "0" * 64},
        {"expected_rows": 4},
    ):
        target.write_text(json.dumps(manifest | change))
        assert lp.run_state(plan, by_name[wanted[1]]) == "mismatch"
        assert lp.manifest_differences(plan, by_name[wanted[1]], manifest | change) == [*change]
    target.write_text(json.dumps(manifest))
    assert lp.run_state(plan, by_name[wanted[1]]) == "finished"
    # a finished run of another item set is never skipped and never overwritten: the lane stops
    target = study.items / "dev_prompt.jsonl"
    target.write_text(target.read_text() + json.dumps(item("dev_prompt", 55, "2021-03-02")) + "\n")
    moved = lp.make_plan(plan["options"])
    assert lp.run_state(moved, lp.select(moved, ["trial"], ["xai"])[0]) == "mismatch"
    assert lp.run_lane(moved, "xai", phases=["trial"], mode="live", runner=third) == 3
    assert not third.commands
    reason = log_rows(plan, "stop")[-1]["reason"]
    assert "complete for another run than the plan's" in reason and "item_ids_sha256" in reason


def test_what_f1_enters_beside_a_route_leaves_the_runs_made_before_it_finished(
    study, monkeypatch
) -> None:
    plan, harness = study.plan, Harness()
    args = (["trial", "dev"], PRIMARIES)
    assert lp.run_lane(plan, "openrouter", 0, *args, mode="live", runner=harness) == 0
    done = len(harness.commands)
    assert done == 16
    # the trial shows the name a provider reports itself under, and a price is read again: both
    # are entered in the harness's table, which changes neither the request nor its pin
    before = dict(rd.ROUTES)
    entered = {
        model: replace(
            before[model], also_served_by=("DeepInfra Inc",), price=(0.11, 0.31, "2026-10-04")
        )
        for model in PRIMARIES
    }
    monkeypatch.setattr(rd, "ROUTES", before | entered)
    assert lp.plan_is_stale(plan)  # the plan holds the table, and the sheet is priced on it
    assert lp.run_lane(plan, "openrouter", 0, *args, mode="live", runner=harness) == 3
    assert log_rows(plan, "stop")[-1]["reason"] == lp.STALE
    later = lp.make_plan(plan["options"])
    assert later["routes"]["deepseek-v3"] != plan["routes"]["deepseek-v3"]
    early = lp.select(later, ["trial", "dev"], ["openrouter"], PRIMARIES)
    assert len(early) == done and {lp.run_state(later, run) for run in early} == {"finished"}
    # the confirmatory phase is not held up, and nothing is read a second time
    assert not lp.lane_refusals(later, "openrouter", ["confirmatory"], PRIMARIES)
    assert lp.run_lane(later, "openrouter", 0, *args, mode="live", runner=harness) == 0
    assert len(harness.commands) == done and len(log_rows(later, "skip")) == done
    # another endpoint, or another precision of the same one, is another run: nothing is
    # skipped, nothing is read again under the old name, and the later phase waits
    for change in ({"provider": "deepinfra/turbo"}, {"quantization": "fp4"}):
        moved = {model: replace(before[model], **change) for model in PRIMARIES}
        monkeypatch.setattr(rd, "ROUTES", before | moved)
        other = lp.make_plan(plan["options"])
        early = lp.select(other, ["trial", "dev"], ["openrouter"], PRIMARIES)
        assert {lp.run_state(other, run) for run in early} == {"mismatch"}
        assert lp.lane_refusals(other, "openrouter", ["confirmatory"], PRIMARIES)
        assert lp.run_lane(other, "openrouter", 0, *args, mode="live", runner=harness) == 3
        assert len(harness.commands) == done
        assert (
            "another run than the plan's: ['provider_object']"
            in (log_rows(plan, "stop")[-1]["reason"])
        )


def test_a_lane_stops_at_the_first_run_the_harness_refuses_and_says_why(
    study, monkeypatch, capsys
) -> None:
    harness = Harness()
    unset = rd.Route(rd.ROUTES["llama-3.3-70b"].model_id, rd.UNSET)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | {"llama-3.3-70b": unset})
    # a plan made on other routes is refused before any run: the sheet is priced on them
    assert lp.run_lane(study.plan, "openrouter", mode="live", runner=harness) == 3
    assert log_rows(study.plan, "stop")[-1]["reason"] == lp.STALE and not harness.commands
    plan = lp.make_plan(study.plan["options"])
    wanted = names(plan, ["trial", "dev"], ["openrouter"], PRIMARIES)
    code = lp.run_lane(
        plan, "openrouter", phases=["trial", "dev"], models=PRIMARIES, mode="live", runner=harness
    )
    first = next(n for n, name in enumerate(wanted) if name.endswith("llama-3.3-70b"))
    assert code == 3 and 0 < first < len(wanted) - 1
    assert harness.runs() == wanted[: first + 1]  # nothing after the refused run was started
    stop = log_rows(plan, "stop")[-1]
    assert stop["run"] == wanted[first] and stop["lane"] == "openrouter"
    assert "ROUTES['llama-3.3-70b'] has no provider yet (UNSET)" in stop["reason"]
    end = log_rows(plan, "end")[-1]
    assert end["run"] == wanted[first] and end["exit"] == 1 and end["reason"] == stop["reason"]
    assert f"lane openrouter stopped at {wanted[first]}" in capsys.readouterr().out
    assert not (study.out / wanted[first]).exists()  # the harness refused before writing
    assert all("llama" not in model for model, _ in study.sdk.calls)
    # a second worker of the same start does not go on either
    stop_record = json.loads(lp.stop_path(lp.launch_dir(plan), "openrouter").read_text())
    code = lp.run_lane(
        plan,
        "openrouter",
        phases=["trial"],
        models=PRIMARIES,
        mode="live",
        launch_id=stop_record["launch_id"],
        runner=harness,
    )
    assert code == 3 and len(harness.commands) == first + 1
    # the stop is one whole file, with nothing left beside it
    stops = lp.stop_path(lp.launch_dir(plan), "openrouter").parent
    assert [path.name for path in stops.iterdir()] == ["openrouter.json"]


def test_a_run_the_plan_has_no_file_for_is_left_and_the_lane_goes_on(study, tmp_path: Path) -> None:
    kept = (study.items / "e5_pairs.jsonl").rename(tmp_path / "e5_pairs.jsonl")
    plan, harness = lp.make_plan(study.plan["options"]), Harness()
    wanted = names(plan, ["trial", "rest"], ["xai"])
    assert plan["counts"]["e5"] == 800 and "e5-grok-4.20" in wanted
    code = lp.run_lane(plan, "xai", phases=["trial", "rest"], mode="live", runner=harness)
    assert code == 3 and harness.runs() == [name for name in wanted if name != "e5-grok-4.20"]
    [blocked] = log_rows(plan, "blocked")
    assert blocked["run"] == "e5-grok-4.20" and "list 'e5' is not on disk" in blocked["reason"]
    assert not log_rows(plan, "stop") and not lp.stop_path(lp.launch_dir(plan), "xai").exists()
    assert lp.unfinished(plan, lp.select(plan, ["trial", "rest"], ["xai"])) == ["e5-grok-4.20"]
    # the file comes: the old plan is refused, and under a new one only that run is read
    kept.rename(study.items / "e5_pairs.jsonl")
    e5 = next(run for run in plan["runs"] if run["run"] == "e5-grok-4.20")
    assert "it is there now: plan again" in lp.plan_gaps(plan, e5)[0]
    assert lp.run_lane(plan, "xai", phases=["rest"], mode="live", runner=harness) == 3
    assert log_rows(plan, "stop")[-1]["reason"] == lp.STALE
    again = Harness()
    assert lp.run_lane(study.plan, "xai", phases=["rest"], mode="live", runner=again) == 0
    assert again.runs() == ["e5-grok-4.20"]
    # a file the plan had and that has other bytes, or is gone, does stop the lane
    run = next(r for r in study.plan["runs"] if r["run"] == "trial-b-gemini-3.8-flash")
    assert not lp.plan_gaps(study.plan, run) and not lp.file_problems(study.plan, run)
    target = study.items / "track_fit.json"
    target.write_text(target.read_text() + "\n")
    last = Harness()
    assert lp.run_lane(study.plan, "google", phases=["trial"], mode="live", runner=last) == 3
    assert log_rows(plan, "stop")[-1]["reason"] == lp.STALE and not last.commands
    assert lp.file_problems(study.plan, run) == [
        f"the fit track record is not the file the plan was made with ({target}): plan again"
    ]
    target.unlink()
    assert lp.file_problems(study.plan, run) == [
        f"the fit track record is not on disk any more: {target}"
    ]


def test_a_run_stopped_by_its_cap_stops_the_lane_with_the_harness_s_status(study) -> None:
    plan, harness = study.plan, Harness()
    wanted = names(plan, ["trial"], ["xai"])

    def reply(model: str, prompt: str) -> None:
        # the second run is billed far more than its cap allows
        study.sdk.tokens = (30_000_000, 60) if len(harness.commands) == 2 else (500, 60)

    study.sdk.reply = reply
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness) == 3
    assert harness.runs() == wanted[:2]
    end = log_rows(plan, "end")[-1]
    assert end["run"] == wanted[1] and end["exit"] == 3
    assert end["reason"].startswith("the harness stopped the run: aborted: recorded spend $37.5")
    assert log_rows(plan, "stop")[-1]["reason"] == end["reason"]
    second = lp.select(plan, ["trial"], ["xai"])[1]
    assert lp.run_state(plan, second) == "partial"
    counts = lp.run_counts(plan, second, log_rows(plan))
    assert (counts["state"], counts["done"], counts["left"], counts["paid"]) == ("partial", 1, 2, 1)
    assert counts["spent"] > counts["cap"]
    # the cap is the harness's to hold: started again, the run is refused again, not skipped
    study.sdk.reply = None
    study.sdk.tokens = (500, 60)
    again = Harness()
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=again) == 3
    assert again.runs() == wanted[1:2] and [r["run"] for r in log_rows(plan, "skip")] == wanted[:1]
    assert "cap" in log_rows(plan, "stop")[-1]["reason"]
    # a line or a manifest that is still being written is not read as a record
    log = study.out / wanted[0] / "spend_log.jsonl"
    whole = lp.read_jsonl(log)
    log.write_text(log.read_text() + '{"event": "call", "usd": 0.0')
    assert lp.read_jsonl(log) == whole
    log.write_text('{"event": "ca\n' + log.read_text())
    with pytest.raises(json.JSONDecodeError):
        lp.read_jsonl(log)
    first = lp.select(plan, ["trial"], ["xai"])[0]
    assert lp.run_state(plan, first) == "finished"
    (study.out / wanted[0] / "run_manifest.json").write_text('{"complete": tr')
    assert lp.manifest_of(plan, first) == {} and lp.run_state(plan, first) == "none"
    # with no record of the harness, the reason is the last line it printed
    assert lp.failure_reason(plan, {"run": "no-run"}, 1, study.out / "none.log") == (
        "the harness refused the run or failed (exit 1): no output"
    )


def test_a_cap_raised_by_hand_holds_in_the_harness_and_the_launcher_raises_none(
    study, capsys
) -> None:
    plan, harness = study.plan, Harness()
    wanted = names(plan, ["trial"], ["xai"])
    second = lp.select(plan, ["trial"], ["xai"])[1]
    note = "A1: the cost trial of grok-4.20 was billed past its run cap"

    def reply(model: str, prompt: str) -> None:
        study.sdk.tokens = (30_000_000, 60) if len(harness.commands) == 2 else (500, 60)

    study.sdk.reply = reply
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness) == 3
    study.sdk.reply, study.sdk.tokens = None, (500, 60)
    assert rd.held_by_run(study.out)[wanted[1]]["held_usd"] > rd.MODEL_CAPS_USD["grok-4.20"]
    # by hand, as PLAN section 9 has it: the run's cap and the model's cap, with a note
    by_hand = lp.harness_args(plan, second, "live")
    by_hand[by_hand.index("--spend-cap-usd") + 1] = "40"
    by_hand += ["--model-cap-usd", "61", "--amendment", note]
    assert rd.main([*by_hand, "--declare-only"]) == 0
    assert rd.model_caps(study.out)["grok-4.20"] == 61
    assert lp.run_counts(plan, second, log_rows(plan))["cap"] == 40  # the cap in the ledger
    # the launcher starts the run again under the plan's cap: it never raises one, the harness
    # stops the run at its first paid call, and the model's raised cap stays in the ledger
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness) == 3
    assert harness.runs() == [*wanted[:2], wanted[1]]
    assert "cap" in log_rows(plan, "stop")[-1]["reason"]
    declared = [
        row
        for row in lp.read_jsonl(study.out / rd.LEDGER_NAME)
        if row["event"] == "declare" and row["run"] == wanted[1]
    ]
    assert [row["cap_usd"] for row in declared] == [second["cap_usd"], 40, second["cap_usd"]]
    assert (declared[-1]["model_cap_usd"], declared[-1]["model_cap_amended_by"]) == (61, note)
    assert lp.run_counts(plan, second, log_rows(plan))["cap"] == second["cap_usd"]
    assert lp.run_state(plan, second) == "partial"
    # resumed by hand to its end, the run is finished for the launcher although its cap is not
    # the plan's, and the rest of the lane goes through under the model's raised cap
    assert rd.main(by_hand) == 0
    assert lp.manifest_of(plan, second)["spend_cap_usd"] == 40
    assert lp.run_state(plan, second) == "finished"
    assert lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness) == 0
    assert harness.runs()[3:] == wanted[2:]
    assert not [c for c in harness.commands if {"--model-cap-usd", "--amendment"} & set(c)]
    ledger = lp.read_jsonl(study.out / rd.LEDGER_NAME)
    last = {row["run"]: row for row in ledger if row["event"] == "declare"}
    for name in wanted[2:]:
        assert (last[name]["model_cap_usd"], last[name]["model_cap_amended_by"]) == (61, note)
    spent = sum(entry["spent_usd"] for entry in rd.held_by_run(study.out).values())
    assert 37.5 < spent < 40 and not lp.unfinished(plan, lp.select(plan, ["trial"], ["xai"]))
    # status shows the dollars against the cap the run ended under
    lp.plan_path(study.out).write_text(lp.plan_text(plan))
    capsys.readouterr()
    assert (
        lp.main(["status", "--out-root", str(study.out), "--phase", "trial", "--lane", "xai"]) == 0
    )
    row = next(
        line for line in capsys.readouterr().out.splitlines() if f" {wanted[1]} " in line
    ).split()
    assert row[3] == "finished" and float(row[7]) > 37.5 and row[8] == "40.0000"


def test_rehearsal_gives_every_command_to_the_harness_as_a_dry_run(study, monkeypatch) -> None:
    monkeypatch.setattr(rd, "REPO", study.repo.parent)  # no repository and no tag: not needed
    plan, harness = study.plan, Harness()
    assert lp.run_lane(plan, "openrouter", phases=lp.PHASES, mode="rehearsal", runner=harness) == 0
    wanted = lp.select(plan, lanes=["openrouter"])
    assert len(harness.commands) == len(wanted) > 80
    assert all("--dry-run" in c and "--allow-live" not in c for c in harness.commands)
    assert not study.sdk.calls and not (study.out / rd.LEDGER_NAME).exists()
    assert sorted(p.name for p in study.out.iterdir()) == [lp.LAUNCH_DIR]
    assert {row["mode"] for row in log_rows(plan, "start")} == {"rehearsal"}
    # a rehearsal is no attempt at a run: status still shows every run as pending
    assert log_rows(plan, "end")[0]["run"] == wanted[0]["run"]
    assert {lp.run_counts(plan, run, log_rows(plan))["state"] for run in wanted} == {"pending"}
    # a file that is missing blocks its runs; the rehearsal goes on and reports them
    (study.items / "track_fit.json").unlink()
    again = Harness()
    code = lp.run_lane(plan, "google", phases=["trial"], mode="rehearsal", runner=again)
    assert code == 3 and len(again.commands) == 3
    [blocked] = log_rows(plan, "blocked")
    assert blocked["run"] == "trial-b-gemini-3.8-flash"
    assert "the fit track record is not on disk any more" in blocked["reason"]
    with pytest.raises(ValueError, match="rehearsal or live"):
        lp.run_lane(plan, "google", mode="print")
    # a command the harness refuses as a dry run is reported with its reason, and the rest go on
    shown = TRACK | {"examples": [TRACK["examples"][0] | {"item_id": "devmpt000"}]}
    (study.items / "track_fit.json").write_text(json.dumps(shown, indent=1))
    plan, third = lp.make_plan(plan["options"]), Harness()
    code = lp.run_lane(plan, "xai", phases=["trial"], mode="rehearsal", runner=third)
    assert code == 3 and len(third.commands) == 5
    refused = [row for row in log_rows(plan, "end") if row["exit"]]
    assert [row["run"] for row in refused] == ["trial-b-grok-4.20"]
    assert "1 items are examples of the track record" in refused[0]["reason"]
    assert log_rows(plan)[-1]["event"] == "lane-end" and log_rows(plan)[-1]["failed"] == 1


# --- status, the completeness check and what is blocked ---------------------------------------


def test_status_prints_counts_and_nothing_of_the_items_or_the_answers(study, capsys) -> None:
    plan, harness = study.plan, Harness()
    garbage = f"{ANSWER_MARK} is not JSON"

    def reply(model: str, prompt: str) -> str | None:
        """For grok-4.20's forecasts: the second item is answered on its repair call, the third
        never."""
        if not model.startswith("grok") or "statement_type" in prompt:
            return None
        if "3 MG 100 Capsules" in prompt:
            return garbage
        return garbage if "2 MG 100 Capsules" in prompt and garbage not in prompt else None

    study.sdk.reply = reply
    for lane in ("google", "xai"):
        lp.run_lane(plan, lane, phases=["trial"], mode="live", runner=harness)
    lp.plan_path(study.out).write_text(lp.plan_text(plan))
    # the spend log also holds what was not a call (a retry, a refusal): none of it is paid
    spend = study.out / "trial-a-gemini-3.8-flash" / "spend_log.jsonl"
    assert {row["event"] for row in lp.read_jsonl(spend)} == {"call"}
    more = [{"event": "retry", "attempt": 1}, {"event": "refusal", "error": garbage}]
    spend.write_text(spend.read_text() + "".join(json.dumps(row) + "\n" for row in more))
    capsys.readouterr()
    assert lp.main(["status", "--out-root", str(study.out)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].split() == ["phase", "lane", "run", "state", *lp.STATUS_COLUMNS]
    assert len(lines) == 1 + len(plan["runs"]) + 3  # a line per run and a line per lane
    row = next(line for line in lines if " trial-a-gemini-3.8-flash " in line).split()
    cap = next(r["cap_usd"] for r in plan["runs"] if r["run"] == "trial-a-gemini-3.8-flash")
    spent = 3 * (500 * 0.75 + 60 * 3.75) / 1e6
    assert row[3:] == ["finished", "3", "0", "3", f"{spent:.4f}", f"{cap:.4f}", "0", "0", "0"]
    pending = next(line for line in lines if " e3-a-gemini-3.8-flash " in line).split()
    assert pending[3:6] == ["pending", "0", "8"]
    # repairs and failures are counts of the whole run, from the harness's manifest
    xai = lp.select(plan, ["trial"], ["xai"])
    counts = {run["line"]: lp.run_counts(plan, run, log_rows(plan)) for run in xai}
    for line in ("trial-a", "trial-b", "trial-probe"):
        assert lp.manifest_of(plan, next(r for r in xai if r["line"] == line))["by_status"] == {
            "failed": 1,
            "ok": 1,
            "repaired": 1,
        }
        got = counts[line]
        assert (got["done"], got["paid"], got["repairs"], got["failed"]) == (3, 5, 2, 1)
    assert (counts["trial-literal"]["paid"], counts["trial-literal"]["repairs"]) == (3, 0)
    failing = next(line for line in lines if " trial-a-grok-4.20 " in line).split()
    assert failing[3:7] == ["finished", "3", "0", "5"] and failing[9:] == ["2", "1", "0"]
    lane = next(line for line in lines if line.startswith("lane xai"))
    assert "(12 runs: 5 finished, 7 pending)" in lane
    left = sum(run["calls"] for run in lp.select(plan, lanes=["xai"])) - 15
    assert lane.split()[2:5] == ["15", str(left), "21"] and lane.split()[7:10] == ["6", "3", "0"]
    # no answer, no notice text, no item id, no prompt and no reason reaches the output
    assert ANSWER_MARK not in out and TEXT_MARK not in out and "is not JSON" not in out
    ids = {item_id for path in study.items.glob("*.jsonl") for item_id in item_ids(path)}
    assert not [item_id for item_id in ids if item_id in out]
    assert "Anagrelide" not in out and "statement_type" not in out
    allowed = {run["run"] for run in plan["runs"]} | set(lp.PHASES) | set(lp.LANES)
    allowed |= {"finished", "pending", "lane", "runs:", "(12", "(9", "(104"}
    words = {w for line in lines[1:] for w in line.replace(",", " ").replace(")", " ").split()}
    assert all(w in allowed or w.replace(".", "").isdigit() for w in words)
    # one phase and one lane can be asked for
    assert (
        lp.main(["status", "--out-root", str(study.out), "--phase", "trial", "--lane", "xai"]) == 0
    )
    assert len(capsys.readouterr().out.splitlines()) == 1 + 5 + 1


def test_status_says_running_failed_and_partial_without_saying_why(study, monkeypatch) -> None:
    harness = Harness()
    unset = rd.Route("grok-4.20-0309-non-reasoning", rd.UNSET)
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | {"grok-4.20": unset})
    plan = lp.make_plan(study.plan["options"])
    lp.run_lane(plan, "xai", phases=["trial"], mode="live", runner=harness)
    first, second = lp.select(plan, ["trial"], ["xai"])[:2]
    assert lp.run_counts(plan, first, log_rows(plan))["state"] == "failed"
    assert lp.run_counts(plan, second, log_rows(plan))["state"] == "pending"
    text = "\n".join(lp.status_lines(plan, ["trial"], ["xai"]))
    assert "UNSET" not in text and "ROUTES" not in text
    folder = lp.launch_dir(plan)
    lp.log_event(folder, event="start", run=second["run"], lane="xai", worker=0, mode="live")
    assert lp.run_counts(plan, second, log_rows(plan))["state"] == "pending"  # nobody is running
    with lp.lane_lock(folder, "xai", 0):
        assert lp.run_counts(plan, second, log_rows(plan))["state"] == "running"


def run_confirmatory(plan: dict, harness: Harness) -> None:
    """The primaries' trial, dev and confirmatory runs, worker after worker in each phase."""
    workers = 1 + max(run["worker"] for run in plan["runs"])
    for phase in ("trial", "dev", "confirmatory"):
        for worker in range(workers):
            code = lp.run_lane(
                plan,
                "openrouter",
                worker,
                [phase],
                PRIMARIES,
                mode="live",
                runner=harness,
                sleep=no_nap,
            )
            assert code == 0


def test_check_says_whether_every_confirmatory_run_is_finished(study, capsys) -> None:
    plan, harness = study.plan, Harness()
    report, ready = lp.confirmatory_report(plan)
    assert not ready and len(report) == 8 and not any(entry["ready"] for entry in report)
    assert {(e["model"], e["line"]) for e in report} == {
        (model, line) for model in rd.PRIMARIES for line in lp.CONFIRMATORY_LINES
    }
    run_confirmatory(plan, harness)
    report, ready = lp.confirmatory_report(plan)
    assert ready and all(entry["ready"] for entry in report)
    assert [(e["expected"], e["answered"], e["missing"]) for e in report] == [
        (3, 3, 0) if e["line"] == "e4-probe" else (8, 8, 0) for e in report
    ]
    lp.plan_path(study.out).write_text(lp.plan_text(plan))
    capsys.readouterr()
    assert lp.main(["check", "--out-root", str(study.out)]) == 0
    out = capsys.readouterr().out
    assert "every confirmatory run of the launcher is finished" in out
    assert "not checked here: the test predictions of the model-free predictors" in out
    assert not [i for i in (f"e3xble{n:03d}" for n in range(8)) if i in out]
    # the harness's check over the whole output root pools the dev and trial runs of the same
    # condition with the confirmatory ones, which is why the launcher names its runs to it
    ids = [f"e3xble{n:03d}" for n in range(8)]
    pooled = rd.check_runs(study.out, expected=ids, template="predictive-v1")
    mine = next(entry for entry in pooled if entry["model"] == "llama-3.3-70b")
    assert mine["unexpected"] == 3 + 5 and mine["ready"] is False
    named = rd.check_runs(
        study.out, expected=ids, template="predictive-v1", runs=["e3-a-llama-3.3-70b"]
    )
    assert [(e["model"], e["unexpected"], e["ready"]) for e in named] == [
        ("llama-3.3-70b", 0, True)
    ]
    # the check makes no folder and no link, under the output root or anywhere else
    assert not [p for p in study.out.rglob("*") if p.is_symlink()]
    # the registered list is the file the plan was made with: once its bytes have changed, or
    # it is gone, there is nothing to compare the runs with, and its two groups are not ready
    listed = study.items / "subset_probe.jsonl"
    kept = listed.read_text()
    listed.write_text(kept.replace("Hematology", "Oncology"))
    assert item_ids(listed) == [f"subobe{n:03d}" for n in range(3)]  # the same ids as before
    report, ready = lp.confirmatory_report(plan)
    assert not ready and [e["line"] for e in report if not e["ready"]] == ["e4-probe"] * 2
    assert {(e["finished"], e["answered"]) for e in report if not e["ready"]} == {(1, 0)}
    listed.unlink()
    assert [e["line"] for e in lp.confirmatory_report(plan)[0] if not e["ready"]] == [
        "e4-probe"
    ] * 2
    listed.write_text(kept)
    assert lp.confirmatory_report(plan)[1]
    # a confirmatory run that is no longer complete, or whose folder is gone, is noticed
    target = study.out / "e3-b-deepseek-v3" / "run_manifest.json"
    manifest = json.loads(target.read_text())
    target.write_text(json.dumps(manifest | {"complete": False}))
    report, ready = lp.confirmatory_report(plan)
    assert not ready
    assert [(e["model"], e["line"]) for e in report if not e["ready"]] == [("deepseek-v3", "e3-b")]
    assert lp.main(["check", "--out-root", str(study.out)]) == 3
    assert "NOT complete: no evaluation against test outcomes yet" in capsys.readouterr().out
    target.write_text(json.dumps(manifest))
    assert lp.confirmatory_report(plan)[1]
    # a run that is complete for another items file than the registered one is not ready,
    # although the harness's own check has nothing against it
    target.write_text(json.dumps(manifest | {"items_sha256": "0" * 64}))
    report, ready = lp.confirmatory_report(plan)
    entry = next(e for e in report if (e["model"], e["line"]) == ("deepseek-v3", "e3-b"))
    assert not ready and (entry["finished"], entry["missing"], entry["ready"]) == (0, 0, False)
    target.write_text(json.dumps(manifest))
    # a run on fewer items than the registered list is not ready either
    readings = study.out / "e4-probe-llama-3.3-70b" / "readings.jsonl"
    kept = readings.read_text().splitlines()
    readings.write_text("\n".join(kept[:-1]) + "\n")
    report, ready = lp.confirmatory_report(plan)
    entry = next(e for e in report if (e["model"], e["line"]) == ("llama-3.3-70b", "e4-probe"))
    assert not ready and (entry["answered"], entry["missing"], entry["ready"]) == (2, 1, False)


def test_check_refuses_a_partial_shard(study, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lp, "SHARD_MIN_CALLS", 2)
    plan = lp.make_plan(options_for(tmp_path, shards={"openrouter": 2}))
    harness = Harness()
    shards = [r for r in lp.select(plan, ["confirmatory"]) if r["run"].startswith("e3-a-llama")]
    assert [run["shard"] for run in shards] == ["0/2", "1/2"]
    run_confirmatory(plan, harness)
    assert lp.confirmatory_report(plan)[1]
    # the second shard never ran: the group is short of its items and is not ready
    gone = study.out / shards[1]["run"]
    kept = gone.rename(tmp_path / "kept")
    report, ready = lp.confirmatory_report(plan)
    entry = next(e for e in report if (e["model"], e["line"]) == ("llama-3.3-70b", "e3-a"))
    assert not ready and (entry["runs"], entry["finished"]) == (2, 1)
    assert entry["missing"] == shards[1]["calls"] and entry["ready"] is False
    assert sum(not e["ready"] for e in report) == 1
    # the same items answered a second time under another name are duplicates for the harness;
    # the launcher's check looks at the registered runs only
    kept.rename(gone)
    twin = study.out / "e3-a-llama-3.3-70b.other"
    twin.mkdir()
    for name in ("readings.jsonl", "run_manifest.json"):
        (twin / name).write_text((gone / name).read_text())
    assert lp.confirmatory_report(plan)[1]


def test_blocked_names_every_missing_value(tmp_path: Path, monkeypatch, capsys) -> None:
    sizes = {k: v for k, v in SIZES.items() if k not in ("dev_prompt", "e5_pairs")}
    write_files(tmp_path / "items", sizes)
    (tmp_path / "items" / "track_fit_dev.json").unlink()
    args = ["--items-dir", str(tmp_path / "items"), "--out-root", str(tmp_path / "out")]
    # the harness's table has every route entered: the rows are taken back here, to see them named
    unset = {model: rd.Route(rd.ROUTES[model].model_id, rd.UNSET) for model in OPENROUTER}
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | unset)
    assert lp.main(["plan", *args, "--local-root", str(tmp_path / "local")]) == 0
    plan = lp.load_plan(tmp_path / "out")
    out = capsys.readouterr().out
    total = len(plan["runs"])
    assert f"0 of {total} runs could start live today" in out
    assert (
        f"- {total} runs (trial, dev, confirmatory, rest): no paid call before the registration"
        in out
    )
    for model in OPENROUTER:
        assert f"ROUTES[{model!r}] has no provider yet (UNSET)" in out
    assert "literal-v1 waits for the pilot sentences ['D1', 'D3'] (PILOT_SENTENCES)" in out
    assert "literal-free-v1 waits for the pilot sentences ['D1'] (PILOT_SENTENCES)" in out
    assert "(confirmatory, rest): no call on late or test-period items before F1" in out
    assert "- 39 runs (trial): the item file of list 'trial' is not on disk" in out
    assert "- 7 runs (rest): the item file of list 'e5' is not on disk" in out
    assert "the fit+dev track record is not on disk" in out
    assert "list 'e5' is planned at 800 items (the plan's fixed size, or --count), not from" in out
    assert "(written by: minimal_pairs.py generate, as analysis/coling/out/e5/e5_pairs.jsonl" in out
    assert (
        "list 'trial' is planned at 20 items" in out and "(written by: dataset.py --items)" in out
    )
    assert "not planned: e3-paraphrases for llama-3.3-70b: read.TEMPLATES holds 0 paraphrase" in out
    assert out.count("ROUTES['gemini-3.8-flash']") == 0  # the two direct routes are set
    # once everything is in place nothing is blocked
    write_files(tmp_path / "items")
    monkeypatch.setattr(rd, "REPO", make_repo(tmp_path / "repo", rd.REGISTRATION_TAG, rd.F1_TAG))
    monkeypatch.setattr(rd, "ROUTES", rd.ROUTES | PINNED)
    monkeypatch.setattr(rd, "PILOT_SENTENCES", {"D1": "", "D3": ""})
    assert lp.main(["plan", *args, "--local-root", str(tmp_path / "local")]) == 0
    capsys.readouterr()
    assert lp.main(["blocked", "--out-root", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].split(" of ")[0] == out[0].split(" of ")[1].split()[0]
    assert [line for line in out[1:] if not line.startswith("- not planned: e3-paraphrases")] == []
    # a plan that its inputs no longer give is the first thing a live start is refused for
    assert not lp.plan_is_stale(lp.load_plan(tmp_path / "out"))
    listed = tmp_path / "items" / "e5_pairs.jsonl"
    listed.write_text(listed.read_text() + json.dumps(item("e5_pairs", 9, "2021-06-01")) + "\n")
    assert lp.main(["blocked", "--out-root", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"- every run: {lp.STALE}" and " runs could start live today" in out[1]
    assert sum("list 'e5' is not the file the plan was made with" in line for line in out) == 1
    with pytest.raises(SystemExit, match="no plan at"):
        lp.main(["status", "--out-root", str(tmp_path / "elsewhere")])
