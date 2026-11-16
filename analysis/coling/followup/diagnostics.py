"""A23: the two registered measurement diagnostics of the IJCNN paper.

P1 (calibration absorption; outcome-free): on the registered literal readings of each scored
condition, the share of evaluable (item, horizon) pairs whose slip argument falls where the
fitted Turnbull curve is flat -- outside the support or on a bracket with no mass -- the exact
saturation counts, and the reading tolerance the registered 0.02 margin of the AVERAGED
two-horizon loss implies on the steepest bracket of each basis. It opens no sealed file.

P2 (horizon projection; uses the registered outcomes on each contrast's scoreable set): the
paired per-horizon difference vector of the H2 contrast (the rule reader against the literal
reading) of each primary and of the pooled replication model,

    D_a = mean_i[(p_a^rule - Y_a)^2 - (p_a^model - Y_a)^2],   D_b likewise,
    D   = (D_a + D_b) / 2      (the registered primary_loss averages the two horizons),

with a descriptive 95% percentile interval over an episode-cluster bootstrap of 10,000 draws,
seed 20261001. No p-value is reported and nothing enters the six-test family. The scoreable
set of each contrast is rebuilt through the shared preparation path (``fixed_sets`` for the
primaries, the eligible scoreable statements for the replication model, exactly as the
authorized computation scores it), then held to the recorded statement count of its contrast;
a set that disagrees by one item refuses the whole diagnostic, and the averaged identity must
reproduce the registered contrast delta to the registered rounding.

Outputs are aggregates only: counts, shares, differences, interval endpoints, hashes of the
state, the scoreable sets and the sources. No item identity, reading text or outcome value is
written.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from analysis.coling import dataset
from analysis.coling import evaluate as ev
from analysis.coling import launch as lp
from analysis.coling import predictors as P
from analysis.coling import sealed_counts
from analysis.coling import secondary_scores as sc
from analysis.coling.followup import calibration as cal

DRAWS = 10_000
"""The registered descriptive bootstrap draws of A23."""
SEED = 20261001
"""The registered seed of A23 (the study's registered seed)."""
MARGIN = 0.02
"""The registered H2 equivalence margin, on the averaged two-horizon loss."""
ROUNDING = 10**-6
"""The registered six-decimal rounding the averaged identity is held to."""


# --------------------------------------------------------------------------------------------
# P1: flat share, saturation and tolerance (no outcome is read)
# --------------------------------------------------------------------------------------------


def knots_of(slip: P.Turnbull) -> tuple[np.ndarray, np.ndarray]:
    """The corners of the mid CDF of one slip estimate (the curve ``predict`` interpolates)."""
    return slip._knots()


def flat_mask(slip: P.Turnbull, u: np.ndarray) -> np.ndarray:
    """Where the slip argument ``u`` sees a flat curve: outside ``[x_1, x_K]``, or on a bracket
    with no mass (consecutive corners of equal value)."""
    x, y = knots_of(slip)
    u = np.asarray(u, dtype=float)
    if not len(x):
        return np.ones(u.shape, dtype=bool)
    flat = (u <= x[0]) | (u > x[-1])
    rising = np.diff(y) > 0
    k = np.clip(np.searchsorted(x, u, side="right") - 1, 0, len(x) - 2)
    flat |= ~rising[k]
    return flat


def saturated(slip: P.Turnbull, u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Where the curve value is exactly zero, or exactly its top value (``reached``)."""
    x, y = knots_of(slip)
    value = slip.cdf(u)
    return value == 0.0, value == (y[-1] if len(y) else 0.0)


def tolerance_of(slip: P.Turnbull) -> dict[str, Any]:
    """The steepest bracket of one slip estimate and the reading tolerance the registered
    margin of the averaged loss implies on it: a single horizon moving contributes half its
    loss change to the average, both horizons moving together contribute it whole."""
    x, y = knots_of(slip)
    if len(x) < 2 or not (np.diff(y) > 0).any():
        return {"steepest_slope": None, "steepest_bracket_days": None,
                "steepest_bracket_mass": None, "widest_bracket_days": None,
                "widest_bracket_mass": None, "tolerance_days_single_horizon": None,
                "tolerance_days_both_horizons": None}
    widths, rises = np.diff(x), np.diff(y)
    rising = rises > 0
    slopes = np.where(rising, rises / widths, -np.inf)
    j = int(np.argmax(slopes))
    w = int(np.argmax(widths))
    return {
        "steepest_slope": float(slopes[j]),
        "steepest_bracket_days": float(widths[j]),
        "steepest_bracket_mass": float(rises[j]),
        "widest_bracket_days": float(widths[w]),
        "widest_bracket_mass": float(rises[w]),
        "tolerance_days_single_horizon": MARGIN / float(slopes[j]),
        "tolerance_days_both_horizons": MARGIN / (2.0 * float(slopes[j])),
    }


def flat_record(calibrator: P.SlipCalibrator, frame: pd.DataFrame, days: pd.Series) -> dict[str, Any]:
    """P1 for one condition: the literal readings ``days`` (NaN where no stated period) on the
    eligible ``frame`` rows, through the fitted ``calibrator``. Aggregates only."""
    read = days.reindex(frame.index).notna().to_numpy()
    by_horizon: dict[str, dict[str, int]] = {}
    out: dict[str, Any] = {
        "readings": int(read.sum()),
        "no_stated_period": int((~read).sum()),
        "evaluable_pairs": 0,
        "flat_pairs": 0,
        "flat_share": None,
        "by_horizon": {},
        "by_basis": {},
        "saturation": {"p_exactly_zero": 0, "p_exactly_reached": 0},
        "tolerance_by_basis": {},
    }
    form_of, revision_of = frame["form"].to_numpy(), frame["revision"].to_numpy()
    for form, revision in sorted(set(zip(form_of[read], revision_of[read], strict=True))):
        rows = read & (form_of == form) & (revision_of == revision)
        basis, estimate = calibrator.basis(form, revision)
        slip = estimate.slip
        r = days.reindex(frame.index)[rows].to_numpy(dtype=float)
        horizons = {name: frame[name].to_numpy()[rows] - r for name in ("h_a", "h_b")}
        flat_counts, evaluable, zeros, reached = {}, 0, 0, 0
        for name, u in horizons.items():
            mask = flat_mask(slip, u)
            zero, top = saturated(slip, u)
            flat_counts[name] = int(mask.sum())
            evaluable += int(len(u))
            zeros += int(zero.sum())
            reached += int(top.sum())
            tally = by_horizon.setdefault(name, {"evaluable": 0, "flat": 0})
            tally["evaluable"] += int(len(u))
            tally["flat"] += int(mask.sum())
        key = f"{basis}:{form}:{revision}"
        total = sum(flat_counts.values())
        out["by_basis"][key] = {"evaluable_pairs": evaluable, "flat_pairs": total}
        out["tolerance_by_basis"][key] = tolerance_of(slip)
        out["evaluable_pairs"] += evaluable
        out["flat_pairs"] += total
        out["saturation"]["p_exactly_zero"] += zeros
        out["saturation"]["p_exactly_reached"] += reached
    for name, tally in by_horizon.items():
        out["by_horizon"][name] = {
            "evaluable": tally["evaluable"],
            "flat": tally["flat"],
            "flat_share": tally["flat"] / tally["evaluable"] if tally["evaluable"] else None,
        }
    out["flat_share"] = (
        float(out["flat_pairs"] / out["evaluable_pairs"]) if out["evaluable_pairs"] else None
    )
    return out


# --------------------------------------------------------------------------------------------
# P2: the paired per-horizon difference vector (the sealed contrast sets)
# --------------------------------------------------------------------------------------------


def horizon_terms(
    rows: pd.DataFrame, predictions: Mapping[str, pd.DataFrame], comparator: str, tested: str,
    ids: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The per-item per-horizon loss differences ``(a, b)`` of the contrast on ``ids``, with the
    episode of each item (the pairing unit)."""
    sub = rows.loc[list(ids)]
    clusters = sub["episode_id"].to_numpy()
    terms = []
    for horizon, event in (("p_a", "y_a"), ("p_b", "y_b")):
        one = predictions[comparator][horizon].loc[sub.index].to_numpy(dtype=float)
        two = predictions[tested][horizon].loc[sub.index].to_numpy(dtype=float)
        y = sub[event].to_numpy(dtype=float)
        terms.append((one - y) ** 2 - (two - y) ** 2)
    return terms[0], terms[1], clusters


def cluster_interval(
    terms_a: np.ndarray, terms_b: np.ndarray, clusters: np.ndarray,
    draws: int = DRAWS, seed: int = SEED,
) -> dict[str, Any]:
    """The descriptive 95% percentile interval of D_a, D_b and D = (D_a + D_b)/2 over an
    episode-cluster bootstrap: episodes are resampled with replacement, each draw recomputes
    the means over every statement of the drawn episodes."""
    episodes = pd.unique(clusters)
    of_episode = {episode: np.flatnonzero(clusters == episode) for episode in episodes}
    rng = np.random.default_rng(seed)
    drawn_a = np.empty(draws)
    drawn_b = np.empty(draws)
    picked = rng.integers(0, len(episodes), size=(draws, len(episodes)))
    for draw in range(draws):
        rows = np.concatenate([of_episode[episodes[k]] for k in picked[draw]])
        drawn_a[draw] = terms_a[rows].mean()
        drawn_b[draw] = terms_b[rows].mean()
    drawn = (drawn_a + drawn_b) / 2.0
    return {
        "d_horizon_a": float(terms_a.mean()),
        "d_horizon_b": float(terms_b.mean()),
        "d_averaged": float((terms_a.mean() + terms_b.mean()) / 2.0),
        "interval": {
            "d_horizon_a": [float(np.percentile(drawn_a, 2.5)), float(np.percentile(drawn_a, 97.5))],
            "d_horizon_b": [float(np.percentile(drawn_b, 2.5)), float(np.percentile(drawn_b, 97.5))],
            "d_averaged": [float(np.percentile(drawn, 2.5)), float(np.percentile(drawn, 97.5))],
        },
        "draws": draws,
        "seed": seed,
        "episodes": int(len(episodes)),
    }


def contrast_record(
    rows: pd.DataFrame, predictions: Mapping[str, pd.DataFrame], comparator: str, tested: str,
    ids: Sequence[str], expected_statements: int, expected_delta: float,
) -> dict[str, Any]:
    """P2 for one contrast on its scoreable set, held to the recorded size and delta of the
    registered/authorized computation before anything is computed."""
    if len(ids) != expected_statements:
        ev.refuse(
            f"the scoreable set of {tested} holds {len(ids)} statements where its recorded "
            f"contrast has {expected_statements}: no diagnostic approximates it"
        )
    terms_a, terms_b, clusters = horizon_terms(rows, predictions, comparator, tested, ids)
    record = cluster_interval(terms_a, terms_b, clusters)
    if abs(record["d_averaged"] - expected_delta) > ROUNDING:
        ev.refuse(
            f"the averaged per-horizon difference of {tested} is {record['d_averaged']:.6f}, "
            f"not its recorded contrast {expected_delta:.6f}"
        )
    record["statements"] = len(ids)
    record["scoreable_set_sha256"] = sha256(
        "\n".join(sorted(ids)).encode("utf-8")).hexdigest()
    return record


# --------------------------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagnostics", description=__doc__.splitlines()[0])
    parser.add_argument("--statements", type=Path, default=dataset.STATEMENTS)
    parser.add_argument("--eligible", type=Path, default=dataset.ELIGIBLE)
    parser.add_argument("--events", type=Path, default=dataset.EVENTS)
    parser.add_argument("--counts", type=Path, default=dataset.COUNTS)
    parser.add_argument("--out-root", type=Path, default=lp.OUT_ROOT)
    parser.add_argument("--selections", type=Path, default=dataset.OUT)
    parser.add_argument("--confirmatory", type=Path, required=True)
    parser.add_argument("--sealed", type=Path, default=ev.SEALED)
    parser.add_argument("--continuation-selection", type=Path, required=True)
    parser.add_argument("--e3-outcome", type=Path, required=True,
                        help="the A22 outcome file of the replication model")
    parser.add_argument("--expect-e3-sha256", required=True)
    parser.add_argument("--expect-sha256", required=True)
    parser.add_argument("--expect-eligible-sha256", required=True)
    parser.add_argument("--expect-baselines-sha256", required=True)
    parser.add_argument("--expect-selection-sha256", action="append", default=[])
    parser.add_argument("--authorized-model", required=True,
                        help="the replication model A22 names (the only secondary read)")
    parser.add_argument("--p1-only", action="store_true",
                        help="stop after the outcome-free flat share: no sealed byte is read "
                             "(P2 waits for the A23 authority)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    want_sealed = sealed_counts.expected_hash(args.expect_sha256, "--expect-sha256")
    want_eligible = sealed_counts.expected_hash(
        args.expect_eligible_sha256, "--expect-eligible-sha256")
    want_baselines = sealed_counts.expected_hash(
        args.expect_baselines_sha256, "--expect-baselines-sha256")
    want_selections = ev.selection_hashes(args.expect_selection_sha256)
    wrong = ev.constants_problem()
    if wrong:
        ev.refuse(wrong)
    if args.authorized_model not in sc.SECONDARY_MODELS:
        ev.refuse(f"--authorized-model must name a secondary model, not {args.authorized_model!r}")
    e3_bytes = args.e3_outcome.read_bytes()
    if sha256(e3_bytes).hexdigest() != args.expect_e3_sha256:
        ev.refuse("the A22 outcome file is not the one A23 pins")
    e3 = json.loads(e3_bytes)

    names = ("statements", "eligible", "events", "counts", "out_root", "selections",
             "confirmatory", "e3_outcome")
    sc.kept_from_sealed_paths(args, names)
    ev.open_paths(args, names)

    data, hashes = ev.open_tables(args, want_eligible)
    confirmatory, _ = sc.confirmatory_record(
        args.confirmatory, hashes, want_sealed, want_baselines, args.sealed)
    said, recorded_selections = sc.declared(confirmatory, {}, want_selections)
    stopped = ""
    try:
        table = ev.table_of(data["the statement table"], True)
        eligible = ev.table_of(data["the eligible list"], False)
        events = ev.table_of(data["the events table"], args.events.suffix == ".gz")
    except Exception as error:  # noqa: BLE001 - named by type alone, as the scorer does
        stopped = type(error).__name__
    if stopped:
        ev.refuse(f"the open inputs are not as the builders write them ({stopped})")
    listed = sealed_counts.listed_statements(table, eligible)
    counts = json.loads(data["the counts file"])
    found = ev.gathered(
        args.out_root, eligible, listed.set_index("statement_group_id"), counts,
        args.selections, hashes["the statement table"], {}, recorded_selections, args.sealed)
    if found.problems:
        ev.refuse("no diagnostic before every confirmatory run is complete: "
                  + "; ".join(found.problems))
    sc.held_to_the_runs(confirmatory, said, found, listed.set_index("statement_group_id"))
    plan, _, problems = ev.read_plan(args.out_root, args.sealed)
    if plan is None or problems:
        ev.refuse("; ".join(problems))
    selection = json.loads(args.continuation_selection.read_text(encoding="utf-8"))
    continuations = sc.continuation_specs(plan, selection, args.out_root)
    more = sc.gathered_more(
        plan, args.out_root, table, eligible, table.set_index("statement_group_id"), counts,
        ("secondary_models",), [args.authorized_model], list(ev.PRIMARIES),
        sealed=args.sealed, continuations=continuations)
    if more.problems:
        ev.refuse("no diagnostic before every run it reads is complete: "
                  + "; ".join(more.problems))
    try:
        prepared = sc.prepare(table, listed, found, more, {})
    except Exception as error:  # noqa: BLE001 - named by type alone
        stopped = type(error).__name__
    if stopped:
        ev.refuse(f"the readings could not be turned into predictions ({stopped})")
    if prepared.problems:
        ev.refuse("the readings cannot be scored: " + "; ".join(prepared.problems))
    if not prepared.baselines_sha256.startswith(want_baselines):
        ev.refuse("the model-free predictions are not those hashed at the freeze")

    # ---- P1: outcome-free, on the fitted state of the open frame ------------------------------
    frame = P.prepare(table)
    ids = list(eligible["statement_group_id"])
    probe_ids = sorted(eligible.loc[eligible[ev.PROBE] == "1", "statement_group_id"])
    open_frame = frame[frame["period"].eq("train") & frame["split"].isin(("fit", "dev"))]
    rows_of_frame = frame.loc[ids]
    baseline_inputs = rows_of_frame.reindex(columns=sorted(cal.BASELINE_FEATURES))
    provenance = cal.recompute_open_calibration(
        open_frame, baseline_inputs, probe_ids,
        statements_sha256=hashes["the statement table"],
        eligible_sha256=hashes["the eligible list"],
        code_sha256={"predictors": sealed_counts.sha256(Path(P.__file__).read_bytes())},
        versions={"python": sys.version.split()[0]},
    )
    calibrator = ev.refit(frame)[0][ev.RULES]
    if not isinstance(calibrator, P.SlipCalibrator):
        ev.refuse("the registered rules predictor is not the slip calibrator")
    p1 = {
        model: flat_record(calibrator, rows_of_frame, days)
        for model, days in sorted(prepared.reading_days.items())
    }
    pooled_readings = sum(record["readings"] for record in p1.values())
    pooled_flat = sum(record["flat_pairs"] for record in p1.values())
    pooled_evaluable = sum(record["evaluable_pairs"] for record in p1.values())

    # ---- P2: the sealed contrast sets ---------------------------------------------------------
    if args.p1_only:
        report = {
            "about": "A23 measurement diagnostics: P1 flat share only (outcome-free)",
            "draws": DRAWS,
            "seed": SEED,
            "margin": MARGIN,
            "loss": "the registered primary loss averages the two horizons: D = (D_a + D_b) / 2",
            "calibration_state": provenance.state_record(),
            "inputs": {
                "baselines_sha256": prepared.baselines_sha256,
                "eligible_sha256": hashes["the eligible list"],
                "statements_sha256": hashes["the statement table"],
            },
            "p1_flat_share": p1,
            "p1_pooled": {"readings": pooled_readings, "flat_pairs": pooled_flat,
                          "evaluable_pairs": pooled_evaluable,
                          "flat_share": (pooled_flat / pooled_evaluable
                                         if pooled_evaluable else None)},
        }
        _write_report(args.out, report)
        print("wrote", args.out, "(P1 only; no sealed byte was read)")
        print("p1 pooled flat share:", report["p1_pooled"]["flat_share"])
        return 0
    sealed = sealed_counts.file_bytes(args.sealed, "the sealed file")
    if sealed_counts.sha256(sealed) != want_sealed:
        ev.refuse("the sealed file is not the one hashed at the freeze")
    rows, _ = ev.unseal(sealed, events, listed)
    sets = sc.fixed_sets(confirmatory, rows, prepared.study)
    family = {(entry.get("hypothesis"), entry.get("model")): entry
              for entry in confirmatory.get("family", []) if isinstance(entry, dict)}
    p2 = {}
    for model in ev.PRIMARIES:
        entry = family.get(("H2", model))
        if entry is None:
            ev.refuse(f"the evaluator's result file records no H2 contrast for {model}")
        fixed = sets[model][0]
        ids_here = rows.loc[fixed][rows.loc[fixed]["scoreable"]].index.tolist() if fixed is not None else []
        p2[model] = contrast_record(
            rows, prepared.study.predictions, ev.RULES, f"{model}:c", ids_here,
            int(entry["statements"]), float(entry["delta"]))
    replication = e3.get("secondary_models", {}).get("models", {}).get(args.authorized_model, {})
    recorded = replication.get("on_every_eligible_statement", {}).get("H2", {})
    if not recorded:
        ev.refuse("the A22 outcome file records no H2 contrast for the replication model")
    scoreable = rows[rows["scoreable"]].index.tolist()
    p2[args.authorized_model] = contrast_record(
        rows, prepared.study.predictions, ev.RULES, f"{args.authorized_model}:c", scoreable,
        int(recorded["statements"]), float(recorded["delta"]))

    report = {
        "about": "A23 measurement diagnostics: P1 flat share (outcome-free) and P2 paired "
                 "per-horizon difference vector of the H2 contrasts",
        "draws": DRAWS,
        "seed": SEED,
        "margin": MARGIN,
        "loss": "the registered primary loss averages the two horizons: D = (D_a + D_b) / 2",
        "calibration_state": provenance.state_record(),
        "inputs": {
            "sealed_outcomes_sha256": sealed_counts.sha256(sealed),
            "baselines_sha256": prepared.baselines_sha256,
            "eligible_sha256": hashes["the eligible list"],
            "statements_sha256": hashes["the statement table"],
            "e3_outcome_sha256": sha256(e3_bytes).hexdigest(),
        },
        "p1_flat_share": p1,
        "p1_pooled": {"readings": pooled_readings, "flat_pairs": pooled_flat,
                      "evaluable_pairs": pooled_evaluable,
                      "flat_share": pooled_flat / pooled_evaluable if pooled_evaluable else None},
        "p2_paired_horizon_differences": p2,
    }
    _write_report(args.out, report)
    print("wrote", args.out)
    print("p1 pooled flat share:", report["p1_pooled"]["flat_share"])
    for model, record in p2.items():
        print(f"p2 {model}: D_a {record['d_horizon_a']:.6f} D_b {record['d_horizon_b']:.6f} "
              f"D {record['d_averaged']:.6f} n {record['statements']}")
    return 0


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    """The aggregate report, written once, exclusively, with no symlink followed."""
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == "__main__":
    raise SystemExit(main())
