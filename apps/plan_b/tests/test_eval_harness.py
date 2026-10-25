"""The Wave 3 evaluation harness (``plan-b eval run`` and ``plan-b eval report``), dry runs only.

Everything runs on development cases through the real runner, store and executor, with P0 and
scripted model transports for P1-P3 (``scripted_policy_factory``; nothing reaches a network or
the spend ledger). Covered:

* the whole pipeline with two parallel episode processes: P0 once and P1-P3 once per seed, each
  episode in its own process and database, the order shuffled within the case from the
  recorded order seed, traces verified, metrics and the report written;
* resumability: a rerun skips finished episodes and reruns only unfinished ones, and a results
  directory holding another plan is refused;
* the truth split: public records and traces carry no evaluator truth, ``runner_private/`` does,
  and ``scripts/run_live_cases.py`` splits its run record the same way;
* timed-out and crashed episodes stay in their denominators;
* held-out loading from ``scenarios/private/eval/`` (a temporary copy of a development case and
  of its public fixture, removed afterwards) and the guard that refuses a held-out run on drift.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from plan_b.cli import main as cli_main
from plan_b.evaluation import manifest as mf
from plan_b.evaluation.export_trace import verify_trace_bytes
from plan_b.evaluation.metrics import suite_metrics
from plan_b.evaluation.policies.base import Policy
from plan_b.evaluation.report import write_report
from plan_b.evaluation.run import (
    RunRefused,
    build_plan,
    load_results,
    run_evaluation,
)
from plan_b.scenarios.policy_host import EpisodeCaps
from plan_b.world.world import load_case

APP = Path(__file__).resolve().parents[1]
HOOK = "tests.test_eval_harness:scripted_policy_factory"
SEEDS = [101, 202, 303]
PUBLIC_FILES = ("plan.json",)
TRUTH_KEYS = ('"matches_expectation"', '"predicates"', '"expected_outcome"', '"case_id"')


# ---------------------------------------------------------------------------------- hooks


def scripted_policy_factory(
    choice: str, profile_id: str, seed: int | None, caps: EpisodeCaps, work_dir: Path
) -> Callable[[], Policy]:
    """P1-P3 around the real provider client with a scripted transport (tests' fakes)."""
    from plan_b.agent.policies.selective import SelectivePolicy
    from plan_b.agent.policies.tool_use import ToolUsePolicy
    from plan_b.agent.policies.verify_all import VerifyAllPolicy
    from tests.test_agent_provider import FakeOpener, ScriptedModel, make_config, make_provider
    from tests.test_live_workflow import ToolScript, menu_pick

    config = make_config(work_dir)

    def make() -> Policy:
        if choice == "tool-use":
            return ToolUsePolicy(
                make_provider(config, FakeOpener(ToolScript())),
                max_model_calls=caps.max_model_calls,
                max_tool_calls=caps.max_tool_calls,
            )
        cls = SelectivePolicy if choice == "live" else VerifyAllPolicy
        return cls(
            make_provider(config, FakeOpener(ScriptedModel(choose=menu_pick))),
            max_model_calls=caps.max_model_calls,
            max_tool_calls=caps.max_tool_calls,
        )

    return make


def raising_policy_factory(
    choice: str, profile_id: str, seed: int | None, caps: EpisodeCaps, work_dir: Path
) -> Callable[[], Policy]:
    raise RuntimeError(f"scripted crash in {work_dir}")


# ---------------------------------------------------------------------------------- helpers


def _public_texts(out: Path) -> dict[str, str]:
    """Every public file of a results directory, traces decompressed."""
    texts = {name: (out / name).read_text(encoding="utf-8") for name in PUBLIC_FILES}
    for path in sorted((out / "episodes").rglob("*")):
        if path.name == "record.json":
            texts[str(path.relative_to(out))] = path.read_text(encoding="utf-8")
        elif path.name == "trace.json.gz":
            texts[str(path.relative_to(out))] = gzip.decompress(path.read_bytes()).decode()
    return texts


def _records(out: Path) -> dict[str, dict[str, Any]]:
    return {
        p.parent.name: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((out / "episodes").glob("*/record.json"))
    }


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("eval") / "campus_dry"
    summary = run_evaluation(
        suite="campus",
        cases=["dev01"],
        policies=["P0", "P1", "P2", "P3"],
        seeds=SEEDS,
        out=out,
        jobs=2,
        policy_factory=HOOK,
        log=lambda _line: None,
    )
    assert summary.planned == 10 and summary.ran == 10 and summary.skipped == 0
    return out


# ---------------------------------------------------------------------------------- the pipeline


def test_the_dry_run_runs_every_planned_episode_once_in_its_own_process(dry_run: Path) -> None:
    plan = json.loads((dry_run / "plan.json").read_text())
    assert plan["dry_run"] is True and plan["model_response_cache"] is False
    assert plan["start_method"] == "spawn"
    episodes = plan["episodes"]
    # P0 once, P1-P3 once per seed, in the order drawn from the recorded order seed.
    assert Counter(e["policy"] for e in episodes) == {"P0": 1, "P1": 3, "P2": 3, "P3": 3}
    assert {e["seed"] for e in episodes if e["policy"] != "P0"} == set(SEEDS)
    expected = build_plan(["dev01"], ["P0", "P1", "P2", "P3"], SEEDS, plan["order_seed"])
    assert [e["key"] for e in episodes] == [e.key for e in expected]
    assert sorted(e["position"] for e in episodes) == list(range(1, 11))
    unshuffled = ["P0", *(["P1"] * 3), *(["P2"] * 3), *(["P3"] * 3)]
    assert [e["policy"] for e in episodes] != unshuffled
    records = _records(dry_run)
    assert set(records) == {e["key"] for e in episodes}
    # A fresh database per episode: distinct episode ids; a fresh policy per episode.
    ids = [r["outcome"]["episode_id"] for r in records.values()]
    assert len(set(ids)) == 10
    for key, record in records.items():
        assert record["status"] in ("completed", "capped"), (key, record["errors"])
        data = gzip.decompress((dry_run / "episodes" / key / "trace.json.gz").read_bytes())
        assert verify_trace_bytes(data) == [] and record["trace"]["verify"] == "intact"
        if record["policy"] == "P0":
            assert record["model"]["calls"] == 0 and record["policy_id"] == "rules/1.0.0"
            assert record["outcome"]["goal_complete"] is True
        else:
            assert record["model_source"] == f"scripted:{HOOK}"
            assert record["model"]["calls"] >= 1 and record["model"]["cost_usd"] > 0
    # The work area is gone; no database or fake key is left behind.
    assert not (dry_run / "work").exists()
    invocations = (dry_run / "invocations.jsonl").read_text().splitlines()
    assert len(invocations) == 1 and json.loads(invocations[0])["jobs"] == 2


def test_the_report_tables_and_figure_come_from_the_results(dry_run: Path) -> None:
    paths = write_report(dry_run)
    metrics = json.loads(paths["metrics"].read_text())
    assert len(metrics["episodes"]) == 10 and metrics["missing"] == []
    by_policy = metrics["by_policy"]
    assert set(by_policy) == {"P0", "P1", "P2", "P3"}
    assert by_policy["P0"]["goal_completion"] == {"k": 1, "n": 1, "cases": ["dev01"]}
    for p in ("P1", "P2", "P3"):
        assert by_policy[p]["goal_completion"]["n"] == 3
        assert by_policy[p]["recorded"] == 3 and by_policy[p]["computation"]["model_calls"] >= 3
    p0 = next(r for r in metrics["episodes"] if r["policy"] == "P0")
    # dev01: one applied plan change after the delay notice, one status check of two minutes.
    assert p0["plan_churn"]["committed_revisions"] == 1
    assert p0["verification"]["status_checks"] == 1
    assert p0["verification"]["simulated_minutes"] == 2
    assert p0["recovery"]["recovered"] is True and p0["recovery"]["delay_minutes"] >= 0

    # Descriptive only: no composite score anywhere.
    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for v in value.values() for k in keys(v)}
        return {k for v in value for k in keys(v)} if isinstance(value, list) else set()

    assert not {k for k in keys(metrics) if k == "score" or "composite" in k}
    text = paths["markdown"].read_text()
    for heading in (
        "## Run manifest",
        "## Primary campus aggregate display",
        "## Counts and denominators",
        "## Per-case display",
        "## Missing and aborted episodes",
    ):
        assert heading in text
    assert text.count("| dev01 | P") == 10
    svg = ET.fromstring(paths["figure"].read_text())
    assert svg.tag.endswith("svg")
    style = paths["figure"].read_text()
    assert "prefers-color-scheme: dark" in style and "<title" in style


def test_public_records_carry_no_evaluator_truth(dry_run: Path) -> None:
    case = load_case("dev01")
    markers = [case.description, *(p.description for p in case.outcome_predicates)]
    for name, text in _public_texts(dry_run).items():
        for key in TRUTH_KEYS:
            assert key not in text, (name, key)
        for marker in markers:
            assert marker not in text, (name, marker[:40])
    for record in _records(dry_run).values():
        assert "matches_expectation=" not in json.dumps(record)
    private = list((dry_run / "runner_private").glob("*.runner.json"))
    assert len(private) == 10
    for path in private:
        data = json.loads(path.read_text())
        assert "matches_expectation" in data and "predicates" in data
    cases = json.loads((dry_run / "runner_private" / "cases.json").read_text())
    assert cases["cases"][0]["outcome_class"] == "goal"


# ---------------------------------------------------------------------------------- resume


def test_a_rerun_skips_finished_episodes_and_reruns_only_unfinished_ones(tmp_path: Path) -> None:
    out = tmp_path / "resume"
    kwargs: dict[str, Any] = {
        "suite": "campus",
        "cases": ["dev04"],
        "policies": ["P0", "P2"],
        "seeds": [7],
        "out": out,
        "jobs": 2,
        "policy_factory": HOOK,
        "log": lambda _line: None,
    }
    first = run_evaluation(**kwargs)
    assert (first.planned, first.ran, first.skipped) == (2, 2, 0)
    records = _records(out)
    stamps = {k: r["finished_at"] for k, r in records.items()}
    again = run_evaluation(**kwargs)
    assert (again.ran, again.skipped) == (0, 2)
    assert {k: r["finished_at"] for k, r in _records(out).items()} == stamps
    # An interrupted episode (no public record yet) runs again; the finished one does not.
    gone = next(k for k in records if k.endswith("__P2__s7"))
    (out / "episodes" / gone / "record.json").unlink()
    third = run_evaluation(**kwargs)
    assert (third.ran, third.skipped) == (1, 1)
    assert _records(out)[gone]["status"] in ("completed", "capped")
    assert len((out / "invocations.jsonl").read_text().splitlines()) == 3
    with pytest.raises(RunRefused, match="different run plan"):
        run_evaluation(**(kwargs | {"seeds": [8]}))


# ---------------------------------------------------------------------------------- failures


def test_timed_out_and_crashed_episodes_stay_in_the_denominators(tmp_path: Path) -> None:
    out = tmp_path / "failures"
    summary = run_evaluation(
        suite="campus",
        cases=["dev01"],
        policies=["P0"],
        seeds=[],
        out=out,
        jobs=1,
        timeout_s=0.05,
        log=lambda _line: None,
    )
    assert summary.statuses == {"timeout": 1}
    crashed = tmp_path / "crashed"
    run_evaluation(
        suite="campus",
        cases=["dev05"],
        policies=["P2"],
        seeds=[1],
        out=crashed,
        policy_factory="tests.test_eval_harness:raising_policy_factory",
        log=lambda _line: None,
    )
    record = _records(crashed)["dev05__P2__s1"]
    assert record["status"] == "crashed" and record["outcome"] is None
    # The public record names the exception's type; its text, which privileged code may have
    # composed from private data, is only in the evaluator record.
    assert record["errors"][0]["message"] == "RuntimeError in the episode process"
    detail = json.loads((crashed / "runner_private" / "dev05__P2__s1.runner.json").read_text())
    assert "scripted crash" in detail["error_detail"]["message"]
    assert str(tmp_path) not in json.dumps(record) + json.dumps(detail)  # placeholders
    # A timed-out episode keeps its database (evaluator side) as its evidence.
    timed_out = json.loads((out / "runner_private" / "dev01__P0__once.runner.json").read_text())
    kept = timed_out["database"]
    assert kept and all((out / k).is_file() for k in kept)
    assert not (out / "work").exists()
    for directory, klass, policy, case in (
        (out, "goal_completion", "P0", "dev01"),
        (crashed, "appropriate_infeasibility", "P2", "dev05"),
    ):
        aggregate = suite_metrics(load_results(directory))["by_policy"][policy]
        assert aggregate[klass] == {"k": 0, "n": 1, "cases": [case]}
        assert aggregate["incomplete"] == 1 and aggregate["missing"] == 0


def test_a_planned_episode_without_a_record_is_listed_as_missing(tmp_path: Path) -> None:
    out = tmp_path / "missing"
    run_evaluation(
        suite="campus",
        cases=["dev04"],
        policies=["P0"],
        seeds=[],
        out=out,
        log=lambda _line: None,
    )
    shutil.rmtree(out / "episodes" / "dev04__P0__once")
    paths = write_report(out)
    metrics = json.loads(paths["metrics"].read_text())
    assert metrics["missing"] == ["dev04__P0__once"]
    assert metrics["by_policy"]["P0"]["missing"] == 1
    assert "`dev04__P0__once`" in paths["markdown"].read_text()


def test_the_run_refuses_bad_requests(tmp_path: Path) -> None:
    base: dict[str, Any] = {"suite": "campus", "out": tmp_path / "x", "log": lambda _l: None}
    with pytest.raises(RunRefused, match="unknown"):
        run_evaluation(**base, cases=["nope"], policies=["P0"], seeds=[])
    with pytest.raises(RunRefused, match="not campus"):
        run_evaluation(**base, cases=["pantry_dev01"], policies=["P0"], seeds=[])
    with pytest.raises(RunRefused, match="policies"):
        run_evaluation(**base, cases=["dev01"], policies=["P9"], seeds=[])
    with pytest.raises(RunRefused, match="seeds"):
        run_evaluation(**base, cases=["dev01"], policies=["P1"], seeds=[1, 1])


# ---------------------------------------------------------------------------------- held-out


def _heldout_case(
    private: Path,
    public: Path,
    *,
    dev: str,
    ref: str,
    case_id: str,
    outcome_class: str = "goal",
    negative_control: bool = False,
    requires_recovery: bool = False,
    annotations: tuple[dict[str, Any], ...] = (),
) -> dict[str, Path]:
    """A held-out case in the given (temporary) directories: a development case under an opaque
    ref, its world changed by one status record id (so it is not a development duplicate), its
    public fixture copied under its own scenario id, and its evaluator data."""
    case = json.loads((APP / f"plan_b/scenarios/private/{dev}.json").read_text())
    scenario = json.loads((APP / "plan_b/scenarios/public/campus_showcase.json").read_text())
    sid = f"hxpub{ref[2:]}"
    case |= {"case_ref": ref, "scenario_id": sid}
    case["status_model"][-1]["response"]["source_record_id"] += "_heldout"
    scenario["scenario_id"] = sid
    evaluator: dict[str, Any] = {
        "artifact": "plan_b.eval_case",
        "case_id": case_id,
        "case_ref": ref,
        "suite": "campus",
        "condition": f"temporary copy of {dev} for the loader test",
        "outcome_class": outcome_class,
        "negative_control": negative_control,
        "negative_control_evidence": "test-only: the original plan stays feasible"
        if negative_control
        else None,
        "requires_recovery": requires_recovery,
        "actionable_record_ids": ["delivery_message_17"] if requires_recovery else [],
        "annotations": list(annotations),
    }
    files = {
        "case": private / f"{ref}.json",
        "eval": private / f"{ref}.eval.json",
        "public": public / f"{sid}.json",
    }
    files["case"].write_text(json.dumps(case, indent=1) + "\n")
    files["eval"].write_text(json.dumps(evaluator, indent=1) + "\n")
    files["public"].write_text(json.dumps(scenario, indent=1) + "\n")
    return files


ANNOTATION = {
    "source_record_id": "delivery_message_17",
    "event_id": "e_showcase_01",
    "resource_id": "projector",
    "effective_time": "2026-11-05T17:25:00-05:00",
    "claimed_change": "delay",
    "source_id": "delivery_contact",
    "booking_ref": "P17",
    "unknown_fields": ["current delivery status"],
}


@pytest.fixture
def heldout_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    """Temporary held-out directories in place of ``scenarios/{private,public}/eval``: no test
    writes into the real ones, so none can disturb a locked ``heldout.json``."""
    real = [mf.HELDOUT_PRIVATE_DIR, mf.HELDOUT_PUBLIC_DIR]
    before = [sorted(d.rglob("*")) if d.exists() else None for d in real]
    private, public = tmp_path / "eval_private", tmp_path / "eval_public"
    private.mkdir()
    public.mkdir()
    monkeypatch.setattr(mf, "HELDOUT_PRIVATE_DIR", private)
    monkeypatch.setattr(mf, "HELDOUT_PUBLIC_DIR", public)
    yield private, public
    assert [sorted(d.rglob("*")) if d.exists() else None for d in real] == before


def test_held_out_cases_load_from_the_private_eval_directory_and_need_the_freeze(
    heldout_dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    from plan_b.domain.fixtures import PUBLIC_SCENARIOS
    from plan_b.world import world

    private, public = heldout_dirs
    goal = _heldout_case(
        private,
        public,
        dev="dev01",
        ref="hxa1",
        case_id="C01",
        requires_recovery=True,
        annotations=(ANNOTATION,),
    )
    _heldout_case(private, public, dev="dev04", ref="hxb2", case_id="C03", negative_control=True)
    freeze, lock = tmp_path / "freeze.json", tmp_path / "heldout.json"
    model = {"provider": "openrouter", "model_id": "test/model", "base_url": None}
    common: dict[str, Any] = {
        "suite": "campus",
        "cases": ["C01", "C03"],
        "policies": ["P0"],
        "seeds": list(mf.DEFAULT_SEEDS),
        "freeze_path": freeze,
        "heldout_path": lock,
        "log": lambda _line: None,
    }
    # No manifest yet: a held-out run is refused before anything runs.
    with pytest.raises(RunRefused, match="freeze does not verify"):
        run_evaluation(**common, out=tmp_path / "refused")
    mf.write_freeze(freeze, model=model)
    mf.write_heldout(lock, freeze_path=freeze)
    locked = json.loads(lock.read_text())
    entries = {c["case_id"]: c for c in locked["suites"]["campus"]}
    assert entries["C01"]["case_ref"] == "hxa1" and entries["C01"]["public_file"].endswith(
        "eval_public/hxpuba1.json"
    )
    # The negative control passed the evaluator's replay of its original plan.
    assert entries["C03"]["negative_control_replay"]["original_plan_completes"] is True
    assert entries["C01"]["negative_control_replay"] is None
    assert locked["freeze_sha256"] == mf.manifest_digest(freeze)
    assert mf.verify_heldout(lock, freeze_path=freeze).ok
    with pytest.raises(RunRefused, match="frozen"):
        run_evaluation(**(common | {"seeds": [1, 2, 3]}), out=tmp_path / "refused")
    with pytest.raises(RunRefused, match="dry runs"):
        run_evaluation(**common, out=tmp_path / "refused", policy_factory=HOOK)

    out = tmp_path / "heldout"
    summary = run_evaluation(**common, out=out, jobs=2)
    assert summary.heldout and summary.statuses == {"completed": 2}
    # The frozen loaders are untouched in this process.
    assert "hxpuba1" not in PUBLIC_SCENARIOS
    assert world.PRIVATE_DIR == APP / "plan_b" / "scenarios" / "private"
    plan = json.loads((out / "plan.json").read_text())
    assert plan["heldout"] and plan["case_refs"] == ["hxa1", "hxb2"]
    assert plan["episode_caps"]["phase"] == "frozen"
    assert plan["policy_subset"] is True and plan["freeze_sha256"] == mf.manifest_digest(freeze)
    assert not (out / "work").exists() and not (out / "runner_private" / "cases").exists()
    record = _records(out)["hxa1__P0__once"]
    assert record["outcome"]["goal_complete"] is True
    assert record["outcome"]["scenario_id"] == "hxpuba1"
    assert record["measured_files_sha256"] == plan["measured_files_sha256"]
    texts = _public_texts(out)
    for name, text in texts.items():
        for case_id in ("C01", "C03"):
            assert case_id not in text, name  # the evaluator ids stay private
        for key in TRUTH_KEYS:
            assert key not in text, (name, key)
    metrics = suite_metrics(load_results(out))
    rows = {row["case_id"]: row for row in metrics["episodes"]}
    assert rows["C01"]["success"] is True and rows["C03"]["success"] is True
    # The evaluator's negative-control designation and recovery data are applied.
    assert rows["C01"]["unnecessary_committed_changes"] is None
    assert rows["C03"]["unnecessary_committed_changes"]["committed_changes"] == 0
    assert rows["C01"]["recovery"]["recovered"] is True
    # P0's frozen parser, replayed, read the annotated message as annotated.
    assert rows["C01"]["extraction"] == [
        {
            "source_record_id": "delivery_message_17",
            "observation_id": "obs_notice_01",
            "label": "correct",
            "mismatched": [],
        }
    ]
    # One byte in the evaluator data: the lock no longer verifies and the run is refused.
    path = goal["eval"]
    path.write_text(path.read_text() + " ")
    assert not mf.verify_heldout(lock).ok
    with pytest.raises(RunRefused, match="held-out file changed"):
        run_evaluation(**common, out=tmp_path / "drift")
    # Neither is an edited freeze.json, though its file hashes are untouched.
    path.write_text(path.read_text()[:-1])
    data = json.loads(freeze.read_text())
    freeze.write_text(json.dumps(data | {"seeds": [1, 2, 3]}, indent=1, sort_keys=True) + "\n")
    assert mf.verify_freeze(freeze).ok  # the seeds are an input, not code...
    with pytest.raises(RunRefused, match="locked against a different freeze"):
        run_evaluation(**(common | {"seeds": [1, 2, 3]}), out=tmp_path / "edited")


def test_the_held_out_loader_refuses_cases_that_break_the_protocol(
    heldout_dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    from plan_b.evaluation.run import heldout_specs

    private, public = heldout_dirs

    def refused(match: str, **kwargs: Any) -> None:
        files = _heldout_case(private, public, **kwargs)
        with pytest.raises(RunRefused, match=match):
            heldout_specs()
        for path in files.values():
            path.unlink()

    refused("C02, C03 and C04", dev="dev04", ref="hxc3", case_id="C02")
    refused("outcome class", dev="dev04", ref="hxc3", case_id="C08")
    refused("not a campus case", dev="dev04", ref="hxc3", case_id="T01")
    refused("must be opaque", dev="dev04", ref="stale_c3", case_id="C03", negative_control=True)
    refused("must be opaque", dev="dev04", ref="hx_c03", case_id="C03", negative_control=True)
    # A development case under a new ref is still a development case.
    files = _heldout_case(
        private, public, dev="dev04", ref="hxd4", case_id="C02", negative_control=True
    )
    case = json.loads(files["case"].read_text())
    original = json.loads((APP / "plan_b/scenarios/private/dev04.json").read_text())
    case["status_model"] = original["status_model"]
    files["case"].write_text(json.dumps(case))
    with pytest.raises(RunRefused, match="repeats the world of development case dev04"):
        heldout_specs()
    for path in files.values():
        path.unlink()
    # A negative control whose original plan does not complete cannot be locked.
    _heldout_case(private, public, dev="dev01", ref="hxe5", case_id="C02", negative_control=True)
    freeze = tmp_path / "freeze.json"
    mf.write_freeze(freeze, model={"provider": "openrouter", "model_id": "m", "base_url": None})
    with pytest.raises(mf.FreezeError, match="cannot be a negative control"):
        mf.write_heldout(tmp_path / "heldout.json", freeze_path=freeze)


def test_the_cli_runs_and_reports_a_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "cli"
    args = [
        "eval",
        "run",
        "--suite",
        "pantry",
        "--cases",
        "pantry_dev02",
        "--policies",
        "P0",
        "--jobs",
        "1",
        "--out",
        str(out),
    ]
    assert cli_main(args) == 0
    assert "pantry_dev02__P0__once: completed" in capsys.readouterr().out
    assert cli_main(["eval", "report", "--results", str(out)]) == 0
    metrics = json.loads((out / "report" / "metrics.json").read_text())
    row = metrics["episodes"][0]
    # pantry_dev02: 10 of 16 handed off, 34 of 40 on time, a 6-kit deficit reported.
    assert row["outcome_class"] == "partial" and row["success"] is True, row["failure_reasons"]
    target = row["pantry"]["targets"][0]
    assert (target["original_target"], target["on_time"], target["service_deficit"]) == (40, 34, 6)
    assert row["pantry"]["conservation_failures"] == 0
    assert row["pantry"]["receipt_integrity_ok"], row["pantry"]["receipt_integrity_problems"]
    assert row["pantry"]["duplicate_or_unauthorized_credits"] == 0
    text = (out / "report" / "evaluation_results.md").read_text()
    assert "## Pantry transfer aggregate display" in text
    assert "## Pantry quantity and receipt ledger" in text
    assert (
        cli_main(
            [
                "eval",
                "run",
                "--suite",
                "pantry",
                "--cases",
                "dev01",
                "--policies",
                "P0",
                "--out",
                str(tmp_path / "bad"),
            ]
        )
        == 2
    )


# ---------------------------------------------------------------------------------- live script


def test_the_live_run_script_keeps_the_verdict_out_of_its_public_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plan_b.agent import config as config_module
    from plan_b.scenarios import runner
    from tests.test_agent_provider import make_config

    spec = importlib.util.spec_from_file_location(
        "run_live_cases", APP / "scripts" / "run_live_cases.py"
    )
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    cfg = make_config(tmp_path)
    factory = scripted_policy_factory(
        "live", "campus_showcase", None, EpisodeCaps(), tmp_path / "w"
    )
    real = runner.run_case
    monkeypatch.setattr(config_module, "load_model_config", lambda: cfg)
    monkeypatch.setattr(
        runner,
        "run_case",
        lambda db, case_ref, **kw: real(db, case_ref, policy_factory=factory, caps=kw["caps"]),
    )
    out = tmp_path / "live"
    assert script.main(["--out", str(out), "--policy", "live", "dev01"]) == 0
    record = json.loads((out / "reports" / "live_p2-live_dev01_run.json").read_text())
    assert "matches_expectation" not in record
    assert "matches_expectation" not in record["outcome_line"]
    assert "matches_expectation" not in json.dumps(record["outcome"])
    private = json.loads(
        (out / "runner_private" / "live_p2-live_dev01_run.private.json").read_text()
    )
    assert private["matches_expectation"] is True
    assert private["outcome_line"].endswith("matches_expectation=True")


def test_the_seed_reaches_run_case_once_it_takes_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interface the policy worker adds: ``run_case(db, case_ref, policy=..., seed=...)``.
    Until it lands the record says ``seed_passed: false``; with it, the seed is passed by
    keyword (in process here, so the stand-in ``run_case`` is visible)."""
    from plan_b.evaluation import run as run_module
    from plan_b.scenarios import runner

    real = runner.run_case
    seen: list[int | None] = []

    def with_seed(db: Any, case_ref: str, *, seed: int | None = None, **kw: Any) -> Any:
        seen.append(seed)
        return real(db, case_ref, **kw)

    monkeypatch.setattr(runner, "run_case", with_seed)
    assert run_module.seed_supported()
    episode = run_module.build_plan(["dev04"], ["P2"], [41], 1)[0]
    frozen = run_module.FrozenSettings(caps=mf.episode_caps(), timeout_s=60, model=None)
    spec = run_module.development_spec("dev04")
    task = run_module._task(episode, spec, tmp_path, tmp_path / "work", None, frozen, HOOK, False)
    run_module.episode_process(task)
    assert seen == [41]
    record = json.loads(run_module.record_path(tmp_path, episode.key).read_text())
    assert record["seed_passed"] is True and record["seed"] == 41
    assert record["status"] in ("completed", "capped")
