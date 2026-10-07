"""The secondary scorer of the COLING 2027 study: registered secondary analyses that need the
sealed test-period outcomes and that the registered evaluator does not compute (PLAN.md, standing
rules on sealing; section 6, "Evaluator"; ``evaluate.NOT_COMPUTED_HERE``). It computes those of
``SECTIONS``. The others are named in every result file, under ``not_computed_here``: those that
another script of the study computes (``COMPUTED_BY_ANOTHER_SCRIPT``) and those that no script
computes at this version of the code (``COMPUTED_BY_NO_SCRIPT``).

It reads ``external_data/sealed/outcomes_test.csv.gz`` only through the command ``score``, only
after every confirmatory run and every run it scores is complete, and only after the registered
evaluator has written its result file. Every output is a count, a mean, a share, an interval or a
p-value over statements and shortage episodes: no statement id, no date and no outcome cell of a
single statement is printed or written.

Nor is a figure written that would give back the outcomes of 1 to 4 statements (PLAN, standing
rules): a figure over so few is withheld, its counts apart (the floor of ``MIN_SHOWN``, whichever
function computed it), and so is a figure that is also written on a set that differs from its own
by so few: the post-cutoff slice within the list and the statements after a cutoff within a
subset (``beside``, ``beside_the_whole``), the answers that parsed within all (``parsed_only``),
one outcome definition beside another (``near_definitions``), the parts of selective prediction
(``selective``), the cells of the two splits of the descriptives (``withheld_cells``). A count
that would say how many of a few statements anyone can name are scoreable, or have a determined
event, is withheld as well, and where a few statements of a set are not scoreable so are the mean
probabilities and the calibration in the large on its scoreable statements, which with the open
predictions would name them (``scores``). The six confirmatory contrasts are the evaluator's and
are not touched here; the same contrasts of the secondary models on every eligible statement
are never withheld for a set beside them: the figure beside one of them is the one withheld.

Nothing of the evaluation is defined here. The runs are gathered by the evaluator's own check
(``evaluate.gather``, ``evaluate.read_group``); readings become predictions by
``evaluate.model_predictions``; the model-free predictors are those of ``evaluate.free_predictions``
(the refit on fit and dev, held to the hash of the freeze); the sealed rows go through
``evaluate.unseal`` and the checked reader of the counts-only code (``sealed_counts._checked_rows``
and ``_same_build``); the scores are ``evaluate.predictor_record``, the contrasts are
``evaluate.contrast`` with the p-value of the registered procedure (``evaluate.P_VALUE_SOURCE``)
and its intervals. The H1, H2 and H3 contrasts of the secondary models carry the 95% interval of
the registered source (``evaluate.interval_method``: the values the registered test does not
reject), as the confirmatory contrasts do, with the percentile intervals beside it, and so does
the contrast of each of their conditions against the structured-only model; every other
interval here is a 95% percentile interval of the bootstrap draws (PLAN section 6, "Intervals").
No claim of multiplicity is made for anything here.

Commands
--------
``train-descriptives --out FILE``. Open data only: the descriptives of E1 (PLAN section 5, E1)
for the train period (fit and dev), from the open statement table, whose train-period outcomes
stop at the train horizon. It never takes the path of a sealed file and can be run at any time.

``score --expect-sha256 H --expect-eligible-sha256 H --expect-baselines-sha256 H
--expect-selection-sha256 MODEL=H ... --confirmatory FILE --out FILE [--not-evaluable
MODEL=REASON] [--section NAME ...] [--left-out MODEL=REASON ...]``. One result file with one
section per analysis (``SECTIONS``; all of them unless ``--section`` names some).
``--expect-selection-sha256`` is given once for each primary that is not declared not
evaluable: the sha256 of its H3 selection file as the freeze records it (PLAN section 6: no
start without it). ``--not-evaluable`` repeats, with the same reason, the declaration the
evaluator's command line was given for a primary whose confirmatory runs could not be
completed: the evaluator's result file must record the same, and a declaration that stands in
that file alone, or on this command line alone, is refused.
``--left-out`` declares a secondary model whose runs could not be completed: its readings are
not scored, its runs are read by the completeness check alone, and the declaration is refused
when that check finds nothing wrong with them; the result file records the declaration and
what the check found. Neither command takes a number of draws: a Turnbull estimate is refitted
on ``SLIP_DRAWS`` of the registered bootstrap draws for its interval, a constant of this file
as the draws and the seed of the evaluator are of its own. The sections ``secondary_models``,
``selective_prediction`` and ``recovery_rule`` read the three conditions of every secondary
model that is not left out; the other sections read the runs of the primaries only.

* ``secondary_models`` (PLAN section 5, E3, "Secondaries" and "Descriptive decomposition";
  section 7.2). For each of the six secondary models: the H1 contrast (a against b, one-sided),
  the H2 contrast (rules plus slip against c, two-sided) and the H3 contrast of each of its
  three conditions against the comparator of H3 (two-sided, with the contrast against the
  structured-only model beside it), on every eligible statement and, where the slice is
  analysed (section 3), on its post-cutoff slice; the bounds of section 7.2 beside each; the
  same contrast on the statements both sides parsed (section 4); the descriptive decomposition
  (content value, reading loss, trust loss), on the same two sets; the contrasts again, in
  short, under the outcome variants (the recovery definition A; the outcome over all and over
  any covered presentation), on the statements first captured by the stated end, with the
  episodes resampled by company, and H2 on the month-and-year form; the E4 probe test for the
  five secondary models that are probed; and for each of the three conditions every score of
  section 7.2 on every eligible statement (primary Brier with its bounds, Murphy's
  decomposition, calibration in the large, the pinball losses, the coverage of the 80%
  interval), with the parse and refusal rates of each run. The scores of a primary are not
  computed here: the evaluator holds them, on the item set the probe fixed.
* ``secondary_lists`` (PLAN section 3, "E3 eligibility"; section 5, E3, "Primaries only"). For
  each primary on the TBD, silent and stale-at-issue lists under conditions (a), (b) and (c):
  stale-value uptake (the share of readings with ``P(E_end)`` above 0.5 for a period that has
  passed), and, on the TBD and silent lists, every score of section 7.2 with the contrast
  against the base-rate predictor (the two horizon events are recovery within 90 and within 180
  days of the statement) and the selective-prediction point of condition (c); the stale list,
  whose statements have no horizon event, has the abstention rate of condition (c) alone.
* ``sampled_quantiles`` (section 5, E3, "Primaries only"): the empirical quantiles of the 20
  sampled medians (``read.sampled_quantiles``) against the verbalised quantiles of the
  temperature-0 answer of condition (a), by pinball loss at 0.5, 0.8 and 0.95 and by coverage
  of the 80% interval, on the 20-sample subset.
* ``prompt_variance`` (section 5, E3, "Primaries only"): the three paraphrases of condition (b)
  on the paraphrase subset, beside the registered prompt on the same statements. In these three
  sections a primary is read on every statement of the list or subset; for one whose probe beat
  the base rate, what is scored against outcomes is given again on the statements dated after
  its cutoff.
* ``name_date_2x2`` (section 5, E4): for each primary under condition (b) on the 2x2 subset, the
  change in primary loss and the mean absolute change in ``P(E_end)``, in ``P(E_end90)`` and in
  the median, from the cell of real names and true dates (the condition (b) run itself) to each
  other cell, with the two main effects and their interaction on the loss.
* ``descriptives`` (section 5, E1): the hold rate of the stated period, the Turnbull estimate
  of slip by form and by revision bucket, the bracket widths and the counts by year, form,
  statement type and company, on the statements of the test split at risk under B. The hold
  rate and the slip by statement type belong to the analysis by statement type, which is not
  computed yet (``COMPUTED_BY_NO_SCRIPT``).
* ``selective_prediction`` (section 7.2): for condition (c) of every model and for the rule
  reader on the eligible list, the abstention rate and the primary loss on the statements read,
  on those abstained on and on all. A primary is read on the item set its probe fixed. The rule
  reader reads every eligible statement by the definition of eligibility: its abstention rate
  is zero by construction, and its point is the loss of rules plus slip.
* ``recovery_rule`` (section 2.5, "Sensitivity analyses" and the Date Discontinued cell): the
  contrasts of every model with limited supply counted as available (BL), with leaving the
  list without a resolution counted as recovery at the first capture where the row is missing,
  and with a Date Discontinued cell that newly appears on a shortage row counted as a
  discontinuation at that capture.

Order of the ``score`` command, each step a refusal when it fails:

1. the hashes of the command line (the sealed file, the eligible list, the model-free
   predictions, and the selection file of each primary that is not declared not evaluable),
   the registered constants, the output path, the declarations (a reason that is printable
   text on one line; never every primary); then, before any file is opened, every path this
   command would read (``kept_from_sealed_paths``): an input of the command line, a selection
   file, the plan of the runs, a path named anywhere in that plan or a file stored in the
   folder of one of its runs that leads to the sealed file or into a sealed folder, as given
   or through a symbolic link, is a refusal;
2. the open inputs of one build (``evaluate.open_tables``), the eligible list behind its hash;
3. the result file of the registered evaluator: it must exist, be a result of
   ``evaluate.py confirmatory`` under the constants in force, hold the six tests with their
   Holm-adjusted p-values, and record the sealed file, the eligible list, the statement table,
   the events table and the model-free predictions that this command is given
   (``confirmatory_record``); it must declare not evaluable the primaries this command line
   declares, with the same reasons, and no other, hold a family that agrees with that, and
   record the selection files of the hashes given (``declared``);
4. the evaluator's completeness check on the confirmatory runs (``evaluate.gathered``), with
   the declarations of the command line and the selection files held to the hashes; then the
   result file against what that check read (``held_to_the_runs``): the readings its tests
   were computed on, the tests the selection files give, the item set of each primary;
5. the declarations of secondary models left out (``left_out_findings``), and the same check
   on every run the sections asked for score (below);
6. the refit of the model-free predictors, held to ``--expect-baselines-sha256``, and every
   prediction;
7. only then the sealed file: read as bytes, hashed, and parsed only behind its hash (a file
   refused for its hash has no character of that hash printed). With the
   outcomes the item set of each primary is worked out again from its probe readings
   (``fixed_sets``), and a result file that records another one stops the scoring.

The secondaries are computed after the six tests. What the checks above can hold the result
file to is that it agrees with the runs, the selection files and the declarations given here:
that it is the file the evaluator wrote rests on procedure, and its sha256 is recorded.

The runs of the sections are those the launcher's plan lists in its phase ``rest``. The
evaluator's check (``evaluate.read_group``) names a track record for the phases ``dev`` and
``confirmatory`` only; the launcher gives the runs of ``rest`` the record of fit and dev, the one
of the confirmatory runs, so they are handed to the check under that phase, which changes
nothing else of it. Every run scored here is held to the registered run sheet, not to the plan
alone: its item list, its template, its samples, its temperature, its masking and its shift are
those the launcher's rule gives the line (``rule_problems``), and that rule is held to the run
sheet of the harness and to the values the plan of the study fixes (``sheet_problems``: 20
samples at temperature 1; names masked, dates shifted by 4 years; the three paraphrase
templates of the harness). A run with its own decoding is refused by the evaluator's check on
exactly two counts, which are replaced here by the same checks against that registered
decoding, on every stored row (``decoded_group``).

Where the plan is silent, this file decides as ``WHERE_THE_PLAN_IS_SILENT`` says; what it does
because the plan states it stands, each point with its section, in ``AS_THE_PLAN_SAYS``. Every
result file carries both lists.

Refusals: status 1 and one sentence on the error stream; nothing is written. A stop while
readings are turned into predictions, or once the sealed rows are in memory, or anywhere else
in a command, gives the type of the error alone, never its message and never a traceback. The
result file and the printout are made as text, and encoded, before a file exists, and the file
is written whole or not at all (``write_result``): a result that cannot be written leaves
nothing behind, and a reason given on the command line that is not printable text on one line
is refused before any file is read. When the file is written and its summary cannot be printed
(a closed pipe), the command says that the file is written and ends with status 1: that is no
refusal.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.secondary_scores train-descriptives \\
        --out analysis/coling/out/e1_train.json
    PYTHONPATH=. python -m analysis.coling.secondary_scores score \\
        --expect-sha256 <sha256 of the sealed file> \\
        --expect-eligible-sha256 <sha256 of analysis/coling/out/eligible_e3.csv> \\
        --expect-baselines-sha256 <sha256 the baselines command printed> \\
        --expect-selection-sha256 <primary>=<sha256 of its selection file> \\
        --expect-selection-sha256 <other primary>=<sha256 of its selection file> \\
        --confirmatory analysis/coling/out/confirmatory.json \\
        --out analysis/coling/out/secondary.json
    PYTHONPATH=. python -m pytest analysis/coling/test_secondary_scores.py -q -p no:cacheprovider
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.coling import corpus, dataset, power, sealed_counts
from analysis.coling import evaluate as ev
from analysis.coling import launch as lp
from analysis.coling import predictors as P
from analysis.coling import read as rd

SECTIONS = (
    "secondary_models",
    "secondary_lists",
    "sampled_quantiles",
    "prompt_variance",
    "name_date_2x2",
    "descriptives",
    "selective_prediction",
    "recovery_rule",
)
MODEL_SECTIONS = ("secondary_models", "selective_prediction", "recovery_rule")
"""The sections that read the three conditions of every secondary model."""
SECONDARY_MODELS = tuple(model for model in rd.STUDY_MODELS if model not in ev.PRIMARIES)
REST = "rest"
"""The launcher's phase of every run scored here."""
CHECKED_AS = "confirmatory"
"""The phase under which the evaluator's check reads those runs: the one whose track record
(fit and dev) the launcher gives them."""
E3_LINES = {"a": "e3-a", "b": "e3-b", "c": "e3-c"}
PROBE_LINE = "e4-probe"
LIST_KEYS = ("tbd", "silent", "stale")
"""The three secondary item lists, by their key in the launcher's plan."""
LIST_LINES = {condition: f"e3-secondary-{condition}" for condition in ev.CONDITIONS}
FALLBACK_LISTS = dataset.FALLBACK_FORMS
"""The lists with horizon events (recovery within 90 and 180 days): TBD and silent."""
SUBSET_COLUMN = {"samples": "samples20", "paraphrase": "paraphrase", "twobytwo": "twobytwo"}
"""The column of the eligible list behind each subset list of the launcher's plan."""
SAMPLES_LINE, PARAPHRASE_LINE, CELLS_LINE = "e3-samples", "e3-paraphrases", "e4-2x2"
SAMPLES, SAMPLES_TEMPERATURE = 20, 1.0
"""PLAN section 5, E3, "Primaries only": 20 samples at temperature 1 of condition (a)."""
PARAPHRASES = 3
"""PLAN section 5, E3, "Primaries only": 3 prompt paraphrases of condition (b)."""
SHIFT_YEARS = 4
"""PLAN section 5, E4: the dates of a shifted cell of the 2x2 are moved forward by 4 years."""
REFERENCE_CELL = "real names, true dates"
CELLS = {
    "masked names, true dates": {"mask_names": True, "shift_years": 0},
    "real names, shifted dates": {"mask_names": False, "shift_years": SHIFT_YEARS},
    "masked names, shifted dates": {"mask_names": True, "shift_years": SHIFT_YEARS},
}
"""The three cells of the 2x2 that have a run of their own; the fourth is condition (b)."""
SAMPLES_FAULT = "{name}: {samples} samples per item where one is planned"
DECODING_FAULT = "{name}: {rows} rows with masked names, shifted dates or a temperature above zero"
"""The two counts on which ``evaluate.read_group`` refuses a run with its own decoding."""
PLAIN = {"mask_names": False, "shift_years": 0, "temperature": 0.0}
PLAIN_RUN = (1, 0.0, False, 0)
"""One answer at temperature zero with real names and true dates, as (samples, temperature,
masking, shift)."""
RUN_CELLS = ("list", "template", "samples", "temperature", "mask_names", "shift_years")
"""The cells of a planned run that the registered run sheet fixes, by their key in the plan."""
DECODINGS = {
    SAMPLES_LINE: [(SAMPLES, SAMPLES_TEMPERATURE, False, 0)],
    PARAPHRASE_LINE: [PLAIN_RUN] * PARAPHRASES,
    CELLS_LINE: [(1, 0.0, cell["mask_names"], cell["shift_years"]) for cell in CELLS.values()],
}
"""The runs one model makes on a line with a decoding or a count of its own, as the plan of the
study fixes them: samples, temperature, masking and shift of each. On every other line scored
here a run is ``PLAIN_RUN``."""
CANNOT_STAND = "the result file of the registered evaluator cannot stand behind the secondaries: "
DECLARATION = ev.skipped_models([f"{ev.PRIMARIES[0]}=-"])[ev.PRIMARIES[0]][:-1]
"""How the evaluator words the reason of a primary declared not evaluable, before the reason
its command line was given."""
UPTAKE_ABOVE = 0.5
MIN_SHOWN = ev.MIN_SHOWN
"""A descriptive outcome statistic over fewer statements is withheld: it would say how one or a
few statements of a named cell ended. The evaluator's own floor (five)."""
SIZES = (
    "not_both_parsed",
    "left_out",
    "statements",
    "scoreable_statements",
    "with_a_horizon_event_undetermined",
    "left_out_right_censored",
)
"""The counts of the statements that a figure is taken over, by the keys under which the
records of this file give them: two records of the same figure on a set and on a part of it
are compared by these (``beside``)."""
COUNT_KEYS = (*SIZES, "episodes", "scoreable_episodes")
"""The counts of a record that stay when its values are withheld."""
KEPT = (*COUNT_KEYS, "comparator", "tested", "sides", "minuend", "subtrahend")
"""What stays of a record whose values are withheld: its counts, and what names it."""
FILLS = ("undetermined_as_no", "undetermined_as_yes")
"""The two scenarios of PLAN section 7.2, by the keys of ``predictors.brier_bounds``."""
HOLD_SHARES = ("among_determined", "undetermined_as_no", "undetermined_as_yes")
"""The three shares of a hold rate: with the counts beside them they are one number."""
NEAR_SET = "withheld_beside_a_set_that_nearly_matches"
"""The mark of a cell of the descriptives whose figure is withheld because its statements are
those of a set whose figure is written, but for a few."""
WITH_ANOTHER = "withheld_with_another_cell"
"""The mark of a cell of the descriptives whose figure is withheld because the whole, less the
cells of its split that are written, would give back the figure on a few statements."""
LINK_HOPS = 40
"""How many symbolic links are followed on the way to a file before the path counts as one
that leads nowhere."""
SLIP_DAYS = (-30, 0, 30, 90, 180, 365)
SLIP_LEVELS = (0.25, 0.50, 0.75, 0.90)
SLIP_DRAWS = 1000
"""How many of the registered bootstrap draws give the intervals of a Turnbull estimate (the
first so many of them). It is fixed with this file and is no option of a command."""
SLIP_NEAR = 1e-3
"""A corner of a Turnbull curve this near a level is looked at again in a tighter fit."""
SLIP_TIGHTER = 1e-2
"""The tolerance of that fit, as a share of ``predictors.TOLERANCE``."""
SLIP_SETTLED = 1e-9
"""A distance from a level, or a mass, at or under this in the tighter fit counts as none."""
WIDTH_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)
DISCONTINUED_CELL = "date_discontinued_on_row_date"
"""The column of the outcome rows with the first capture where a Date Discontinued cell newly
appears on the shortage row (``corpus.followup_fields``)."""
RECOVERY_VARIANTS = (
    "limited_supply_counts_as_available",
    "leaving_the_list_counts_as_recovery",
    "date_discontinued_cell_counts_as_discontinuation",
)
VARIANT_COLUMNS = dict(
    zip(
        RECOVERY_VARIANTS,
        ("outcome_BL", f"exit_date_{dataset.DEFINITION}", DISCONTINUED_CELL),
        strict=True,
    )
)
"""The column of the outcome rows that each sensitivity analysis of the recovery rule needs."""
ABOUT = (
    "Secondary analyses of the COLING 2027 study over the sealed test outcomes (PLAN.md, standing "
    "rules; section 6, Evaluator). Descriptive: no multiplicity claim. No value of a single "
    "statement."
)
ABOUT_TRAIN = (
    "The descriptives of E1 for the train period (PLAN.md section 5, E1), from the open statement "
    "table: train-period outcomes followed to the train horizon. No sealed file is read."
)
AS_THE_PLAN_SAYS = (
    "a secondary model is scored on every eligible statement, and again on its post-cutoff "
    "slice when the slice holds at least 50 scoreable statements (section 3; section 5, E3, "
    '"Secondaries"); the scores of section 7.2 of a primary are the evaluator\'s, on the item '
    'set its probe fixed (section 5, E3; section 6, "Evaluator"), and none is computed here',
    "the comparator of H3 is the base rate by listing age for the secondary models too "
    '(section 6, "Comparator"): it is read from the selection files of the primaries, which '
    "the evaluator's check holds to that rule; the contrast against the structured-only model "
    "stands beside it, as Delta_GBM stands beside H3 of a primary",
    "every run scored here showed the track record of fit and dev (section 5, E3, condition b) "
    "and passes the refusals of section 6 (standing rules); the decodings are the registered "
    "ones: 20 samples at temperature 1 of condition (a), three paraphrases of condition (b), "
    "names masked and dates shifted forward by 4 years (section 5, E3 and E4; section 9)",
    "a reading that fails counts by its fallback: the base rate under conditions (a) and (b), "
    "the no-date table under (c) (section 4); the number of answers that put P(E_end90) below "
    "P(E_end) is given for each model and condition; a sensitivity analysis uses only the "
    "statements that both compared readings parsed; its contrast is withheld, its counts "
    f"apart, when it leaves out or rests on 1 to {MIN_SHOWN - 1} scoreable statements, and "
    f"where the failed answers of one side, or of both, number 1 to {MIN_SHOWN - 1}, its "
    "counts are withheld as well, since they would say how many of those few are scoreable "
    "(section 4)",
    "a TBD or silent statement is scored at the horizons the prompts asked about, 90 and 180 "
    'days after the statement date (section 5, E3, "Reader outputs"); under condition (c) a '
    "reading that gives a period goes through the slip estimate over all dated forms (section "
    "8, the backoff of the calibrator: a TBD or silent cell holds no dated statement)",
    "the sampled quantiles are scored at the pinball levels 0.5, 0.8 and 0.95 (section 7.2), "
    "each with its own quantile; a sample that fails to parse is left out and counted, the "
    "quantiles are those of the parsed medians, and a statement with no parsed sample takes "
    'the base-rate quantiles (section 5, E3, "Primaries only")',
    "the fourth cell of the 2x2 is the run of condition (b) on the subset (section 5, E4; "
    "section 9)",
    "the hold rate and the slip distribution of E1 are those of the dated statements that are "
    "not stale at issue (section 2.5; section 5, E1)",
    "the H1, H2 and H3 contrasts of the secondary models carry the 95% interval of the "
    "registered test with the percentile interval beside it, and H2 its 90% interval; every "
    'other secondary keeps a 95% percentile interval (section 6, "Intervals")',
    "a primary keeps the item set its probe fixed (section 5, E3 and E4), and a model whose "
    "probe beats the base rate is excluded from outcome claims on events dated before its "
    "cutoff (section 5, E4)",
    "in its sensitivity analysis a Date Discontinued cell that newly appears on a shortage row "
    "counts as a discontinuation at that capture: a displayed presentation that is censored, "
    "or whose recovery is first shown at that capture or a later one, is discontinued there, "
    "and one that had recovered at an earlier capture keeps its recovery (section 2.5)",
    "the two scenarios of section 7.2 stand beside the primary-loss estimates; where 1 to "
    f"{MIN_SHOWN - 1} statements of a set are not scoreable, the figures over every statement "
    "of the set that fill its undetermined horizon events (the two scenarios, and the two "
    "limits of calibration in the large) are withheld, and the mean probabilities and the "
    "calibration in the large on the scoreable statements, which name the few that are not, "
    f"are then withheld too; the same holds where only 1 to {MIN_SHOWN - 1} statements of a "
    'set are scoreable; the pinball losses and the coverage stay (section 2.5, "Horizon '
    'events")',
    f"a secondary figure is withheld, its counts apart, where it rests on 1 to {MIN_SHOWN - 1} "
    "statements, and where the same figure is also written on a set that differs from its own "
    f"by 1 to {MIN_SHOWN - 1} statements, so that the two together would give back the "
    "outcomes of those few (a slice within its whole, the answers that parsed within all, one "
    "outcome definition beside another); the second check is made on pairs of sets, and in "
    "the tables of E1 also on the cells written with their whole; a count is withheld too "
    "where it says, by itself or by subtraction from a count beside it, how many of 1 to "
    f"{MIN_SHOWN - 1} statements are scoreable or have a determined event; the H1, H2 and H3 "
    "contrasts of the six secondary models on every eligible statement are never withheld on "
    "the second ground: the figure that stands beside one of them is the one withheld "
    "(standing rules; sections 2.5, 4, 5 (E1 and E4), 6 and 13 name the cases known at "
    "registration)",
    "a contrast under a sensitivity analysis or under another outcome definition (definition "
    "A; the outcome over all or over any covered presentation) that gives 1 to "
    f"{MIN_SHOWN - 1} statements of its item set another horizon event, or 1 to "
    f"{MIN_SHOWN - 1} of those scoreable under either definition, is withheld with its two "
    "scenarios, and the number of statements with another horizon event is given: beside the "
    "same contrast under the primary outcome it would give the change of the losses of those "
    'few (section 2.5, "Sensitivity analyses")',
    "this command reads the sealed rows through the checked reader of the counts-only code, "
    "behind its own hash check, reads no stored file that leads into a sealed folder through a "
    "link, and prints no character of a sealed file's hash where it refuses the file for its "
    "hash (standing rules; the evaluator reads the sealed outcomes so, and a scorer in the "
    "same way)",
    f"the figures of a probe over 1 to {MIN_SHOWN - 1} targets are withheld; its verdict is "
    "given; with fewer than two episodes left there is no verdict (section 5, E4, "
    '"Test": for the probe of a secondary model as for that of a primary)',
    "the Brier decomposition into reliability, resolution and uncertainty is the evaluator's, "
    "with 10 equal-count bins for each horizon event: statements that share a probability "
    "count with the frequency of the event among all of them, so that the figures do not "
    "depend on the order of the statements, and a forecast of one value has no resolution "
    '(section 7.2, "Brier decomposition")',
    "in the tables of the hold rate and of the slip of E1, a further cell is withheld and "
    "marked where the cells written and the whole would otherwise give back the figure on 1 "
    f"to {MIN_SHOWN - 1} statements (section 5, E1)",
    f"the intervals of a Turnbull estimate use the first {SLIP_DRAWS:,} of the {ev.DRAWS:,} "
    "registered draws, since every draw needs a fit of its own (section 5, E1); the number is a "
    "constant of the code and no option of a command, the result file records it, and every "
    "other interval uses all the draws",
    "for a primary whose probe beat the base rate, the figures of the 20-sample subset, of the "
    "paraphrase subset and of the TBD, silent and stale lists that are scored against outcomes "
    'are given again on the statements dated after its cutoff (section 5, E3, "Primaries '
    'only")',
    "a primary whose confirmatory runs could not be completed is declared not evaluable on "
    "this command line as on the evaluator's, with the same reason: a declaration that the "
    "evaluator's result file does not record is refused, and so is one that the file records "
    'and this command line does not give (section 6, "Confirmatory runs")',
)
"""What this file does as the plan states it, each point with its section: no choice of the
code. Every result file carries the list."""
WHERE_THE_PLAN_IS_SILENT = (
    "the probe test of a secondary model is reported beside its numbers without changing the "
    "item set: the exclusion of E4 for a model that beats the base rate is applied from that "
    "verdict when its numbers are read",
    "the descriptive decomposition of E3 is given for a secondary model on every eligible "
    "statement and again on its post-cutoff slice when that slice is analysed, each part "
    "two-sided with a 95% percentile interval, as the evaluator gives it for a primary; its "
    "reading loss is the H2 contrast with the sign turned",
    "the contrasts of a secondary model are repeated, in short and with percentile intervals, "
    "under the outcome variants (the recovery definition A; the outcome over all and over any "
    "covered presentation), on the statements first captured by the stated end, with the "
    "episodes resampled by company, and H2 on the month-and-year form, as the evaluator "
    "repeats the tests of a primary; they are given on every eligible statement, because a "
    "secondary model has no item set fixed by a probe; a repeat on a part of the statements "
    "stands beside the contrast on all of them, and under the standing rule it is the one "
    f"withheld when the part leaves out 1 to {MIN_SHOWN - 1} scoreable statements; a repeat "
    "under an outcome definition is held to the rule of section 2.5 against the primary "
    "outcome and against each definition written before it",
    "a primary is read on every statement of the 20-sample subset, the paraphrase subset, the "
    "subset of the 2x2 and the TBD, silent and stale lists, with the evaluator's record of its "
    "item set beside each; where its figures are given again on the statements dated after its "
    "cutoff, those on the whole subset or list are marked as holding statements the probe "
    "excludes, and those after the cutoff are withheld when they, or the statements before the "
    f"cutoff, number 1 to {MIN_SHOWN - 1}, or as many scoreable ones, or as many that are not "
    "scoreable, and each of them when the part or the count it rests on differs by so few from "
    "the same on the whole; the 2x2, which is the memory control, keeps the whole subset, and "
    "so do the quantities that read no outcome",
    "the runs scored here are those of the launcher's phase rest; the evaluator's own check "
    "reads them under the phase whose track record they showed, and the two counts on which "
    "that check refuses a sampled, masked or shifted run are replaced by the same checks "
    "against the registered decoding, on every stored row; each run is held to the registered "
    "run sheet (item list, template, samples, temperature, masking, shift; the three "
    "paraphrase templates of the harness), whatever the plan of the runs says",
    "stale-value uptake is given again over the parsed readings alone",
    "a sample that did not parse is left out, not replaced by the base rate, and a statement "
    "with no parsed sample takes the base-rate quantiles, as the plan says; the quantile at "
    "level t of the k parsed medians of a statement is the j-th smallest, with j the smallest "
    "whole number at least t times k (the harness rule, read.sampled_quantiles); the "
    "statements with a sample left out, and those with none parsed, are counted",
    "prompt variance is the range and the standard deviation of the mean primary loss over the "
    "three paraphrases (and with the registered prompt as a fourth), the mean over statements of "
    "the standard deviation of P(E_end), P(E_end90) and the median across the paraphrases, and "
    "each paraphrase's change from the registered prompt",
    "the changes of the 2x2 are measured from the cell of condition (b): a change is the other "
    "cell minus that cell; beside the three changes the plan names stand the two main effects "
    "and their interaction on the loss (the main effect of a factor is the mean of its two "
    "changes, and the interaction is the difference between them), and the mean absolute "
    "change is given for P(E_end90) as well as for P(E_end) and the median",
    "every change, effect and contrast outside the H1, H2 and H3 contrasts of the secondary "
    "models carries a 95% percentile interval and, beside it, the p-value of the registered "
    'procedure (PLAN section 6, "Intervals"); no p-value here is adjusted and none is read '
    "as a verdict, and an interval and the p-value beside it can disagree; the equivalence "
    "reading on the H2 contrast of a secondary model is the rule of section 6 applied outside "
    "the family",
    "the counts and the bracket widths of E1 cover the statements at risk under B in the sets "
    "dated, stale, TBD and silent (for the test period: those of the test split, whether or "
    "not their horizon is reached)",
    "the hold rate is given among the statements whose E_end is determined, and with every "
    "undetermined one set to no and then to yes; the Turnbull share recovered by the stated end "
    "stands beside it",
    "the slip quantiles and the share not recovered within reach of a Turnbull estimate, and "
    "the quantiles of the bracket widths, are given without an interval",
    "where a Turnbull curve is flat exactly at a quantile level (a corner at the level, with "
    "no recovery for some days after it), the slip quantile is the start of the flat stretch, "
    "the smallest day that reaches the level, and the day on which the stretch ends is given "
    "beside it; a corner counts as standing at the level when it is within 0.001 of it and at "
    "most a third as far in a second fit under a tolerance a hundred times tighter, which "
    "tells what the iteration left over from a corner that stands off the level",
    "how the standing rule is applied in the descriptives of E1: a slip estimate or the "
    f"bracket widths over 1 to {MIN_SHOWN - 1} statements, and the three shares of a hold rate "
    "with so few determined statements, are the figures that rest on a few; a hold rate over "
    "so few statements keeps their number alone; the further cell withheld in a table is the "
    "one with the fewest determined statements (for a slip estimate the fewest statements; "
    "the first by name among equals), one cell after another until the cells written, with "
    "the whole, give back no hold rate, no count of determined statements and no slip "
    "estimate on so few, and a set of cells of one split beside a set of cells of the other "
    "counts among the cells written",
    "the standing rule of withholding on the losses: the loss of a part of selective prediction "
    f"over 1 to {MIN_SHOWN - 1} scoreable statements is withheld with its bounds, and the other "
    "part with it (the loss on all, which is given, less the part shown would give it back); "
    "the mean losses, their changes, the effects and the spread of the mean loss in the 2x2 and "
    "across the paraphrases over so few, while the mean absolute changes, which use no outcome, "
    "stay; the floor of five statements holds for every figure written here, whichever "
    "function computed it: a contrast, a score of section 7.2 or a pinball loss over 1 to "
    f"{MIN_SHOWN - 1} statements is withheld, counts apart; a contrast that is not evaluable "
    "(fewer than two shortage episodes: section 6) carries no estimate",
    "the counts that the standing rule withholds here, each written as null or left out: the "
    f"scoreable statements among 1 to {MIN_SHOWN - 1} failed answers, or among as few that "
    "parsed; the scoreable statements of a part of selective prediction of so few statements "
    "(and those of the other part, which the whole would give); every count but the number of "
    "statements in a score, a scenario or a repeat over so few statements; every count of a "
    "post-cutoff slice of a secondary model, or of a repeat on a part of the statements, that "
    "is the list but for so few statements (such a slice is not said to be analysed or not, "
    "which would tell as much); and every count of a contrast under an outcome definition "
    "that is withheld by section 2.5, with the two counts of a recovery variant over the "
    "eligible list where it moves so few statements of the list",
    "a secondary model's contrast against the structured-only model, which the plan asks for "
    "the primaries alone, carries the 95% interval of the registered source with the percentile "
    "intervals beside it, as the plan gives them to the H1, H2 and H3 contrasts of the secondary "
    "models; the same holds where those contrasts are repeated on the post-cutoff slice; H2 of "
    "a secondary model also carries the equivalence reading; a contrast that is not evaluable "
    "holds no interval",
    "the sensitivity analysis of section 4 on the statements that both compared readings parsed "
    "stands beside the H1, H2 and H3 contrasts of the secondary models, the contrasts of the "
    "TBD and silent lists against the base rate, the loss changes of the 2x2 and of the "
    "paraphrases, and sampled against verbalised quantiles (parsed there: the verbalised answer "
    "was, and at least one sample of the statement), under one rule of withholding for all of "
    "them, the plan's (section 4), applied as well between a set and a part of it on which the "
    "same contrast is written (the post-cutoff slice within the list, the statements after a "
    "cutoff within a subset); the failed answers of one side are those that failed on it "
    "alone, and of both those that failed on both; a record whose counts are withheld keeps "
    "the number of answers that failed, which anyone can count; it carries no bounds; the "
    "contrasts repeated under another outcome or recovery rule are given on every scoreable "
    "statement only",
    "with fewer than ten scoreable statements the Brier decomposition, which is the "
    "evaluator's, has one bin for each statement",
    "a secondary model whose runs cannot be completed (sections 9 and 12) is left out by a "
    "declaration on the command line, as section 6 gives it for a primary; the declaration is "
    "refused when the completeness check finds nothing wrong with the runs this command would "
    "read of the model, so a model whose runs are complete is scored even when it was dropped "
    "elsewhere; the result file records the reason given and what the check found",
    "the two scenarios of section 7.2 (the bounds) stand beside each contrast, each mean loss "
    "of the 2x2 and of the paraphrases, each effect of the 2x2 (the combination of the cells' "
    "scenario means that gives the effect) and each spread across prompts (the range and the "
    "standard deviation of the prompts' scenario means), each part of selective prediction, "
    "and each contrast under a variant of the recovery rule (there over the statements at risk "
    "under the variant); in selective prediction the scenarios of both parts are withheld when "
    f"either part holds 1 to {MIN_SHOWN - 1} statements that are not scoreable; the stale "
    "list, whose statements have no horizon event, has an abstention rate and no loss",
    "selective prediction is one point per reader: the share of statements on which the reading "
    "gives no stated period (ABSTAIN, a failed reading, or a period of another statement type), "
    "and the primary loss on the statements read, on the others (the no-date table) and on all; "
    "the rule reader reads every eligible statement by the definition of eligibility, so its "
    "abstention rate is zero by construction and its point is the loss of rules plus slip that "
    "the evaluator reports; the TBD, silent and stale lists are defined by the rule reading (it "
    "reads none of the first two and all of the third), so no point of the rule reader is "
    "given there",
    "the sensitivity analyses of the recovery rule repeat the contrasts on the displayed "
    "presentation; a statement not at risk under BL is not scored there; in the analysis of "
    "the Date Discontinued cell the stored lower bound is not rebuilt, so that variant serves "
    "the horizon events and the capped time target only (no bracket width is read from it); "
    "the rule of section 2.5 on a variant that gives a few statements another horizon event "
    "is applied as well between any two outcome definitions whose contrasts are written on the "
    "same statements, pair by pair as the standing rule has it, and the models withheld for it "
    "are named; a variant whose column the outcome rows do not hold is recorded as not "
    "computed",
)
"""The choices of this file where the plan gives no rule, and how it applies the standing rule
of withholding where the plan names no case. Every result file carries the list."""
COMPUTED_BY_ANOTHER_SCRIPT = (
    "E2 and E5: they read no sealed file and have a scorer of their own (literal_scores.py)",
    "the accuracy of the rule reading on the 100-statement check, beside H2: from the "
    "reference-reading check (audit_reference.py; PLAN section 10)",
    "the minimum detectable differences beside a null: from the power code at the gate (power.py)",
)
"""Registered figures that this file does not compute and another script of the study does."""
COMPUTED_BY_NO_SCRIPT = (
    "the fit that leaves out the dominant company (Hospira and Pfizer)",
    "the full-follow-up refit of every train-fitted component (it needs the second sealed file)",
    "the analysis by statement type (PLAN section 5, E3): the contrasts, the losses, the "
    "calibration in the large and the overconfidence criterion on the recovery statements and "
    "on the next-delivery statements apart, and with it the hold rate and the slip "
    "distribution of E1 by statement type",
    "the mean of P(E_end) minus the Turnbull share recovered by the stated end, beside the "
    "overconfidence criterion (PLAN section 13)",
    "E7 (the next in the cut order of PLAN section 12)",
)
"""Registered secondary analyses over a sealed file that no script of the study computes at
this version of the code: what this file does not compute yet."""
STILL_NOT_COMPUTED = (
    "a secondary analysis that is still not computed by the freeze of numbers is named in the "
    "paper as not run (PLAN section 6; section 12)"
)


# --------------------------------------------------------------------------------------------
# The runs of the phase rest, read by the evaluator's check
# --------------------------------------------------------------------------------------------


def runs_of(plan: Mapping[str, Any], model: str, line: str, **where: Any) -> list[dict]:
    """The runs of ``model`` on ``line`` in the phase ``rest`` whose plan cells are ``where``
    (the item list, the template, masking or the shift)."""
    return [
        run
        for run in lp.select(plan, [REST], models=[model])
        if run["line"] == line and all(run.get(key) == value for key, value in where.items())
    ]


def as_checked(plan: Mapping[str, Any], runs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The plan with these runs alone, under the phase the evaluator's check reads them as."""
    return {**plan, "runs": [{**run, "phase": CHECKED_AS} for run in runs]}


def checked_group(
    plan: Mapping[str, Any],
    out_root: Path,
    model: str,
    line: str,
    expected: Iterable[str],
    first: pd.DataFrame | None,
    **where: Any,
) -> ev.Group:
    """``evaluate.read_group`` on the runs of ``runs_of``: complete, of the registered route,
    template and item set, with the track record of fit and dev."""
    shown = as_checked(plan, runs_of(plan, model, line, **where))
    group = ev.read_group(shown, out_root, CHECKED_AS, model, line, expected, first)
    return replace(group, problems=(*group.problems, *rule_problems(plan, model, line, **where)))


def sheet_problems(line: str) -> list[str]:
    """What is wrong with the launcher's rule for a line scored here (``launch.parts_of``),
    which ``rule_problems`` holds the plan to: the rule is itself held to the run sheet of the
    harness (its runs give the calls per item of the sheet line on each item list of the line:
    the rule of ``launch.check_rules``) and to the decodings the plan of the study fixes
    (``DECODINGS``). The launcher is not the only word on what is registered."""
    sheet = sheet_line(line)
    parts, why = lp.parts_of(sheet)
    if not parts:
        return [f"{line}: {why}"]
    problems = []
    lists = {spec.key for spec in lp.LISTS if spec.count == sheet.count}
    calls = {key: sum(part.samples for part in parts if part.items == key) for key in lists}
    if {part.items for part in parts} != lists or set(calls.values()) != {sheet.per_item}:
        problems.append(
            f"{line}: the launcher's runs do not give the {sheet.per_item} calls per item of the "
            "run sheet on each item list of the line"
        )
    decodings = [
        (part.samples, part.temperature, part.mask_names, part.shift_years) for part in parts
    ]
    if sorted(decodings) != sorted(DECODINGS.get(line, [PLAIN_RUN] * len(parts))):
        problems.append(
            f"{line}: the launcher's runs do not have the registered decoding (samples, "
            "temperature, masking and shift)"
        )
    return problems


def rule_problems(plan: Mapping[str, Any], model: str, line: str, **where: Any) -> list[str]:
    """Whether the runs of ``runs_of`` are runs of the registered run sheet: the launcher's rule
    for the line (``launch.parts_of``, which holds the paraphrase line to the templates of the
    harness; ``sheet_problems`` holds the rule itself to the run sheet and to the plan of the
    study) fixes the item list, the template, the number of samples, the temperature, the
    masking and the shift of each of its runs (``RUN_CELLS``), and the plan is held to that
    rule, not the run to the plan alone."""
    sheet = sheet_line(line)
    parts, _ = lp.parts_of(sheet)
    registered = {
        (
            part.items,
            part.template or sheet.template,
            part.samples,
            part.temperature,
            part.mask_names,
            part.shift_years,
        )
        for part in parts
    }
    other = sum(
        tuple(run[key] for key in RUN_CELLS) not in registered
        for run in runs_of(plan, model, line, **where)
    )
    if not other:
        return []
    return [
        f"{model} {line}: the plan holds {other} runs that are not runs of the registered run "
        "sheet (item list, template, samples, temperature, masking or shift)"
    ]


def decoded_group(
    plan: Mapping[str, Any],
    out_root: Path,
    model: str,
    line: str,
    expected: Iterable[str],
    first: pd.DataFrame,
    **where: Any,
) -> tuple[ev.Group, dict[tuple[str, int], dict]]:
    """A run with its own decoding: the group of ``checked_group`` and every stored row by
    (item, sample). The evaluator's check refuses such a run for its sample count and for rows
    that are masked, shifted or sampled above temperature zero. Those two counts, and no other,
    are taken out of its problems when they are exactly what the plan gives the run, and
    ``checked_group`` holds the plan's run to the registered run sheet, so that decoding is the
    registered one; every stored row of every sample is then held to it, to the evaluator's
    other row checks and to the registered horizons."""
    runs = runs_of(plan, model, line, **where)
    group = checked_group(plan, out_root, model, line, expected, first, **where)
    if not runs or not group.rows:
        return group, {}
    name, run = f"{model} {line}", runs[0]
    decoding = {key: run[key] for key in PLAIN}
    allowed = set()
    if run["samples"] != 1:
        allowed.add(SAMPLES_FAULT.format(name=name, samples=run["samples"]))
    if decoding != PLAIN:
        allowed.add(DECODING_FAULT.format(name=name, rows=len(group.rows)))
    problems = [problem for problem in group.problems if problem not in allowed]
    pooled = rd.collect_readings(out_root, [run["run"] for run in runs])
    rows = next(iter(pooled.values()))["rows"]
    other = sum({key: row.get(key) for key in PLAIN} != decoding for row in rows.values())
    if other:
        problems.append(f"{name}: {other} rows with another decoding than the registered one")
    faulty = sum(
        bool(ev.row_faults({**row, **PLAIN}, model, group.template)) for row in rows.values()
    )
    if faulty:
        problems.append(f"{name}: {faulty} rows that the evaluator's row checks refuse")
    for sample in range(1, run["samples"]):
        drawn = {item: row for (item, index), row in rows.items() if index == sample}
        if ev.asked_elsewhere(drawn, first):
            problems.append(f"{name}: rows of a later sample asked about other horizons")
            break
    return replace(group, problems=tuple(problems)), rows


def asked_wrongly(rows: Mapping[str, dict], first: pd.DataFrame) -> int:
    """How many stored rows of a predictive condition asked about other horizons than the
    statement table gives the statement (``horizon_a``, ``horizon_b`` and the rule that set
    them: the stated end and 90 days later, or 90 and 180 days after the statement date)."""
    wrong = 0
    cells = zip(
        first.index, first["horizon_a"], first["horizon_b"], first["horizon_rule"], strict=True
    )
    for item_id, a, b, rule in cells:
        if item_id in rows:
            asked = rows[item_id].get("horizons") or {}
            wrong += (asked.get("a"), asked.get("b"), asked.get("rule")) != (a, b, rule)
    return wrong


def sheet_line(line: str) -> rd.SheetLine:
    """A line of the harness's run sheet, by its name."""
    return next(entry for entry in rd.RUN_SHEET if entry.name == line)


def sheet_models(line: str) -> tuple[str, ...]:
    """The models that read a line of the harness's run sheet."""
    return sheet_line(line).models


@dataclass
class More:
    """The runs of the sections asked for, as the completeness check found them."""

    problems: list[str] = field(default_factory=list)
    models: dict[str, dict[str, ev.Group]] = field(default_factory=dict)
    """By secondary model and condition (a, b, c, and the probe where the model is probed)."""
    ids: dict[str, list[str]] = field(default_factory=dict)
    """The statements of each item list besides the eligible one, by the plan's key."""
    lists: dict[str, dict[str, dict[str, ev.Group]]] = field(default_factory=dict)
    """By primary, secondary list and condition."""
    samples: dict[str, dict[tuple[str, int], dict]] = field(default_factory=dict)
    """By primary: every stored row of the 20-sample run, by (item, sample)."""
    cells: dict[str, dict[str, ev.Group]] = field(default_factory=dict)
    """By primary and cell of the 2x2."""
    paraphrases: dict[str, dict[str, ev.Group]] = field(default_factory=dict)
    """By primary and paraphrase template."""
    records: dict[str, Any] = field(default_factory=dict)


def gather_more(
    plan: Mapping[str, Any],
    out_root: Path,
    table: pd.DataFrame,
    eligible: pd.DataFrame,
    first: pd.DataFrame,
    counts: Mapping[str, Any],
    sections: Sequence[str],
    models: Sequence[str],
    primaries: Sequence[str],
) -> More:
    """The completeness check on every run the ``sections`` score: the three conditions (and
    the probe) of the secondary ``models``, and the secondary lists, the 20 samples, the
    paraphrases and the cells of the 2x2 of the ``primaries``. ``first`` holds the first-sight
    cells of every statement of the table, by id. No outcome is read."""
    more = More()
    ids = list(eligible["statement_group_id"])
    probe_ids = sorted(eligible.loc[eligible[ev.PROBE] == "1", "statement_group_id"])

    def keep(what: str, group: ev.Group) -> ev.Group:
        more.problems += [f"{what}{problem}" for problem in group.problems]
        return group

    def subset(key: str) -> list[str]:
        chosen = sorted(eligible.loc[eligible[SUBSET_COLUMN[key]] == "1", "statement_group_id"])
        more.problems += ev.list_problems(plan, key, chosen, f"the {key} subset of the list")
        more.problems += ev.item_file_problems(plan, counts, (key,))
        more.ids[key] = chosen
        return chosen

    def registered(*lines: str) -> None:
        for line in lines:
            more.problems += sheet_problems(line)

    if set(MODEL_SECTIONS) & set(sections):
        probed = sheet_models(PROBE_LINE) if "secondary_models" in sections else ()
        registered(*E3_LINES.values(), *([PROBE_LINE] if probed else []))
        for model in models:
            more.models[model] = {
                condition: keep("", checked_group(plan, out_root, model, line, ids, first))
                for condition, line in E3_LINES.items()
            }
            if model in probed:
                more.models[model][ev.PROBE] = keep(
                    "", checked_group(plan, out_root, model, PROBE_LINE, probe_ids, first)
                )
    if "secondary_lists" in sections:
        registered(*LIST_LINES.values())
        written = dataset.item_lists(table, eligible)
        for key in LIST_KEYS:
            more.ids[key] = list(written[f"e3_{key}"][0])
            if more.ids[key]:
                more.problems += ev.list_problems(
                    plan, key, more.ids[key], f"the registered {key} list"
                )
                more.problems += ev.item_file_problems(plan, counts, (key,))
        for model in primaries:
            more.lists[model] = {}
            for key in (key for key in LIST_KEYS if more.ids[key]):
                cells = first.loc[more.ids[key]]
                more.lists[model][key] = {}
                for condition, line in LIST_LINES.items():
                    group = keep(
                        f"{key} list, ",
                        checked_group(plan, out_root, model, line, more.ids[key], None, list=key),
                    )
                    more.lists[model][key][condition] = group
                    predictive = group.template in rd.TEMPLATES and (
                        rd.TEMPLATES[group.template].kind == "predictive"
                    )
                    wrong = asked_wrongly(group.rows, cells) if predictive else 0
                    if wrong:
                        more.problems.append(
                            f"{key} list, {model} {line}: {wrong} rows asked about other "
                            "horizons than the registered"
                        )
    if "sampled_quantiles" in sections:
        registered(SAMPLES_LINE)
        chosen = subset("samples")
        for model in primaries:
            group, more.samples[model] = decoded_group(
                plan, out_root, model, SAMPLES_LINE, chosen, first.loc[chosen]
            )
            status = [row.get("status") for row in more.samples[model].values()]
            more.records.setdefault(model, {})[SAMPLES_LINE] = {
                **keep("", group).record,
                "rows": len(status),
                "parse_failure_rate": status.count("failed") / len(status) if status else None,
                "refusal_rate": status.count("refused") / len(status) if status else None,
            }
    if "name_date_2x2" in sections:
        registered(CELLS_LINE)
        chosen = subset("twobytwo")
        for model in primaries:
            more.cells[model] = {}
            for cell, decoding in CELLS.items():
                group, _ = decoded_group(
                    plan, out_root, model, CELLS_LINE, chosen, first.loc[chosen], **decoding
                )
                more.cells[model][cell] = keep(f"{cell}, ", group)
    if "prompt_variance" in sections:
        registered(PARAPHRASE_LINE)
        chosen = subset("paraphrase")
        # the templates are those of the harness, as many as the run sheet registers, and not
        # whatever the plan lists on the line; a run of the line under any other template is
        # not a run of the run sheet
        sheet = sheet_line(PARAPHRASE_LINE)
        templates = [part.template or sheet.template for part in lp.parts_of(sheet)[0]]
        for model in primaries:
            more.problems += rule_problems(plan, model, PARAPHRASE_LINE)
            more.paraphrases[model] = {
                template: keep(
                    f"{template}, ",
                    checked_group(
                        plan,
                        out_root,
                        model,
                        PARAPHRASE_LINE,
                        chosen,
                        first.loc[chosen],
                        template=template,
                    ),
                )
                for template in templates
            }
    return more


def left_out_findings(
    plan: Mapping[str, Any],
    out_root: Path,
    eligible: pd.DataFrame,
    first: pd.DataFrame,
    sections: Sequence[str],
    left_out: Iterable[str],
) -> dict[str, list[str]]:
    """What the completeness check finds wrong with the runs of each secondary model that is
    declared left out: the runs this command would read of it (``gather_more``), its three
    conditions and, where the section of the secondary models is computed and the model is
    probed, its probe. A stop of the check on a stored run is a finding too, named by the type
    of the error alone. A model with no finding has complete runs and is not left out
    (``run_score`` refuses the declaration); no reading of a model left out is scored. The
    findings are counts and run names, never items (``evaluate.read_group``)."""
    ids = list(eligible["statement_group_id"])
    probe_ids = sorted(eligible.loc[eligible[ev.PROBE] == "1", "statement_group_id"])
    probed = sheet_models(PROBE_LINE) if "secondary_models" in sections else ()
    out: dict[str, list[str]] = {}
    for model in left_out:
        lines = [(line, ids) for line in E3_LINES.values()]
        lines += [(PROBE_LINE, probe_ids)] if model in probed else []
        out[model] = []
        for line, expected in lines:
            try:
                out[model] += checked_group(plan, out_root, model, line, expected, first).problems
            except Exception as error:
                stopped = type(error).__name__
                out[model].append(
                    f"{model} {line}: the check stopped on the stored run ({stopped})"
                )
    return out


def gathered_more(*args: Any) -> More:
    """``gather_more``, for the command. A stop inside it is one more thing the check finds,
    named by the type of the error alone: its message may quote a stored row."""
    try:
        return gather_more(*args)
    except Exception as error:
        stopped = type(error).__name__
    why = (
        f"the completeness check stopped on the plan or the stored runs ({stopped}): they are "
        "not as the launcher and the harness write them"
    )
    return More(problems=[why])


# --------------------------------------------------------------------------------------------
# The result file of the registered evaluator
# --------------------------------------------------------------------------------------------


def confirmatory_record(
    path: Path | None, hashes: Mapping[str, str], want_sealed: str, want_baselines: str
) -> tuple[dict[str, Any], str]:
    """The result file of ``evaluate.py confirmatory`` and its sha256. Refused unless it is
    there, holds the six tests with their Holm-adjusted p-values under the constants in force,
    and records the files this command is given: the sealed file and the model-free predictions
    of the two expected hashes, and the eligible list, the statement table and the events table
    of ``hashes``. The secondaries are computed after the six tests, never before."""
    if path is None or not path.name:
        ev.refuse("--confirmatory is required: the result file of the registered evaluator")
    if not path.is_file():
        ev.refuse(
            "no secondary score before the six tests: the result file of the registered "
            f"evaluator is not there ({path.as_posix()})"
        )
    data = sealed_counts.file_bytes(path, "the result file of the evaluator")
    try:
        record = json.loads(data)
    except ValueError:
        record = None
    record = record if isinstance(record, dict) else {}
    family, inputs = record.get("family"), record.get("inputs")
    inputs = inputs if isinstance(inputs, dict) else {}
    wrong = []
    if record.get("about") != ev.ABOUT_RESULTS or not isinstance(family, list):
        wrong.append("it is not a result of the confirmatory command")
    elif len(family) != ev.TESTS or not all(
        isinstance(entry, dict) and "p_holm" in entry for entry in family
    ):
        wrong.append("it does not hold the six tests with their Holm-adjusted p-values")
    if record.get("registered") != json.loads(ev.report_text(ev.registered_record())):
        wrong.append("it was written under other registered constants than those in force")
    same = {
        "the sealed file": str(inputs.get("sealed_outcomes_sha256")).startswith(want_sealed),
        "the model-free predictions": str(inputs.get("baseline_predictions_sha256")).startswith(
            want_baselines
        ),
        "the eligible list": inputs.get("eligible_sha256") == hashes["the eligible list"],
        "the statement table": inputs.get("statements_sha256") == hashes["the statement table"],
        "the events table": inputs.get("events_sha256") == hashes["the events table"],
    }
    other = [what for what, ok in same.items() if not ok]
    if other:
        wrong.append(f"it was computed on another file than given here for: {', '.join(other)}")
    if wrong:
        ev.refuse(CANNOT_STAND + "; ".join(wrong))
    return record, sealed_counts.sha256(data)


def part_of(record: Any, *keys: str) -> dict[str, Any]:
    """The mapping under ``keys`` of a record read from a file; empty when the file holds
    anything else there."""
    for key in keys:
        record = record.get(key) if isinstance(record, dict) else None
    return record if isinstance(record, dict) else {}


def tests_under(
    selection: Mapping[str, str], comparator: str
) -> dict[str, list[tuple[str, str, str, int]]]:
    """The three tests of each primary (``evaluate.tests_of``), as (hypothesis, comparator,
    tested, sides), under a comparator of H3 and the condition selected for each primary."""
    held = ev.Study(
        first=pd.DataFrame(),
        probe_ids=[],
        predictions={},
        parsed={},
        probe={},
        selection=dict(selection),
        comparator=comparator,
        runs={},
        not_evaluable={},
        refit={},
    )
    return {model: ev.tests_of(model, held) for model in ev.PRIMARIES}


def declared(
    record: Mapping[str, Any], skipped: Mapping[str, str], frozen: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """What the evaluator's result file records of its own check: the primaries declared not
    evaluable with the reason it was given, and the sha256 of the selection file of each other
    primary. No run has been read yet. Refused:

    * unless the file records its declarations as the evaluator writes them: a mapping of
      model to reason, empty when none was made;
    * when the file declares every primary: the evaluator refuses to start so, and the sealed
      file is not opened for the secondaries alone;
    * unless the primaries it declares, each with its reason, are those of ``skipped`` (the
      ``--not-evaluable`` of this command: the file confirms a declaration and never grants
      one);
    * unless its family is H1, H2 and H3 of each primary in the evaluator's order, the three
      tests of a declared primary are recorded as not evaluable for the reason declared, and
      no test of another primary is (one that the probe left without an item set is not
      evaluable either, for that reason and not by a declaration);
    * unless the selection hash of each primary that is not declared is the one of ``frozen``
      (``--expect-selection-sha256``: the hashes of the freeze)."""
    said = record.get("not_evaluable_by_declaration")
    if not isinstance(said, dict) or not all(isinstance(reason, str) for reason in said.values()):
        ev.refuse(
            CANNOT_STAND + "it does not record, model by model with the reason, which primaries "
            "were declared not evaluable"
        )
    if set(said) >= set(ev.PRIMARIES):
        ev.refuse(
            CANNOT_STAND + "it declares every primary not evaluable: no test of the family can "
            "have been computed, and the sealed file is not opened for the secondaries alone"
        )
    if said != dict(skipped):
        ev.refuse(
            CANNOT_STAND + f"the primaries it records as declared not evaluable ({sorted(said)}) "
            "are not those that --not-evaluable names, each with the reason given there "
            f"({sorted(skipped)})"
        )
    family = list(record["family"])
    registered = [
        (model, test[0]) for model, tests in tests_under({}, "").items() for test in tests
    ]
    if [(entry.get("model"), entry.get("hypothesis")) for entry in family] != registered:
        ev.refuse(CANNOT_STAND + "its six tests are not H1, H2 and H3 of each primary")
    wrong = []
    for model in ev.PRIMARIES:
        entries = [entry for entry in family if entry["model"] == model]
        if model in said:
            if not all(
                entry.get("evaluable") is False and entry.get("reason") == said[model]
                for entry in entries
            ):
                wrong.append(f"it holds tests of {model}, which it declares not evaluable")
        elif not all(
            isinstance(entry.get("evaluable"), bool)
            and not str(entry.get("reason", "")).startswith(DECLARATION)
            for entry in entries
        ):
            wrong.append(
                f"it does not say whether each test of {model} is evaluable, or records one as "
                "declared not evaluable where it declares nothing"
            )
    if wrong:
        ev.refuse(CANNOT_STAND + "; ".join(wrong))
    hashes = {
        model: str(part_of(record, "h3", "selections", model).get("sha256") or "")
        for model in ev.PRIMARIES
        if model not in skipped
    }
    if any(len(value) != 64 for value in hashes.values()):
        ev.refuse("the result file of the registered evaluator names no selection file hash")
    other = [model for model, value in hashes.items() if not value.startswith(frozen[model])]
    if other:
        ev.refuse(
            CANNOT_STAND + "it was computed with another selection file than the one hashed at "
            f"the freeze for: {', '.join(other)}"
        )
    return dict(said), hashes


def held_to_the_runs(
    record: Mapping[str, Any], said: Mapping[str, str], found: ev.Gathered, first: pd.DataFrame
) -> None:
    """Refuse unless the evaluator's result file is the one of the confirmatory runs and the
    selection files that the completeness check found (``found``; ``first`` holds the
    first-sight cells of the eligible statements): a file that is stale, edited or made by hand
    stands behind no secondary.

    * The stored readings of every confirmatory run are those the six tests were computed on
      (the sha256 of each run's readings, as that file records it).
    * The comparator of H3 is the one of the selection files, and the three tests of each
      primary that is not declared not evaluable (``said``; ``declared`` has held the family to
      the declaration) are those the selection files give (``evaluate.tests_of``).
    * Each such primary has the item set its probe fixed: every eligible statement or its
      post-cutoff slice, with the size the first-sight dates give that slice, or none with the
      reason; and each of its tests names that item set."""
    wrong = []
    stale = [
        f"{model} {group.line}"
        for model, groups in found.groups.items()
        for condition, group in groups.items()
        if part_of(record, "runs", model, condition).get("readings_sha256")
        != group.record["readings_sha256"]
    ]
    if stale:
        wrong.append(
            f"the stored readings are not those the six tests were computed on ({', '.join(stale)})"
        )
    family = list(record["family"])
    tests = tests_under(
        {model: found.selections[model]["selected"] for model in found.groups}, found.comparator
    )
    if (
        part_of(record, "h3").get("comparator") != found.comparator
        or found.comparator not in ev.COMPARATOR_CANDIDATES
    ):
        wrong.append("its comparator of H3 is not the one of the selection files")
    for model in ev.PRIMARIES:
        entries = [entry for entry in family if entry["model"] == model]
        if model in said:
            continue
        named = [
            (entry["hypothesis"], entry.get("comparator"), entry.get("tested"), entry.get("sides"))
            for entry in entries
        ]
        if named != tests[model]:
            wrong.append(f"its tests of {model} are not those the selection file gives")
        fixed = part_of(record, "item_sets", model)
        cutoff = sealed_counts.CUTOFF_MONTH_ENDS[model]
        after = int((first["event_date"] > cutoff.isoformat()).sum())
        items = fixed.get("items") if fixed.get("evaluable") is True else None
        if (
            not isinstance(fixed.get("evaluable"), bool)
            or fixed.get("slice_statements") != after * sealed_counts.has_slice(cutoff)
            or (fixed["evaluable"] and items not in (ev.ALL_ITEMS, ev.SLICE_ITEMS))
            or any(entry.get("items") != items for entry in entries)
        ):
            wrong.append(f"it does not hold the item set the probe fixed for {model}")
    if wrong:
        ev.refuse(CANNOT_STAND + "; ".join(wrong))


# --------------------------------------------------------------------------------------------
# Before the sealed file: every prediction
# --------------------------------------------------------------------------------------------


@dataclass
class Prepared:
    """Everything the sections need besides the outcomes, fixed before the sealed file is
    read."""

    study: ev.Study
    """The eligible list: first-sight cells, the predictions of the model-free predictors and
    of every condition of every model (``<model>:<condition>``), the parsed flags, the probe
    predictions and the comparator of H3."""
    baselines_sha256: str
    population: pd.DataFrame
    """The first-sight rows of the statement table for the test-split statements at risk under
    B in an analysis set with horizons (the eligible list and the secondary lists are in it)."""
    reading_days: dict[str, pd.Series] = field(default_factory=dict)
    """By model: the end of its literal reading on each eligible statement, in days."""
    literal_rows: dict[str, Mapping[str, dict]] = field(default_factory=dict)
    """By model: the stored rows of condition (c), for the counts of its readings on a part of
    the eligible list."""
    lists: dict[str, dict[str, dict[str, pd.DataFrame]]] = field(default_factory=dict)
    """By primary and secondary list: the predictions of ``base_rate``, a, b and c."""
    lists_parsed: dict[str, dict[str, dict[str, pd.Series]]] = field(default_factory=dict)
    lists_days: dict[str, dict[str, pd.Series]] = field(default_factory=dict)
    lists_runs: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    sampled: dict[str, pd.DataFrame] = field(default_factory=dict)
    """By primary: the sampled quantiles on the 20-sample subset."""
    sampled_counts: dict[str, dict[str, Any]] = field(default_factory=dict)
    sampled_parsed: dict[str, pd.Series] = field(default_factory=dict)
    """By primary: which statements of the 20-sample subset have a parsed sample."""
    cells: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)
    cells_parsed: dict[str, dict[str, pd.Series]] = field(default_factory=dict)
    cells_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    paraphrases: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)
    paraphrases_parsed: dict[str, dict[str, pd.Series]] = field(default_factory=dict)
    paraphrases_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    """By primary and cell or paraphrase: the record of the run with the counts PLAN section 4
    asks for per model and condition (readings replaced by the base rate, and answers that
    put ``P(E_end90)`` below ``P(E_end)``)."""
    problems: list[str] = field(default_factory=list)


def at_risk_in_the_test_split(table: pd.DataFrame) -> pd.DataFrame:
    """The statements of the test split at risk under B in the analysis sets with horizons
    (dated, stale, TBD, silent), sorted by id: the population of the test-period descriptives.
    The Late split is not read for outcomes."""
    keep = (
        (table["split"] == "test")
        & dataset.true(table["at_risk_B"])
        & table["analysis_set"].isin(P.SETS)
    )
    return table[keep].sort_values("statement_group_id").reset_index(drop=True)


def sampled_table(
    rows: Mapping[tuple[str, int], dict], ids: Sequence[str], base: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any], pd.Series]:
    """The sampled quantiles of each statement of ``ids`` (``read.sampled_quantiles``: the
    empirical quantiles of the medians its samples gave; a sample with no parsed reading is
    left out, so the quantile at level t of the k parsed medians of a statement is the j-th
    smallest, with j the smallest whole number at least t times k), with the base-rate
    quantiles of ``base`` where no sample was parsed; counts: the statements with a sample
    left out (those with no parsed sample among them), and the sampled answers that put
    ``P(E_end90)`` below ``P(E_end)`` (PLAN section 4); and which statements have a parsed
    sample."""
    drawn = rd.sampled_quantiles(rows.values())
    keys = list(P.QUANTILE_KEYS)
    planned = max((entry["samples"] for entry in drawn.values()), default=0)
    values, some, short, parsed = [], [], 0, 0
    for item_id in ids:
        entry = drawn[item_id]
        parsed += entry["parsed"]
        short += entry["parsed"] < planned
        some.append(entry["quantiles"] is not None)
        if entry["quantiles"] is None:
            values.append(base.loc[item_id, keys].tolist())
        else:
            values.append([float(entry["quantiles"][key]) for key in keys])
    answers = [row["reading"] for row in rows.values() if row.get("reading") is not None]
    counts = {
        "statements": len(ids),
        "samples_per_statement": planned,
        "samples_parsed": parsed,
        "statements_with_a_sample_left_out": short,
        "statements_with_no_parsed_sample": len(ids) - sum(some),
        "p_b_below_p_a": sum(
            float(reading["p_by_horizon_b"]) < float(reading["p_by_horizon_a"])
            for reading in answers
        ),
    }
    table = pd.DataFrame(values, index=list(ids), columns=keys, dtype=float)
    return table, counts, pd.Series(some, index=list(ids), dtype=bool)


def prepare(
    table: pd.DataFrame,
    listed: pd.DataFrame,
    found: ev.Gathered,
    more: More,
    skipped: Mapping[str, str],
) -> Prepared:
    """The refit of the model-free predictors and every prediction the sections score: on the
    eligible list for every model (``evaluate.model_predictions``, as the evaluator turns
    readings into predictions), on the secondary lists, the 2x2 cells and the paraphrases, and
    the sampled quantiles. No outcome is read."""
    frame = P.prepare(table)
    ids = list(listed["statement_group_id"])
    population = at_risk_in_the_test_split(table)
    first = population.set_index("statement_group_id")
    fitted, predictions, probe_base, record = ev.free_predictions(frame, ids, found.probe_ids)
    study = ev.Study(
        first=listed.set_index("statement_group_id"),
        probe_ids=found.probe_ids,
        predictions=dict(predictions),
        parsed={},
        probe={ev.BASE: probe_base},
        selection={model: found.selections[model]["selected"] for model in found.groups},
        comparator=found.comparator,
        runs={},
        not_evaluable=dict(skipped),
        refit=record,
    )
    out = Prepared(study, ev.baseline_hash(predictions, probe_base), population)
    rows, base = frame.loc[ids], predictions[ev.BASE]
    for model, groups in {**found.groups, **more.models}.items():
        made, parsed, counts, problems = ev.model_predictions(
            groups, fitted, rows, study.first, base
        )
        out.problems += [f"{model} {problem}" for problem in problems]
        out.reading_days[model] = ev.literal_days(groups["c"].rows, study.first)[0]
        out.literal_rows[model] = groups["c"].rows
        for condition in ev.CONDITIONS:
            study.predictions[f"{model}:{condition}"] = made[condition]
            study.parsed[f"{model}:{condition}"] = parsed[condition]
        if ev.PROBE in groups:
            study.probe[model], study.parsed[f"{model}:{ev.PROBE}"], counts[ev.PROBE] = (
                ev.predictive(groups[ev.PROBE].rows, study.first.loc[found.probe_ids], probe_base)
            )
        study.runs[model] = {
            condition: ev.group_record(group, counts[condition])
            for condition, group in groups.items()
        }
    for model, by_list in more.lists.items():
        out.lists[model], out.lists_parsed[model] = {}, {}
        out.lists_days[model], out.lists_runs[model] = {}, {}
        for key, groups in by_list.items():
            chosen = more.ids[key]
            cells, typed = first.loc[chosen], frame.loc[chosen]
            base_here = fitted[ev.BASE].predict(typed)
            made, parsed, counts, problems = ev.model_predictions(
                groups, fitted, typed, cells, base_here
            )
            out.problems += [f"{model} {key} list, {problem}" for problem in problems]
            out.lists[model][key] = {ev.BASE: base_here, **made}
            out.lists_parsed[model][key] = parsed
            out.lists_days[model][key] = ev.literal_days(groups["c"].rows, cells)[0]
            out.lists_runs[model][key] = {
                condition: ev.group_record(group, counts[condition])
                for condition, group in groups.items()
            }
    for model, stored in more.samples.items():
        chosen = more.ids["samples"]
        out.sampled[model], out.sampled_counts[model], out.sampled_parsed[model] = sampled_table(
            stored, chosen, base.loc[chosen]
        )
    for name, source, kept, flags, runs in (
        ("twobytwo", more.cells, out.cells, out.cells_parsed, out.cells_runs),
        (
            "paraphrase",
            more.paraphrases,
            out.paraphrases,
            out.paraphrases_parsed,
            out.paraphrases_runs,
        ),
    ):
        chosen = more.ids.get(name, [])
        for model, groups in source.items():
            kept[model], flags[model], runs[model] = {}, {}, {}
            for label, group in groups.items():
                kept[model][label], flags[model][label], counts = ev.predictive(
                    group.rows, study.first.loc[chosen], base.loc[chosen]
                )
                runs[model][label] = ev.group_record(group, counts)
    return out


# --------------------------------------------------------------------------------------------
# With the outcomes: the sealed rows
# --------------------------------------------------------------------------------------------


def unseal_population(
    sealed: bytes, events: pd.DataFrame, population: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame | None]]:
    """The typed frame of the test-split population with the primary outcome, and the typed
    frames of the same statements under the three sensitivity analyses of the recovery rule
    (PLAN section 2.5; section 6, "Evaluator"): limited supply counted as available (the
    definition BL of the corpus builder); a row that left the list without a resolution counted
    as recovered at the first capture where it was missing; and a Date Discontinued cell that
    newly appears on the shortage row counted as a discontinuation at that capture
    (``discontinued_by_the_cell``). A variant whose column the outcome rows do not hold
    (``VARIANT_COLUMNS``) is None, and the result file says that it was not computed. The
    sealed rows pass the checks of the counts-only code first."""
    outcomes = sealed_counts._checked_rows(ev.table_of(sealed, True), events)
    sealed_counts._same_build(population, outcomes)
    typed = ev.typed_outcomes(dataset.attach_outcomes(population, outcomes))
    limited, left_the_list, cell = RECOVERY_VARIANTS
    variants: dict[str, pd.DataFrame | None] = dict.fromkeys(RECOVERY_VARIANTS)
    if VARIANT_COLUMNS[limited] in outcomes.columns:
        variants[limited] = ev.typed_outcomes(dataset.attach_outcomes(population, outcomes, "BL"))
    if VARIANT_COLUMNS[left_the_list] in outcomes.columns:
        variants[left_the_list] = ev.typed_outcomes(
            dataset.attach_outcomes(population, recovered_on_leaving(outcomes))
        )
    if VARIANT_COLUMNS[cell] in outcomes.columns:
        variants[cell] = ev.typed_outcomes(
            dataset.attach_outcomes(population, discontinued_by_the_cell(outcomes))
        )
    return typed, variants


def recovered_on_leaving(outcomes: pd.DataFrame) -> pd.DataFrame:
    """The outcome rows with a row that left the list without a resolution read as a recovery
    at the first capture where it was missing (PLAN section 2.5, "Sensitivity analyses"): a
    censored row with an exit date becomes a recovery with that date as its upper bound. A row
    that recovered, was discontinued or is not at risk keeps its outcome and its bracket,
    whatever its exit date."""
    kind, upper = f"outcome_{dataset.DEFINITION}", f"upper_date_{dataset.DEFINITION}"
    exit_column = VARIANT_COLUMNS[RECOVERY_VARIANTS[1]]
    left = (outcomes[kind] == "censored") & (outcomes[exit_column] != "")
    moved = outcomes.copy()
    moved.loc[left, kind] = "recovered"
    moved.loc[left, upper] = moved.loc[left, exit_column]
    return moved


def discontinued_by_the_cell(outcomes: pd.DataFrame) -> pd.DataFrame:
    """The outcome rows with a Date Discontinued cell on the shortage row read as a
    discontinuation (PLAN section 2.5: "In that analysis the cell counts as a discontinuation
    at that capture: a displayed presentation that is censored, or whose recovery is first
    shown at that capture or a later one, is discontinued there (discontinuation wins ties);
    one that had recovered at an earlier capture keeps its recovery"). A row with the capture
    where such a cell newly appears (``DISCONTINUED_CELL``) becomes a discontinuation with that
    capture as its upper bound when it is censored, or when it recovered and the capture that
    first shows the recovery is that one or a later one. A row that recovered at an earlier
    capture, is discontinued already or is not at risk stays as it is. The stored lower bound
    is left alone, so the frame serves the horizon events and the capped time target only (a
    discontinuation is no at every horizon and at the cap): no bracket width and no
    observability may be read from it."""
    kind, upper = f"outcome_{dataset.DEFINITION}", f"upper_date_{dataset.DEFINITION}"
    cell = outcomes[DISCONTINUED_CELL]
    recovered_no_earlier = (outcomes[kind] == "recovered") & (cell <= outcomes[upper])
    moved = (cell != "") & ((outcomes[kind] == "censored") | recovered_no_earlier)
    out = outcomes.copy()
    out.loc[moved, kind] = "discontinued"
    out.loc[moved, upper] = cell[moved]
    return out


def other_events(rows: pd.DataFrame, typed: pd.DataFrame) -> pd.Series:
    """Which statements of ``rows`` have another horizon event under an outcome variant
    (``typed``: the same statements) than under the primary outcome; an event that is
    undetermined under one and not under the other counts."""
    changed = np.zeros(len(rows), dtype=bool)
    for column in ("y_a", "y_b"):
        one = rows[column].to_numpy(dtype=float)
        other = typed.loc[rows.index, column].to_numpy(dtype=float)
        changed |= ~((one == other) | (np.isnan(one) & np.isnan(other)))
    return pd.Series(changed, index=rows.index)


def near_definitions(
    rows: pd.DataFrame, definitions: Mapping[str, pd.DataFrame | None], ids: pd.Index
) -> dict[str, tuple[int, bool]]:
    """For the statements ``ids`` of an item set and each outcome definition besides the
    primary one (``definitions``, in their order: the outcome variants of the evaluator, then
    the variants of the recovery rule; ``rows`` holds the primary outcome): how many statements
    have another horizon event under it than under the primary outcome, and whether its
    contrasts are withheld.

    PLAN, standing rules ("one outcome definition beside another"), and section 2.5,
    "Sensitivity analyses": a contrast under a definition that gives 1 to ``MIN_SHOWN`` - 1
    statements of the item set another horizon event, or as few of those scoreable under
    either definition, is withheld with its two scenarios, because beside the same contrast
    under the primary outcome it would give the change of the losses of those few. A
    statement that is scoreable under neither definition is in no loss, so a definition that
    moves many statements can still change the losses of a few (``evaluate.other_events``
    with ``scored``, as the evaluator holds the tests of a primary to it). The same holds
    between two definitions: a definition is also withheld when it differs by so few
    statements from one before it whose contrasts are written. Every definition is looked at
    whichever section is computed, so that two result files of one study withhold the same."""
    primary = rows.loc[ids]
    written = [primary]
    out: dict[str, tuple[int, bool]] = {}
    for label, frame in definitions.items():
        if frame is None:
            continue
        under = frame.loc[ids]
        near = any(
            small(ev.other_events(kept, under)) or small(ev.other_events(kept, under, scored=True))
            for kept in written
        )
        out[label] = (int(other_events(primary, under).sum()), near)
        if not near:
            written.append(under)
    return out


# --------------------------------------------------------------------------------------------
# Scores shared by the sections
# --------------------------------------------------------------------------------------------


def mean_record(
    values: Any, clusters: Sequence[str], draws: int, seed: int, least: int = 1
) -> dict[str, Any]:
    """The mean of ``values`` over statements with its 95% percentile interval by cluster
    bootstrap (None with fewer than two clusters). Withheld, counts apart, with fewer than
    ``least`` statements."""
    values, ids = np.asarray(values, dtype=float), list(clusters)
    out: dict[str, Any] = {"statements": len(ids), "episodes": len(set(ids))}
    if len(ids) < max(least, 1):
        return out | {"mean": None, "ci95": None, "withheld": len(ids) > 0}
    out |= {"mean": float(values.mean()), "ci95": None}
    if len(set(ids)) >= ev.MIN_EPISODES:
        out["ci95"] = P.interval(P.bootstrap_means(values, ids, draws, seed)[:, 0], 0.95)
    return out


def small(count: int) -> bool:
    """Whether a number of statements is one over which an outcome statistic is withheld: 1 to
    ``MIN_SHOWN`` - 1 (over none there is nothing to withhold)."""
    return 0 < count < MIN_SHOWN


def withheld(record: Mapping[str, Any], *blank: str) -> dict[str, Any]:
    """The counts of a record whose values are withheld, with what names the record (``KEPT``);
    the keys of ``blank`` stay, with no value. A record over no statement holds nothing to
    withhold, and is not marked."""
    kept = {key: record[key] for key in KEPT if key in record}
    return kept | dict.fromkeys(blank) | {"withheld": record.get("statements", 1) > 0}


def beside(whole: Any, part: Any) -> Any:
    """The record ``part`` of figures on a set as it can stand beside ``whole``, the record of
    the same figures on a set that holds it (PLAN, standing rules: a secondary figure is
    withheld where the same figure is also written on a set that differs from its own by 1 to
    4 statements, so that the two together would give back the outcomes of those few: a slice
    within its whole, the statements after a cutoff within a list). Every record of ``part``,
    at any depth, whose count under one of ``SIZES`` differs by 1 to ``MIN_SHOWN`` - 1 from
    the count of the record in the same place of ``whole`` is withheld, counts apart. A figure
    that one of the two withholds already has no neighbour to be taken from, and stays as it
    is."""
    if not isinstance(whole, Mapping) or not isinstance(part, Mapping):
        return part
    if "withheld" in whole or "withheld" in part:
        return dict(part)
    for key in SIZES:
        one, other = whole.get(key), part.get(key)
        sizes = all(isinstance(n, int) and not isinstance(n, bool) for n in (one, other))
        if sizes and small(abs(one - other)):
            if key == "not_both_parsed":  # how many of a few known statements are counted
                return {key: other, "withheld": True}
            return withheld(part)
    return {key: beside(whole.get(key), value) for key, value in part.items()}


def floored(record: Mapping[str, Any], *keep: str) -> dict[str, Any]:
    """A contrast under the floor of this file (PLAN, standing rules: a secondary figure is
    withheld, its counts apart, where it rests on 1 to 4 statements), whichever function
    computed it: withheld over 1 to ``MIN_SHOWN`` - 1 statements, and without an estimate when
    it is not evaluable (fewer than two shortage episodes: the evaluator's functions write the
    difference of the two mean losses there all the same). ``keep``: further keys of the
    record that are counts or that name it."""
    if small(int(record["statements"])):
        kept = {key: value for key, value in record.items() if key in (*KEPT, *keep)}
        return kept | {"withheld": True}
    if record.get("evaluable") is False:
        kept = (*KEPT, *keep, "evaluable", "reason", "p")
        return {key: value for key, value in record.items() if key in kept}
    return dict(record)


def few_open(rows: pd.DataFrame) -> bool:
    """Whether 1 to ``MIN_SHOWN`` - 1 statements of ``rows`` are not scoreable. PLAN section
    2.5, "Horizon events": the figures over every statement of such a set are withheld, because
    beside the figures on its scoreable statements they would give the horizon events of those
    few."""
    return small(int((~rows["scoreable"]).sum()))


def few_failed(sides: Sequence[np.ndarray]) -> bool:
    """PLAN section 4: whether the answers that failed on one side alone, on the other alone
    or on both number 1 to ``MIN_SHOWN`` - 1, or the answers that parsed on both do.
    ``sides`` flags, for each compared reading that can fail (one or two), the statements it
    parsed. Which answers failed is open: the counts of a contrast on the parsed answers, by
    themselves or taken from one another, would say how many of those few are scoreable."""
    one = np.asarray(sides[0], dtype=bool)
    other = np.asarray(sides[1], dtype=bool) if len(sides) > 1 else np.ones(len(one), dtype=bool)
    groups = (~one & other, one & ~other, ~one & ~other, one & other)
    return any(small(int(group.sum())) for group in groups)


def parsed_only(
    both: Mapping[str, Any],
    counted: np.ndarray,
    sides: Sequence[np.ndarray],
    outside: tuple[np.ndarray, Sequence[np.ndarray]] | None = None,
) -> dict[str, Any]:
    """The sensitivity analysis of PLAN section 4 ("only the events that both compared
    conditions parsed") as it stands beside a contrast on every statement that a set counts.
    ``both`` is the contrast on the statements every compared reading parsed; ``counted``
    flags the statements of the set that the contrast counts (the scoreable ones; for a
    pinball loss those with a target), ``sides`` the statements each compared reading parsed
    (one array for each reading that can fail). The record carries, before its own, the two
    counts it rests on: ``not_both_parsed`` (which readings failed is open) and ``left_out``,
    the counted statements among them.

    * It is withheld, counts apart, when it leaves out or rests on 1 to ``MIN_SHOWN`` - 1
      counted statements (section 4, and the evaluator's record of a test of the family):
      beside the contrast on all of them it would give the summed difference on the few.
    * It is withheld with its counts, ``not_both_parsed`` apart, where the failed answers of
      one side, or of both, number 1 to ``MIN_SHOWN`` - 1, or the answers both parsed do
      (section 4; ``few_failed``): its counts would say how many of those few known
      statements are counted, which is a fact of their outcomes. Three answers that failed on
      one side are a few, however many failed on the other.
    * ``outside`` gives the same flags for the statements of a set that holds this one and on
      which the same contrast is written, less this one's (a list less its statements after
      a cutoff). Both rules hold for those statements too: the figures and the counts of the
      two sets, taken from one another, are those of the statements between them.

    One rule for every contrast of this file."""
    parsed = np.logical_and.reduce([np.asarray(side, dtype=bool) for side in sides])
    not_parsed, left_out = int((~parsed).sum()), int((counted & ~parsed).sum())
    record = {"not_both_parsed": not_parsed, "left_out": left_out} | dict(both)
    few_known = few_failed(sides)
    few_counted = small(left_out) or small(int(both["statements"]))
    if outside is not None:
        counted_there, sides_there = outside
        parsed_there = np.logical_and.reduce([np.asarray(s, dtype=bool) for s in sides_there])
        few_known = few_known or few_failed(sides_there)
        few_counted = (
            few_counted
            or small(int((counted_there & ~parsed_there).sum()))
            or small(int((counted_there & parsed_there).sum()))
        )
    if few_known:
        return {"not_both_parsed": not_parsed, "withheld": True}
    return withheld(record) if few_counted else record


def loss_bounds(rows: pd.DataFrame, pred: pd.DataFrame) -> dict[str, Any]:
    """The two scenarios of PLAN section 7.2 beside a mean primary loss (its "bounds"): the
    mean loss over every statement of ``rows`` with each undetermined horizon event set to no,
    then to yes. Withheld, counts apart, over fewer than ``MIN_SHOWN`` statements, where a few
    of the statements are not scoreable (``few_open``), and where a few are scoreable: the
    predictions being open, a scenario less its filled part is the loss on the scoreable
    statements, which is withheld there."""
    out: dict[str, Any] = {
        "statements": len(rows),
        "with_a_horizon_event_undetermined": int((~rows["scoreable"]).sum()),
    }
    if small(len(rows)):  # how many of a few statements are undetermined is theirs to tell
        return {"statements": len(rows), "withheld": True}
    if len(rows) < MIN_SHOWN or few_open(rows) or small(int(rows["scoreable"].sum())):
        return out | {"withheld": len(rows) > 0}
    mine = pred.loc[rows.index]
    return out | P.brier_bounds(mine["p_a"], mine["p_b"], rows["y_a"], rows["y_b"])


def contrast_bounds(
    rows: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    comparator: str,
    tested: str,
    estimate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """``evaluate.bounds`` beside a contrast (the first loss minus the second over every
    statement of ``rows``, under each of the two scenarios for the undetermined horizon
    events). Withheld, counts apart, over fewer than ``MIN_SHOWN`` statements, where a few of
    the statements are not scoreable (``few_open``) and where a few are scoreable
    (``loss_bounds``), whether or not the evaluator's own function withholds them there; and
    where the contrast they stand beside (``estimate``, its record) carries no estimate: the
    scenarios of a contrast without one would be one."""
    if small(len(rows)):  # how many of a few statements are undetermined is theirs to tell
        return {"statements": len(rows), "withheld": True}
    out = ev.bounds(rows, predictions, comparator, tested)
    few = len(rows) < MIN_SHOWN or few_open(rows) or small(int(rows["scoreable"].sum()))
    bare = estimate is not None and "delta" not in estimate
    return out if "withheld" in out or not (few or bare) else withheld(out)


def pinball_record(q: Any, frame: pd.DataFrame, level: float) -> dict[str, Any]:
    """``predictors.pinball_scores`` (the pinball loss of the quantiles ``q`` on the statements
    of ``frame`` whose time to recovery is not right-censored before the cap, with its bounds
    over every statement), withheld, counts apart, over 1 to ``MIN_SHOWN`` - 1 statements, or
    with as few that have such a target."""
    record = P.pinball_scores(q, frame, level)
    if small(len(frame)) or small(int(record["statements"])):
        return withheld(record)
    return record


def scores(rows: pd.DataFrame, pred: pd.DataFrame, draws: int, seed: int) -> dict[str, Any]:
    """Every score of section 7.2 of one predictor on the statements of ``rows``
    (``evaluate.predictor_record``), under the rules of this file, whether or not the
    evaluator's own function applies them:

    * over 1 to ``MIN_SHOWN`` - 1 statements the record holds their number alone; with as few
      scoreable ones, what is scored on them is withheld (the losses, the calibration in the
      large, Murphy's decomposition) and with it the figures over every statement that fill
      the horizon events, which less their filled part are the same sums. The pinball losses
      (each with its own floor, ``pinball_record``) and the coverage, which score the time to
      recovery over every statement, stay.
    * where a few of the statements are not scoreable (``few_open``), the figures over every
      statement that fill the horizon events (the two scenarios of the loss, and the least
      and greatest calibration in the large) are withheld, counts apart, and so are the two
      mean probabilities over the scoreable statements (None) and the calibration in the
      large on them (PLAN section 2.5, "Horizon events"): the predictions being open, their
      sum over every statement less that mean times its count is the sum over the few that
      are not scoreable, and names them, and the calibration in the large is that mean less
      the frequency of the event, which the uncertainty of the Brier decomposition gives."""
    record = ev.predictor_record(rows, pred, draws, seed)
    counts = {
        "statements": len(rows),
        "with_a_horizon_event_undetermined": int((~rows["scoreable"]).sum()),
        "withheld": True,
    }
    scoreable = int(rows["scoreable"].sum())
    if small(len(rows)):  # not even how many of them are scoreable
        return {"statements": len(rows), "withheld": True}
    for level, shown in record.get("pinball_all_statements", {}).items():
        if small(int(shown["statements"])):
            record["pinball_all_statements"][level] = withheld(shown)
    if small(scoreable):
        kept = ("scoreable_statements", "scoreable_episodes", "statements")
        over_all = ("pinball_all_statements", "coverage_80")
        return (
            {key: record[key] for key in kept}
            | {"withheld": True}
            | {key: record[key] for key in over_all}
        )
    if few_open(rows):
        over_all = ("bounds_all_statements", "calibration_all_statements")
        for key in (*over_all, "calibration_in_the_large"):
            if key in record:
                record[key] = dict(counts)
        for key in ("mean_p_E_end", "mean_p_E_end90"):
            if key in record:
                record[key] = None
    return record


def brief(result: Mapping[str, Any], sides: int) -> dict[str, Any]:
    """A contrast in short (``evaluate.short``) under the registered p-value procedure and the
    floor of this file (``floored``)."""
    return floored(ev.short(result, sides, ev.P_VALUE_SOURCE))


def probe_of(model: str, study: ev.Study, rows: pd.DataFrame, draws: int, seed: int) -> dict:
    """The probe test of E4 for one secondary model: the evaluator's record
    (``evaluate.probe_test``), as it is. PLAN section 5, E4, "Test": the figures of a probe
    over 1 to ``MIN_SHOWN`` - 1 targets are withheld (the estimate, the p-value and the two
    pinball losses; the counts stay) and its verdict is given; a test that cannot be made
    carries no estimate and no verdict."""
    return ev.probe_test(model, study, rows, draws, seed, ev.P_VALUE_SOURCE)


def paired(
    comparator: Any, tested: Any, clusters: Sequence[str], sides: int, draws: int, seed: int
) -> dict[str, Any]:
    """``evaluate.contrast`` of two columns of losses, in short: the first minus the second."""
    return brief(ev.contrast(comparator, tested, list(clusters), draws, seed), sides)


def where_both_parsed(
    rows: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    comparator: str,
    tested: str,
    parsed: pd.Series | Sequence[pd.Series],
    draws: int,
    seed: int,
    within: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], int | None]:
    """PLAN section 4 ("A sensitivity analysis uses only the events that both compared
    conditions parsed"), for a two-sided contrast in short: the contrast again on the
    statements of ``rows`` that every reading compared parsed, under the rules of
    ``parsed_only``, and how many scoreable statements it leaves out (None where the record
    withholds that count). ``parsed`` flags the statements a reading parsed: one series, or
    one for each of the two readings when both can fail. ``within``: a set that holds
    ``rows`` and on which the same is written."""
    series = [parsed] if isinstance(parsed, pd.Series) else list(parsed)

    def sides(frame: pd.DataFrame) -> list[np.ndarray]:
        return [flags.loc[frame.index].to_numpy(dtype=bool) for flags in series]

    flags = np.logical_and.reduce(sides(rows))
    scoreable = rows["scoreable"].to_numpy(dtype=bool)
    outside = None
    if within is not None:
        others = within.loc[within.index.difference(rows.index)]
        outside = (others["scoreable"].to_numpy(dtype=bool), sides(others))
    both = brief(ev.scored(rows[flags], predictions, comparator, tested, draws=draws, seed=seed), 2)
    record = parsed_only(both, scoreable, sides(rows), outside)
    return record, record.get("left_out")


def contrast_entry(
    rows: pd.DataFrame,
    study: ev.Study,
    comparator: str,
    tested: str,
    sides: int,
    draws: int,
    seed: int,
    equivalence: bool = False,
    within: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """One contrast as the evaluator reports a test of the family, without Holm: the full
    record of ``evaluate.contrast`` on the scoreable statements of ``rows`` with the 95%
    interval of the registered source (and, beside it, the percentile intervals), its p-value
    under the registered procedure, the bounds of section 7.2, the same contrast on the
    statements both sides parsed (``parsed_only``) and how many scoreable answers of each side
    were not parsed. With ``equivalence`` (H2) it also carries the 90% interval, the reading of
    ``evaluate.equivalence`` and on how many statements and episodes the two losses differ.
    The record is under the floor of this file (``floored``).

    The counts of each side are withheld (None), and with them those of the contrast on the
    statements both sides parsed, when the readings that failed on one side alone, on the
    other alone or on both number 1 to ``MIN_SHOWN`` - 1, or those that both parsed do
    (``few_failed``; PLAN section 4: which readings failed is open, so the counts would say
    how many of those few known statements are scoreable).
    ``within``: a set that holds ``rows`` and on which the same contrast is written; the rules
    of the counts and of ``parsed_only`` then hold for its other statements as well."""
    predictions = study.predictions

    def flagged(frame: pd.DataFrame) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """The scoreable statements of a frame, and which of them each side parsed."""
        every = np.ones(len(frame), dtype=bool)
        parsed = {
            name: study.parsed[name].loc[frame.index].to_numpy(dtype=bool)
            if name in study.parsed
            else every
            for name in (comparator, tested)
        }
        return frame["scoreable"].to_numpy(dtype=bool), parsed

    result = ev.scored(
        rows,
        predictions,
        comparator,
        tested,
        draws=draws,
        seed=seed,
        source=ev.P_VALUE_SOURCE,
        levels=("ci95", ev.EQUIVALENCE_LEVEL) if equivalence else ("ci95",),
        margin=ev.H2_MARGIN if equivalence else None,
    )
    evaluable = bool(result["evaluable"]) and not small(int(result["statements"]))
    scoreable, parsed = flagged(rows)
    keep = parsed[comparator] & parsed[tested]
    missed: dict[str, int | None] = {
        name: int((scoreable & ~flags).sum()) for name, flags in parsed.items()
    }
    hidden, outside = few_failed(list(parsed.values())), None
    if within is not None:
        there, parsed_there = flagged(within.loc[within.index.difference(rows.index)])
        hidden = hidden or few_failed(list(parsed_there.values()))
        outside = (there, list(parsed_there.values()))
    both = ev.scored(rows[keep], predictions, comparator, tested, draws=draws, seed=seed)
    shown = floored(result)
    entry = {
        "comparator": comparator,
        "tested": tested,
        "sides": sides,
        **shown,
        "p": ev.registered_p(result, sides, ev.P_VALUE_SOURCE) if evaluable else None,
        "bounds": contrast_bounds(rows, predictions, comparator, tested, shown),
        "both_sides_parsed": parsed_only(
            brief(both, sides), scoreable, list(parsed.values()), outside
        ),
        "scoreable_not_parsed": dict.fromkeys(missed) if hidden else missed,
    }
    if equivalence and evaluable:
        entry["equivalence"] = ev.equivalence(entry)
        entry.pop("at_the_margin", None)  # the reading holds the two p-values
        entry["losses_differ"] = ev.differing(
            *ev.paired_losses(rows, predictions, comparator, tested)
        )
    return entry


def model_tests(model: str, comparator: str) -> list[tuple[str, str, str, int]]:
    """The registered contrasts of a model, as (name, comparator, tested, sides): H1, H2, and
    H3 with each of its three conditions (a secondary model has no dev runs, so no selected
    one)."""
    return [
        ("H1", f"{model}:a", f"{model}:b", 1),
        ("H2", ev.RULES, f"{model}:c", 2),
        *(
            (f"H3 with condition {condition}", comparator, f"{model}:{condition}", 2)
            for condition in ev.CONDITIONS
        ),
    ]


def contrasts_of(
    model: str,
    rows: pd.DataFrame,
    study: ev.Study,
    draws: int,
    seed: int,
    within: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """The contrasts of ``model_tests`` on ``rows``, each with the 95% interval of the
    registered test and the percentile intervals beside it (PLAN section 6, "Intervals"), and
    with the contrast of each condition against the structured-only model beside its H3
    contrast: that one carries both intervals as well, and the bounds of section 7.2.
    ``within``: a set that holds ``rows`` and on which the same contrasts are written
    (``contrast_entry``)."""
    out = {}
    for name, comparator, tested, sides in model_tests(model, study.comparator):
        out[name] = contrast_entry(
            rows, study, comparator, tested, sides, draws, seed, name == "H2", within
        )
        if name.startswith("H3"):
            beside_it = ev.scored(
                rows,
                study.predictions,
                ev.STRUCTURED,
                tested,
                draws=draws,
                seed=seed,
                source=ev.P_VALUE_SOURCE,
                levels=("ci95",),
            )
            shown = brief(beside_it, sides)
            if "delta" in shown:  # one that is withheld or not evaluable holds no interval
                shown["percentile"] = beside_it["percentile"]
            shown["bounds"] = contrast_bounds(rows, study.predictions, ev.STRUCTURED, tested, shown)
            out[name]["against_gbm_structured"] = shown
    return out


def decomposition_of(
    model: str, rows: pd.DataFrame, study: ev.Study, draws: int, seed: int
) -> dict[str, Any]:
    """PLAN section 5, E3, "Descriptive decomposition", for one secondary model on the scoreable
    statements of ``rows``, as ``evaluate.evaluate`` builds it for a primary: each part is the
    first loss minus the second, two-sided, with a 95% percentile interval."""
    parts = {
        "content_value_of_the_text": (ev.BASE, ev.RULES),
        "content_value_against_the_structured_model": (ev.STRUCTURED, ev.RULES),
        "reading_loss": (f"{model}:c", ev.RULES),
        "trust_loss": (f"{model}:a", f"{model}:c"),
    }
    return {
        name: {"minuend": pair[0], "subtrahend": pair[1]}
        | brief(ev.scored(rows, study.predictions, *pair, draws=draws, seed=seed), 2)
        for name, pair in parts.items()
    }


def repeats_of(
    model: str,
    rows: pd.DataFrame,
    outcome_variants: Mapping[str, pd.DataFrame],
    study: ev.Study,
    draws: int,
    seed: int,
    definitions: Mapping[str, pd.DataFrame | None] | None = None,
) -> dict[str, Any]:
    """The contrasts of ``model_tests`` again, in short and on every eligible statement, as
    ``evaluate.evaluate`` repeats the tests of a primary (PLAN section 5, E3, "Secondaries"),
    under the evaluator's names: under each outcome variant (the outcome over all and over any
    covered presentation, the recovery definition A), on the statements first captured by the
    stated end, with the episodes resampled by company, and H2 alone on the month-and-year
    form.

    A repeat on a part of the statements stands beside the contrast on all of them: it is
    withheld, counts apart, when the part leaves out 1 to ``MIN_SHOWN`` - 1 scoreable
    statements, and H2 on the month-and-year form also when its scoreable statements and those
    first captured by the stated end differ by so few (PLAN, standing rules). Where the part
    itself is the list but for so few statements (or the two parts differ by so few), which
    anyone can name from the open cells, the record holds its names and ``withheld`` alone:
    its counts, beside those of the other, would say how many of the few are scoreable. A
    repeat under an
    outcome variant is withheld when the variant gives so few statements another horizon event
    than the primary outcome, or so few of those scoreable under either (PLAN section 2.5), or
    as few against another definition whose contrasts are written
    (``near_definitions``; ``definitions``: every outcome definition of the result file, those
    of ``outcome_variants`` when none is given)."""
    first = study.first.loc[rows.index]
    early = rows[(first["delayed_entry"] != "True").to_numpy()]
    monthly = rows[(first["form"] == ev.MONTH_YEAR).to_numpy()]
    on_a_part = ("h2_on_the_month_and_year_form", "first_captured_by_the_stated_end")
    frames: dict[str, tuple[pd.DataFrame, str, tuple[str, ...]]] = {
        on_a_part[0]: (monthly, "episode_id", ("H2",)),
        on_a_part[1]: (early, "episode_id", ()),
        "clusters_by_company": (rows, "company", ()),
        **{
            name: (frame.loc[rows.index], "episode_id", ())
            for name, frame in outcome_variants.items()
        },
    }
    every = set(rows.index[rows["scoreable"].to_numpy(dtype=bool)])
    counted = {
        label: set(frames[label][0].index[frames[label][0]["scoreable"].to_numpy(dtype=bool)])
        for label in on_a_part
    }
    near = {label: small(len(every - counted[label])) for label in on_a_part}
    near[on_a_part[0]] = near[on_a_part[0]] or small(
        len(counted[on_a_part[0]] ^ counted[on_a_part[1]])
    )
    # a part that is the list but for a few statements, which the open cells name (or the two
    # parts but for a few): its counts beside the others would say how many are scoreable
    held = {label: set(frames[label][0].index) for label in on_a_part}
    bare = {label: small(len(rows) - len(held[label])) for label in on_a_part}
    bare[on_a_part[0]] = bare[on_a_part[0]] or small(len(held[on_a_part[0]] ^ held[on_a_part[1]]))
    moved = near_definitions(
        rows, outcome_variants if definitions is None else definitions, rows.index
    )
    # under a definition that moves a few statements the counts would say, beside those under
    # the primary outcome, how many of the few are scoreable: the number moved is given
    bare |= {label: moved[label][1] for label in outcome_variants}
    out: dict[str, Any] = {}
    for label, (frame, cluster, only) in frames.items():
        out[label] = {}
        for name, comparator, tested, sides in model_tests(model, study.comparator):
            if only and name not in only:
                continue
            record = brief(
                ev.scored(frame, study.predictions, comparator, tested, cluster, draws, seed),
                sides,
            )
            if small(len(frame)) or bare.get(label):  # how many of a few are scoreable
                record = {"withheld": True}
            out[label][name] = {"comparator": comparator, "tested": tested} | (
                withheld(record) if near.get(label) and "withheld" not in record else record
            )
    return out


# --------------------------------------------------------------------------------------------
# The sections
# --------------------------------------------------------------------------------------------


def secondary_models(
    prepared: Prepared,
    rows: pd.DataFrame,
    outcome_variants: Mapping[str, pd.DataFrame],
    models: Sequence[str],
    draws: int,
    seed: int,
    definitions: Mapping[str, pd.DataFrame | None] | None = None,
) -> dict[str, Any]:
    """PLAN section 5, E3, "Secondaries" and "Descriptive decomposition", and section 7.2, for
    the six secondary models: the H1 and H2 contrasts and the H3 contrast for each of the three
    conditions; the decomposition; the contrasts again under the outcome variants, on the
    statements first captured by the stated end and with the resampling by company, and H2 on
    the month-and-year form (``repeats_of``); the post-cutoff slice; every metric of every
    condition; and the probe test of E4 for the secondary models that are probed. The metrics
    of a primary are the evaluator's, on the item set its probe fixed.

    What is given on the post-cutoff slice stands beside the same on every eligible statement
    (``beside``, and ``contrast_entry`` for the statements both sides parsed): a figure of the
    slice is withheld, counts apart, where it leaves out 1 to ``MIN_SHOWN`` - 1 of the
    statements the figure on the list counts. Where the slice is the list but for so few
    statements, which anyone can name from their dates, nothing of it is written but the
    number of its statements: its counts, taken from those of the list, would say how many
    of the few are scoreable (PLAN, standing rules), and whether it holds the 50 scoreable
    statements of an analysed slice would say the same. Beside the repeats under the outcome
    variants stands how
    many statements each variant gives another horizon event (``near_definitions``;
    ``definitions``: every outcome definition of the result file)."""
    study = prepared.study
    definitions = outcome_variants if definitions is None else definitions
    moved = near_definitions(rows, definitions, rows.index)
    out: dict[str, Any] = {
        "models": {},
        "scores_on_every_eligible_statement": {},
        "scores_of_the_primaries": "in the result file of the registered evaluator (losses), "
        "on the item set the probe fixed for each primary",
    }
    for model in models:
        entry: dict[str, Any] = {"runs": study.runs[model]}
        whole = contrasts_of(model, rows, study, draws, seed)
        parts = decomposition_of(model, rows, study, draws, seed)
        every = {
            condition: scores(rows, study.predictions[f"{model}:{condition}"], draws, seed)
            for condition in ev.CONDITIONS
        }
        entry["on_every_eligible_statement"] = whole
        entry["decomposition_on_every_eligible_statement"] = parts
        entry["repeated_on_every_eligible_statement"] = repeats_of(
            model, rows, outcome_variants, study, draws, seed, definitions
        )
        entry["outcome_variants"] = {
            label: {
                "statements_with_another_horizon_event": moved[label][0],
                "withheld_beside_another_outcome": moved[label][1],
            }
            for label in outcome_variants
        }
        if model in study.probe:
            entry["probe"] = probe_of(model, study, rows, draws, seed)
        else:
            entry["probe"] = None
        sliced, record = ev.item_set(model, True, study.first, rows)
        entry["post_cutoff_slice"] = {
            key: record[key] for key in record if key.startswith(("cutoff", "slice"))
        }
        if small(len(rows) - int(record["slice_statements"])):  # the list but for a few
            entry["post_cutoff_slice"] |= {
                "slice_scoreable": None,
                "slice_scoreable_episodes": None,
                "slice_analysed": None,
                "withheld": True,
            }
            bare = {"statements": int(record["slice_statements"]), "withheld": True}
            entry["on_the_post_cutoff_slice"] = dict(bare)
            entry["decomposition_on_the_post_cutoff_slice"] = dict(bare)
            entry["scores_on_the_post_cutoff_slice"] = dict(bare)
        elif sliced is not None:
            part = rows.loc[sliced]
            entry["on_the_post_cutoff_slice"] = beside(
                whole, contrasts_of(model, part, study, draws, seed, within=rows)
            )
            entry["decomposition_on_the_post_cutoff_slice"] = beside(
                parts, decomposition_of(model, part, study, draws, seed)
            )
            entry["scores_on_the_post_cutoff_slice"] = {
                condition: beside(
                    every[condition],
                    scores(part, study.predictions[f"{model}:{condition}"], draws, seed),
                )
                for condition in ev.CONDITIONS
            }
        out["models"][model] = entry
        out["scores_on_every_eligible_statement"][model] = every
    return out


def uptake(pred: pd.DataFrame, parsed: pd.Series, clusters: Sequence[str], draws: int, seed: int):
    """Stale-value uptake (PLAN section 5, E3): the share of readings that give ``P(E_end)``
    above 0.5 for a period that has already passed, over every statement of the list (a failed
    reading counted by its fallback) and over the parsed readings alone."""
    above = (pred["p_a"].to_numpy(dtype=float) > UPTAKE_ABOVE).astype(float)
    flags, ids = parsed.to_numpy(dtype=bool), np.asarray(list(clusters), dtype=object)
    return {
        "share_above_one_half": mean_record(above, ids, draws, seed),
        "share_above_one_half_among_parsed": mean_record(above[flags], ids[flags], draws, seed),
        "not_parsed": int((~flags).sum()),
    }


def selective(
    rows: pd.DataFrame,
    pred: pd.DataFrame,
    reading_days: pd.Series,
    draws: int,
    seed: int,
    with_loss: bool = True,
    within: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Selective prediction of one literal reader (PLAN section 7.2): the abstention rate (the
    share of statements whose reading gives no stated period), and the primary loss on the
    scoreable statements read, on those abstained on (which take the no-date table) and on
    all, each with the bounds of section 7.2 over every statement of its part. The two parts
    add up to the whole, whose loss is given in any case: when either part holds 1 to
    ``MIN_SHOWN`` - 1 statements, or as many scoreable ones, the losses and the bounds of both
    parts are withheld, so that the part shown does not give the other back; and when either
    part holds as few statements that are not scoreable, the bounds of both parts are
    (``few_open``). When a part holds 1 to ``MIN_SHOWN`` - 1 statements, the counts of the
    scoreable and of the undetermined statements of both parts are withheld as well: which
    statements a reader abstains on is open, so they would be facts of the outcomes of those
    few. ``within``: a set that holds ``rows`` and on which the same is written (a
    list, for its statements after a cutoff); the same rules then hold for the statements of
    each part that lie between the two sets. Without ``with_loss`` (a list whose statements
    have no horizon event) the abstention rate stands alone: no loss and no scenario is
    written."""
    read = reading_days.loc[rows.index].notna().to_numpy()
    out: dict[str, Any] = {
        "statements": len(rows),
        "abstained": int((~read).sum()),
        "abstention_rate": float((~read).mean()) if len(rows) else None,
    }
    if not with_loss:
        return out
    scoreable = rows["scoreable"].to_numpy()
    loss = P.primary_loss(
        pred.loc[rows.index, "p_a"], pred.loc[rows.index, "p_b"], rows["y_a"], rows["y_b"]
    )
    clusters = rows["episode_id"].to_numpy()
    parts = {"read": read, "abstained_on": ~read}
    groups = [(part, scoreable) for part in parts.values()]
    if within is not None:  # each part again, on the statements between the two sets
        others = within.loc[within.index.difference(rows.index)]
        read_there = reading_days.loc[others.index].notna().to_numpy()
        scoreable_there = others["scoreable"].to_numpy()
        groups += [(part, scoreable_there) for part in (read_there, ~read_there)]
    hidden = any(
        small(int(part.sum())) or small(int((counted & part).sum())) for part, counted in groups
    )
    open_few = any(small(int((~counted & part).sum())) for part, counted in groups)
    # which statements a reader abstains on is open: of a part of a few statements, how many
    # are scoreable is a fact of their outcomes, and so is that of the other part
    known_few = any(small(int(part.sum())) for part, _ in groups)
    for name, part in (*parts.items(), ("all", np.ones(len(rows), dtype=bool))):
        keep = scoreable & part
        record = mean_record(loss[keep], clusters[keep], draws, seed, MIN_SHOWN)
        bounds = loss_bounds(rows[part], pred)
        if name != "all":
            if hidden:
                record = withheld(record, "mean", "ci95")
            if (hidden or open_few) and "withheld" not in bounds:
                bounds = withheld(bounds)
            if known_few:
                record = {"mean": None, "ci95": None, "withheld": True}
                bounds = {"statements": int(part.sum()), "withheld": True}
        out[f"primary_brier_{name}"] = record | {"bounds_all_statements": bounds}
    return out


def secondary_lists(
    prepared: Prepared,
    everything: pd.DataFrame,
    more: More,
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    draws: int,
    seed: int,
) -> dict[str, Any]:
    """PLAN section 5, E3 ("Primaries only"; "Stale-at-issue events (primaries): stale-value
    uptake"; "TBD and silent events (primaries) against the base-rate predictor") on the three
    secondary lists of section 3. The lists are not part of the eligible list, so a primary is
    read on every statement of each; for a primary whose probe beat the base rate, the scores
    of the TBD and silent lists are given again on the statements dated after its cutoff
    (``beside_the_whole``). Stale-value uptake reads no outcome."""
    out: dict[str, Any] = {}
    days = prepared.population.set_index("statement_group_id")["event_date"]
    entry_counts = ("statements", "episodes")
    for model, by_list in prepared.lists.items():
        out[model] = {}
        for key, predictions in by_list.items():
            rows = everything.loc[more.ids[key]]

            def figures(
                chosen: pd.DataFrame,
                within: pd.DataFrame | None = None,
                key: str = key,
                model: str = model,
                predictions: Mapping[str, pd.DataFrame] = predictions,
            ) -> dict[str, Any]:
                return list_figures(
                    chosen,
                    key,
                    model,
                    predictions,
                    prepared.lists_parsed[model][key],
                    prepared.lists_days[model][key],
                    draws,
                    seed,
                    within,
                )

            whole = figures(rows)
            entry: dict[str, Any] = {
                "statements": whole["statements"],
                "episodes": whole["episodes"],
                "item_set_fixed_by_the_probe": fixed_record(sets, model),
                "runs": prepared.lists_runs[model][key],
                **{name: value for name, value in whole.items() if name not in entry_counts},
            }
            if key in FALLBACK_LISTS:
                later = after_the_cutoff(sets, model, rows, days)
                entry |= beside_the_whole(rows, later, figures, whole)
            out[model][key] = entry
    return out


def list_figures(
    rows: pd.DataFrame,
    key: str,
    model: str,
    predictions: Mapping[str, pd.DataFrame],
    parsed: Mapping[str, pd.Series],
    reading_days: pd.Series,
    draws: int,
    seed: int,
    within: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """What ``secondary_lists`` gives of one primary on the statements ``rows`` of one list:
    stale-value uptake on the stale list; on the TBD and silent lists every score of section
    7.2 and the contrast of each condition against the base rate; and the selective-prediction
    point of condition (c). ``within``: the list, when ``rows`` are its statements after a
    cutoff (``where_both_parsed``, ``selective``)."""
    clusters = list(rows["episode_id"])
    entry: dict[str, Any] = {"statements": len(rows), "episodes": len(set(clusters))}
    if key not in FALLBACK_LISTS:
        entry["stale_value_uptake"] = {
            condition: uptake(
                predictions[condition].loc[rows.index],
                parsed[condition].loc[rows.index],
                clusters,
                draws,
                seed,
            )
            for condition in ev.CONDITIONS
        }
    else:
        named = {
            ev.BASE: predictions[ev.BASE],
            **{f"{model}:{c}": predictions[c] for c in ev.CONDITIONS},
        }
        entry["scoreable_statements"] = int(rows["scoreable"].sum())
        entry["horizon_events"] = "recovery within 90 and within 180 days"
        entry["scores"] = {
            name: scores(rows, pred.loc[rows.index], draws, seed) for name, pred in named.items()
        }
        entry["against_the_base_rate"] = {}
        for condition in ev.CONDITIONS:
            tested = f"{model}:{condition}"
            contrast = brief(ev.scored(rows, named, ev.BASE, tested, draws=draws, seed=seed), 2)
            both, left_out = where_both_parsed(
                rows, named, ev.BASE, tested, parsed[condition], draws, seed, within
            )
            entry["against_the_base_rate"][condition] = contrast | {
                "bounds": contrast_bounds(rows, named, ev.BASE, tested, contrast),
                "both_sides_parsed": both,
                "scoreable_not_parsed_by_both": left_out,
            }
    # a stale statement has no horizon event: its list has the abstention rate alone
    entry["selective_prediction_of_condition_c"] = selective(
        rows, predictions["c"], reading_days, draws, seed, key in FALLBACK_LISTS, within
    )
    return entry


def fixed_record(
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]], model: str
) -> dict[str, Any]:
    """The item set the probe fixed for a primary (``fixed_sets``), in short: whether the probe
    switched it, whether its tests are evaluable, and on which statements or why not. It
    stands beside an analysis of a primary on a subset of the eligible list or on a secondary
    list, which is given on every statement of the subset or the list."""
    record = sets[model][1] if model in sets else {}
    return {
        key: record[key] for key in ("switched", "evaluable", "items", "reason") if key in record
    }


def after_the_cutoff(
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    model: str,
    rows: pd.DataFrame,
    days: pd.Series,
) -> pd.DataFrame | None:
    """The statements of ``rows`` dated after the cutoff of a primary whose probe beat the base
    rate (``days``: the first-sight date of every statement, by id); None for a primary whose
    probe did not. PLAN section 5, E4: a model that beats the base rate is excluded from
    outcome claims on events dated before its cutoff."""
    record = sets[model][1] if model in sets else {}
    if record.get("switched") is not True:
        return None
    return rows[(days.loc[rows.index] > str(record["cutoff_month_end"])).to_numpy()]


def beside_the_whole(
    whole: pd.DataFrame, later: pd.DataFrame | None, figures: Any, written: Mapping[str, Any]
) -> dict[str, Any]:
    """What stands beside the figures on outcomes that a section gives for a primary on a whole
    subset or list (``whole``; ``written``: those figures): whether its probe excludes the
    statements dated before its cutoff from outcome claims and, when it does, the same figures
    on the statements dated after the cutoff (``later``, from ``after_the_cutoff``):
    ``figures(later, whole)``.

    The two sets are nested, and the same figures stand on both (PLAN, standing rules). All of
    the figures after the cutoff are withheld, counts apart, when they or the statements
    before the cutoff number 1 to ``MIN_SHOWN`` - 1, or as many scoreable ones, or as many
    that are not scoreable. Each of them is withheld when the count it is itself taken over
    (the statements with a target for a pinball loss, a part of selective prediction, the
    statements both readings parsed) differs by so few from the count of the same figure on
    the whole (``beside``; ``parsed_only`` and ``selective`` are told of the whole by
    ``figures``)."""
    if later is None:
        return {"probe_excludes_the_statements_before_the_cutoff": False}
    sizes = [len(later), len(whole) - len(later)]
    if "scoreable" in whole.columns:
        scoreable = int(later["scoreable"].sum())
        sizes += [scoreable, int(whole["scoreable"].sum()) - scoreable]
        sizes += [sizes[0] - sizes[2], sizes[1] - sizes[3]]
    if any(small(size) for size in sizes):
        shown: dict[str, Any] = {"statements": len(later), "withheld": True}
    else:
        shown = {"statements": len(later)} | beside(written, figures(later, whole))
    return {"probe_excludes_the_statements_before_the_cutoff": True, "after_the_cutoff": shown}


def sampled_quantiles(
    prepared: Prepared,
    rows: pd.DataFrame,
    more: More,
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    draws: int,
    seed: int,
) -> dict[str, Any]:
    """PLAN section 5, E3 ("Primaries only"): the sampled quantiles against the verbalised ones
    of the temperature-0 answer of condition (a), by pinball loss and by coverage of the 80%
    interval, on the 20-sample subset. A positive ``delta`` favours the sampled quantiles. For
    a primary whose probe beat the base rate the same is given again on the statements of the
    subset dated after its cutoff (``beside_the_whole``)."""
    out = {}
    part = rows.loc[more.ids["samples"]]
    for model, sampled in prepared.sampled.items():
        verbal = prepared.study.predictions[f"{model}:a"]
        # both parsed: the verbalised answer was, and at least one sample of the statement
        parsed = (
            prepared.study.parsed[f"{model}:a"].loc[part.index],
            prepared.sampled_parsed[model].loc[part.index],
        )

        def figures(
            chosen: pd.DataFrame,
            within: pd.DataFrame | None = None,
            sampled: pd.DataFrame = sampled,
            verbal: pd.DataFrame = verbal,
            parsed: Sequence[pd.Series] = parsed,
        ) -> dict[str, Any]:
            return sampled_scores(chosen, sampled, verbal, parsed, draws, seed, within)

        whole = figures(part)
        later = after_the_cutoff(sets, model, part, prepared.study.first["event_date"])
        out[model] = {
            "item_set_fixed_by_the_probe": fixed_record(sets, model),
            **prepared.sampled_counts[model],
            "run": more.records[model][SAMPLES_LINE],
            "verbalised_not_parsed": int(
                (~prepared.study.parsed[f"{model}:a"].loc[part.index]).sum()
            ),
            **whole,
            **beside_the_whole(part, later, figures, whole),
        }
    return out


def sampled_scores(
    part: pd.DataFrame,
    sampled: pd.DataFrame,
    verbal: pd.DataFrame,
    parsed: pd.Series | Sequence[pd.Series],
    draws: int,
    seed: int,
    within: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """The sampled against the verbalised quantiles on the statements of ``part``: the pinball
    loss of each at the levels of section 7.2 with their difference (verbalised minus sampled,
    on the statements whose time to recovery is not right-censored before the cap), the same
    difference on the statements that ``parsed`` flags (section 4: the verbalised answer was
    parsed and at least one sample was; one series, or one for each of the two;
    ``parsed_only``, which counts the statements with a target), and the coverage of the 80%
    interval of each. ``within``: a set that holds ``part`` and on which the same is
    written."""
    targeted = (part["ttr_kind"] != "right_censored").to_numpy(dtype=bool)
    kept = part[targeted]
    target = kept["ttr_mid"].to_numpy(dtype=float)
    sampled, verbal = sampled.loc[part.index], verbal.loc[part.index]
    series = [parsed] if isinstance(parsed, pd.Series) else list(parsed)

    def sides(frame: pd.DataFrame) -> list[np.ndarray]:
        return [flags.loc[frame.index].to_numpy(dtype=bool) for flags in series]

    outside = None
    if within is not None:
        others = within.loc[within.index.difference(part.index)]
        outside = ((others["ttr_kind"] != "right_censored").to_numpy(dtype=bool), sides(others))
    flags = np.logical_and.reduce(sides(part))[targeted]
    clusters = kept["episode_id"].to_numpy()
    out: dict[str, Any] = {"pinball": {}}
    for level, key in power.PINBALL_KEYS.items():
        spoken = P.pinball(verbal.loc[kept.index, key], target, level)
        drawn = P.pinball(sampled.loc[kept.index, key], target, level)
        both = paired(spoken[flags], drawn[flags], clusters[flags], 2, draws, seed)
        record = parsed_only(both, targeted, sides(part), outside)
        out["pinball"][f"{level:.2f}"] = {
            "sampled": pinball_record(sampled[key], part, level),
            "verbalised": pinball_record(verbal[key], part, level),
            "verbalised_minus_sampled": paired(spoken, drawn, clusters, 2, draws, seed),
            "verbalised_minus_sampled_both_parsed": record,
            "not_parsed_by_both": record.get("left_out"),
        }
    if not small(len(part)):  # the coverage of a few statements would say where they ended
        out["coverage_80"] = {
            "sampled": ev.coverage80(sampled, part),
            "verbalised": ev.coverage80(verbal, part),
        }
    return out


def absolute_change(
    one: pd.DataFrame, other: pd.DataFrame, clusters: Sequence[str], draws: int, seed: int
) -> dict[str, Any]:
    """The mean absolute change, over statements, of ``P(E_end)``, ``P(E_end90)`` and the
    median between two sets of predictions of the same statements."""
    named = {"p_E_end": "p_a", "p_E_end90": "p_b", "median_days": "q50"}
    return {
        name: mean_record(
            np.abs(one[column].to_numpy(dtype=float) - other[column].to_numpy(dtype=float)),
            clusters,
            draws,
            seed,
        )
        for name, column in named.items()
    }


def changes(
    rows: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    parsed: Mapping[str, pd.Series],
    reference: str,
    draws: int,
    seed: int,
    within: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, Any], dict[str, Any]]:
    """What several readings of the same statements share: the primary loss of each on the
    scoreable statements with its clusters, the mean loss of each with the bounds of section
    7.2, and the change of each from ``reference``: its loss minus the reference's with the
    bounds, the same on the statements both parsed (``where_both_parsed``; ``within``: a set
    that holds ``rows`` and on which the same is written), and the mean absolute change of the
    two probabilities and the median over every statement and over those both parsed. With 1
    to ``MIN_SHOWN`` - 1 scoreable statements every loss and every change of a loss is
    withheld; the absolute changes use no outcome and stay."""
    scoreable = rows[rows["scoreable"]]
    clusters = list(scoreable["episode_id"])
    losses = power.primary_losses(scoreable, predictions)
    means = {
        name: mean_record(losses[name], clusters, draws, seed, MIN_SHOWN)
        | {"bounds_all_statements": loss_bounds(rows, predictions[name])}
        for name in predictions
    }
    moved = {}
    every = list(rows["episode_id"])
    known = rows.index if within is None else within.index
    for name in (name for name in predictions if name != reference):
        both = parsed[name].loc[known] & parsed[reference].loc[known]
        flags = both.loc[rows.index].to_numpy()
        one, other = predictions[name].loc[rows.index], predictions[reference].loc[rows.index]
        change = paired(losses[name], losses[reference], clusters, 2, draws, seed)
        on_both, missed = where_both_parsed(
            rows,
            predictions,
            name,
            reference,
            (parsed[name].loc[known], parsed[reference].loc[known]),
            draws,
            seed,
            within,
        )
        moved[name] = {
            "primary_loss": change
            | {"bounds": contrast_bounds(rows, predictions, name, reference, change)},
            "primary_loss_both_parsed": on_both,
            "scoreable_not_parsed_by_both": missed,
            "mean_absolute_change": absolute_change(one, other, every, draws, seed),
            "mean_absolute_change_both_parsed": absolute_change(
                one[flags], other[flags], rows["episode_id"][flags], draws, seed
            ),
            "not_parsed": int((~parsed[name].loc[rows.index]).sum()),
        }
    return losses, clusters, means, moved


def combined_bounds(
    bounded: Mapping[str, Mapping[str, Any]],
    plus: Sequence[str],
    minus: Sequence[str],
    scale: float,
) -> dict[str, Any]:
    """The bounds of an effect on the loss: the combination of the cells' losses that gives the
    effect, taken of their bounds (``loss_bounds``) under each setting of the undetermined
    horizon events. Withheld when those are."""
    first = bounded[plus[0]]
    if FILLS[0] not in first:
        return dict(first)
    return {key: first[key] for key in COUNT_KEYS if key in first} | {
        fill: scale
        * (sum(bounded[cell][fill] for cell in plus) - sum(bounded[cell][fill] for cell in minus))
        for fill in FILLS
    }


def name_date_2x2(
    prepared: Prepared,
    rows: pd.DataFrame,
    more: More,
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    draws: int,
    seed: int,
) -> dict[str, Any]:
    """PLAN section 5, E4 ("Name and date 2x2"; primaries, condition b): the change in primary
    loss and the mean absolute change in ``P(E_end)``, in ``P(E_end90)`` and in the median,
    from the cell of real names and true dates to each other cell, and the two main effects
    with their interaction on the loss. Descriptive."""
    out = {}
    part = rows.loc[more.ids["twobytwo"]]
    real, masked, shifted, both = REFERENCE_CELL, *CELLS
    effects = {
        "names_masked": ((masked, both), (real, shifted), 0.5),
        "dates_shifted": ((shifted, both), (real, masked), 0.5),
        "interaction": ((both, real), (masked, shifted), 1.0),
    }
    for model, cells in prepared.cells.items():
        name = f"{model}:b"
        predictions = {REFERENCE_CELL: prepared.study.predictions[name].loc[part.index], **cells}
        parsed = {REFERENCE_CELL: prepared.study.parsed[name], **prepared.cells_parsed[model]}
        losses, clusters, means, moved = changes(
            part, predictions, parsed, REFERENCE_CELL, draws, seed
        )
        bounded = {cell: record["bounds_all_statements"] for cell, record in means.items()}
        shown = {}
        for label, (plus, minus, scale) in effects.items():
            effect = paired(
                (losses[plus[0]] + losses[plus[1]]) * scale,
                (losses[minus[0]] + losses[minus[1]]) * scale,
                clusters,
                2,
                draws,
                seed,
            )
            shown[label] = effect | {"bounds": combined_bounds(bounded, plus, minus, scale)}
        out[model] = {
            "item_set_fixed_by_the_probe": fixed_record(sets, model),
            "statements": len(part),
            "scoreable_statements": len(losses),
            "runs": prepared.cells_runs[model],
            "primary_brier": means,
            "change_from_the_reference_cell": moved,
            "effects_on_primary_loss": shown,
        }
    return out


def spread_bounds(bounded: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The bounds of the spread of a mean loss across prompts: the range and the standard
    deviation of the prompts' bounds (``loss_bounds``) under each setting of the undetermined
    horizon events. Withheld when those are."""
    first = bounded[0]
    if FILLS[0] not in first:
        return dict(first)
    out = {key: first[key] for key in COUNT_KEYS if key in first}
    for fill in FILLS:
        values = np.array([record[fill] for record in bounded], dtype=float)
        out[fill] = {
            "range": float(values.max() - values.min()),
            "sd": float(values.std(ddof=1)) if len(values) > 1 else None,
        }
    return out


def prompt_variance(
    prepared: Prepared,
    rows: pd.DataFrame,
    more: More,
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    draws: int,
    seed: int,
) -> dict[str, Any]:
    """PLAN section 5, E3 ("3 prompt paraphrases of (b) on a 200-item subset, to measure prompt
    variance"): the loss of each paraphrase and of the registered prompt on the same statements,
    the spread of the mean loss across prompts, the spread of each statement's probabilities and
    median across the paraphrases, and each paraphrase's change from the registered prompt (in
    the loss, and in ``P(E_end)``, ``P(E_end90)`` and the median). For a primary whose probe
    beat the base rate the same is given again on the statements of the subset dated after its
    cutoff (``beside_the_whole``)."""
    out = {}
    part = rows.loc[more.ids["paraphrase"]]
    registered = sheet_line(E3_LINES["b"]).template
    for model, made in prepared.paraphrases.items():
        name = f"{model}:b"
        predictions = {registered: prepared.study.predictions[name], **made}
        parsed = {registered: prepared.study.parsed[name], **prepared.paraphrases_parsed[model]}

        def figures(
            chosen: pd.DataFrame,
            within: pd.DataFrame | None = None,
            predictions: Mapping[str, pd.DataFrame] = predictions,
            parsed: Mapping[str, pd.Series] = parsed,
        ) -> dict[str, Any]:
            return variance_figures(chosen, predictions, parsed, registered, draws, seed, within)

        whole = figures(part)
        later = after_the_cutoff(sets, model, part, prepared.study.first["event_date"])
        out[model] = {
            "item_set_fixed_by_the_probe": fixed_record(sets, model),
            "statements": len(part),
            "scoreable_statements": whole["scoreable_statements"],
            "runs": prepared.paraphrases_runs[model],
            **{name: value for name, value in whole.items() if name != "scoreable_statements"},
            **beside_the_whole(part, later, figures, whole),
        }
    return out


def variance_figures(
    part: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    parsed: Mapping[str, pd.Series],
    registered: str,
    draws: int,
    seed: int,
    within: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Prompt variance on the statements of ``part``: ``predictions`` and ``parsed`` hold the
    registered prompt (``registered``) and, after it, the paraphrases. ``within``: the subset,
    when ``part`` holds its statements after a cutoff (``changes``)."""
    predictions = {name: pred.loc[part.index] for name, pred in predictions.items()}
    made = [name for name in predictions if name != registered]
    losses, clusters, means, moved = changes(
        part, predictions, parsed, registered, draws, seed, within
    )
    entry: dict[str, Any] = {
        "scoreable_statements": len(losses),
        "primary_brier": means,
        "change_from_the_registered_prompt": moved,
        "spread_of_the_mean_primary_loss": {},
        "spread_across_the_paraphrases_per_statement": {},
    }
    several = len(set(clusters)) >= ev.MIN_EPISODES
    for label, names in (("paraphrases", made), ("with_the_registered_prompt", None)):
        columns = losses[names] if names else losses
        mean = columns.mean().to_numpy()
        spread: dict[str, Any] = {
            "prompts": columns.shape[1],
            "range": float(mean.max() - mean.min()),
            "sd": float(mean.std(ddof=1)) if len(mean) > 1 else None,
            "range_ci95": None,
        }
        if several and len(losses):
            drawn = P.bootstrap_means(columns.to_numpy(), clusters, draws, seed)
            spread["range_ci95"] = P.interval(drawn.max(axis=1) - drawn.min(axis=1), 0.95)
        if small(len(losses)):  # the spread of a handful of losses is withheld with them
            spread = dict.fromkeys(spread) | {"prompts": columns.shape[1], "withheld": True}
        spread["bounds"] = spread_bounds(
            [means[prompt]["bounds_all_statements"] for prompt in columns.columns]
        )
        entry["spread_of_the_mean_primary_loss"][label] = spread
    for label, column in (("p_E_end", "p_a"), ("p_E_end90", "p_b"), ("median_days", "q50")):
        across = np.stack([predictions[t][column].to_numpy() for t in made])
        sd = across.std(axis=0, ddof=1) if len(made) > 1 else np.zeros(len(part))
        entry["spread_across_the_paraphrases_per_statement"][label] = mean_record(
            sd, part["episode_id"], draws, seed
        )
    return entry


def fixed_sets(
    confirmatory: Mapping[str, Any], rows: pd.DataFrame, study: ev.Study
) -> dict[str, tuple[pd.Index | None, dict[str, Any]]]:
    """By primary that is not declared not evaluable: the statements it is scored on, and the
    evaluator's record of that item set. The item set is the one the probe fixed (PLAN section
    5, E3 and E4): every eligible statement, those dated after the cutoff of the model, or
    none (None) when its tests are not evaluable. It is not taken from the evaluator's result
    file: it is worked out again from the probe readings (``evaluate.probe_test`` and
    ``evaluate.item_set``, under the registered draws and seed), which ``held_to_the_runs``
    held to the hash that file records, and a file whose record of the item set says anything
    else stops the scoring."""
    out = {}
    for model in (model for model in ev.PRIMARIES if model not in study.not_evaluable):
        probe = ev.probe_test(model, study, rows, ev.DRAWS, ev.SEED, ev.P_VALUE_SOURCE)
        ids, record = ev.item_set(model, probe["beats_base_rate"], study.first, rows)
        record = json.loads(ev.report_text(record))
        if part_of(confirmatory, "item_sets", model) != record:
            raise ValueError("the item set of a primary is not the one its probe gives")
        out[model] = (ids, record)
    return out


def selective_prediction(
    prepared: Prepared,
    rows: pd.DataFrame,
    sets: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    models: Sequence[str],
    draws: int,
    seed: int,
) -> dict[str, Any]:
    """PLAN section 7.2 ("Selective prediction: loss against abstention rate, for condition (c)
    and the rule reader only"), on the eligible list (section 5, E3, "Items"): one point per
    reader. A primary is read on the item set its probe fixed (``fixed_sets``) and has no point
    without one; the rule reader and the secondary models on every eligible statement. A
    statement is eligible only when its rule reading is dated, so the rule reader abstains on
    none by definition: its rate of zero is marked as fixed by eligibility (and the scoring
    stops if an eligible statement has no stated period), and its point is the loss of rules
    plus slip at full coverage. No point of the rule reader is given on the TBD, silent and
    stale lists, which its reading defines."""
    study = prepared.study
    rule = selective(rows, study.predictions[ev.RULES], rows["end_days"], draws, seed)
    if rule["abstained"]:  # the marker is held to the data, not asserted
        raise ValueError("an eligible statement has no stated period")
    out = {"rule_reader": rule | {"abstention_rate_fixed_by_eligibility": True}}
    chosen = {
        model: (ids, record["items"]) for model, (ids, record) in sets.items() if ids is not None
    }
    chosen |= {model: (rows.index, ev.ALL_ITEMS) for model in models}
    for model, (ids, items) in chosen.items():
        days = prepared.reading_days[model]
        _, _, counts = ev.literal_days(prepared.literal_rows[model], study.first.loc[ids])
        out[f"{model}:c"] = (
            {"items": items}
            | selective(rows.loc[ids], study.predictions[f"{model}:c"], days, draws, seed)
            | {key: int(count) for key, count in counts.items()}
        )
    return out


def recovery_rule(
    prepared: Prepared,
    rows: pd.DataFrame,
    variants: Mapping[str, pd.DataFrame | None],
    fixed: Mapping[str, tuple[pd.Index | None, dict[str, Any]]],
    models: Sequence[str],
    draws: int,
    seed: int,
    before: Mapping[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """PLAN section 2.5 ("Sensitivity analyses: leaving the list without a resolution counts as
    recovery at the first capture where the row is missing, and limited supply counts as
    available (BL)"; and the Date Discontinued cell that newly appears on a shortage row, which
    counts as a discontinuation at that capture): the contrasts of every model again under
    each (``unseal_population``). A primary is evaluated on the item set its probe fixed
    (``fixed_sets``) with its three tests (``evaluate.tests_of``); a secondary model on every
    eligible statement. Beside each contrast stand the bounds of section 7.2 over the
    statements of its item set that are at risk under the variant: one that is not at risk has
    no horizon event there and is not scored.

    A variant can move few statements. Beside the same contrast under the primary outcome, a
    contrast under a variant that gives 1 to ``MIN_SHOWN`` - 1 statements of the item set
    another horizon event, or as few of those scoreable under either definition, would give
    the change of the losses on those few: it is withheld with its bounds, and the number of
    statements with another horizon event is given for each model (section 2.5). Its counts
    are withheld with it, as the evaluator withholds those of a primary's tests: beside the
    counts under the primary outcome they would say how many of the few are scoreable (PLAN,
    standing rules), and so would the two counts of the variant over the eligible list where
    it moves so few of the list. The same holds between two outcome definitions
    (``near_definitions``;
    ``before``: the outcome variants of the evaluator, which stand before these three): the
    models whose contrasts under a variant are withheld are named. A variant whose column the
    outcome rows do not hold is recorded as not computed."""
    study = prepared.study
    sets: dict[str, tuple[pd.Index, list[tuple[str, str, str, int]]]] = {
        model: (ids, ev.tests_of(model, study))
        for model, (ids, _) in fixed.items()
        if ids is not None
    }
    for model in models:
        sets[model] = (rows.index, model_tests(model, study.comparator))
    definitions = {**(before or {}), **variants}
    near = {model: near_definitions(rows, definitions, ids) for model, (ids, _) in sets.items()}
    on_the_list = near_definitions(rows, definitions, rows.index)
    out: dict[str, Any] = {}
    for label, frame in variants.items():
        if frame is None:
            out[label] = {
                "computed": False,
                "reason": f"the outcome rows hold no column {VARIANT_COLUMNS[label]}",
            }
            continue
        typed = frame.loc[rows.index]
        at_risk = typed["outcome"].isin(dataset.AT_RISK_KINDS)
        contrasts: dict[str, Any] = {}
        for model, (ids, tests) in sets.items():
            chosen, contrasts[model] = typed.loc[ids], {}
            for name, comparator, tested, sides in tests:
                result = brief(
                    ev.scored(
                        chosen, study.predictions, comparator, tested, draws=draws, seed=seed
                    ),
                    sides,
                )
                bounds = contrast_bounds(
                    chosen[at_risk.loc[ids].to_numpy()],
                    study.predictions,
                    comparator,
                    tested,
                    result,
                )
                if near[model][label][1]:  # no count either: the number moved is given
                    result, bounds = {"withheld": True}, {"withheld": True}
                contrasts[model][name] = (
                    {"comparator": comparator, "tested": tested} | result | {"bounds": bounds}
                )
        few_moved = on_the_list[label][1]
        out[label] = {
            "computed": True,
            "eligible_statements": len(typed),
            "not_at_risk_under_the_variant": None if few_moved else int((~at_risk).sum()),
            "scoreable_statements": None if few_moved else int(typed["scoreable"].sum()),
            "statements_with_another_horizon_event": {
                model: near[model][label][0] for model in sets
            },
            "withheld_beside_another_outcome": [model for model in sets if near[model][label][1]],
            "contrasts": contrasts,
        }
    return out


# --------------------------------------------------------------------------------------------
# The descriptives of E1
# --------------------------------------------------------------------------------------------


def hold_record(rows: pd.DataFrame, draws: int, seed: int) -> dict[str, Any]:
    """The hold rate of the stated period, ``P(E_end)``, on dated statements (conditional on
    survival to first sight): among the statements whose event is determined, and over all of
    them with each undetermined event set to no and then to yes. With the counts beside them
    the three shares are one number, the number of statements that held: all three are
    withheld when 1 to ``MIN_SHOWN`` - 1 statements are determined, however many there are."""
    held = rows["y_a"].to_numpy(dtype=float)
    known = ~np.isnan(held)
    clusters = rows["episode_id"].to_numpy()
    out = {
        "statements": len(rows),
        "determined": int(known.sum()),
        "undetermined": int((~known).sum()),
        "among_determined": mean_record(held[known], clusters[known], draws, seed, MIN_SHOWN),
        "undetermined_as_no": mean_record(
            np.where(known, held, 0.0), clusters, draws, seed, MIN_SHOWN
        ),
        "undetermined_as_yes": mean_record(
            np.where(known, held, 1.0), clusters, draws, seed, MIN_SHOWN
        ),
    }
    return hold_withheld(out) if small(out["determined"]) else out


def hold_withheld(record: Mapping[str, Any]) -> dict[str, Any]:
    """A hold rate with its three shares withheld and its counts kept."""
    return dict(record) | {key: withheld(record[key], "mean", "ci95") for key in HOLD_SHARES}


def near_unions(
    first: np.ndarray, second: np.ndarray, groups: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray] | None:
    """Two sets, each a union of the groups of one split, that differ by 1 to ``MIN_SHOWN`` - 1
    items: None when there are none, else which groups make each of them (two masks).
    ``first`` and ``second`` give the group of every item in the two splits (-1: in no group
    whose figure is known), ``groups`` how many groups each split has."""
    sizes = [
        np.bincount(labels[labels >= 0], minlength=count)
        for labels, count in zip((first, second), groups, strict=True)
    ]
    both = (first >= 0) & (second >= 0)
    shared = np.zeros(groups, dtype=np.int64)
    np.add.at(shared, (first[both], second[both]), 1)
    one, other = ((np.arange(1, 1 << count)[:, None] >> np.arange(count)) & 1 for count in groups)
    mine, theirs = one @ sizes[0], other @ sizes[1]
    apart = mine[:, None] + theirs[None, :] - 2 * (one @ shared @ other.T)
    near = (apart > 0) & (apart < MIN_SHOWN) & (mine[:, None] > 0) & (theirs[None, :] > 0)
    found = np.argwhere(near)
    if not len(found):
        return None
    return one[found[0][0]].astype(bool), other[found[0][1]].astype(bool)


def withheld_cells(
    whole: Sequence[Any],
    splits: Mapping[str, Mapping[str, Iterable[Any]]],
    shown: Mapping[str, Iterable[str]],
    total: bool,
    rank: Any,
) -> dict[tuple[str, str], str]:
    """The cells to withhold, beyond those that already are, so that the figures written on a
    set and on the cells of its splits give none back on 1 to ``MIN_SHOWN`` - 1 items (PLAN,
    standing rules). ``whole``: the items; ``splits``: the items of every cell of each split
    (the cells of a split share none); ``shown``: the cells of each split whose figure is
    written so far; ``total``: whether the figure on the whole is written.

    A figure that adds up over statements (a count, a share with its count) is known on every
    union of the cells shown of a split and, beside the total, on the rest of the split taken
    together. Two such sets that differ by a few items give the figure on those few:

    * the rest of a split of 1 to ``MIN_SHOWN`` - 1 items: one more cell of the split is
      withheld (``WITH_ANOTHER``);
    * a union in one split beside a union in another: a cell of the later split is withheld,
      chosen so that the rest of that split lies partly in the union and partly out of it
      (``NEAR_SET``).

    The cell withheld is the first by ``rank(split, cell)`` among those that serve, and the
    search starts again until nothing is given back. Returns the mark of each cell."""
    place = {item: k for k, item in enumerate(whole)}
    member = {
        name: {
            cell: np.array([place[i] for i in items], dtype=int) for cell, items in cells.items()
        }
        for name, cells in splits.items()
    }
    left = {name: [cell for cell in shown[name] if len(member[name][cell])] for name in splits}
    marks: dict[tuple[str, str], str] = {}

    def groups(name: str) -> np.ndarray:
        """The group of every item: a cell shown, or the rest (known beside the total)."""
        out = np.full(len(place), len(left[name]) if total else -1)
        for k, cell in enumerate(left[name]):
            out[member[name][cell]] = k
        return out

    def straddling(name: str, union: np.ndarray) -> tuple[list[str], str]:
        """The cells shown whose withholding puts the rest of the split partly in ``union``,
        and the mark of the one withheld: for the union when the rest is not yet part of it,
        for the cells of the rest when it is."""
        rest_in = bool(union[-1]) and bool((groups(name) == len(left[name])).any())
        cells = [cell for k, cell in enumerate(left[name]) if bool(union[k]) != rest_in]
        return cells, WITH_ANOTHER if rest_in else NEAR_SET

    def withhold(name: str, cells: Sequence[str], mark: str) -> None:
        cell = min(cells, key=lambda one: rank(name, one))
        left[name].remove(cell)
        marks[name, cell] = mark

    while True:
        before = len(marks)
        for name in splits:
            if left[name] and small(int((groups(name) == len(left[name])).sum())):
                withhold(name, left[name], WITH_ANOTHER)
                break
        else:
            names = list(splits)
            pairs = [(a, b) for k, a in enumerate(names) for b in names[k + 1 :]]
            for first, second in pairs:
                sizes = (len(left[first]) + 1, len(left[second]) + 1)
                near = near_unions(groups(first), groups(second), sizes)
                if near is None:
                    continue
                for name, union in ((second, near[1]), (first, near[0])):
                    serve, mark = straddling(name, union)
                    if serve:
                        withhold(name, serve, mark)
                        break
                break
        if len(marks) == before:
            return marks


def hold_tables(
    dated: pd.DataFrame, splits: Mapping[str, Mapping[str, pd.DataFrame]], draws: int, seed: int
) -> dict[str, Any]:
    """The hold rate on all dated statements and on every cell of the splits of them (by form,
    by revision bucket), with what ``withheld_cells`` withholds so that the cells written give
    back neither of two things about 1 to ``MIN_SHOWN`` - 1 statements:

    * how many of them have a determined event (a fact of their outcomes): a cell of that few
      statements keeps their number alone (``counts_apart``), and so does each cell withheld
      for it, over the statements of the cells;
    * how many of them held: the shares of a cell with that few determined statements are
      withheld (``hold_record``), and so are those of each cell withheld for it
      (``hold_withheld``), over the statements with a determined event.

    A cell withheld for another carries the mark that says why. The cell chosen is the one
    with the fewest determined statements (the first by name among equals)."""
    records = {
        name: {cell: hold_record(frame, draws, seed) for cell, frame in cells.items()}
        for name, cells in splits.items()
    }
    whole = hold_record(dated, draws, seed)

    def rank(name: str, cell: str) -> tuple[int, str]:
        return records[name][cell]["determined"], cell

    def determined(frame: pd.DataFrame) -> pd.Index:
        return frame.index[frame["y_a"].notna().to_numpy()]

    def rated(record: Mapping[str, Any]) -> bool:
        return record["among_determined"]["mean"] is not None

    counted = {
        name: [cell for cell, frame in cells.items() if len(frame) >= MIN_SHOWN]
        for name, cells in splits.items()
    }
    bare = withheld_cells(
        list(dated.index),
        {
            name: {cell: frame.index for cell, frame in cells.items()}
            for name, cells in splits.items()
        },
        counted,
        len(dated) >= MIN_SHOWN,
        rank,
    )
    hidden = withheld_cells(
        list(determined(dated)),
        {
            name: {cell: determined(frame) for cell, frame in cells.items()}
            for name, cells in splits.items()
        },
        {
            name: [c for c in cells if (name, c) not in bare and rated(records[name][c])]
            for name, cells in counted.items()
        },
        len(dated) >= MIN_SHOWN and rated(whole),
        rank,
    )
    out: dict[str, Any] = {"all_dated_forms": counts_apart(whole) if small(len(dated)) else whole}
    for name, cells in records.items():
        out[name] = {}
        for cell, record in cells.items():
            mark = bare.get((name, cell), hidden.get((name, cell)))
            if small(record["statements"]) or (name, cell) in bare:
                record = counts_apart(record)
            elif (name, cell) in hidden:
                record = hold_withheld(record)
            out[name][cell] = record | ({mark: True} if mark else {})
    return out


def counts_apart(cell: Mapping[str, Any]) -> dict[str, Any]:
    """A cell of the hold rate without the counts that depend on outcomes: the number of its
    statements stays, how many have a determined event does not, and its shares are
    withheld."""
    bare = {"mean": None, "ci95": None, "withheld": True}
    return (
        dict(cell)
        | {"determined": None, "undetermined": None}
        | {key: dict(bare) for key in HOLD_SHARES}
    )


def slip_quantile(
    curve: P.Turnbull, tighter: Any, level: float
) -> tuple[float | None, bool, float | None]:
    """The quantile of a Turnbull curve at ``level`` (None where the curve does not reach it),
    whether the curve is flat at that level, and the day on which the flat stretch ends (None
    where the curve does not rise again within reach of the data).

    The iteration stops a little short of its limit. Where the limit has a corner exactly at
    the level, with no recovery for some days after it, what is left over decides on which
    side of the level the corner stands, and ``curve.quantile`` would give either end of the
    flat stretch or a day in an interval that the limit leaves empty. A corner is taken to
    stand at the level when it is within ``SLIP_NEAR`` of it and at most a third as far (or
    within ``SLIP_SETTLED``) in the tighter fit that ``tighter()`` gives (None when that fit
    does not settle: no corner is then moved): what the iteration left over shrinks with the
    tolerance, and a corner that stands off the level stays where it is. The intervals after
    it whose mass shrinks in the same way are empty. The quantile is then that corner, the
    smallest value that reaches the level (``predictors.Turnbull.quantile``), and the flat
    stretch ends where the next interval that holds mass starts. Anywhere else it is
    ``curve.quantile(level)`` unchanged."""
    value = float(curve.quantile(np.asarray(level)))
    finite = np.isfinite(curve.right)
    left, right = curve.left[finite], curve.right[finite]
    off = np.abs(np.cumsum(curve.mass[finite]) - level)
    again = tighter() if (off <= SLIP_NEAR).any() else None
    if again is not None:
        closer = np.abs(np.cumsum(again.mass[finite]) - level)
        at = np.flatnonzero((off <= SLIP_NEAR) & (closer <= np.maximum(off / 3, SLIP_SETTLED)))
        if len(at):
            start, beyond = float(right[at[0]]), int(at[0]) + 1
            mass, less = curve.mass[finite], again.mass[finite]
            while beyond < len(left) and less[beyond] <= max(mass[beyond] / 3, SLIP_SETTLED):
                beyond += 1
            end = float(left[beyond]) if beyond < len(left) else None
            if end is None or end > start:
                return min(value, start), True, end
    return (value if np.isfinite(value) else None), False, None


def slip_record(rows: pd.DataFrame, slip_draws: int, seed: int) -> dict[str, Any]:
    """The slip distribution of dated statements (recovery minus the stated end, in days) as a
    Turnbull estimate: the share recovered by each day of ``SLIP_DAYS`` after the stated end,
    the quantiles of ``SLIP_LEVELS`` (``slip_quantile``: None where the estimate does not reach
    the level; where the curve is flat at a level, the start of the flat stretch, with its end
    beside it), and the share not recovered within reach of the data. The intervals are
    percentile intervals over the first ``slip_draws`` of the registered bootstrap draws of the
    episodes, each with a Turnbull fit of its own; the quantiles carry none."""
    out: dict[str, Any] = {
        "statements": len(rows),
        "episodes": int(rows["episode_id"].nunique()),
    }
    if len(rows) < MIN_SHOWN:
        return out | {"withheld": len(rows) > 0}
    left, right = P.slip_brackets(rows)
    curve = P.turnbull(left, right)
    days = np.asarray(SLIP_DAYS, dtype=float)
    refit: list[P.Turnbull | None] = []

    def tighter() -> P.Turnbull | None:
        """The same estimate under a tighter tolerance, fitted once and only when a corner
        stands near a level; None when it does not settle within the steps allowed."""
        if not refit:
            try:
                refit.append(P.turnbull(left, right, tolerance=P.TOLERANCE * SLIP_TIGHTER))
            except RuntimeError:
                refit.append(None)
        return refit[0]

    quantiles = {f"{level:.2f}": slip_quantile(curve, tighter, level) for level in SLIP_LEVELS}
    out |= {
        "share_recovered_by_days_after_the_stated_end": {
            str(day): float(share) for day, share in zip(SLIP_DAYS, curve.cdf(days), strict=True)
        },
        "slip_quantiles_days": {level: value for level, (value, _, _) in quantiles.items()},
        "slip_quantiles_flat_to_days": {
            level: end for level, (_, flat, end) in quantiles.items() if flat
        },
        "share_not_recovered_within_reach": float(1.0 - curve.reached),
        "ci95": None,
        "draws": 0,
    }
    codes = pd.Categorical(rows["episode_id"]).codes
    groups = int(codes.max()) + 1
    if groups >= ev.MIN_EPISODES and slip_draws > 0:
        taken = P.cluster_draws(groups, ev.DRAWS, seed)[:slip_draws]
        position = np.arange(len(rows))
        drawn = np.empty((len(taken), len(days)))
        for k, counts in enumerate(taken):
            chosen = np.repeat(position, counts[codes])
            drawn[k] = P.turnbull(left[chosen], right[chosen]).cdf(days)
        out["ci95"] = {str(day): P.interval(drawn[:, k], 0.95) for k, day in enumerate(SLIP_DAYS)}
        out["draws"] = len(taken)
    return out


def slip_tables(
    dated: pd.DataFrame,
    splits: Mapping[str, Mapping[str, pd.DataFrame]],
    slip_draws: int,
    seed: int,
) -> dict[str, Any]:
    """The slip estimate on all dated statements and on every cell of the splits of them. The
    estimate of a set is, where the brackets of its statements do not overlap, the mean of
    those of its cells weighted by their size, so that the cells of a split come back from the
    whole as a count would: ``withheld_cells`` withholds a further cell, and marks it, where
    the estimates written would give back that of 1 to ``MIN_SHOWN`` - 1 statements (the cell
    of the fewest statements, the first by name among equals)."""
    dropped = withheld_cells(
        list(dated.index),
        {
            name: {cell: frame.index for cell, frame in cells.items()}
            for name, cells in splits.items()
        },
        {
            name: [cell for cell, frame in cells.items() if len(frame) >= MIN_SHOWN]
            for name, cells in splits.items()
        },
        len(dated) >= MIN_SHOWN,
        lambda name, cell: (len(splits[name][cell]), cell),
    )
    out: dict[str, Any] = {"all_dated_forms": slip_record(dated, slip_draws, seed)}
    for name, cells in splits.items():
        out[name] = {}
        for cell, frame in cells.items():
            if (name, cell) in dropped:
                out[name][cell] = {
                    "statements": len(frame),
                    "episodes": int(frame["episode_id"].nunique()),
                    "withheld": True,
                    dropped[name, cell]: True,
                }
            else:
                out[name][cell] = slip_record(frame, slip_draws, seed)
    return out


def width_record(rows: pd.DataFrame, draws: int, seed: int) -> dict[str, Any]:
    """The distribution of bracket widths: the days between the two captures that bracket a
    recovery or a discontinuation, over the statements with such a bracket."""
    finite = rows[rows["outcome"].isin(("recovered", "discontinued")) & rows["upper_days"].notna()]
    width = (finite["upper_days"] - finite["lower_days"]).to_numpy(dtype=float)
    clusters = finite["episode_id"].to_numpy()
    out: dict[str, Any] = {
        "statements": len(rows),
        "with_a_finite_bracket": len(finite),
        "right_censored": int((rows["outcome"] == "censored").sum()),
    }
    if small(len(rows)):  # which of a few statements have a bracket is theirs to tell
        return {"statements": len(rows), "withheld": True}
    if len(finite) < MIN_SHOWN:
        return out | {"withheld": len(finite) > 0}
    return out | {
        "quantiles_days": {
            f"{level:.2f}": float(value)
            for level, value in zip(WIDTH_LEVELS, np.quantile(width, WIDTH_LEVELS), strict=True)
        },
        "mean_days": mean_record(width, clusters, draws, seed),
        f"share_of_{corpus.OBSERVABLE_WIDTH_DAYS}_days_or_less": mean_record(
            (width <= corpus.OBSERVABLE_WIDTH_DAYS).astype(float), clusters, draws, seed
        ),
    }


def count_record(rows: pd.DataFrame, first: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Statements by year, form (after the merge of small classes), statement type, company,
    analysis set and revision bucket: first-sight cells only."""
    cells = first.loc[rows.index]
    columns = {
        "year": cells["event_date"].str[:4],
        "form": rows["form"],
        "statement_type": cells["statement_type"],
        "company": cells["company_name"],
        "analysis_set": rows["analysis_set"],
        "revision": rows["revision"],
    }
    return {
        f"by_{name}": {str(key): int(n) for key, n in sorted(column.value_counts().items())}
        for name, column in columns.items()
    }


def descriptives(
    rows: pd.DataFrame,
    first: pd.DataFrame,
    draws: int = ev.DRAWS,
    slip_draws: int | None = None,
    seed: int = ev.SEED,
) -> dict[str, Any]:
    """The descriptives of E1 (PLAN section 5, E1) on the statements of ``rows`` (the typed
    frame with outcomes; ``first`` holds their first-sight cells as text): the hold rate of the
    stated period, the Turnbull estimate of slip (on ``slip_draws`` of the registered draws:
    ``SLIP_DRAWS`` unless given), the bracket widths, and the counts by year, form, statement
    type and company. Intervals: percentile bootstrap, 95%, clustered by episode.

    The hold rate and the slip estimate are written on all dated statements and on each cell
    of two splits of them, by form and by revision bucket. The cells of a split add up to the
    whole, and a set of cells of one split can hold the statements of a set of cells of the
    other but for a few (PLAN, standing rules: the same figure on a set that differs from its
    own by 1 to 4 statements): ``hold_tables`` and ``slip_tables`` withhold and mark the cells
    that would give a figure back on that few."""
    dated = rows[rows["analysis_set"] == "dated"]
    slip_draws = SLIP_DRAWS if slip_draws is None else slip_draws
    splits = {
        "by_form": {form: dated[dated["form"] == form] for form in sorted(set(dated["form"]))},
        "by_revision": {bucket: dated[dated["revision"] == bucket] for bucket in P.REVISIONS},
    }
    return {
        "statements": len(rows),
        "episodes": int(rows["episode_id"].nunique()),
        "dated_statements_not_stale": len(dated),
        "counts": count_record(rows, first),
        "hold_rate": hold_tables(dated, splits, draws, seed),
        "slip": slip_tables(dated, splits, slip_draws, seed),
        "bracket_widths": width_record(rows, draws, seed),
    }


# --------------------------------------------------------------------------------------------
# The commands
# --------------------------------------------------------------------------------------------


def leads_to_sealed(path: Any, sealed: Any) -> bool:
    """Whether ``path`` is the sealed file, its folder, or anything in a folder named as the
    registered sealed one: the path as given, or the one a symbolic link on its way leads to.
    The path is walked part by part, and each step is compared as text before the file system
    is asked whether it is a link: nothing is asked about the sealed file, about its folder
    or about a folder named as the sealed one. ``sealed`` is compared as given. Another file
    in the folder of ``sealed`` is sealed only when that folder is named as the registered
    one. Links that lead in a circle count as sealed: nothing is read through them."""
    target = os.path.abspath(sealed)
    folder = os.path.dirname(target)
    try:
        text = os.fspath(path)
    except TypeError:
        return False
    if not isinstance(text, str) or "\0" in text:
        return False
    pending = [part for part in os.path.join(os.getcwd(), text).split(os.sep) if part]
    current, hops = os.sep, 0
    while pending:
        part = pending.pop(0)
        if part == ".":
            continue
        if part == "..":
            current = os.path.dirname(current)
            continue
        current = os.path.join(current, part)
        if current == target or part == sealed_counts.SEALED_FOLDER:
            return True
        if current == folder:  # the folder itself, or the way to a file in it: not asked about
            if not pending:
                return True
            continue
        if os.path.islink(current):
            hops += 1
            if hops > LINK_HOPS:
                return True
            try:
                link = os.readlink(current)
            except OSError:
                return True
            current = os.sep if os.path.isabs(link) else os.path.dirname(current)
            pending = [part for part in link.split(os.sep) if part] + pending
    return False


def strings_of(value: Any) -> Iterable[str]:
    """Every string a parsed JSON value holds, at any depth (the keys of a mapping apart)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from strings_of(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_of(item)


def kept_from_sealed_paths(args: argparse.Namespace, names: Sequence[str]) -> None:
    """Refuse, before any file is opened and before the file system is asked anything about
    a sealed path, when something this command would read leads to the sealed file or into a
    sealed folder (``leads_to_sealed``): an input of the command line
    (``names``), the selection file of a primary, the plan of the runs, any path the plan
    names (every string it holds is looked at, wherever it stands: an item file, a track
    record, the field of a single run), and every file stored in the folder of a run of the
    plan, whether or not its model is scored. A stored file that is a symbolic link to the
    sealed file would otherwise be read, and hashed, as an open one. A plan that is not there,
    or is no plan, is left to the completeness check."""
    sealed = args.sealed

    def held(path: Any, what: str) -> None:
        if leads_to_sealed(path, sealed):
            ev.refuse(
                f"{what} leads into a sealed folder; only --sealed names a sealed file, and "
                "nothing is read through a link to one"
            )

    for name in names:  # in the words of ``evaluate.open_paths``, which looks at the same
        if leads_to_sealed(getattr(args, name), sealed):
            ev.refuse(
                f"--{name.replace('_', '-')} would be read from a sealed folder; only --sealed "
                "names a sealed file"
            )
    if "selections" in names:
        for model in ev.PRIMARIES:
            held(
                args.selections / ev.SELECTION_NAME.format(model=model),
                f"the selection file of {model}",
            )
    if "out_root" not in names:
        return
    path = lp.plan_path(args.out_root)
    held(path, "the plan of the runs")
    try:
        plan = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return
    if any(leads_to_sealed(text, sealed) for text in strings_of(plan)):
        ev.refuse("the plan of the runs names a path in a sealed folder; none of its files is read")
    runs = plan.get("runs") if isinstance(plan, dict) else None
    named = [
        run.get("run") for run in (runs if isinstance(runs, list) else []) if isinstance(run, dict)
    ]
    folders = [path.parent, *(args.out_root / name for name in named if isinstance(name, str))]
    for folder in dict.fromkeys(folders):
        held(folder, "the folder of a run of the plan")
        try:
            stored = sorted(entry.name for entry in os.scandir(folder))
        except OSError:
            continue
        for name in stored:
            held(folder / name, f"a stored file of the runs ({folder.name}/{name})")


def output_path(path: Path | None, sealed: Any) -> Path:
    """The file ``--out`` names (``evaluate.output_paths``: given, outside a sealed folder,
    not there yet, in a folder that is). A name that leads into a sealed folder through a
    link is refused first, in the same words, before the file system is asked about it."""
    if path is not None and path.name and leads_to_sealed(path, sealed):
        ev.refuse("--out lies in a sealed folder; results are written outside it")
    return ev.output_paths(path)[0]


def write_result(path: Path, text: str) -> None:
    """Write a result file, which must not exist yet, whole or not at all: under another name
    in the same folder first, then given its own by a link, which fails when the name is
    taken (nothing is overwritten). A write that stops half way (a disk that is full) leaves
    nothing behind."""
    partial = path.with_name(f".partial.{os.getpid()}.{path.name}")
    stopped = ""
    try:
        with partial.open("x", encoding="utf-8") as handle:
            handle.write(text)
        os.link(partial, path)
    except OSError as error:
        stopped = type(error).__name__
    with contextlib.suppress(OSError):
        partial.unlink()
    if stopped:
        ev.refuse(f"the output cannot be written ({stopped}): {path.as_posix()}")


def print_summary(out: Path, lines: Sequence[str]) -> int:
    """Print the summary of a result file that has been written, and where it is. When the
    printout cannot be made (the reader of a pipe has gone), the command says on the error
    stream that the file is written and ends with status 1: it is no refusal, and the file
    is whole."""
    stopped = ""
    try:
        for line in (*lines, f"wrote {out.as_posix()}"):
            print(line)
        sys.stdout.flush()
    except OSError as error:
        stopped = type(error).__name__
    if not stopped:
        return 0
    if sys.stdout is sys.__stdout__:  # nothing more goes to the closed stream when Python ends
        with contextlib.suppress(OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    raise SystemExit(
        f"wrote {out.as_posix()}: the result file is written and whole; its summary could not "
        f"be printed ({stopped})"
    )


def code_record() -> dict[str, str]:
    """The sha256 of this file with the record of the evaluator's code and libraries."""
    mine = sealed_counts.sha256(sealed_counts.file_bytes(Path(__file__), "secondary_scores.py"))
    return {"secondary_scores.py": mine, **ev.code_record()}


def left_out_models(values: Sequence[str]) -> dict[str, str]:
    """``--left-out MODEL=REASON`` as a mapping: a secondary model whose runs are not scored.
    The reason is printable text on one line: it is written into the result file, and a byte
    of the command line that was no text could not be written there."""
    out = {}
    for value in values:
        model, _, reason = value.partition("=")
        if model not in SECONDARY_MODELS or not reason.strip():
            ev.refuse(
                f"--left-out takes MODEL=REASON with a secondary model of {list(SECONDARY_MODELS)}"
            )
        if not reason.isprintable():  # a line break, or a byte that was no text
            ev.refuse("--left-out takes a REASON of printable text, on one line")
        out[model] = "declared on the command line: " + reason.strip()
    return out


def chosen_sections(values: Sequence[str]) -> list[str]:
    """``--section NAME`` (several times) as the sections to compute, in the order of
    ``SECTIONS``; all of them when none is named."""
    unknown = sorted(set(values) - set(SECTIONS))
    if unknown:
        ev.refuse(f"--section takes a name of {list(SECTIONS)}")
    return [name for name in SECTIONS if not values or name in values]


def score(
    prepared: Prepared,
    more: More,
    sealed: bytes,
    events: pd.DataFrame,
    listed: pd.DataFrame,
    confirmatory: Mapping[str, Any],
    sections: Sequence[str],
    models: Sequence[str],
    draws: int = ev.DRAWS,
    slip_draws: int | None = None,
    seed: int = ev.SEED,
) -> dict[str, Any]:
    """Every section asked for, from the sealed bytes: the eligible list through
    ``evaluate.unseal``, the wider population through the same checked reader. The item set of
    each primary is worked out from its probe first (``fixed_sets``), whatever is asked for:
    a result file of the evaluator that records another one stands behind no section."""
    rows, outcome_variants = ev.unseal(sealed, events, listed)
    everything, variants = unseal_population(sealed, events, prepared.population)
    first = prepared.population.set_index("statement_group_id")
    scoreable = rows[rows["scoreable"]]
    out: dict[str, Any] = {
        "items": {
            "eligible_statements": len(rows),
            "eligible_episodes": int(rows["episode_id"].nunique()),
            "scoreable_statements": len(scoreable),
            "scoreable_episodes": int(scoreable["episode_id"].nunique()),
            "test_split_statements_at_risk": len(everything),
        }
    }
    sets = fixed_sets(confirmatory, rows, prepared.study)
    definitions = {**outcome_variants, **variants}
    for name in sections:
        if name == "secondary_models":
            out[name] = secondary_models(
                prepared, rows, outcome_variants, models, draws, seed, definitions
            )
        elif name == "secondary_lists":
            out[name] = secondary_lists(prepared, everything, more, sets, draws, seed)
        elif name == "sampled_quantiles":
            out[name] = sampled_quantiles(prepared, rows, more, sets, draws, seed)
        elif name == "prompt_variance":
            out[name] = prompt_variance(prepared, rows, more, sets, draws, seed)
        elif name == "name_date_2x2":
            out[name] = name_date_2x2(prepared, rows, more, sets, draws, seed)
        elif name == "descriptives":
            out[name] = descriptives(everything, first, draws, slip_draws, seed)
        elif name == "selective_prediction":
            out[name] = selective_prediction(prepared, rows, sets, models, draws, seed)
        elif name == "recovery_rule":
            out[name] = recovery_rule(
                prepared, rows, variants, sets, models, draws, seed, outcome_variants
            )
    return out


def summary_lines(report: Mapping[str, Any]) -> list[str]:
    items = report["items"]
    lines = [
        f"eligible: {items['eligible_statements']} statements in {items['eligible_episodes']} "
        f"episodes; scoreable: {items['scoreable_statements']} in {items['scoreable_episodes']}",
        f"sections: {', '.join(report['sections'])}; p-values: "
        f"{report['registered']['p_value_source']}; no multiplicity claim",
    ]
    for model, entry in (report.get("secondary_models") or {}).get("models", {}).items():
        for name, result in entry["on_every_eligible_statement"].items():
            if result.get("evaluable"):
                lines.append(
                    f"  {model:17s} {name}: delta {result['delta']:.4f}, p {result['p']:.4f}"
                )
    return lines


def run_score(args: argparse.Namespace) -> int:
    want_sealed = sealed_counts.expected_hash(args.expect_sha256, "--expect-sha256")
    want_eligible = sealed_counts.expected_hash(
        args.expect_eligible_sha256, "--expect-eligible-sha256"
    )
    want_baselines = sealed_counts.expected_hash(
        args.expect_baselines_sha256, "--expect-baselines-sha256"
    )
    want_selections = ev.selection_hashes(args.expect_selection_sha256)
    wrong = ev.constants_problem()
    if wrong:
        ev.refuse(wrong)
    out = output_path(args.out, args.sealed)
    sections = chosen_sections(args.section)
    left_out = left_out_models(args.left_out)
    skipped = ev.skipped_models(args.not_evaluable)
    if set(skipped) >= set(ev.PRIMARIES):
        ev.refuse(
            "every primary is declared not evaluable: no test of the family can have been "
            "computed, and the sealed file is not opened for the secondaries alone"
        )
    unhashed = [
        model for model in ev.PRIMARIES if model not in skipped and model not in want_selections
    ]
    if unhashed:
        ev.refuse(
            f"--expect-selection-sha256 is required for {unhashed}: the H3 selections are held "
            "to the hashes of the freeze"
        )
    if args.confirmatory is None:
        ev.refuse("--confirmatory is required: the result file of the registered evaluator")
    names = ("statements", "eligible", "events", "counts", "out_root", "selections", "confirmatory")
    kept_from_sealed_paths(args, names)
    ev.open_paths(args, names)

    # open inputs, the evaluator's result, the completeness checks and every prediction
    data, hashes = ev.open_tables(args, want_eligible)
    confirmatory, confirmatory_sha = confirmatory_record(
        args.confirmatory, hashes, want_sealed, want_baselines
    )
    said, recorded_selections = declared(confirmatory, skipped, want_selections)
    stopped = ""
    try:
        table = ev.table_of(data["the statement table"], True)
        eligible = ev.table_of(data["the eligible list"], False)
        events = ev.table_of(data["the events table"], args.events.suffix == ".gz")
    except Exception as error:
        stopped = type(error).__name__
    if stopped:
        ev.refuse(f"the open inputs are not as the builders write them ({stopped})")
    listed = sealed_counts.listed_statements(table, eligible)
    counts = json.loads(data["the counts file"])
    found = ev.gathered(
        args.out_root,
        eligible,
        listed.set_index("statement_group_id"),
        counts,
        args.selections,
        hashes["the statement table"],
        skipped,
        recorded_selections,
        args.sealed,
    )
    if found.problems:
        ev.refuse(
            "no secondary score before every confirmatory run is complete (PLAN, standing "
            "rules): " + "; ".join(found.problems)
        )
    held_to_the_runs(confirmatory, said, found, listed.set_index("statement_group_id"))
    plan, _, problems = ev.read_plan(args.out_root, args.sealed)
    if plan is None or problems:
        ev.refuse("; ".join(problems))
    left_out_check = left_out_findings(
        plan, args.out_root, eligible, table.set_index("statement_group_id"), sections, left_out
    )
    complete = [model for model, findings in left_out_check.items() if not findings]
    if complete:
        ev.refuse(
            "--left-out names a secondary model whose runs pass the completeness check "
            f"({', '.join(complete)}): a model is left out only when its runs are not complete "
            "(PLAN sections 9 and 12)"
        )
    models = [model for model in SECONDARY_MODELS if model not in left_out]
    primaries = [model for model in ev.PRIMARIES if model not in skipped]
    more = gathered_more(
        plan,
        args.out_root,
        table,
        eligible,
        table.set_index("statement_group_id"),
        counts,
        sections,
        models,
        primaries,
    )
    if more.problems:
        ev.refuse(
            "no secondary score before every run it scores is complete: " + "; ".join(more.problems)
        )
    try:
        prepared = prepare(table, listed, found, more, skipped)
    except Exception as error:
        stopped = type(error).__name__  # its message may name an item
    if stopped:
        ev.refuse(f"the readings could not be turned into predictions ({stopped})")
    if prepared.problems:
        ev.refuse("the readings cannot be scored: " + "; ".join(prepared.problems))
    if not prepared.baselines_sha256.startswith(want_baselines):
        ev.refuse(
            "the model-free predictions are not those hashed at the freeze: their sha256 "
            f"starts with {prepared.baselines_sha256[:16]}, expected {want_baselines[:16]}"
        )

    # the sealed file: hashed as bytes, parsed only when the hash is the expected one; a file
    # refused for its hash has no character of that hash printed (PLAN, standing rules)
    sealed = sealed_counts.file_bytes(args.sealed, "the sealed file")
    sealed_sha = ev.hash_required(
        sealed, want_sealed, "the sealed file", args.sealed, args.sealed, of_sealed=True
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # a warning may quote a cell
            results = score(
                prepared,
                more,
                sealed,
                events,
                listed,
                confirmatory,
                sections,
                models,
                slip_draws=SLIP_DRAWS,
            )
        report = {
            "about": ABOUT,
            "command": "PYTHONPATH=. python -m analysis.coling.secondary_scores score "
            "--expect-sha256 <sealed file> --expect-eligible-sha256 <eligible list> "
            "--expect-baselines-sha256 <model-free predictions> --expect-selection-sha256 "
            "<model>=<selection file> (one for each primary) --confirmatory <result file of "
            "the evaluator> --out <file>",
            "registered": ev.registered_record(),
            "inputs": {
                "sealed_outcomes_sha256": sealed_sha,
                "eligible_sha256": hashes["the eligible list"],
                "statements_sha256": hashes["the statement table"],
                "events_sha256": hashes["the events table"],
                "dataset_counts_sha256": hashes["the counts file"],
                "plan_sha256": found.plan_sha256,
                "plan_sha256_of_the_confirmatory_result": part_of(confirmatory, "inputs").get(
                    "plan_sha256"
                ),
                "baseline_predictions_sha256": prepared.baselines_sha256,
                "selection_sha256": recorded_selections,
                "confirmatory_result_sha256": confirmatory_sha,
                "code_sha256": code_record(),
                "code_sha256_of_the_confirmatory_result": part_of(confirmatory, "inputs").get(
                    "code_sha256"
                ),
            },
            "sections": list(sections),
            "secondary_models_scored": models,
            "secondary_models_left_out": left_out,
            "secondary_models_left_out_check": left_out_check,
            "primaries_not_evaluable_by_declaration": skipped,
            "h3_comparator": prepared.study.comparator,
            "bootstrap": {
                "draws": ev.DRAWS,
                "draws_of_a_turnbull_estimate": SLIP_DRAWS,
                "seed": ev.SEED,
                "clusters": "shortage episodes",
            },
            "refit": prepared.study.refit,
            **results,
            "as_the_plan_says": list(AS_THE_PLAN_SAYS),
            "where_the_plan_is_silent": list(WHERE_THE_PLAN_IS_SILENT),
            "not_computed_here": {
                "computed_by_another_script": list(COMPUTED_BY_ANOTHER_SCRIPT),
                "computed_by_no_script": list(COMPUTED_BY_NO_SCRIPT),
                "if_no_script_computes_it": STILL_NOT_COMPUTED,
            },
        }
        # every text is made before a file exists: a stop here must leave nothing behind
        text, printed = ev.report_text(report), "\n".join(summary_lines(report))
        text.encode("utf-8")  # what cannot be written stops here too
    except Exception as error:
        stopped = type(error).__name__  # the error itself, and its message, go no further
    if stopped:
        ev.refuse(
            f"the scoring stopped on the sealed rows ({stopped}); the message is withheld "
            "because it may quote a sealed value"
        )
    write_result(out, text)
    return print_summary(out, [printed])


def of_the_descriptives(lines: Iterable[str]) -> list[str]:
    """The lines of a list carried in the result files that speak of the descriptives of E1:
    those that name E1 or a Turnbull estimate."""
    return [line for line in lines if "E1" in line or "Turnbull" in line]


def run_train(args: argparse.Namespace) -> int:
    kept_from_sealed_paths(
        argparse.Namespace(**vars(args), sealed=ev.SEALED), ("statements", "counts")
    )
    ev.open_paths(args, ("statements", "counts"))
    out = output_path(args.out, ev.SEALED)
    statements = sealed_counts.file_bytes(args.statements, "the statement table")
    counts = sealed_counts.file_bytes(args.counts, "the counts file")
    sha = sealed_counts.sha256(statements)
    ev.same_build(json.loads(counts), {"the statement table": sha})
    stopped = ""
    try:
        table = ev.table_of(statements, True)
        frame = P.prepare(table)  # stops at an outcome cell of a statement of the test period
        rows = P.fitting_rows(frame[frame["period"] == "train"])
        result = descriptives(rows, table.set_index("statement_group_id"), ev.DRAWS, SLIP_DRAWS)
    except Exception as error:
        stopped = type(error).__name__
    if stopped:
        ev.refuse(f"the statement table is not as the dataset builder writes it ({stopped})")
    report = {
        "about": ABOUT_TRAIN,
        "command": "PYTHONPATH=. python -m analysis.coling.secondary_scores train-descriptives "
        "--out <file>",
        "inputs": {
            "statements_sha256": sha,
            "dataset_counts_sha256": sealed_counts.sha256(counts),
            "code_sha256": code_record(),
        },
        "period": "train (fit and dev), outcomes followed to the train horizon",
        "bootstrap": {
            "draws": ev.DRAWS,
            "draws_of_a_turnbull_estimate": SLIP_DRAWS,
            "seed": ev.SEED,
            "clusters": "shortage episodes",
        },
        "descriptives": result,
        "as_the_plan_says": of_the_descriptives(AS_THE_PLAN_SAYS),
        "where_the_plan_is_silent": of_the_descriptives(WHERE_THE_PLAN_IS_SILENT),
    }
    text = ev.report_text(report)  # made, and encoded, before a file exists
    text.encode("utf-8")
    write_result(out, text)
    said = (
        f"train period: {result['statements']} statements at risk in {result['episodes']} "
        f"episodes; {result['dated_statements_not_stale']} dated and not stale"
    )
    return print_summary(out, [said])


def arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = sealed_counts.Parser(
        prog="python -m analysis.coling.secondary_scores",
        description=(__doc__ or "").splitlines()[0],
        allow_abbrev=False,
    )
    commands = ap.add_subparsers(dest="command", required=True, parser_class=sealed_counts.Parser)

    def common(sub: argparse.ArgumentParser, *names: str) -> None:
        options: dict[str, tuple[Any, str]] = {
            "statements": (dataset.STATEMENTS, "the open statement table"),
            "eligible": (dataset.ELIGIBLE, "the E3 eligible list"),
            "events": (dataset.EVENTS, "the open events table"),
            "counts": (dataset.COUNTS, "the counts file of the dataset builder"),
            "out-root": (lp.OUT_ROOT, "the output root of the reading runs"),
            "selections": (dataset.OUT, "the folder of the H3 selection files"),
        }
        for name in names:
            default, text = options[name]
            sub.add_argument(f"--{name}", type=Path, default=default, help=text)

    train = commands.add_parser(
        "train-descriptives", allow_abbrev=False, help="E1 on the train period; open data only"
    )
    train.add_argument("--out", type=Path, help="the result file to write; it must not exist")
    common(train, "statements", "counts")
    train.set_defaults(run=run_train)

    final = commands.add_parser("score", allow_abbrev=False, help="the secondary analyses")
    final.add_argument("--expect-sha256", help="sha256 of the sealed file")
    final.add_argument("--expect-eligible-sha256", help="sha256 of the eligible list")
    final.add_argument("--expect-baselines-sha256", help="sha256 the baselines command printed")
    final.add_argument(
        "--confirmatory", type=Path, help="the result file of evaluate.py confirmatory"
    )
    final.add_argument("--out", type=Path, help="the result file to write; it must not exist")
    final.add_argument("--sealed", type=Path, default=ev.SEALED, help="the sealed test outcomes")
    final.add_argument(
        "--expect-selection-sha256",
        action="append",
        default=[],
        metavar="MODEL=SHA256",
        help="sha256 of a primary's H3 selection file, as the freeze amendment records it",
    )
    final.add_argument(
        "--not-evaluable",
        action="append",
        default=[],
        metavar="MODEL=REASON",
        help="a primary the evaluator was told is not evaluable, with the same reason",
    )
    final.add_argument("--section", action="append", default=[], metavar="NAME")
    final.add_argument("--left-out", action="append", default=[], metavar="MODEL=REASON")
    common(final, "statements", "eligible", "events", "counts", "out-root", "selections")
    final.set_defaults(run=run_score)
    return ap.parse_args(None if argv is None else list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Run a command. Whatever stops it outside its own refusals is a refusal too, named by the
    type of the error alone: no traceback, and no message that may quote a stored row or a
    sealed value."""
    args = arguments(argv)
    stopped = ""
    try:
        return args.run(args)
    except Exception as error:
        stopped = type(error).__name__
    ev.refuse(
        f"the command stopped ({stopped}); the message is withheld because it may quote a stored "
        "row or a sealed value"
    )


if __name__ == "__main__":
    raise SystemExit(main())
