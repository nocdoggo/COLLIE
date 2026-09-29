"""Stage D evaluation: the registered contrasts on the stage D runs. Committed before the runs.

Three hypothesis families (``PLAN.md``, stage D), each with Holm's step-down at 0.05 over its own
tests, on net reward per episode (``total_reward``), one-sided cluster sign-flip p-values and
seed-cluster bootstrap intervals exactly as stage C computes them (``confirm.contrast``: 100,000
flips and 10,000 draws, seed 20260927):

* ``high_margin`` (p/h = 19, the stage D pool): hedge - gate, hedge - arm 1 and hedge -
  content-free, on each primary model (6 tests).
* ``low_margin`` (p/h = 1, the same pool): hedge - gate on each primary model (2 tests).
* ``noisy_lead`` (p/h = 4, the stochastic-lead stratum): hedge - arm 1 on each primary model
  (2 tests).

Every run also gets stage C's full secondary readout (``confirm.evaluate_run``: every stage C
contrast on net and gross, null safety with the -25 margin, net by family, exposure, perception,
cost), and each low-margin run the non-inferiority of hedge - arm 1 over all its episodes at the
same margin.

Usage::

    uv run python -m analysis.commitment.confirm_d [--out-root out] [--out out/confirm_d.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest import mock

from analysis.commitment import confirm

MODELS = ("gemini-3.8-flash", "grok-4.20")
FAMILIES = {
    "high_margin": {
        "prefix": "d19",
        "profit": 19.0,
        "pool": "main",
        "tests": (
            ("cth-arm10", confirm.CTH, confirm.ARM10),
            ("cth-arm1", confirm.CTH, confirm.ARM1),
            ("cth-uniform", confirm.CTH, confirm.UNIFORM),
        ),
    },
    "low_margin": {
        "prefix": "d1",
        "profit": 1.0,
        "pool": "main",
        "tests": (("cth-arm10", confirm.CTH, confirm.ARM10),),
    },
    "noisy_lead": {
        "prefix": "dsl",
        "profit": 4.0,
        "pool": "stochastic",
        "tests": (("cth-arm1", confirm.CTH, confirm.ARM1),),
    },
}
EPISODES = {"main": 240, "stochastic": 40}


def run_name(family: str, model: str) -> str:
    return f"{FAMILIES[family]['prefix']}-{model}"


def check_run(root: Path, family: str, run: str) -> None:
    """Refuse a run whose pool, ratio or size is not the registered one."""
    spec = FAMILIES[family]
    stage = json.loads((root / run / "stage_d.json").read_text())
    manifest = json.loads((root / run / "run_manifest.json").read_text())
    if stage["pool"] != spec["pool"]:
        raise ValueError(f"{run}: pool {stage['pool']}, registered {spec['pool']}")
    if float(manifest["profit"]) != spec["profit"]:
        raise ValueError(f"{run}: profit {manifest['profit']}, registered {spec['profit']}")
    episodes = confirm.episode_frame(run).episode_id.nunique()
    if episodes != EPISODES[spec["pool"]]:
        raise ValueError(f"{run}: {episodes} episodes, registered {EPISODES[spec['pool']]}")


def evaluate(root: Path, models=MODELS) -> dict:
    out: dict = {
        "analysis_class": "exploratory",
        "registered_in": "analysis/commitment/PLAN.md, stage D",
        "families": {},
        "runs": {},
    }
    with mock.patch.object(confirm, "OUT", root):
        for family, spec in FAMILIES.items():
            tests, pvalues = {}, {}
            for model in models:
                run = run_name(family, model)
                check_run(root, family, run)
                frame = confirm.episode_frame(run)
                for name, treat, control in spec["tests"]:
                    key = f"{name}|{model}"
                    tests[key] = confirm.contrast(frame, treat, control, "net")
                    pvalues[key] = tests[key]["p_one_sided"]
                if run not in out["runs"]:
                    readout = confirm.evaluate_run(run)
                    if family == "low_margin":
                        overall = confirm.contrast(frame, confirm.CTH, confirm.ARM1, "net")
                        readout["overall_non_inferiority"] = {
                            **overall,
                            "margin": confirm.NULL_MARGIN,
                            "non_inferior": bool(overall["b"][0] > confirm.NULL_MARGIN),
                        }
                    out["runs"][run] = readout
            out["families"][family] = {
                "profit": spec["profit"],
                "pool": spec["pool"],
                "tests": tests,
                "holm": confirm.holm(pvalues),
            }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.confirm_d")
    ap.add_argument("--out-root", type=Path, default=confirm.OUT)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    args = ap.parse_args(argv)
    report = evaluate(args.out_root, tuple(args.models))
    path = args.out or args.out_root / "confirm_d.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for family, block in report["families"].items():
        for key, test in block["tests"].items():
            holm = block["holm"][key]
            print(
                f"{family:12s} {key:28s} {test['mean']:+9.1f} "
                f"[{test['b'][0]:.1f}, {test['b'][1]:.1f}] p={test['p_one_sided']:.4f} "
                f"{'reject' if holm['reject'] else 'no'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
