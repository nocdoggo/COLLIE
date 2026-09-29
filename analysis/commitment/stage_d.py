"""Stage D runner: the frozen stage C runner on stage D's two layouts. Exploratory.

Stage D (``PLAN.md``) reuses stage C's runner, arm set, method and endpoints unchanged; only the
episodes differ. This wrapper swaps the layout the runner builds, for the duration of one call,
and records which pool it used next to the run's manifest (``stage_d.json``):

* ``--pool main``: the stage D pool, ``seed = family * 1_000_000 + D_BASE + i`` for
  ``i = 0..7`` in every family (48 units, 240 episodes; the same unit construction, conditions,
  twins and alerts as stage C). Run at ``--profit 19`` and ``--profit 1``.
* ``--pool stochastic``: the stochastic-lead stratum reserved in ``episodes.py`` (family 4,
  ``i = 12..19`` of stage C's base, 8 units, 40 episodes), whose per-order lead-time noise is
  the registered arrival null's delay law. Run at ``--profit 4``.

``--base`` moves either pool (the structural tests use ``THROWAWAY_BASE``); every other argument
goes to ``analysis.commitment.runner`` unchanged.

Usage::

    uv run python -m analysis.commitment.stage_d --pool main --profit 19 \\
        --endpoint gemini-3.8-flash --run-name d19-gemini-3.8-flash --allow-live [...]
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

import analysis.commitment.arms  # noqa: F401  (registers the confirm arm set)
import analysis.commitment.runner as runner
from analysis.commitment.episodes import (
    FRESH_BASE,
    STOCHASTIC_FIRST_INDEX,
    build_layout,
    build_stochastic_lead_layout,
)

D_BASE = 200_000
N_PER_FAMILY = 8
STOCHASTIC_UNITS = 8
"""Module 03's dev/cal bank renders distinct texts for four units per split and family."""


def layout_builder(pool: str, base: int):
    if pool == "main":

        def build(root: Path, n_per_family: int, *, profit: float):
            return build_layout(root, n_per_family, profit=profit, base=base)

    elif pool == "stochastic":

        def build(root: Path, n_per_family: int, *, profit: float):
            return build_stochastic_lead_layout(
                root,
                base=base,
                first_index=STOCHASTIC_FIRST_INDEX,
                n_units=STOCHASTIC_UNITS,
                profit=profit,
            )

    else:
        raise ValueError(f"unknown pool {pool!r}")
    return build


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.stage_d", add_help=True)
    ap.add_argument("--pool", choices=("main", "stochastic"), required=True)
    ap.add_argument("--base", type=int, default=None)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--out-root", type=Path, default=runner.OUT_ROOT)
    args, rest = ap.parse_known_args(argv)
    if "--layout" in rest or "--arm-set" in rest or "--n-per-family" in rest:
        raise SystemExit("stage D fixes --layout, --arm-set and --n-per-family")
    base = args.base if args.base is not None else (D_BASE if args.pool == "main" else FRESH_BASE)
    forwarded = [
        "--layout",
        "fresh",
        "--arm-set",
        "confirm",
        "--n-per-family",
        str(N_PER_FAMILY),
        "--run-name",
        args.run_name,
        "--out-root",
        str(args.out_root),
        *rest,
    ]
    with mock.patch.object(runner, "build_layout", layout_builder(args.pool, base)):
        code = runner.main(forwarded)
    out_dir = args.out_root / args.run_name
    if out_dir.is_dir():
        (out_dir / "stage_d.json").write_text(
            json.dumps(
                {
                    "stage": "D",
                    "pool": args.pool,
                    "base": base,
                    "units": (
                        f"families 1-6, i = 0..{N_PER_FAMILY - 1}"
                        if args.pool == "main"
                        else f"family 4, i = {STOCHASTIC_FIRST_INDEX}.."
                        f"{STOCHASTIC_FIRST_INDEX + STOCHASTIC_UNITS - 1}"
                    ),
                    "note": "run_manifest.json says layout 'fresh'; this file names the pool",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
