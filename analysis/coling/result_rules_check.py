"""Train-period and first-sight figures that the plan cites for its result rules.

The figures stand in PLAN.md, sections 5, 7.2, 13 and 16 and item 41 of "Changes from the 29
September draft"; section 17 records the hash of this file and of its output.

Inputs. All are open tables under ``analysis/coling/out``, and each has a flag of its name
(``INPUTS``). A path in a folder named ``sealed``, ``keys`` or ``cloud_endpoint``, and a key
file, are refused.

* The statement table of ``dataset.py`` (``statements.csv.gz``). Outcome cells are used on
  train-period rows only: statements dated before 2023-01-01. From every other row the
  first-sight columns alone are taken (``dataset.FIRST_SIGHT_COLUMNS``; the frozen rule reading
  is among them: form, statement type, stated end, stale flag, distractor dates). A table in
  which a row dated 2023-01-01 or later, or a row of another period than train, has an outcome
  cell that is not blank is refused (``train_rows``).
* The E3 eligible list (``eligible_e3.csv``): test-period statements, ids only.
* The dev losses of ``power.py`` (``dev_losses.json``), to check that this file and that record
  rest on the same build (below).
* The literal sample (``audit/samples/sample_literal.csv``, ids only) and the allocation of the
  samples (``audit/samples/strata.csv``, counts by stratum).
* The minimal pairs (``e5/e5_pairs.jsonl``: fictitious items, no outcome) and their counts
  (``e5/e5_counts.json``).

Predictors. The base rate by listing age, the stated date at face value and rules plus slip are
fitted on the fit split (statements dated before 2021-01-01) and read on the dated statements
of the dev split (2021-01-01 to 2022-12-31), as ``power.fit_and_predict`` does it. The two
gradient-boosted models are not fitted, because no figure below needs them. The dev counts,
every score of the three predictors and the contrasts between them are then computed with
``power.loss_report`` and must equal those of ``dev_losses.json`` to its six decimals.

Terms. A dated statement is *scoreable* when both horizon events are determined. The *Turnbull
share* recovered by a day is the estimate of ``predictors.turnbull`` on the brackets of slip
(recovery minus the stated end), read at 0 days (by the stated end) and at 90 days (within 90
days of it). The *statement type* is that of the frozen rule reading: recovery or next
delivery for a dated statement. An interval is the 95% percentile interval over 10,000 draws of
the shortage episodes with seed 20261001 (``predictors.bootstrap_means``); for calibration in
the large it is the interval of ``evaluate.calibration``, which the tests check.

Figures: one key of the output each, with the counts it rests on.

* ``A_base_rate_calibration_scoreable_dev``: calibration in the large of the base rate on
  ``E_end`` over the scoreable dev statements: the mean of ``P(E_end)``, the number of yes
  answers, their difference and its interval.
* ``B_base_rate_against_turnbull_share``: the mean of the base rate's ``P(E_end)`` against the
  Turnbull share recovered by the stated end, over the dated statements of dev, and of fit
  (where the base rate was fitted).
* ``C_calibration_limits_dated_dev``: over the dated dev statements, the least value that
  calibration in the large on ``E_end`` can take (every undetermined ``E_end`` counted as yes)
  and the greatest (every one counted as no), each with its interval, for the base rate and for
  the stated date at face value.
* ``D_turnbull_shares_dev``: the two Turnbull shares over the dated dev statements and over
  the scoreable ones.
* ``E_primary_brier_scoreable_dev``: the primary Brier loss, on the scoreable dev statements,
  of answering no to both horizon events of every statement, and of the base rate.
* ``F_base_rate_minus_rules_plus_slip``: the base rate's mean primary loss minus that of rules
  plus slip: on the scoreable dev statements; under the two scenarios over the dated dev
  statements (every undetermined horizon event set to no, then to yes;
  ``predictors.brier_bounds``); and on the scoreable dev statements of each statement type.
* ``G_turnbull_share_by_statement_type``: the Turnbull shares of the dated statements of fit
  and of dev, by statement type.
* ``H_eligible_list_by_statement_type``: the statements of the eligible list and their
  episodes, by statement type. First-sight columns only.
* ``I_literal_sample_letter_items``: the items of the literal sample whose rule reading gives
  a period (a dated form) and lists no distractor date: how many, in how many episodes, by
  form, by statement type, and how many are stale at issue; beside them the number of strata
  of the sample that are named after a dated form and the number of items drawn from those.
  First-sight columns only.
* ``J_certainty_marker_minimal_pairs``: the items of the certainty-marker factor by level, and
  on how many of each level the frozen rule reader (``forms.classify`` on the item's text at
  its Date of update) still finds a period. An item *keeps* its date when it does and has it
  *taken away* when it does not.

Refusals. The command stops with one sentence and status 1, and writes nothing, when a row
outside the train period carries an outcome cell; when the dev losses on disk, the eligible
list or the literal sample are not from the build of the statement table; when the counts of
the minimal pairs by level are not those of ``e5_counts.json``; and when ``rules.py`` is not the
frozen file that ``forms.py`` names.

Output. ``out/result_rules_check.json``: the command, the first 16 hex characters of the sha256
of every input as it was read, of this file and of ``predictors.py``, the seed and the number
of draws, and the ten figures. Floats are rounded to six decimals. Nothing in it changes from
one run to the next on the same inputs.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.result_rules_check            # write the output
    PYTHONPATH=. python -m analysis.coling.result_rules_check --check    # recompute and compare
    PYTHONPATH=. python -m pytest analysis/coling/test_result_rules_check.py -q -p no:cacheprovider

Run the command again after any change to an input, to ``predictors.py`` or to this file:
``--check`` and ``test_output_is_up_to_date`` report a stale output until then.
"""

from __future__ import annotations

import argparse
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pandas as pd

from analysis.coling import corpus, dataset, forms, rules
from analysis.coling import power as W
from analysis.coling import predictors as P

SEED = P.SEED
DRAWS = P.DRAWS
COVERAGE = 0.95
TEST_START = dataset.TEST_START.isoformat()
"""Outcome cells are used on statements dated before this day only."""
TYPES = ("recovery", "next_delivery")
"""The statement types of a dated statement, in the order of the literal answer schema."""
PREDICTORS = ("base_rate", "face_value", "rules_plus_slip")
"""The predictors fitted here: those of ``gbm.PREDICTORS`` that need no gradient-boosted model."""
SAMPLE = "literal"
FACTOR = "certainty"
MONTH_YEAR = "month_year"
OUT = dataset.OUT
INPUTS: dict[str, tuple[Path, str]] = {
    "statements": (dataset.STATEMENTS, "the statement table"),
    "eligible_e3": (dataset.ELIGIBLE, "the E3 eligible list"),
    "dev_losses": (W.DEV_LOSSES, "the dev losses of power.py"),
    "sample_literal": (dataset.SAMPLES / f"sample_{SAMPLE}.csv", "the literal sample"),
    "strata": (dataset.SAMPLES / "strata.csv", "the allocation of the samples"),
    "e5_pairs": (OUT / "e5" / "e5_pairs.jsonl", "the minimal pairs"),
    "e5_counts": (OUT / "e5" / "e5_counts.json", "the counts of the minimal pairs"),
}
"""The inputs by the name under which the output records their hash: default path and what it
is. Each has a flag of its name (``--eligible-e3 FILE``)."""
REPORT = OUT / "result_rules_check.json"
CLOSED = frozenset({"sealed", "keys", "cloud_endpoint"})
"""Folders no input or output may lie in."""
COMMAND = "PYTHONPATH=. python -m analysis.coling.result_rules_check"
ABOUT = (
    "Train-period and first-sight figures cited for the result rules (PLAN.md sections 5, 7.2, "
    "13 and 16): fitted on the fit split, read on the dev split. Outcome cells of train-period "
    "statements only; first-sight columns of the others; no sealed file."
)


def refuse(reason: str) -> NoReturn:
    """Stop with status 1; the reason, one sentence, is the only thing printed."""
    raise SystemExit(f"refused: {reason}")


# --------------------------------------------------------------------------------------------
# Rows: train-period statements with their outcomes, every statement at first sight
# --------------------------------------------------------------------------------------------


def train_rows(table: pd.DataFrame) -> pd.DataFrame:
    """The train-period rows of the statement table, dated before ``TEST_START``: the only rows
    whose outcome cells are used. Refuses a table in which any other row has an outcome cell
    that is not blank."""
    iso = table["event_date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    later = ~iso | (table["event_date"] >= TEST_START) | (table["period"] != "train")
    filled = (table.loc[later, list(dataset.OUTCOME_COLUMNS)] != "").any(axis=1)
    if filled.any():
        refuse(
            f"the statement table has an outcome cell on {int(filled.sum())} of its rows dated "
            f"{TEST_START} or later, not dated as YYYY-MM-DD, or outside the train period"
        )
    return table[~later]


def first_sight(table: pd.DataFrame) -> pd.DataFrame:
    """Every statement with its first-sight columns only, indexed by ``statement_group_id``."""
    return table.loc[:, list(dataset.FIRST_SIGHT_COLUMNS)].set_index("statement_group_id")


def table_of(data: bytes, gzipped: bool = False) -> pd.DataFrame:
    """A CSV held in memory with every cell as text (as ``dataset.read_table`` reads a file)."""
    compression = "gzip" if gzipped else None
    return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, compression=compression)


# --------------------------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------------------------


def interval(
    values: Any, clusters: Sequence[str], draws: int = DRAWS, seed: int = SEED
) -> list[float]:
    """The 95% percentile interval of the mean of ``values`` over draws of the clusters."""
    return P.interval(P.bootstrap_means(values, list(clusters), draws, seed)[:, 0], COVERAGE)


def calibration(
    p: Any, y: Any, clusters: Sequence[str], draws: int = DRAWS, seed: int = SEED
) -> dict[str, Any]:
    """Calibration in the large on determined events ``y`` (1 or 0): the mean probability, the
    yes answers, their frequency, the difference and its interval by episode."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return {
        "statements": len(y),
        "episodes": len(set(clusters)),
        "mean_p": float(p.mean()),
        "yes": int(y.sum()),
        "frequency": float(y.mean()),
        "difference": float((p - y).mean()),
        "ci95": interval(p - y, clusters, draws, seed),
    }


def event_counts(y: Any) -> dict[str, int]:
    """The answers of a horizon event: yes (1), no (0) and undetermined (missing)."""
    y = np.asarray(y, dtype=float)
    return {
        "statements": len(y),
        "yes": int((y == 1).sum()),
        "no": int((y == 0).sum()),
        "undetermined": int(np.isnan(y).sum()),
    }


def calibration_limits(
    p: Any, y: Any, clusters: Sequence[str], draws: int = DRAWS, seed: int = SEED
) -> dict[str, Any]:
    """The least and the greatest value that calibration in the large can take when some events
    of ``y`` are undetermined (missing): the mean probability minus the frequency with every
    undetermined event counted as yes, and then as no. Each with its interval by episode."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    out: dict[str, Any] = {"mean_p": float(p.mean())}
    for name, value in (("least", 1.0), ("greatest", 0.0)):
        gap = p - np.where(np.isnan(y), value, y)
        out[name] = {"value": float(gap.mean()), "ci95": interval(gap, clusters, draws, seed)}
    return out


def turnbull_shares(rows: pd.DataFrame) -> dict[str, Any]:
    """The Turnbull shares of the dated statements ``rows`` recovered by the stated end and
    within 90 days of it."""
    curve = P.turnbull(*P.slip_brackets(rows))
    return {
        "statements": len(rows),
        "by_stated_end": float(curve.cdf(0.0)),
        "within_90_days": float(curve.cdf(float(dataset.HORIZON_DAYS))),
    }


def against_turnbull(p: Any, rows: pd.DataFrame) -> dict[str, Any]:
    """The mean of the probabilities ``p`` of recovery by the stated end, one per row of
    ``rows``, against the Turnbull share recovered by then."""
    mean, share = float(np.mean(np.asarray(p, dtype=float))), turnbull_shares(rows)["by_stated_end"]
    return {
        "statements": len(rows),
        "mean_p_E_end": mean,
        "turnbull_share_by_stated_end": share,
        "difference": mean - share,
    }


def always_no(rows: pd.DataFrame) -> float:
    """The mean primary loss on the scoreable statements ``rows`` of answering no (probability
    0) to both horizon events."""
    return float(np.mean(P.primary_loss(0.0, 0.0, rows["y_a"], rows["y_b"])))


def by_type(rows: pd.DataFrame, kinds: pd.Series) -> dict[str, pd.DataFrame]:
    """The dated statements ``rows`` by statement type (``kinds``, by statement). A statement
    of another type than those of ``TYPES`` is an error."""
    kind = kinds.reindex(rows.index)
    if not kind.isin(TYPES).all():
        raise ValueError("a dated statement is neither a recovery nor a next-delivery statement")
    return {name: rows[(kind == name).to_numpy()] for name in TYPES}


def mean_difference(delta: pd.Series, rows: pd.DataFrame) -> dict[str, Any]:
    """The mean of the paired differences ``delta`` on ``rows`` (None when there is no row),
    with what it rests on."""
    return {
        "statements": len(rows),
        "episodes": int(rows["episode_id"].nunique()),
        "delta": float(delta.loc[rows.index].mean()) if len(rows) else None,
    }


def loss_difference(
    rows: pd.DataFrame, comparator: pd.DataFrame, tested: pd.DataFrame, kinds: pd.Series
) -> dict[str, Any]:
    """The comparator's mean primary loss minus the tested predictor's on the dated statements
    ``rows``: on the scoreable ones, under the two scenarios over all of them, and on the
    scoreable ones of each statement type (``kinds``, by statement)."""
    scoreable = rows[rows["scoreable"]]
    losses = W.primary_losses(scoreable, {"comparator": comparator, "tested": tested})
    delta = losses["comparator"] - losses["tested"]
    first, second = (
        P.brier_bounds(q.loc[rows.index, "p_a"], q.loc[rows.index, "p_b"], rows["y_a"], rows["y_b"])
        for q in (comparator, tested)
    )
    return {
        "scoreable": mean_difference(delta, scoreable),
        "scenarios_all_dated": {
            "statements": len(rows),
            **{name: first[name] - second[name] for name in first},
        },
        "by_statement_type_scoreable": {
            name: mean_difference(delta, part) for name, part in by_type(scoreable, kinds).items()
        },
    }


def tally(column: pd.Series, order: Sequence[str]) -> dict[str, int]:
    """How often each value of ``order`` stands in ``column``; a value that is absent is left
    out, and a value outside ``order`` is an error."""
    counts = column.value_counts()
    if not set(counts.index) <= set(order):
        raise ValueError(f"unexpected values: {sorted(set(counts.index) - set(order))}")
    return {name: int(counts[name]) for name in order if name in counts.index}


# --------------------------------------------------------------------------------------------
# Figures A to G: train-period outcomes, fit and dev
# --------------------------------------------------------------------------------------------


def fit_and_predict(
    frame: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, pd.DataFrame]]:
    """The predictors of ``PREDICTORS`` fitted on the fit split, the dated dev statements and
    each predictor's output on them: ``power.fit_and_predict`` without the two gradient-boosted
    models."""
    fit = frame[frame["split"] == "fit"]
    fitted = {
        "base_rate": P.fit_base_rate(fit),
        "face_value": P.FaceValue(),
        "rules_plus_slip": P.fit_calibrator(fit),
    }
    dev = W.dev_rows(frame)
    return fitted, dev, {name: fitted[name].predict(dev) for name in PREDICTORS}


def same_build(recorded: Mapping[str, Any], report: Mapping[str, Any]) -> bool:
    """Whether the dev losses on disk (``recorded``) hold, to their six decimals, the dev
    counts, the resampling settings, every score of the predictors of ``report`` (a
    ``power.loss_report``) and the contrasts between them."""
    mine = W.rounded(report)
    names = set(mine["losses"])

    def keyed(contrasts: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Any]:
        pairs = {(c["comparator"], c["tested"]): c for c in contrasts}
        return {pair: c for pair, c in pairs.items() if set(pair) <= names}

    return (
        all(recorded.get(part) == mine[part] for part in ("dev", "bootstrap"))
        and all(recorded.get("losses", {}).get(name) == mine["losses"][name] for name in names)
        and keyed(recorded.get("contrasts", ())) == keyed(mine["contrasts"])
    )


def dev_figures(
    frame: pd.DataFrame,
    kinds: pd.Series,
    recorded: Mapping[str, Any],
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """Figures A to G from the typed frame of the train-period statements, their statement
    types (``kinds``, by statement) and the dev losses on disk (``recorded``)."""
    fitted, dev, predictions = fit_and_predict(frame)
    if not same_build(recorded, W.loss_report(dev, predictions, draws, seed)):
        refuse("the dev losses on disk and the statement table are not from the same build")
    fit = frame[(frame["split"] == "fit") & (frame["analysis_set"] == "dated")]
    scoreable = dev[dev["scoreable"]]
    base, face = predictions["base_rate"], predictions["face_value"]
    episodes = dev["episode_id"]
    return {
        "A_base_rate_calibration_scoreable_dev": {
            "event": "E_end",
            **calibration(
                base.loc[scoreable.index, "p_a"],
                scoreable["y_a"],
                scoreable["episode_id"],
                draws,
                seed,
            ),
        },
        "B_base_rate_against_turnbull_share": {
            "dev": against_turnbull(base["p_a"], dev),
            "fit": against_turnbull(fitted["base_rate"].predict(fit)["p_a"], fit),
        },
        "C_calibration_limits_dated_dev": {
            "event": "E_end",
            **event_counts(dev["y_a"]),
            "episodes": int(episodes.nunique()),
            "base_rate": calibration_limits(base["p_a"], dev["y_a"], episodes, draws, seed),
            "face_value": calibration_limits(face["p_a"], dev["y_a"], episodes, draws, seed),
        },
        "D_turnbull_shares_dev": {
            "dated": turnbull_shares(dev),
            "scoreable": turnbull_shares(scoreable),
        },
        "E_primary_brier_scoreable_dev": {
            "statements": len(scoreable),
            "by_E_end_and_E_end90": W.outcome_mix(scoreable),
            "always_no": always_no(scoreable),
            "base_rate": float(
                W.primary_losses(scoreable, {"base_rate": base})["base_rate"].mean()
            ),
        },
        "F_base_rate_minus_rules_plus_slip": loss_difference(
            dev, base, predictions["rules_plus_slip"], kinds
        ),
        "G_turnbull_share_by_statement_type": {
            split: {name: turnbull_shares(part) for name, part in by_type(rows, kinds).items()}
            for split, rows in (("fit", fit), ("dev", dev))
        },
    }


# --------------------------------------------------------------------------------------------
# Figures H to J: first-sight columns and the rule reading, no outcome
# --------------------------------------------------------------------------------------------


def eligible_by_type(eligible: pd.DataFrame, first: pd.DataFrame) -> dict[str, Any]:
    """Figure H: the statements of the eligible list and their episodes, by statement type."""
    flagged = first[dataset.true(first["e3_eligible"])]
    if sorted(eligible["statement_group_id"]) != sorted(flagged.index):
        refuse("the eligible list and the statement table are not from the same build")
    parts = {name: flagged[flagged["statement_type"] == name] for name in TYPES}
    return {
        "statements": len(flagged),
        "episodes": dataset.episodes(flagged),
        **{
            name: {"statements": len(rows), "episodes": dataset.episodes(rows)}
            for name, rows in parts.items()
        },
    }


def letter_items(sample: pd.DataFrame, strata: pd.DataFrame, first: pd.DataFrame) -> dict[str, Any]:
    """Figure I: the items of the literal sample whose rule reading gives a period and lists no
    distractor date, and the allocation of the sample to the strata named after a dated form."""
    ids = list(sample["statement_group_id"])
    if not set(ids) <= set(first.index):
        refuse("the literal sample names a statement that the statement table does not hold")
    rows = first.loc[ids]
    dated = rows["form"].isin(forms.DATED_FORMS)
    letter = rows[dated & (pd.to_numeric(rows["distractor_dates"]) == 0)]
    drawn = strata[(strata["sample"] == SAMPLE) & strata["stratum"].isin(forms.DATED_FORMS)]
    return {
        "items": len(rows),
        "letter_items": len(letter),
        "episodes": dataset.episodes(letter),
        "with_no_episode": int((letter["episode_id"] == "").sum()),
        "by_form": tally(letter["form"], forms.DATED_FORMS),
        "of_forms_other_than_month_year": int((letter["form"] != MONTH_YEAR).sum()),
        "by_statement_type": tally(letter["statement_type"], forms.STATEMENT_TYPES),
        "stale_at_issue": int(dataset.true(letter["stale_at_issue"]).sum()),
        "strata_named_after_a_dated_form": int(drawn["stratum"].nunique()),
        "drawn_from_those_strata": int(pd.to_numeric(drawn["drawn"]).sum()),
    }


def keeps_its_date(item: Mapping[str, Any]) -> bool:
    """Whether the frozen rule reader finds a period in the text of an item of the reading
    harness, read at its Date of update."""
    text = corpus.statement_text(item["availability_information"], item["related_information"])
    return forms.classify(text, item["date_of_update"]).dated


def certainty_items(
    items: Sequence[Mapping[str, Any]], counts: Mapping[str, Any]
) -> dict[str, Any]:
    """Figure J: the minimal-pair items of the certainty-marker factor by level, and whether
    the rule reading of each still gives a period. ``counts`` is ``e5_counts.json``."""
    if dataset.sha16(Path(rules.__file__).read_bytes()) != forms.RULES_SHA256:
        refuse("rules.py is not the frozen rule reader that forms.py names")
    kept: dict[str, list[bool]] = {}
    for item in items:
        if item["factor"] == FACTOR:
            kept.setdefault(item["level"], []).append(keeps_its_date(item))
    by_level = {
        level: {"items": len(kept[level]), "date_kept": int(sum(kept[level]))}
        for level in sorted(kept)
    }
    listed = {level: row["items"] for level, row in by_level.items()}
    if counts.get("per_factor_and_level", {}).get(FACTOR) != listed:
        refuse("the minimal pairs and their counts file are not from the same build")
    sides = {
        "date_taken_away": {
            level: row["items"] - row["date_kept"] for level, row in by_level.items()
        },
        "date_kept": {level: row["date_kept"] for level, row in by_level.items()},
    }
    return {
        "items": sum(listed.values()),
        **{
            name: {"items": sum(side.values()), "levels": [level for level, n in side.items() if n]}
            for name, side in sides.items()
        },
        "by_level": by_level,
    }


# --------------------------------------------------------------------------------------------
# The report and the command line
# --------------------------------------------------------------------------------------------


def build(
    table: pd.DataFrame,
    eligible: pd.DataFrame,
    recorded: Mapping[str, Any],
    sample: pd.DataFrame,
    strata: pd.DataFrame,
    pairs: Sequence[Mapping[str, Any]],
    pair_counts: Mapping[str, Any],
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """The ten figures from the statement table, the eligible list, the dev losses on disk, the
    literal sample and its strata, and the minimal pairs with their counts."""
    train, first = train_rows(table), first_sight(table)
    return {
        **dev_figures(P.prepare(train), first["statement_type"], recorded, draws, seed),
        "H_eligible_list_by_statement_type": eligible_by_type(eligible, first),
        "I_literal_sample_letter_items": letter_items(sample, strata, first),
        "J_certainty_marker_minimal_pairs": certainty_items(pairs, pair_counts),
    }


def code_record() -> dict[str, str]:
    """The hashes of this file and of the modules its figures rest on."""
    files = {
        "result_rules_check": __file__,
        "predictors": P.__file__,
        "power": W.__file__,
        "dataset": dataset.__file__,
        "forms": forms.__file__,
        "corpus": corpus.__file__,
    }
    return {
        f"{name}_sha256": dataset.sha16(Path(path).read_bytes()) for name, path in files.items()
    }


def report_text(figures: Mapping[str, Any], inputs: Mapping[str, str]) -> str:
    """The text of the output file."""
    head = {
        "about": ABOUT,
        "command": COMMAND,
        "inputs": dict(inputs),
        "parameters": {
            "seed": SEED,
            "draws": DRAWS,
            "interval": f"{COVERAGE:.0%} percentile, by shortage episode",
            "outcome_cells_used_on_statements_dated_before": TEST_START,
        },
    }
    return W.report_text({**head, **figures})


def print_summary(figures: Mapping[str, Any]) -> None:
    """One line per figure, as the output holds it."""
    for key, figure in W.rounded(figures).items():
        print(f"{key}: {json.dumps(figure, ensure_ascii=False)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.result_rules_check",
        description=(__doc__ or "").splitlines()[0],
    )
    for name, (path, what) in INPUTS.items():
        ap.add_argument(f"--{name.replace('_', '-')}", type=Path, default=path, help=what)
    ap.add_argument("--out", type=Path, default=REPORT, help="the output")
    ap.add_argument("--check", action="store_true", help="recompute and compare; write nothing")
    args = ap.parse_args(argv)
    paths = {name: getattr(args, name) for name in INPUTS}
    for path in (*paths.values(), args.out):
        for parts in (path.parts, path.absolute().parts):  # as written first: no system call
            if CLOSED & set(parts) or path.suffix == ".key":
                refuse(
                    f"{path.as_posix()} is in a sealed, key or endpoint folder, or is a key file"
                )
        if CLOSED & set(path.resolve().parts):  # then through links
            refuse(f"{path.as_posix()} leads into a sealed, key or endpoint folder")
    data = {name: path.read_bytes() for name, path in paths.items()}
    inputs = {f"{name}_sha256": dataset.sha16(blob) for name, blob in data.items()}
    figures = build(
        table_of(data["statements"], paths["statements"].suffix == ".gz"),
        table_of(data["eligible_e3"]),
        json.loads(data["dev_losses"]),
        table_of(data["sample_literal"]),
        table_of(data["strata"]),
        [json.loads(line) for line in data["e5_pairs"].decode("utf-8").split("\n") if line],
        json.loads(data["e5_counts"]),
    )
    text = report_text(figures, {**inputs, **code_record()})
    if args.check:
        stale = not args.out.exists() or args.out.read_text(encoding="utf-8") != text
        print(f"differs from a fresh run: {args.out.as_posix()}" if stale else "up to date")
        return 1 if stale else 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print_summary(figures)
    print(f"wrote {args.out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
