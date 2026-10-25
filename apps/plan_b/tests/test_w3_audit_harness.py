"""Harness and freeze fixes of the Wave 3 freeze audit. Development cases, P0 or scripted
providers, temporary directories; nothing reaches a network or the real manifests.

* A run is bound to the measured code (and, held out, the cases and model) it started under:
  an episode process that finds them changed records nothing and the run stops; a resume under
  other code is refused (audit C1, E1, E2).
* A harness stop (the cumulative spend cap, the endpoint configuration) is ``aborted``: not
  scored and rerun by a resume; the per-run spend cap is the episode's own frozen budget,
  ``capped`` (C4, E3).
* One invocation at a time per results directory (C5).
* The freeze records symbolic links and unreadable files as entries, the runtime, and the
  per-run cost cap; a held-out lock checks its own aggregate and protocol (E5, E6, E9, E3).
* The policy order is drawn over all four policies, so a subset keeps its positions (E10, C7).
* The frozen model is matched key by key, a None included (E4, C8).
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

import pytest

from plan_b.evaluation import manifest as mf
from plan_b.evaluation import run as runmod
from plan_b.evaluation.metrics import suite_metrics
from plan_b.evaluation.run import (
    RunRefused,
    build_plan,
    finished,
    has_records,
    load_results,
    run_evaluation,
)
from tests.test_agent_provider import make_config


def _quiet(_line: str) -> None:
    return None


# ---------------------------------------------------------------------------------- binding


def test_an_episode_that_finds_the_measured_code_changed_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent binds the run to a hash the episode processes do not find (as if the code
    changed after the run started): the first episode records nothing, no other starts."""
    real = mf.tree_hash
    monkeypatch.setattr(mf, "tree_hash", lambda files: "0" * 64 if files else real(files))
    out = tmp_path / "drift"
    with pytest.raises(RunRefused, match="the measured code changed since the run started"):
        run_evaluation(
            suite="campus",
            cases=["dev04", "dev05"],
            policies=["P0"],
            seeds=[],
            out=out,
            jobs=1,
            log=_quiet,
        )
    assert not (out / "episodes").exists()
    assert not list((out / "runner_private").glob("*.drift.txt"))


def test_a_resume_under_other_measured_code_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "resume"
    kwargs: dict[str, Any] = {
        "suite": "campus",
        "cases": ["dev04"],
        "policies": ["P0"],
        "seeds": [],
        "out": out,
        "log": _quiet,
    }
    run_evaluation(**kwargs)
    plan = json.loads((out / "plan.json").read_text())
    assert plan["measured_files_sha256"] == mf.tree_hash(mf.measured_files())
    monkeypatch.setattr(mf, "tree_hash", lambda files: "f" * 64)
    with pytest.raises(RunRefused, match="different run plan"):
        run_evaluation(**kwargs)


def test_the_frozen_model_is_matched_key_by_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import plan_b.agent.config as config

    cfg = make_config(tmp_path)
    monkeypatch.setattr(config, "load_model_config", lambda: cfg)
    public = cfg.public()
    frozen = {k: public[k] for k in runmod.MODEL_KEYS}
    assert runmod._model_config_public(["P2"], frozen, None) is not None
    for key, value in (("base_url", None), ("max_run_cost_usd", 0.01), ("model_id", "x/y")):
        with pytest.raises(RunRefused, match=f"configured {key}"):
            runmod._model_config_public(["P2"], frozen | {key: value}, None)


# ---------------------------------------------------------------------------------- aborted


def _decision(failure: str, summary: str) -> dict[str, Any]:
    return {"kind": "stop", "summary": summary, "details": {"failure": failure}}


def test_harness_stops_are_aborted_and_the_per_run_cap_is_a_cap() -> None:
    status = runmod._episode_status
    cumulative = "Stopped for this episode: spend cap reached: cumulative cap 4.00 USD: ..."
    per_run = "Stopped for this episode: spend cap reached: per-run cap 0.50 USD: spent ..."
    assert status(None, [_decision("spend_cap", cumulative)]) == "aborted"
    assert status(None, [_decision("provider_config", "the key file is missing")]) == "aborted"
    assert status(None, [_decision("spend_cap", per_run)]) == "capped"
    assert status({"reached": ["model_calls"]}, []) == "capped"
    assert status({"reached": []}, []) == "completed"


def test_an_aborted_episode_is_listed_apart_and_rerun_by_a_resume(tmp_path: Path) -> None:
    out = tmp_path / "aborted"
    kwargs: dict[str, Any] = {
        "suite": "campus",
        "cases": ["dev04"],
        "policies": ["P0"],
        "seeds": [],
        "out": out,
        "log": _quiet,
    }
    run_evaluation(**kwargs)
    key = "dev04__P0__once"
    record_file = out / "episodes" / key / "record.json"
    record = json.loads(record_file.read_text())
    record_file.write_text(json.dumps(record | {"status": "aborted"}))
    assert has_records(out, key) and not finished(out, key)
    metrics = suite_metrics(load_results(out))
    assert metrics["aborted"] == [key] and metrics["missing"] == []
    aggregate = metrics["by_policy"]["P0"]
    assert aggregate["aborted"] == 1 and aggregate["recorded"] == 0
    assert "goal_completion" not in aggregate  # not in any outcome-class denominator
    again = run_evaluation(**kwargs)
    assert (again.ran, again.skipped) == (1, 0)
    assert json.loads(record_file.read_text())["status"] == "completed"


# ---------------------------------------------------------------------------------- lock


def test_one_invocation_at_a_time_per_results_directory(tmp_path: Path) -> None:
    fcntl = pytest.importorskip("fcntl")
    out = tmp_path / "locked"
    out.mkdir()
    fd = os.open(out / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RunRefused, match="another invocation"):
            run_evaluation(
                suite="campus", cases=["dev04"], policies=["P0"], seeds=[], out=out, log=_quiet
            )
    finally:
        os.close(fd)
    assert not (out / "episodes").exists()


# ---------------------------------------------------------------------------------- freeze


def test_symbolic_links_and_unreadable_files_are_entries_of_the_freeze(tmp_path: Path) -> None:
    app = tmp_path / "app"
    (app / "plan_b" / "agent").mkdir(parents=True)
    (app / "plan_b" / "agent" / "a.py").write_text("A = 1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "mod.py").write_text("B = 2\n")
    before = mf.measured_files(app)
    (app / "plan_b" / "agent" / "extra").symlink_to(outside, target_is_directory=True)
    after = mf.measured_files(app)
    assert after["plan_b/agent/extra"].startswith(f"symlink:{outside}:")
    # What the link reaches is hashed too: editing the target is drift.
    (outside / "mod.py").write_text("B = 3\n")
    assert mf.measured_files(app)["plan_b/agent/extra"] != after["plan_b/agent/extra"]
    assert mf._compare(before, after, "measured file") == [
        "measured file added: plan_b/agent/extra"
    ]
    if os.geteuid() != 0:
        target = app / "plan_b" / "agent" / "a.py"
        target.chmod(0)
        try:
            assert mf.measured_files(app)["plan_b/agent/a.py"].startswith("unreadable:")
        finally:
            target.chmod(0o644)


def test_the_freeze_records_the_runtime_and_the_per_run_cost_cap(tmp_path: Path) -> None:
    model = {"provider": "openrouter", "model_id": "m", "base_url": None, "max_run_cost_usd": 0.5}
    freeze = tmp_path / "freeze.json"
    data = mf.write_freeze(freeze, model=model)
    assert data["runtime"]["python"] == platform.python_version()
    assert set(data["runtime"]["distributions"]) == set(mf.RUNTIME_DISTRIBUTIONS)
    assert data["model"]["max_run_cost_usd"] == 0.5
    assert mf.verify_freeze(freeze).ok
    edited = data | {"runtime": data["runtime"] | {"python": "3.0.0"}}
    freeze.write_text(json.dumps(edited, indent=1, sort_keys=True) + "\n")
    assert mf.verify_freeze(freeze).drift == ["setting changed: runtime"]


def test_a_held_out_lock_checks_its_own_aggregate_and_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mf, "HELDOUT_PRIVATE_DIR", tmp_path / "none_private")
    monkeypatch.setattr(mf, "HELDOUT_PUBLIC_DIR", tmp_path / "none_public")
    lock = tmp_path / "heldout.json"
    good = {
        "artifact": mf.HELDOUT_ARTIFACT,
        "protocol_version": mf.PROTOCOL_VERSION,
        "files": {},
        "files_sha256": mf.tree_hash({}),
        "suites": {},
        "freeze_sha256": None,
    }
    mf.write_json(good, lock)
    assert mf.verify_heldout(lock).ok
    mf.write_json(good | {"files_sha256": "0" * 64}, lock)
    assert "files_sha256 does not match" in mf.verify_heldout(lock).drift[0]
    mf.write_json(good | {"protocol_version": "x/0"}, lock)
    assert "protocol version" in mf.verify_heldout(lock).drift[0]
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}")
    mf.write_json(good, lock)
    assert "was not made against freeze.json" in mf.verify_heldout(lock, freeze).drift[0]


# ---------------------------------------------------------------------------------- order


def test_a_subset_keeps_the_positions_of_the_full_order() -> None:
    seeds = [101, 202, 303]
    full = {e.key: e.position for e in build_plan(["dev01"], ["P0", "P1", "P2", "P3"], seeds, 7)}
    for subset in (["P0"], ["P1", "P3"]):
        part = build_plan(["dev01"], subset, seeds, 7)
        assert part and all(full[e.key] == e.position for e in part)
        assert {e.policy for e in part} == set(subset)


def test_a_link_in_the_held_out_directory_is_its_own_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "eval_private"
    private.mkdir()
    monkeypatch.setattr(mf, "HELDOUT_PRIVATE_DIR", private)
    monkeypatch.setattr(mf, "HELDOUT_PUBLIC_DIR", tmp_path / "none")
    case = private / "k7q2.json"
    case.write_text("{}")
    (private / "notes").symlink_to(case)
    before = mf.heldout_files()
    assert len(before) == 2 and before[mf._rel(case)] == mf.file_hash(case)
    case.write_text('{"edited": true}')
    drift = mf._compare(before, mf.heldout_files(), "held-out file")
    assert sorted(drift) == sorted(
        f"held-out file changed: {mf._rel(p)}" for p in (case, private / "notes")
    )


def test_a_trace_left_by_a_failed_episode_is_kept_aside(tmp_path: Path) -> None:
    out = tmp_path / "failed"
    key = "dev04__P0__once"
    trace = out / "episodes" / key / "trace.json.gz"
    trace.parent.mkdir(parents=True)
    trace.write_bytes(b"partial")
    task = {
        "out": str(out),
        "work": str(out / "work"),
        "episode": {
            "key": key,
            "case_ref": "dev04",
            "policy": "P0",
            "choice": "rules",
            "seed": None,
            "trial": 1,
            "position": 1,
        },
        "suite": "campus",
        "case_id": "dev04",
        "expected_class": "goal",
        "hook": None,
    }
    runmod._record_failure(task, "timeout", "no result after 900 s", 900.0)
    assert not trace.exists()
    assert (out / "runner_private" / "failed" / f"{key}.trace.json.gz").read_bytes() == b"partial"
    row = suite_metrics(load_results_with(out, key))["episodes"][0]
    assert row["status"] == "timeout"


def load_results_with(out: Path, key: str) -> dict[str, Any]:
    plan = {
        "suite": "campus",
        "heldout": False,
        "policies": ["P0"],
        "seeds": [],
        "case_refs": ["dev04"],
        "episodes": [
            {
                "key": key,
                "case_ref": "dev04",
                "policy": "P0",
                "seed": None,
                "trial": 1,
                "position": 1,
            }
        ],
    }
    (out / "plan.json").write_text(json.dumps(plan))
    return load_results(out)
