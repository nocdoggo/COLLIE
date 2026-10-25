"""A second held-out set (the v1.2 harness): case-scoped held-out manifests.

``plan-b eval lock-heldout --manifest heldout2.json --cases ...`` writes a lock that records its
``case_scope`` and covers only the named cases' files; ``verify-freeze`` and ``eval run`` honor
that scope. Everything runs on synthetic held-out cases (copies of development cases) in
temporary directories, with a temporary manifests directory: the real ``scenarios/*/eval/``
and ``evaluation/manifests/`` are never read or written.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from plan_b.cli import main as cli_main
from plan_b.evaluation import manifest as mf
from plan_b.evaluation import run as runmod
from plan_b.evaluation.run import RunRefused, RunSummary, run_evaluation, scoped_heldout_cases
from tests.test_eval_harness import _heldout_case

MODEL = {"provider": "openrouter", "model_id": "test/model", "base_url": None}


def _quiet(_line: str) -> None:
    return None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Temporary held-out directories and manifests directory, with three synthetic campus
    cases: C01 (ref hxa1), C03 (ref hxb2, a negative control) and C05 (ref hxc3). The measured
    files and the code-declared settings are computed once and held for the test, so an
    unrelated edit of the working tree while it runs does not trip the code freeze; these
    tests are about the held-out lock (``test_eval_manifest.py`` covers the code freeze)."""
    snapshot = mf.measured_files()
    declared = mf.settings(model=MODEL)

    def settings(
        *,
        seeds: Any = mf.DEFAULT_SEEDS,
        order_seed: int = mf.DEFAULT_ORDER_SEED,
        model: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chosen = dict(model) if model is not None else declared["model"]
        return declared | {"seeds": list(seeds), "order_seed": order_seed, "model": chosen}

    monkeypatch.setattr(mf, "measured_files", lambda app_dir=mf.APP_DIR: dict(snapshot))
    monkeypatch.setattr(mf, "settings", settings)
    private, public = tmp_path / "eval_private", tmp_path / "eval_public"
    manifests = tmp_path / "manifests"
    for d in (private, public, manifests):
        d.mkdir()
    monkeypatch.setattr(mf, "HELDOUT_PRIVATE_DIR", private)
    monkeypatch.setattr(mf, "HELDOUT_PUBLIC_DIR", public)
    monkeypatch.setattr(mf, "MANIFEST_DIR", manifests)
    cases = {
        "C01": _heldout_case(private, public, dev="dev01", ref="hxa1", case_id="C01"),
        "C03": _heldout_case(
            private, public, dev="dev04", ref="hxb2", case_id="C03", negative_control=True
        ),
        "C05": _heldout_case(private, public, dev="dev01", ref="hxc3", case_id="C05"),
    }
    freeze = manifests / "freeze_v1_2.json"
    mf.write_freeze(freeze, model=MODEL)
    yield {
        "private": private,
        "public": public,
        "manifests": manifests,
        "cases": cases,
        "freeze": freeze,
        "heldout2": manifests / "heldout2.json",
    }


def _rels(files: dict[str, Path]) -> set[str]:
    return {mf._rel(p) for p in files.values()}


def _lock2(capsys: pytest.CaptureFixture[str], *cases: str) -> tuple[int, str]:
    code = cli_main(
        [
            "eval",
            "lock-heldout",
            "--manifest",
            "heldout2.json",
            "--freeze",
            "freeze_v1_2.json",
            "--cases",
            *cases,
        ]
    )
    return code, capsys.readouterr().out


def _verify2(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = cli_main(
        ["eval", "verify-freeze", "--freeze", "freeze_v1_2.json", "--heldout", "heldout2.json"]
    )
    return code, capsys.readouterr().out


def test_bare_manifest_names_resolve_in_the_manifests_directory(
    world: dict[str, Any], tmp_path: Path
) -> None:
    assert mf.manifest_path("heldout2.json") == world["manifests"] / "heldout2.json"
    assert mf.manifest_path(str(tmp_path / "x.json")) == tmp_path / "x.json"
    assert mf.manifest_path("./x.json") == Path("./x.json")
    assert mf.manifest_path("sub/x.json") == Path("sub/x.json")


def test_a_case_scoped_lock_covers_only_its_cases_files(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    # Ids and refs, comma- and space-separated, mixed.
    code, out = _lock2(capsys, "C01,", "hxc3")
    assert code == 0, out
    assert "case scope C01, C05" in out
    data = json.loads(world["heldout2"].read_text())
    assert data["case_scope"] == ["C01", "C05"]
    assert [c["case_id"] for c in data["suites"]["campus"]] == ["C01", "C05"]
    cases = world["cases"]
    assert set(data["files"]) == _rels(cases["C01"]) | _rels(cases["C05"])
    assert not set(data["files"]) & _rels(cases["C03"])
    assert data["files_sha256"] == mf.tree_hash(data["files"])
    public = {mf._rel(cases[c]["public"]) for c in ("C01", "C05")}
    assert data["public_files_sha256"] == mf.tree_hash(
        {k: v for k, v in data["files"].items() if k in public}
    )
    assert data["private_files_sha256"] == mf.tree_hash(
        {k: v for k, v in data["files"].items() if k not in public}
    )
    assert data["freeze_sha256"] == mf.manifest_digest(world["freeze"])
    check = mf.verify_heldout(world["heldout2"], freeze_path=world["freeze"])
    assert check.ok and check.detail["case_scope"] == ["C01", "C05"]
    code, out = _verify2(capsys)
    assert code == 0, out
    assert "heldout2.json: verified" in out and "case_scope" in out


def test_unknown_or_repeated_cases_are_refused(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _lock2(capsys, "C01", "C99")
    assert code == 1
    assert "unknown held-out case(s): C99" in out and "C01, C03, C05" in out
    code, out = _lock2(capsys, "C01", "hxa1")
    assert code == 1 and "a second time" in out
    code, out = _lock2(capsys, ",")
    assert code == 1 and "names no case" in out
    assert not world["heldout2"].exists()


def test_scoped_verification_ignores_other_cases_and_catches_its_own(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert _lock2(capsys, "C01", "C05")[0] == 0
    # A v1.1-style whole-directory lock (no --cases, the --out alias) over the same tree.
    whole = tmp_path / "heldout_v11.json"
    assert (
        cli_main(["eval", "lock-heldout", "--out", str(whole), "--freeze", str(world["freeze"])])
        == 0
    )
    capsys.readouterr()
    assert "case_scope" not in json.loads(whole.read_text())
    assert mf.verify_heldout(whole).ok
    # An out-of-scope case file and a new file: no drift for the scoped lock...
    other = world["cases"]["C03"]["eval"]
    other.write_text(other.read_text() + " ")
    (world["private"] / "notes.txt").write_text("x\n")
    assert mf.verify_heldout(world["heldout2"]).ok
    code, out = _verify2(capsys)
    assert code == 0, out
    # ...while the whole-directory lock keeps its v1.1 behavior.
    drift = mf.verify_heldout(whole).drift
    assert f"held-out file changed: {mf._rel(other)}" in drift
    assert f"held-out file added: {mf._rel(world['private'] / 'notes.txt')}" in drift
    # A scoped file: drift.
    mine = world["cases"]["C05"]["eval"]
    mine.write_text(mine.read_text() + " ")
    check = mf.verify_heldout(world["heldout2"])
    assert check.drift == [f"held-out file changed: {mf._rel(mine)}"]
    code, out = _verify2(capsys)
    assert code == 1 and "DRIFT" in out and mf._rel(mine) in out
    mine.write_text(mine.read_text()[:-1])
    assert mf.verify_heldout(world["heldout2"]).ok
    # A removed scoped file is drift too.
    gone = world["cases"]["C01"]["public"]
    saved = gone.read_bytes()
    gone.unlink()
    assert f"held-out file removed: {mf._rel(gone)}" in mf.verify_heldout(world["heldout2"]).drift
    gone.write_bytes(saved)
    # A case_scope edited by hand no longer matches the locked cases.
    data = json.loads(world["heldout2"].read_text())
    mf.write_json(data | {"case_scope": ["C01"]}, world["heldout2"])
    assert (
        "case_scope does not match the locked cases" in mf.verify_heldout(world["heldout2"]).drift
    )


def test_a_run_under_a_scoped_lock_defaults_to_its_cases_and_refuses_drift(
    world: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate and the case selection, up to the run plan: ``_run_plan`` is replaced by a
    recorder, so no episode process starts (``test_eval_harness.py`` runs held-out episodes)."""
    plans: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> RunSummary:
        plans.append(kwargs["plan"])
        n = len(kwargs["episodes"])
        return RunSummary(kwargs["out"], n, 0, n, {"completed": n}, kwargs["heldout"])

    monkeypatch.setattr(runmod, "_run_plan", record)
    assert _lock2(capsys, "C01", "C05")[0] == 0
    common: dict[str, Any] = {
        "suite": "campus",
        "policies": ["P0"],
        "seeds": list(mf.DEFAULT_SEEDS),
        "freeze_path": mf.manifest_path("freeze_v1_2.json"),
        "heldout_path": mf.manifest_path("heldout2.json"),
        "log": _quiet,
    }
    assert scoped_heldout_cases(world["heldout2"], "campus") == ["C01", "C05"]
    with pytest.raises(RunRefused, match="locks no pantry case"):
        scoped_heldout_cases(world["heldout2"], "pantry")
    # A held-out case outside the scoped lock is refused.
    with pytest.raises(RunRefused, match=r"hxb2 \(C03\) is not in the held-out lock heldout2"):
        run_evaluation(**common, cases=["C03"], out=tmp_path / "outside")
    # No --cases: the lock's cases of the suite, not every held-out case.
    out = tmp_path / "scoped"
    summary = run_evaluation(**common, cases=None, out=out, jobs=2)
    assert summary.heldout and summary.planned == 2
    plan = plans[-1]
    assert plan["heldout"] and plan["case_refs"] == ["hxa1", "hxc3"]
    assert plan["episode_caps"]["phase"] == "frozen"
    assert plan["freeze_sha256"] == mf.manifest_digest(world["freeze"])
    assert plan["heldout_sha256"] == mf.manifest_digest(world["heldout2"])
    # Through the CLI with bare names: an out-of-scope edit does not stop a scoped run's gate.
    other = world["cases"]["C03"]["case"]
    other.write_text(other.read_text() + " ")
    args = ["eval", "run", "--suite", "campus", "--policies", "P0"]
    args += ["--freeze", "freeze_v1_2.json", "--heldout", "heldout2.json"]
    assert cli_main([*args, "--out", str(tmp_path / "cli")]) == 0
    assert "2 planned" in capsys.readouterr().out
    assert plans[-1]["case_refs"] == ["hxa1", "hxc3"]
    other.write_text(other.read_text()[:-1])
    # A scoped file drifts: refused before anything runs.
    mine = world["cases"]["C01"]["eval"]
    mine.write_text(mine.read_text() + " ")
    with pytest.raises(RunRefused, match="held-out file changed"):
        run_evaluation(**common, cases=None, out=tmp_path / "drift")
    assert cli_main([*args, "--out", str(tmp_path / "cli_drift")]) == 2
    assert "run refused" in capsys.readouterr().out
    assert len(plans) == 2  # neither refused run reached the plan
    mine.write_text(mine.read_text()[:-1])
    # The freeze manifest drifts: refused too (an edited setting, then an edited file hash).
    freeze = world["freeze"]
    original = freeze.read_text()
    data = json.loads(original)
    freeze.write_text(json.dumps(data | {"seeds": [1, 2, 3]}, indent=1, sort_keys=True) + "\n")
    with pytest.raises(RunRefused, match="heldout2.json was locked against a different freeze"):
        run_evaluation(**(common | {"seeds": [1, 2, 3]}), cases=None, out=tmp_path / "f1")
    files = dict(data["files"])
    files["plan_b/tools/executor.py"] = "f" * 64
    freeze.write_text(json.dumps(data | {"files": files}, indent=1, sort_keys=True) + "\n")
    with pytest.raises(RunRefused, match="freeze does not verify"):
        run_evaluation(**common, cases=None, out=tmp_path / "f2")
    freeze.write_text(original)
    assert mf.verify_heldout(world["heldout2"], freeze_path=freeze).ok
    assert len(plans) == 2


def test_a_later_set_takes_its_ids_classes_and_controls_from_its_evaluator_files(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Later ids of the protocol's form (C09 and up) load with their evaluator file's outcome
    class and negative-control flag, and a scoped lock covers them. Catches: the v1.1 id table
    refusing every later id, or applying C02-C04 as the only negative controls to later ids.
    An id outside the form, and a v1.1 id with the wrong class, are still refused."""
    private, public = world["private"], world["public"]
    _heldout_case(private, public, dev="dev01", ref="hxd4", case_id="C09")
    _heldout_case(private, public, dev="dev04", ref="hxe5", case_id="C10", negative_control=True)
    specs = {s.case_id: s for s in runmod.heldout_specs()}
    assert specs["C09"].outcome_class == "goal" and not specs["C09"].negative_control
    assert specs["C10"].negative_control
    assert _lock2(capsys, "C09", "C10")[0] == 0
    assert json.loads(world["heldout2"].read_text())["case_scope"] == ["C09", "C10"]
    _heldout_case(private, public, dev="dev01", ref="hxf6", case_id="X11")
    with pytest.raises(RunRefused, match="not a campus case of the protocol"):
        runmod.heldout_specs()
    (private / "hxf6.json").unlink()
    (private / "hxf6.eval.json").unlink()
    _heldout_case(private, public, dev="dev01", ref="hxg7", case_id="C08")
    with pytest.raises(RunRefused, match="outcome class goal"):
        runmod.heldout_specs()


def test_a_later_set_may_keep_its_files_in_a_subdirectory(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches: a loader that scans only the top level of ``eval/`` (the later set would be
    "unknown"), or one that lets a case ref appear twice across directories."""
    private, public = world["private"] / "set2", world["public"] / "set2"
    private.mkdir()
    public.mkdir()
    files = _heldout_case(private, public, dev="dev01", ref="hxh8", case_id="C11")
    assert "C11" in {s.case_id for s in runmod.heldout_specs()}
    assert _lock2(capsys, "C11")[0] == 0
    data = json.loads(world["heldout2"].read_text())
    assert set(data["files"]) == _rels(files)
    assert _verify2(capsys)[0] == 0
    _heldout_case(world["private"], world["public"], dev="dev01", ref="hxh8", case_id="C12")
    with pytest.raises(RunRefused, match="two|already taken"):
        runmod.heldout_specs()


def test_freeze_writes_a_bare_name_into_the_manifests_directory(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """``plan-b eval freeze --out freeze_v1_2.json`` writes next to the other manifests, as
    ``lock-heldout``, ``verify-freeze`` and ``run`` read it. Catches: a bare name written into
    the working directory."""
    assert cli_main(["eval", "freeze", "--out", "freeze_x.json"]) == 0
    assert (world["manifests"] / "freeze_x.json").is_file()
    assert not Path("freeze_x.json").exists()
    capsys.readouterr()


def test_a_recorded_report_is_never_overwritten_with_different_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """audit2: re-rendering the v1.1 run of record with later report code changes its policy id
    line, so `eval report` refuses to replace a different report unless --force is given. The
    record itself is only read: the report goes to a copy of its report directory."""
    import shutil

    from plan_b.evaluation.report import ReportRefused, write_report

    record = mf.APP_DIR / "evaluation" / "results" / "wave3_heldout_20261025T1625Z" / "campus"
    copy = tmp_path / "report"
    shutil.copytree(record / "report", copy)
    before = {p.name: p.read_bytes() for p in copy.iterdir()}
    with pytest.raises(ReportRefused, match="different report"):
        write_report(record, copy)
    assert {p.name: p.read_bytes() for p in copy.iterdir()} == before
    assert cli_main(["eval", "report", "--results", str(record), "--out", str(copy)]) == 2
    assert "report refused" in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in copy.iterdir()} == before
    # The same content again is not a change, and --force replaces a different report.
    write_report(record, copy, force=True)
    write_report(record, copy)
    assert (copy / "evaluation_results.md").read_bytes() != before["evaluation_results.md"]
