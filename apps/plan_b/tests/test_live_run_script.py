"""A recorded live run's error names no local path (``scripts/run_live_cases.py``).

Run records go into the committed evidence packet. An error raised outside the provider, such
as an ``OSError`` from the spend ledger or the episode database, names its file, so its text is
recorded with the run's temporary directory, the repository and the home directory replaced.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

APP = Path(__file__).resolve().parents[1]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_live_cases", APP / "scripts" / "run_live_cases.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_run_error_is_recorded_without_local_paths(tmp_path: Path) -> None:
    script = _script()
    ledger = Path.home() / "planb" / "var" / "model_spend.json"
    denied = PermissionError(13, "Permission denied", str(ledger))
    message = script.public_message(denied, str(tmp_path))
    assert str(Path.home()) not in message
    assert message.endswith("'~/planb/var/model_spend.json'")

    db = tmp_path / "live.sqlite3"
    failed = OSError(f"cannot open {db}; the app is {script.APP}")
    message = script.public_message(failed, str(tmp_path))
    assert message == "cannot open <tmp>/live.sqlite3; the app is <repo>/apps/plan_b"


def test_a_long_run_error_is_cut_to_300_characters(tmp_path: Path) -> None:
    script = _script()
    assert len(script.public_message(ValueError("x" * 1000), str(tmp_path))) == 300
