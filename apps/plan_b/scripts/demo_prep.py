"""Prepare a clean state for the seven-minute demo (PEEAI_plan/handoffs/wave_2/DEMO.md).

Usage (from apps/plan_b, after `npm run build` in web/; no paid call, no key read):

    uv run python scripts/demo_prep.py [--dest var/demo] [--port 8790] [--serve]

It (re)creates ``<dest>`` with two directories:

* ``state/``: an empty state directory. ``plan-b serve --var <dest>/state`` creates a fresh
  SQLite database in it, and a moderator code in ``state/moderator_code.txt`` (mode 0600) unless
  ``PLAN_B_MODERATOR_CODE`` is set.
* ``replays/``: copies of the recorded traces in ``data/recorded/`` (from the Wave 2
  packet), each checked with the same integrity rules as ``plan-b verify-trace``; a trace
  that fails is not copied. These are what the board's
  **Recorded replay** lists for the offline fallback. They are recordings of runs that happened,
  never a new trial.

A ``<dest>`` from an earlier run of this script (it holds the marker file ``.demo_prep``) is
removed first: that is the reset between rehearsals. Any other non-empty ``<dest>`` is refused.
It then prints the serve command and the URLs. With ``--serve`` it becomes ``plan-b serve`` on
127.0.0.1 in the foreground (one process: Ctrl+C or its PID stops it). Nothing here reads the
model endpoint configuration or a key: whether the model-driven choices are available is shown
by the moderator panel.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
EVIDENCE_TRACES = APP / "data" / "recorded"
MARKER = ".demo_prep"
DEFAULT_PORT = 8790
# The traces the runbook opens by name (DEMO.md): the live agent's (P2) paid-backup run, P3's run
# of the same case, P1's first pantry run (failed on a defect in our P1 harness, kept on record)
# and its rerun under the fixed prompt, the live agent's pantry run, and the deterministic one.
DEMO_TRACES = (
    "live_p2-live_dev02_trace.json",
    "live_p3-verify-all_dev02_trace.json",
    "live_p1-tool-use_pantry_dev01_trace.json",
    "live_p1-tool-use_pantry_dev01_r2_trace.json",
    "live_p2-live_pantry_dev01_trace.json",
    "pantry_dev01_trace.json",
)


@dataclass(frozen=True)
class Prepared:
    dest: Path
    state: Path
    replays: Path
    copied: tuple[str, ...]
    refused: tuple[tuple[str, str], ...]


def prepare(dest: Path, traces: Path = EVIDENCE_TRACES) -> Prepared:
    """(Re)create ``dest`` with an empty state directory and the verified recorded traces."""
    from plan_b.evaluation.export_trace import verify_trace_bytes

    dest = dest.resolve()
    if dest.exists():
        if not (dest / MARKER).is_file() and any(dest.iterdir()):
            raise SystemExit(f"refusing to replace {dest}: it was not made by demo_prep.py")
        shutil.rmtree(dest)
    state = dest / "state"
    replays = dest / "replays"
    state.mkdir(parents=True)
    replays.mkdir()
    (dest / MARKER).write_text("made by apps/plan_b/scripts/demo_prep.py; safe to delete\n")
    copied: list[str] = []
    refused: list[tuple[str, str]] = []
    for trace in sorted(traces.glob("*.json")):
        data = trace.read_bytes()
        problems = verify_trace_bytes(data)
        if problems:
            refused.append((trace.name, "; ".join(problems)))
            continue
        (replays / trace.name).write_bytes(data)
        copied.append(trace.name)
    return Prepared(dest, state, replays, tuple(copied), tuple(refused))


def serve_command(prepared: Prepared, port: int) -> list[str]:
    return [
        "uv",
        "run",
        "plan-b",
        "serve",
        "--port",
        str(port),
        "--var",
        str(prepared.state),
        "--replay-dir",
        str(prepared.replays),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dest", default=str(APP / "var" / "demo"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--serve", action="store_true", help="start plan-b serve afterwards")
    args = parser.parse_args()

    prepared = prepare(Path(args.dest))
    base = f"http://127.0.0.1:{args.port}/"
    print(f"clean demo state: {prepared.state} (empty; the database is created on first serve)")
    print(f"recorded replays: {prepared.replays} ({len(prepared.copied)} traces verified intact)")
    for name, why in prepared.refused:
        print(f"  NOT copied (integrity check failed): {name}: {why}")
    missing = [n for n in DEMO_TRACES if n not in prepared.copied]
    if missing:
        print(f"  missing traces the runbook opens: {', '.join(missing)}")
    if not (APP / "web" / "dist" / "index.html").is_file():
        print("  web/dist is missing: run `npm run build` in web/ first")
    print()
    print("serve: " + " ".join(serve_command(prepared, args.port)))
    print(f"board (moderator sign-in): {base}")
    print(f"moderator code: {prepared.state / 'moderator_code.txt'} after the first start")
    print("  (or set PLAN_B_MODERATOR_CODE before serving)")
    for name in DEMO_TRACES:
        if name in prepared.copied:
            print(f"replay: {base}#/replay/{name}")
    if missing or prepared.refused:
        return 1
    if args.serve:
        # Become the same server as the printed command (one process: Ctrl+C or its PID stops it).
        sys.stdout.flush()
        os.chdir(APP)
        os.execv(
            sys.executable,
            [sys.executable, "-m", "plan_b.cli", *serve_command(prepared, args.port)[3:]],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
