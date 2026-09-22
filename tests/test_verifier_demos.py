"""The checkpoint demos are executable audit surfaces, not untested documentation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def test_demand_demo_prints_the_registered_path_and_writes_plot(tmp_path: Path) -> None:
    plot = tmp_path / "demand-evidence.png"
    result = _run("collie.verify.demand", "--demo", "--plot", str(plot))
    assert "registered episode:" in result.stdout
    assert "e_value" in result.stdout
    assert f"wrote {plot}" in result.stdout
    assert plot.stat().st_size > 0


def test_arrival_demo_prints_power_validity_and_compound_lifecycle() -> None:
    result = _run("collie.verify.arrival", "--demo")
    assert "lost-shipment burst: activated=True" in result.stdout
    assert "noisy registered null: activated=False" in result.stdout
    assert "anytime_valid_collie_shockspec_only" in result.stdout
    assert "compound lifecycle timeline" in result.stdout


@pytest.mark.parametrize(
    ("script", "arguments", "exit_code"),
    [
        ("demand.py", ["--demo"], 0),
        ("arrival.py", ["--demo"], None),
    ],
)
def test_demo_main_blocks_are_covered_in_process(
    script: str,
    arguments: list[str],
    exit_code: int | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Mirror the subprocess audit under the coverage tracer, which does not follow children."""
    import runpy

    if script == "demand.py":
        arguments = [*arguments, "--plot", str(tmp_path / "covered-demand.png")]
    monkeypatch.setattr(sys, "argv", [script, *arguments])
    path = REPO_ROOT / "collie" / "verify" / script
    if exit_code is None:
        runpy.run_path(str(path), run_name="__main__")
    else:
        with pytest.raises(SystemExit) as caught:
            runpy.run_path(str(path), run_name="__main__")
        assert caught.value.code == exit_code
    assert capsys.readouterr().out
