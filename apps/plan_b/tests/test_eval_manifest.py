"""The Wave 3 freeze manifest (``plan_b.evaluation.manifest``) and ``plan-b eval verify-freeze``.

The drift tests freeze a copy of the measured tree in a temporary directory and change that
copy, so the real tree and the real ``evaluation/manifests/`` are never touched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from plan_b.cli import main as cli_main
from plan_b.evaluation import manifest as mf

APP = Path(__file__).resolve().parents[1]
MODEL = {"provider": "openrouter", "model_id": "test/model", "base_url": None}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of everything ``measured_files`` reads, fixture data included."""
    root = tmp_path / "app"
    shutil.copytree(APP / "plan_b", root / "plan_b", ignore=shutil.ignore_patterns("__pycache__"))
    for name in mf.MEASURED_FILES:
        shutil.copyfile(APP / name, root / name)
    return root


def _flip_one_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-2] = data[-2] ^ 0x01
    path.write_bytes(bytes(data))


def test_the_freeze_records_hashes_and_every_frozen_setting(tree: Path, tmp_path: Path) -> None:
    data = mf.write_freeze(tmp_path / "freeze.json", model=MODEL, app_dir=tree)
    files = data["files"]
    for measured in (
        "plan_b/agent/orchestrator.py",
        "plan_b/agent/policies/tool_use.py",
        "plan_b/agent/policies/verify_all.py",
        "plan_b/agent/prompts/tool_use.v2.txt",
        "plan_b/evaluation/policies/rules.py",
        "plan_b/evaluation/policies/pantry_rules.py",
        "plan_b/tools/executor.py",
        "plan_b/tools/handlers.py",
        "plan_b/domain/candidates.py",
        "plan_b/domain/constraints.py",
        "plan_b/domain/objective.py",
        "plan_b/domain/adapters/pantry.py",
        "plan_b/evaluation/scoring.py",
        "plan_b/evaluation/metrics.py",
        "plan_b/evaluation/run.py",
        "plan_b/scenarios/runner.py",
        "plan_b/scenarios/policy_host.py",
        "plan_b/world/world.py",
        "plan_b/store/migrations/0004_consumable_stock.sql",
        "uv.lock",
    ):
        assert measured in files, measured
    # Fixture data and the non-measured modules are excluded; heldout.json covers fixtures.
    assert not [
        f for f in files if f.startswith(("plan_b/scenarios/public", "plan_b/scenarios/private"))
    ]
    for excluded in ("plan_b/cli.py", "plan_b/evaluation/report.py", "plan_b/api/app.py"):
        assert excluded not in files
    assert not [f for f in files if "__pycache__" in f or f.endswith(".pyc")]
    assert data["files_sha256"] == mf.tree_hash(files)
    assert data["protocol_version"] == mf.PROTOCOL_VERSION
    assert data["model"] == MODEL
    assert data["seeds"] == list(mf.DEFAULT_SEEDS) and data["order_seed"] == mf.DEFAULT_ORDER_SEED
    assert data["episode_caps"] == mf.episode_caps()
    assert set(data["episode_caps"]) == {"max_tool_calls", "max_model_calls"}
    assert data["episode_timeout_s"] == mf.EPISODE_TIMEOUT_S
    assert data["p3_relevance_rule"].startswith("verify-all-relevance/")
    assert data["policies"] == {"P0": "rules", "P1": "tool-use", "P2": "live", "P3": "verify-all"}
    assert data["policy_ids"]["P2"].startswith("live/")
    assert data["policy_ids"]["P1"].startswith("tool-use/")
    assert data["policy_ids"]["P3"].startswith("verify-all/")
    assert set(data["policy_ids"]["P0"]) == {"event", "pantry"}
    assert set(data["prompts"]) >= {"interpret.v1", "choose_action.v1", "tool_use.v2"}
    assert data["generation"]["request_template"]["response_format"]["json_schema"]["strict"]
    assert data["retry_rules"] and data["model_response_cache"] is False
    with pytest.raises(ValueError):
        mf.compute_freeze(seeds=[1, 2], model=MODEL, app_dir=tree)


def test_verify_freeze_detects_a_one_byte_change(tree: Path, tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    mf.write_freeze(path, model=MODEL, app_dir=tree)
    assert mf.verify_freeze(path, app_dir=tree).ok
    target = tree / "plan_b" / "agent" / "orchestrator.py"
    original = target.read_bytes()
    _flip_one_byte(target)
    check = mf.verify_freeze(path, app_dir=tree)
    assert not check.ok
    assert check.drift == ["measured file changed: plan_b/agent/orchestrator.py"]
    target.write_bytes(original)
    assert mf.verify_freeze(path, app_dir=tree).ok
    # An added or removed measured file is drift too.
    added = tree / "plan_b" / "tools" / "extra.py"
    added.write_text("X = 1\n")
    assert mf.verify_freeze(path, app_dir=tree).drift == [
        "measured file added: plan_b/tools/extra.py"
    ]
    added.unlink()
    removed = tree / "plan_b" / "agent" / "prompts" / "interpret.v1.txt"
    saved = removed.read_bytes()
    removed.unlink()
    assert mf.verify_freeze(path, app_dir=tree).drift == [
        "measured file removed: plan_b/agent/prompts/interpret.v1.txt"
    ]
    removed.write_bytes(saved)


def test_fixture_data_and_excluded_files_cannot_trip_the_freeze(tree: Path, tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    mf.write_freeze(path, model=MODEL, app_dir=tree)
    _flip_one_byte(tree / "plan_b" / "scenarios" / "private" / "dev01.json")
    _flip_one_byte(tree / "plan_b" / "scenarios" / "public" / "campus_showcase.json")
    held = tree / "plan_b" / "scenarios" / "private" / "eval"
    held.mkdir(exist_ok=True)
    (held / "x.json").write_text("{}\n")
    _flip_one_byte(tree / "plan_b" / "evaluation" / "report.py")
    _flip_one_byte(tree / "plan_b" / "cli.py")
    assert mf.verify_freeze(path, app_dir=tree).ok


def test_a_tampered_manifest_or_setting_is_drift(tree: Path, tmp_path: Path) -> None:
    path = tmp_path / "freeze.json"
    data = mf.write_freeze(path, model=MODEL, app_dir=tree)
    path.write_text(
        json.dumps(data | {"episode_caps": {"max_tool_calls": 16, "max_model_calls": 8}})
    )
    assert mf.verify_freeze(path, app_dir=tree).drift == ["setting changed: episode_caps"]
    files = dict(data["files"])
    files["plan_b/scenarios/runner.py"] = "0" * 64
    path.write_text(json.dumps(data | {"files": files}))
    drift = mf.verify_freeze(path, app_dir=tree).drift
    assert "measured file changed: plan_b/scenarios/runner.py" in drift
    assert "files_sha256 does not match the recorded file hashes" in drift
    path.write_text("not json")
    assert not mf.verify_freeze(path, app_dir=tree).ok
    assert not mf.verify_freeze(tmp_path / "absent.json", app_dir=tree).present


def test_the_cli_fails_loudly_on_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "freeze.json"
    absent = tmp_path / "heldout.json"
    assert cli_main(["eval", "verify-freeze", "--freeze", str(path), "--heldout", str(absent)]) == 1
    assert "no freeze manifest" in capsys.readouterr().out
    assert cli_main(["eval", "freeze", "--out", str(path), "--seeds", "5,6,7"]) == 0
    data = json.loads(path.read_text())
    assert data["seeds"] == [5, 6, 7]
    # The real tree against its own fresh freeze: verified (held-out lock not required yet).
    assert cli_main(["eval", "verify-freeze", "--freeze", str(path), "--heldout", str(absent)]) == 0
    assert "verified" in capsys.readouterr().out
    assert (
        cli_main(
            [
                "eval",
                "verify-freeze",
                "--freeze",
                str(path),
                "--heldout",
                str(absent),
                "--require-heldout",
            ]
        )
        == 1
    )
    capsys.readouterr()
    files = dict(data["files"])
    files["plan_b/tools/executor.py"] = "f" * 64
    path.write_text(json.dumps(data | {"files": files}))
    assert cli_main(["eval", "verify-freeze", "--freeze", str(path), "--heldout", str(absent)]) == 1
    out = capsys.readouterr().out
    assert "measured file changed: plan_b/tools/executor.py" in out
    assert "FREEZE VERIFICATION FAILED" in out
