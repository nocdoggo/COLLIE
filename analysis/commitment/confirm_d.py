"""Stage D evaluation: the registered contrasts on the stage D runs. Committed before the runs.

Three hypothesis families (``PLAN.md``, stage D), each with Holm's step-down at 0.05 over its own
tests, on net reward per episode (``total_reward``), one-sided cluster sign-flip p-values and
seed-cluster bootstrap intervals as stage C computes them (``confirm.contrast``: 100,000 flips
and 10,000 draws, seed 20260927), with two changes made before any stage D run (amendment DA2):
the flip test's tie tolerance is relative to the observed mean, and with 16 clusters or fewer the
p-value is the exact enumeration over all sign patterns, which decides:

* ``high_margin`` (p/h = 19, the stage D pool): hedge - gate, hedge - arm 1 and hedge -
  content-free, on each primary model (6 tests).
* ``low_margin`` (p/h = 1, the same pool): hedge - gate on each primary model (2 tests).
* ``noisy_lead`` (p/h = 4, the stochastic-lead stratum): hedge - arm 1 on each primary model
  (2 tests; 8 clusters, so the exact p decides).

Every run also gets stage C's full secondary readout (``confirm.evaluate_run``: every stage C
contrast on net and gross, null safety with the -25 margin, net by family, exposure, perception,
cost), and each low-margin run the non-inferiority of hedge - arm 1 over all its episodes at the
same margin.

A run is refused unless it is the registered one (amendments DA1 and DA7): its pool, base and
ratio, the exact set of registered seeds, a complete (not partial) run of arm set ``confirm`` on
the run name's ladder rung and its served model id, and every arm a contrast reads on every
episode. Only the default two-model call is
confirmatory (DA6); ``--models`` with a subset is refused unless ``--not-confirmatory`` is given,
and ``--throwaway-base`` (structural checks) always marks the output as not confirmatory. A family
with a refused run is recorded as not evaluated, with the reasons; the other families are (DA9).

Usage::

    uv run python -m analysis.commitment.confirm_d [--out-root out] [--out out/confirm_d.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from analysis.commitment import confirm
from analysis.commitment.endpoints import LADDER
from analysis.commitment.episodes import (
    FRESH_BASE,
    STOCHASTIC_FIRST_INDEX,
    fresh_units,
    stochastic_lead_units,
)
from analysis.commitment.stage_d import D_BASE, N_PER_FAMILY, STOCHASTIC_UNITS

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
REGISTERED_BASE = {"main": D_BASE, "stochastic": FRESH_BASE}
COMPLETE_ARMS = frozenset(
    {arm for _, t, c, _ in confirm.CONTRASTS for arm in (t, c)}
    | {arm for spec in FAMILIES.values() for _, t, c in spec["tests"] for arm in (t, c)}
)
"""Arms every contrast reads; each must have every episode. The alert upper bound and the
oracle run on shocked episodes only, by design, and enter no contrast."""
EXACT_MAX_CLUSTERS = 16
RELATIVE_TIE_TOLERANCE = 1e-9
_SEED = re.compile(r"/s(\d+)/")


def run_name(family: str, model: str) -> str:
    return f"{FAMILIES[family]['prefix']}-{model}"


def registered_seeds(pool: str, base: int) -> frozenset[int]:
    """The unit seeds a pool must cover exactly (arithmetic only; nothing is materialised)."""
    if pool == "main":
        return frozenset(u.seed for u in fresh_units(N_PER_FAMILY, base=base))
    units = stochastic_lead_units(
        base=base, first_index=STOCHASTIC_FIRST_INDEX, n_units=STOCHASTIC_UNITS
    )
    return frozenset(u.seed for u in units)


def check_run(root: Path, family: str, model: str, *, base: int | None = None) -> None:
    """Refuse a run that is not the registered one. ``base`` other than the registered one is
    for structural checks on the throwaway pool, and skips the model and run-name checks."""
    spec = FAMILIES[family]
    run = run_name(family, model)
    pool = spec["pool"]
    expected_base = REGISTERED_BASE[pool] if base is None else base
    stage = json.loads((root / run / "stage_d.json").read_text())
    manifest = json.loads((root / run / "run_manifest.json").read_text())
    problems = []
    if stage["pool"] != pool:
        problems.append(f"pool {stage['pool']}, registered {pool}")
    if int(stage["base"]) != expected_base:
        problems.append(f"base {stage['base']}, expected {expected_base}")
    if float(manifest["profit"]) != spec["profit"]:
        problems.append(f"profit {manifest['profit']}, registered {spec['profit']}")
    if manifest.get("partial") is not False:
        problems.append("the run is partial")
    if manifest.get("arm_set") != "confirm":
        problems.append(f"arm set {manifest.get('arm_set')!r}, registered 'confirm'")
    if base is None and manifest.get("run_name") != run:
        problems.append(f"manifest run name {manifest.get('run_name')!r}")
    if base is None:
        rung = manifest.get("ladder_rung", {}).get("name")
        served = manifest.get("endpoint", {}).get("model_id")
        if rung != model or served != LADDER[model].model_id:
            problems.append(f"ladder rung {rung!r} serving {served!r}, run is {model}")
    with mock.patch.object(confirm, "OUT", root):
        frame = confirm.episode_frame(run)
    ids = set(frame.episode_id)
    if len(ids) != EPISODES[pool]:
        problems.append(f"{len(ids)} episodes, registered {EPISODES[pool]}")
    seeds = {int(m.group(1)) for m in map(_SEED.search, ids) if m}
    if seeds != registered_seeds(pool, expected_base):
        problems.append("its unit seeds are not the registered pool's")
    for arm in sorted(COMPLETE_ARMS):
        rows = frame[frame.arm == arm]
        if len(rows) != len(ids) or set(rows.episode_id) != ids:
            problems.append(f"arm {arm} has {len(rows)} rows for {len(ids)} episodes")
    if problems:
        raise ValueError(f"{run}: " + "; ".join(problems))


def sign_flip(values: pd.Series, clusters: pd.Series) -> dict:
    """One-sided p for mean > 0 from sign flips of whole-cluster sums: stage C's random flips
    (same seed and draws) with a tie tolerance relative to the observed mean, and the exact
    enumeration over all ``2^k`` patterns when there are at most ``EXACT_MAX_CLUSTERS``."""
    sums = values.groupby(clusters.values).sum().to_numpy(dtype=float)
    n = len(values)
    observed = sums.sum() / n
    tolerance = RELATIVE_TIE_TOLERANCE * max(1.0, abs(observed))
    rng = np.random.default_rng(confirm.SEED)
    signs = rng.choice((-1.0, 1.0), size=(confirm.FLIPS, len(sums)))
    draws = signs @ sums / n
    out = {"p_mc": float((1 + np.sum(draws >= observed - tolerance)) / (confirm.FLIPS + 1))}
    if len(sums) <= EXACT_MAX_CLUSTERS:
        patterns = np.array(list(itertools.product((-1.0, 1.0), repeat=len(sums))))
        out["p_exact"] = float(np.mean(patterns @ sums / n >= observed - tolerance))
    return out


def contrast(frame: pd.DataFrame, treat: str, control: str, endpoint: str = "net") -> dict:
    """``confirm.contrast`` on complete paired data, with the stage D p-value (``sign_flip``)."""
    pivot = frame.pivot(index="episode_id", columns="arm", values=endpoint)
    diff = pivot[treat] - pivot[control]
    if diff.isna().any():
        raise ValueError(f"{treat} - {control}: unpaired episodes")
    clusters = frame.drop_duplicates("episode_id").set_index("episode_id")["cluster"]
    stage_c = confirm.contrast(frame, treat, control, endpoint)
    p = sign_flip(diff, clusters.reindex(diff.index))
    rule = "p_exact" if "p_exact" in p else "p_mc"
    return {
        **stage_c,
        "p_one_sided_stage_c_rule": stage_c["p_one_sided"],
        **p,
        "p_rule": rule,
        "p_one_sided": p[rule],
    }


def evaluate(root: Path, models=MODELS, *, base: dict[str, int] | None = None) -> dict:
    confirmatory = tuple(models) == MODELS and base is None
    out: dict = {
        "analysis_class": "exploratory" if confirmatory else "not confirmatory",
        "registered_in": "analysis/commitment/PLAN.md, stage D (amendments DA1 to DA7)",
        "models": list(models),
        "families": {},
        "runs": {},
    }
    with mock.patch.object(confirm, "OUT", root):
        for family, spec in FAMILIES.items():
            refused = []
            for model in models:
                try:
                    check_run(
                        root, family, model, base=None if base is None else base[spec["pool"]]
                    )
                except (ValueError, OSError, KeyError) as error:
                    refused.append(str(error))
            if refused:
                out["families"][family] = {"evaluated": False, "refused": refused}
                continue
            tests, pvalues = {}, {}
            for model in models:
                run = run_name(family, model)
                frame = confirm.episode_frame(run)
                for name, treat, control in spec["tests"]:
                    key = f"{name}|{model}"
                    tests[key] = contrast(frame, treat, control, "net")
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
                "evaluated": True,
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
    ap.add_argument(
        "--not-confirmatory",
        action="store_true",
        help="allow a model subset; the output is marked as not confirmatory",
    )
    ap.add_argument(
        "--throwaway-base",
        type=int,
        default=None,
        help="structural check: both pools at this base; never confirmatory",
    )
    args = ap.parse_args(argv)
    if tuple(args.models) != MODELS and not args.not_confirmatory:
        raise SystemExit("only the two-model call is confirmatory; pass --not-confirmatory")
    base = None
    if args.throwaway_base is not None:
        if args.throwaway_base in REGISTERED_BASE.values():
            raise SystemExit("--throwaway-base must not be a registered base")
        base = {"main": args.throwaway_base, "stochastic": args.throwaway_base}
    report = evaluate(args.out_root, tuple(args.models), base=base)
    path = args.out or args.out_root / "confirm_d.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for family, block in report["families"].items():
        if not block["evaluated"]:
            print(f"{family:12s} not evaluated: {block['refused']}")
            continue
        for key, test in block["tests"].items():
            holm = block["holm"][key]
            print(
                f"{family:12s} {key:28s} {test['mean']:+9.2f} "
                f"[{test['b'][0]:.2f}, {test['b'][1]:.2f}] p={test['p_one_sided']:.5f} "
                f"({test['p_rule']}) {'reject' if holm['reject'] else 'no'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
