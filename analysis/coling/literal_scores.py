"""The scorer of two registered secondary experiments of the COLING 2027 study: E2 and E5.

E2 is the literal reading of the labelled statements against the adjudicated labels and against
the rule reader; E5 is the minimal pairs. PLAN.md sections 4 ("Parse failures"), 5 (E2 and E5),
7.1, 8, 9 and 13 (what its registered pattern reads of E2 and E5); AUDIT_GUIDE.md sections 3, 5
and 7.

Neither command reads an outcome of any period. The inputs are stored readings of the reading
harness, the gold of the task, the item file, and, for E2, the open events table (first-sight
fields) and the guide. Every output is a count, a share, an interval or a p-value; per item the
result file holds an id and flags (correct or not, parsed or not), never a text and never a
reading.

What is scored
--------------
A *reading* has a statement type, an interval or an abstention, a certainty class and a stale
flag. A stored row without a parsed answer (failed after its repair call, or refused) counts as
ABSTAIN (PLAN section 4): no interval, stale flag false, and no statement type and no certainty
class, so it is never right on those two. Failure and refusal rates are reported per model and
template, as the evaluator reports them.

The rule reader is ``rules.read`` on the statement text of the item (``corpus.statement_text``
of its two text fields, as the form classifier and the minimal-pair generator read it) at its
Date of update, mapped by ``rules.as_literal_v1``. HeidelTime and SUTime are disclosed as not
run (PLAN section 8); nothing is installed for them.

Metrics (PLAN section 7.1), each from sums over items (:func:`metrics`):

* statement-type accuracy;
* interval IoU in days, over the items whose gold gives an interval (a reader that abstains
  there scores 0); days are counted with both end days, so one day against the same day is 1;
* interval coverage: among the items whose gold gives an interval, the share where the reader
  gives one (the "coverage" PLAN section 8 asks of the rule reader, given for every reader);
* endpoint error of the start and of the end, in days, absolute and signed (reader minus
  gold), over the items where reader and gold both give an interval;
* abstention precision, recall and F1 (the positive class is "no date");
* false-commitment rate: the share of gold-ABSTAIN items where the reader gives an interval;
* stale-flag accuracy, precision, recall and F1 (the reader's own flag against the gold's);
* distractor uptake: among the gold items that carry a distractor date, the share where the
  reader's interval has IoU of at least 0.5 with a distractor's interval and below 0.5 with
  the gold interval (or the gold abstains). A distractor's interval is every time expression of
  its quoted words as ``rules.find_timexes`` reads it at the item's Date of update;
* certainty-class accuracy over all items, and Cohen's kappa over the parsed readings;
* ``correct``: the E2 rule (the statement type is the gold one, and both abstain or the IoU is
  at least 0.5); ``identical_interval``: the same start and end, or two abstentions (the
  guide's section 8.1), reported in addition;
* letter accuracy: among the letter items (the gold gives an interval and carries no
  distractor date), the share of readings that are ``correct``.

E2 (``e2``)
-----------
Readers: the eight models under ``literal-v1`` and under ``literal-free-v1`` (the lines
``e2-literal`` and ``e2-literal-free`` of the run sheet), the rule reader, and the two
annotators scored against each other (the literal ceiling of PLAN section 8, leave-one-out):
on every item both labelled (``literal_ceiling_on_every_labelled_item``), and on the gold
items of each item set (``literal_ceiling``), where the margins of the models over an
annotator need the items the models are scored on.

Strata and weights come from the open events table and the guide through the sampler's own
code (``audit_sample.load_inputs``): the stratum, the shortage episode and the masked template
of the statement behind each item id, and, per stratum, the number of statements and of
distinct templates in the frame without the statements the guide excludes. Results are given
per stratum of the guide's allocation table, which is "by form" in the literal task (PLAN
sections 2.6 and 5); pooled over the sample without weights; and weighted by event and by
template as PLAN section 7.1 defines the two weights: an item of stratum ``s`` weighs the
frame statements of ``s``, or its distinct masked templates, over the scored items of ``s``,
so that every scored item of a stratum counts the same. Intervals are 95% percentile intervals
over 10,000 draws of shortage episodes with seed 20261001; none is given per stratum. An item
must carry the date of its statement in the events table, and, when the sampler's key of the
sample is on disk (``--key``; ``keys/literal_key.csv`` under the folder of the task), the
stratum the key gives.

The registered test: for each primary, one exact two-sided McNemar test of the model under
``literal-v1`` against the rule reader on ``correct``, over the items outside the month-and-year
stratum, with Holm over the two at 0.05. The same counts are given for every other model and
template, per stratum and on the parsed readings alone, as descriptions. The figures of the
plan's "positive result" stand beside them, on the item sets the plan names (PLAN section 5,
E2): the lead in IoU over the rules on the part-of-month, no-year and range strata and on the
two distractor rows together (the lead runs over the items whose gold gives an interval), with
the lead on the relative stratum beside them; and false commitment against the 5% bar on the
gold-ABSTAIN items of the TBD and silent strata, with the rate over every gold-ABSTAIN item
beside it.

The letter reading (PLAN section 5, E2, "Test"; it is no third test of the family): the
difference between a model's letter accuracy and the rule reader's over the gold letter items
pooled without weights, with its 90% and its 95% percentile interval over the same draws
(``versus_rules``, under ``letter_accuracy`` and ``sample``; the registered one is that of a
primary under ``literal-v1`` on every gold item), and the same difference under the two
weightings beside it. What section 13 lists as support is given for every reader: the two
false-commitment rates and distractor uptake with their counts and their exact binomial
interval (``exact``) beside the percentile one, and the stale-flag scores. Beside them, the
difference of a model's false-commitment rates and distractor uptake from the rule reader's
(``margins``) and from each annotator's (``versus_ceiling``) is given with its 95% interval
over the same draws. Neither command applies the floors of the registered pattern of section
13 or decides its sentence: the two result files hold the quantities it reads.

Item sets. Everything is reported three times: on every gold item, which is the registered
family; without the items adjudicated as ``gap`` (AUDIT_GUIDE section 5); and without the
items whose reading rests on a convention the prompt does not state (D14 of the guide). The
ids of the last kind are read from the list that is fixed with the gold (PLAN section 5, E2,
"Gold"): ``literal_convention_items.csv`` under the folder of the task, one column ``item_id``
(one id per line; the header is skipped), held to ``--expect-convention-sha256``;
``--convention-items`` names the list when it lies elsewhere. The plan keeps a list in every
case, with its header alone when no item rests on such a convention: the third report is then
that of every gold item. Without the list nothing is scored.

E5 (``e5``)
-----------
Readers: seven models under ``literal-v1`` (the line ``e5``); the rule reader beside them as a
description. A reading of an edited item is an error when it is not ``correct``, or, for the
certainty factor, when its certainty class is wrong, or, for the stale factor, when its stale
flag is wrong. A reading of an unedited seed item is held to the criterion of the factor it is
compared with (PLAN section 5, E5, "Target"): the E2 rule, and in the contrast of the certainty
factor its certainty class too, in the contrast of the stale factor its stale flag too. So
each contrast has one definition of error on both of its sides.

The test is a logistic GEE of error on factor and model with their interaction, clustered by
seed, with the independence working correlation and the robust variance (:func:`gee`: the
logistic fit by Newton steps and the sandwich of the seed sums of the scores). Each unedited
seed item enters three times for each reader, once under each of the three criteria, in the
cluster of its seed (:func:`long_table`): a reader has a cell for each factor and three cells
for its seed items, ``seed`` (the E2 rule), ``seed|certainty`` and ``seed|stale``. A reader's
contrasts and their robust variances are those of that reader's rows alone, so the model is
fitted reader by reader, without the cells whose error rate is 0 or 1, which have no finite
coefficient; the intercept of a fit is the first seed cell that has one (``reference_cell``).
For each primary and each of the six factors, the contrast between the items edited on that
factor and the seed rows under that factor's criterion (``against``) is the difference of
their log odds; its Wald p-value is two-sided. When the robust variance of one of the twelve
cannot be computed (an error rate of 0 or 1 in a cell of a primary, a fit of a primary that
does not converge, or a contrast of a primary with no positive variance), all twelve tests
come from a cluster bootstrap over seeds (10,000 draws, seed 20261001) of the difference ``d``
of the two error rates, edited minus unedited (:func:`drawn_contrast`). Its p-value is
two-sided on the centred draws, ``(1 + #{|d* - d| >= |d|}) / (B + 1)``, with a draw that has
no item on one side left out; the percentile p-value stands beside it (``p_percentile``) and
enters no rule. The cells of the five other models never decide the procedure of the twelve.
Holm runs over the twelve at 0.05. The bootstrap is reported for every contrast; the Wald
result for every contrast whose two cells have error rates strictly between 0 and 1 and whose
robust variance is positive; ``p_from`` names the one a p-value comes from. A contrast is
not evaluable (p = 1) when the items of its factor, or the unedited seed items, lie on fewer
than two seeds; the seeds of each side are counted in ``seeds``. Error rates are given by factor, by level and by model, with an unedited item
under the E2 rule there and in ``per_item``; the three seed cells of each model are in
``seed_items``. The metrics of section 7.1 are given per model and factor. Items made from
test-period seeds are scored like the others, and counted.

For a standing factor (certainty marker, stale, distractor date, silent; PLAN section 13) a
contrast also holds what the standing part of the registered pattern reads beside the test:
the error rate on the items of the two letter factors (surface form, granularity) taken
together, under the criterion of the factor (``letter_factors``); the rate of the factor's own
error on the items of the factor on which it can occur (``own_error``: a period given where
the gold gives none, the distractor's period taken, a period given without the stale flag);
and the errors on the items of the factor that are of another kind
(``errors_of_another_kind``).

Refusals (status 1, the reason alone, nothing written)
------------------------------------------------------
No gold file (``e2`` compares nothing with the items of the literal task before their gold is
fixed); a gold file whose sha256 is not ``--expect-gold-sha256``; for ``e2``, a gold that is
not the one the manifest of the audit folder records, a folder with no manifest or a manifest
with no record of a gold, or a manifest there that cannot be read;
a ``rules.py`` that is not the frozen file; an output that exists; a plan, a run or a stored
row that the evaluator's own check of a line refuses (``evaluate.read_group``: a partial run,
another item set, another route, template or decoding); a plan, a manifest or a stored row
that cannot be read as the launcher and the harness write them (named by the type of the
error alone); a line planned under another template than the registered one; an item file
that is not the file the runs read; a gold that is not of the item file, or a table with a row
of more or fewer cells than its header; items that are not of the events table, or not in the
stratum of the key; no list of convention items; an input named in a sealed folder.
``--not-run MODEL=REASON`` (for ``e2`` also ``MODEL/TEMPLATE=REASON``) declares that a model's
runs, or its run under one template, could not be completed. They are checked like the others
and not scored, and what the check found is recorded (``not_run_checked``); a declaration for
runs that are complete and could be scored is a refusal. A primary whose ``literal-v1`` run is
declared keeps its tests in their family with p = 1. A refusal names runs and gives counts,
never an item.

The result file
---------------
``registered`` (seed, draws, level, lines, models, template pins); ``inputs`` (the sha256 of
every file read and of the code); ``runs`` (rows, statuses, failure and refusal rates per model
and template); ``not_run`` and ``not_run_checked``; ``where_the_plan_is_silent``; ``per_item``
(ids and flags). For E2 also ``gold``, ``frame``, ``literal_ceiling_on_every_labelled_item``
and ``item_sets``, each set with ``readers`` (per reader: ``n``, ``exact``, ``sample``,
``weighted_by_event``, ``weighted_by_template``, ``by_stratum``), ``tests``, ``versus_rules``
(with ``letter_accuracy`` and ``margins``), ``literal_v1_versus_literal_free_v1``,
``positive_result``, ``literal_ceiling`` and ``versus_ceiling``. For E5 also ``errors``,
``rule_reader``, ``seed_items`` (per model, the parts of the error on the unedited items and
their error rate in each of the three seed ``cells``), ``metrics``, ``gee``, ``tests`` (the
twelve, each with the seed rows it is ``against``, with both p-values of its ``bootstrap``,
and, for a standing factor, with ``letter_factors``, ``own_error`` and
``errors_of_another_kind``) and ``other_models``. A float has
six decimals; ``p``, ``p_holm`` and ``p_percentile``, wherever they stand, have six
significant digits, so that a small p-value does not read 0; ``holds`` is decided before any
rounding.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.literal_scores e2 \\
        --expect-gold-sha256 <sha256 of the gold, as the manifest of the audit folder records it> \\
        --expect-convention-sha256 <sha256 of the list> [--convention-items FILE] \\
        [--audit-dir analysis/coling/out/audit] [--gold FILE] [--items FILE] [--key FILE] \\
        [--events analysis/coling/out/events.csv.gz] [--guide analysis/coling/plan/AUDIT_GUIDE.md] \\
        [--out-root analysis/coling/out/read] [--not-run MODEL[/TEMPLATE]=REASON ...] \\
        --out analysis/coling/out/e2_scores.json
    PYTHONPATH=. python -m analysis.coling.literal_scores e5 \\
        --expect-gold-sha256 <sha256 of external_data/annotation/keys/e5_gold.csv> \\
        [--gold FILE] [--items analysis/coling/out/e5/e5_pairs.jsonl] \\
        [--out-root analysis/coling/out/read] [--not-run MODEL=REASON ...] \\
        --out analysis/coling/out/e5_scores.json

``--items`` is the registered item file (for E2, ``literal_items.jsonl`` under the folder of the
task): the runs must have read a file with exactly its bytes (the sha256 the launcher's plan
holds for the list), whatever its path. Each command writes its result file, which must not
exist, and prints a short table.
    PYTHONPATH=. python -m pytest analysis/coling/test_literal_scores.py -q -p no:cacheprovider
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zlib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from scipy import special, stats

from analysis.coling import audit_agreement as A
from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import evaluate as ev
from analysis.coling import forms as F
from analysis.coling import launch as lp
from analysis.coling import minimal_pairs as MP
from analysis.coling import predictors as P
from analysis.coling import read as rd
from analysis.coling import rules as R
from analysis.coling import sealed_counts

SEED = P.SEED
DRAWS = P.DRAWS
ALPHA = 0.05
"""The familywise level of each secondary family (two tests in E2, twelve in E5)."""
IOU_CORRECT = 0.5
"""A reading's interval is right when its IoU with the gold interval reaches this."""
IOU_LEAD = 0.15
FALSE_COMMITMENT_BAR = 0.05
"""The two thresholds of the plan's "positive result" of E2; they decide no test."""
PRIMARIES = rd.PRIMARIES
PHASE = "rest"
"""The phase of the launcher's plan that holds the runs of E2 and E5."""
E2_LINES = {"literal-v1": "e2-literal", "literal-free-v1": "e2-literal-free"}
"""The registered templates of E2 and the line of the run sheet that reads each."""
E2_TEMPLATE = "literal-v1"
"""The template of the registered test of E2."""
E2_MODELS = rd.STUDY_MODELS
E5_LINE, E5_TEMPLATE = "e5", "literal-v1"
E5_MODELS = tuple(m for m in rd.STUDY_MODELS if m != "gemini-3.8-flash")
LISTS = {"e2": "e2", "e5": "e5"}
"""The launcher's keys of the two item lists."""
RULES = "rules"
MONTH_YEAR = "month_year"
TBD_OR_SILENT = ("tbd", "silent")
LEAD_STRATA = ("part_of_month", "month_no_year", "range")
"""The three strata on which the plan's positive result expects the models to lead the rules
in IoU by ``IOU_LEAD`` (PLAN section 5, E2)."""
DISTRACTOR_STRATA = ("dated_distractor", "distractor")
DISTRACTOR_ROWS = "distractor_rows"
"""The fourth place of that lead: the two distractor rows of the guide's table together, which
is the stratum of dated targets beside a distractor date with the distractor-only items whose
gold gives an interval, since a lead runs over the items whose gold gives one."""
BESIDE_THE_LEAD = ("relative",)
"""The stratum whose lead the plan reports beside the three; it is no part of the bar."""
MARGIN_METRICS = ("false_commitment", "false_commitment_tbd_or_silent", "distractor_uptake")
"""The metrics whose difference from a comparator's is given with an interval (section 13)."""
RATE_COLUMNS = {
    "false_commitment": ("false_commitment", "gold_abstains"),
    "false_commitment_tbd_or_silent": ("marked_false_commitment", "marked_gold_abstains"),
    "distractor_uptake": ("uptake", "has_distractor"),
}
"""The same metrics as two columns of :func:`columns`, the items counted above and below the
line: section 13 asks for their counts and for an exact binomial interval."""
SEED_FACTOR = MP.SEED_FACTOR
FACTORS = MP.FACTORS
OWN_FIELD = {"certainty": "certainty_wrong", "stale": "stale_wrong"}
"""The two factors of E5 whose error has a part beside the E2 rule, and that part (PLAN section
5, E5, "Target")."""
SEED_ROWS = {factor: f"{SEED_FACTOR}|{factor}" for factor in OWN_FIELD}
"""The level under which the unedited seed items stand a second and a third time in the model
of E5: held to the criterion of the certainty factor, and to that of the stale factor."""
SEED_CELLS = (SEED_FACTOR, *SEED_ROWS.values())
"""The three cells of the unedited seed items of a reader: under the E2 rule, and under each
of those two criteria."""
LETTER_FACTORS = ("surface_form", "granularity")
"""The two letter factors of E5: the edit rewrites the period or changes the period itself
(PLAN section 13, "Terms"). The four other factors are the standing factors."""
STANDING_FACTORS = tuple(factor for factor in FACTORS if factor not in LETTER_FACTORS)
OWN_ERROR = {
    "certainty": ("false_commitment", "gold_abstains"),
    "silent": ("false_commitment", "gold_abstains"),
    "distractor": ("uptake", "has_distractor"),
    "stale": ("unflagged", "gold_stale"),
}
"""The own error of each standing factor (PLAN section 13, the standing part, (c)) as two
columns of :func:`columns`: where it occurs, and where it can occur. A period given where the
gold gives none; the distractor's period taken; a period given without the stale flag."""
STATEMENT_TYPES = rd.STATEMENT_TYPES
CERTAINTY = rd.CERTAINTY_CLASSES
ABSTAIN = "ABSTAIN"
"""What the answer schema holds in the place of an interval when the reading gives none."""
DECISIONS = ("agree", *A.DECISIONS)
GAP = "gap"
ANNOTATORS = S.ANNOTATORS
NORMALISERS_NOT_RUN = {
    "HeidelTime": "disclosed as not run (PLAN section 8): not installed",
    "SUTime": "disclosed as not run (PLAN section 8): not installed",
}
GEE_TOLERANCE = 1e-10
GEE_STEPS = 100
"""The Newton steps of the GEE stop when no coefficient moves by more than the tolerance; a fit
that needs more steps than this has not converged."""
GEE_VARIANCE_FLOOR = 1e-10
"""A robust variance of a contrast at or below this is the rounding of a variance of zero (two
cells with the same errors seed by seed), and the contrast then has no Wald test."""
E2_ITEMS, E2_KEY = "literal_items.jsonl", "literal_key.csv"
E2_CONVENTION_ITEMS = "literal_convention_items.csv"
"""The list of the gold items whose reading rests on a convention the prompt does not state,
under the folder of the task unless ``--convention-items`` names another file."""
E5_ITEMS = MP.OUT / MP.ITEMS_FILE
E5_GOLD = MP.KEYS / MP.GOLD_FILE
ABOUT_E2 = (
    "E2 of PLAN.md: literal readings of the labelled statements against the adjudicated gold "
    "and against the rule reader. No outcome is read; per item, ids and flags only."
)
ABOUT_E5 = (
    "E5 of PLAN.md: errors of literal readings on the minimal pairs, the GEE of error on factor "
    "and model, and twelve tests under Holm. No outcome is read; per item, ids and flags only."
)
WHERE_THE_PLAN_IS_SILENT = (
    "a reading that failed or was refused, an abstention by section 4, has the stale flag "
    "false, no statement type and no certainty class: it is wrong on both and never correct "
    "by the E2 rule; Cohen's kappa of the certainty class runs over the parsed readings",
    "IoU counts days with both end days; it is defined where the gold gives an interval, and a "
    "reader that abstains there scores 0; endpoint errors run over the items where reader and "
    "gold both give an interval, as the mean absolute and the mean signed difference",
    "the quoted words of a distractor may hold several time expressions: each one that the "
    "rule reader finds there, at the item's Date of update, is an interval of the distractor, "
    "and uptake is counted against any of them; a gold item carries a distractor date when "
    "one of its quotes gives an interval",
    "the intervals of E2 are percentile intervals over the 10,000 draws of shortage episodes "
    "with seed 20261001: for every metric and under each weighting the 95% one that section 6 "
    "keeps for the secondaries, with the weight of an item fixed over the draws; a statement "
    "with no episode is a cluster of its generic, as in the sampler; no interval is given per "
    "stratum",
    "the frame of the two weights of section 7.1 is counted by the sampler's code on the "
    "events table given; a stratum with no scored item gives its frame no weight, so a weighted "
    "figure of an item set that empties a stratum describes the other strata",
    "with two annotators the leave-one-out ceiling of section 8 is each annotator scored "
    "against the other one's labels, with the same metrics, on every item both labelled; the "
    "same on the gold items of each item set stands in that set, because the margins of the "
    "models over an annotator need the items the models are scored on; an annotator's letter "
    "accuracy is read on the letter items of the gold, by the E2 rule against the other one's "
    "label",
    "the list of convention items is held to a sha256 given on the command line, the audit "
    "manifest having no record of it; a line of the list that starts with # is skipped, and "
    "so are quotes around an id; an item set with no gold item left is named as not computed; "
    "the tests on each of the two other item sets carry a Holm of their own, as descriptions",
    "the exact McNemar test is two-sided: twice the smaller binomial tail of the discordant "
    "pairs at one half, at most 1, and 1 with no discordant pair; the sensitivity analysis of "
    "section 4 is the same test on the registered pooling, with a p-value outside Holm's rule",
    "a run declared not run (a model, or for E2 one template of a model) is checked like the "
    "others and not scored; a primary whose literal-v1 run is declared not run keeps its tests "
    "in the family with p = 1; a declaration for runs that are complete on the registered item "
    "list, route and template is refused",
    "the rule reading of an item is made here, by the frozen rules.py at the item's Date of "
    "update, from the statement text that the corpus code builds of the two text fields of "
    "the item file, and is put into the answer schema of literal-v1 by the rule reader's own "
    "mapping",
    "the two bars of the positive result (0.15 IoU, 5% false commitment) are read on the "
    "sample figures, model by model, the lead on each of its four places apart (three strata, "
    "and the two distractor rows together); the lead is also given for each distractor row "
    "alone and over the gold items with a distractor date whatever their stratum, as "
    "descriptions",
    "the letter reading of E2 is given for every model and template and on each item set, with "
    "the same difference under the two weightings beside it; its 90% interval runs from the "
    "5th to the 95th percentile of the difference over the draws that hold a letter item",
    "E5: the GEE is the logistic fit with the sandwich of the seed sums of the scores, with no "
    "small-sample factor; the contrast of a factor is the difference of the log odds of error "
    "between its items and the seed rows under its criterion, in the same model; Wald p-values "
    "are two-sided normal ones",
    "E5: the GEE is fitted reader by reader, without the cells whose error rate is 0 or 1 "
    "(such a cell has no finite coefficient), so that a contrast whose two cells have one "
    "keeps its Wald result on display when the twelve come from the bootstrap; the three sets "
    "of seed rows of a reader are three cells; a robust variance of 1e-10 or less counts as "
    "zero; in both bootstrap p-values B is the number of draws that hold an item on each side; "
    "a contrast of one of the five other models takes its own Wald p-value where it has one, "
    "whatever the procedure of the twelve, and the centred bootstrap p-value where it has "
    "none, as a description",
    "E5: a test that is not evaluable keeps its place in the family with p = 1: one with no "
    "item of its factor or no unedited seed item, and one whose edited items, or whose "
    "unedited items, lie on fewer than two seeds; the seeds of a contrast are counted on each "
    "of its sides, since a side on one seed is the same in every draw that holds it, and the "
    "two counts stand with the test",
    "E5: the metrics of section 7.1 are given per model, with intervals from draws of seeds, "
    "and per model and factor without, all unweighted; the pairs have no frame to weigh by",
    "E5: the own error of the stale factor (section 13) is a reading that gives a period "
    "without the stale flag, counted over the items of the factor whose gold is stale; the "
    "own errors, and the error rate on the items of the two letter factors together under "
    "the criterion of a standing factor, are given for every model, outside the family",
    "E5: the gold of the minimal pairs is held to the sha256 given on the command line and, "
    "row by row, to the seed, the factor and the level of the item file; the manifest of the "
    "generator is not read",
    "the coverage of the rule reader per form (section 8) is, among the items of a stratum "
    "whose gold gives an interval, the share on which the reader gives one; it is given for "
    "every reader; the sample is drawn on the rule reader's own form classes, so its figure "
    "per stratum says little, and the pooled and weighted figures are the informative ones",
    "beside the rates that section 13 lists as support, the scorer gives the difference of a "
    "model's figure and a comparator's (the rule reader's, or an annotator's against the other "
    "one's labels) for false commitment (on every gold-ABSTAIN item, and on those of the TBD "
    "and silent strata) and for distractor uptake, under each weighting, with a 95% percentile "
    "interval over the same draws of episodes; each of the two readers is scored on its own "
    "denominator and the two are paired by the draw alone; on the TBD and silent strata the "
    "rule reader abstains by construction, so that margin over the rules is the model's own "
    "rate; the exact binomial interval of those rates is the Clopper-Pearson one at 95%, on "
    "the unweighted counts of the sample",
)

P_FIELDS = ("p", "p_holm", "p_percentile")
"""The fields of a result file that hold a p-value: they keep six significant digits."""


def report_text(report: Mapping[str, Any]) -> str:
    """A result file as JSON, as the evaluator writes one (floats at six decimals; a number
    that is not finite is null), except that a p-value keeps six significant digits: an exact
    McNemar or a Wald p-value below 5e-7 would read 0.0 at six decimals."""

    def held(value: Any, key: Any = None) -> Any:
        if isinstance(value, Mapping):
            return {name: held(item, name) for name, item in value.items()}
        if isinstance(value, list | tuple):
            return [held(item) for item in value]
        if isinstance(value, float | np.floating):
            if not np.isfinite(value):
                return None
            return float(f"{float(value):.6g}") if key in P_FIELDS else round(float(value), 6)
        if isinstance(value, np.integer):
            return int(value)
        return value

    return json.dumps(held(report), indent=1, ensure_ascii=False, allow_nan=False) + "\n"


refuse = ev.refuse
holm = ev.holm


# --------------------------------------------------------------------------------------------
# Readings and gold
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """A literal reading in the fields that are scored."""

    statement_type: str | None
    interval: tuple[date, date] | None
    certainty: str | None
    stale: bool
    parsed: bool = True


NO_ANSWER = Reading(None, None, None, False, parsed=False)
"""What stands for a reading that failed after its repair call or was refused: ABSTAIN."""


@dataclass(frozen=True)
class Gold:
    """The gold of one item: its reading, and the intervals of its distractor dates."""

    item_id: str
    reading: Reading
    abstain_reason: str = ""
    distractors: tuple[tuple[date, date], ...] = ()
    roles: int = 0
    decision: str = ""
    hard: bool = False


def span_days(span: tuple[date, date]) -> int:
    """The days of an interval, both end days counted."""
    return (span[1] - span[0]).days + 1


def iou(first: tuple[date, date], second: tuple[date, date]) -> float:
    """Intersection over union of two intervals, in days."""
    shared = (min(first[1], second[1]) - max(first[0], second[0])).days + 1
    shared = max(0, shared)
    return shared / (span_days(first) + span_days(second) - shared)


def distractor_intervals(quotes: Iterable[str], anchor: date) -> tuple[tuple[date, date], ...]:
    """The interval of every time expression in the quoted words of the distractors, read by
    the frozen conventions (``rules.find_timexes``) at the item's Date of update."""
    found = []
    for quote in quotes:
        for timex in R.find_timexes(R.normalise(quote), anchor):
            start, end = (date.fromisoformat(day) for day in timex.interval)
            found.append((start, end))
    return tuple(found)


def stored_reading(row: Mapping[str, Any]) -> Reading:
    """The reading of a stored row of the harness; a row without a parsed answer is ABSTAIN.
    A stored answer is held to the answer schema in the four fields that are scored: a
    statement type and a certainty class of the schema, a stale flag that is true or false,
    and an interval that is ``ABSTAIN`` or a period that does not end before it starts. Raises
    ValueError, without quoting a cell, when one of them is something else."""
    answer = row.get("reading")
    if answer is None:
        return NO_ANSWER
    kind, certainty, stale, given = (
        answer[name] for name in ("statement_type", "certainty", "stale", "interval")
    )
    if kind not in STATEMENT_TYPES or certainty not in CERTAINTY:
        raise ValueError("a statement type or a certainty class outside the answer schema")
    if not isinstance(stale, bool):
        raise ValueError("a stale flag that is not true or false")
    span = None
    if isinstance(given, Mapping):
        span = (date.fromisoformat(given["start"]), date.fromisoformat(given["end"]))
        if span[0] > span[1]:
            raise ValueError("an interval that ends before it starts")
    elif given != ABSTAIN:
        raise ValueError("an interval that is neither a period nor an abstention")
    return Reading(kind, span, certainty, stale)


def item_anchor(item: Mapping[str, Any]) -> date:
    return rd.parse_date(item["date_of_update"])


def rule_reading(item: Mapping[str, Any]) -> Reading:
    """The frozen rule reading of an item, in the answer schema of ``literal-v1``."""
    text = C.statement_text(
        str(item.get("availability_information") or ""), str(item.get("related_information") or "")
    )
    literal = R.as_literal_v1(R.read(text, item_anchor(item)))
    given = literal["interval"]
    span = None
    if isinstance(given, Mapping):
        span = (date.fromisoformat(given["start"]), date.fromisoformat(given["end"]))
    return Reading(literal["statement_type"], span, literal["certainty"], bool(literal["stale"]))


def gold_of(item_id: str, cells: Mapping[str, str], anchor: date, stale: str | None = None) -> Gold:
    """The gold of one row of a gold file (the entered columns of AUDIT_GUIDE section 3.4,
    dates in full). ``stale`` is the file's own flag where it has one (the minimal pairs);
    otherwise the flag is derived from the interval and the anchor. Raises ValueError, without
    quoting a cell, when the row cannot be a gold row."""
    get = {name: (cells.get(name) or "").strip() for name in cells}
    kind, certainty = get.get("statement_type", ""), get.get("certainty", "")
    if kind not in STATEMENT_TYPES or certainty not in CERTAINTY:
        raise ValueError("a statement type or a certainty class outside the answer schema")
    if get.get("abstain") not in ("0", "1") or stale not in (None, "0", "1"):
        raise ValueError("an abstain or stale cell that is not 0 or 1")
    days = [date.fromisoformat(get[name]) for name in ("start", "end") if get.get(name)]
    if (get["abstain"] == "1") != (not days) or len(days) == 1:
        raise ValueError("dates that contradict the abstain cell")
    span = (days[0], days[1]) if days else None
    if span is not None and span[0] > span[1]:
        raise ValueError("an interval that ends before it starts")
    late = bool(span and span[1] < anchor) if stale is None else stale == "1"
    quotes = S.split_list(get.get("distractor_quotes", ""))
    return Gold(
        item_id=item_id,
        reading=Reading(kind, span, certainty, late),
        abstain_reason=get.get("abstain_reason", ""),
        distractors=distractor_intervals(quotes, anchor),
        roles=len(S.split_list(get.get("distractor_roles", ""))),
        decision=get.get("adj_decision", ""),
        hard=get.get("hard") == "1",
    )


def label_gold(label: S.Label) -> Gold:
    """An annotator's label as the gold another reader is scored against."""
    anchor = label.anchor or date.min
    return Gold(
        item_id=label.item_id,
        reading=label_reading(label),
        abstain_reason=label.abstain_reason,
        distractors=distractor_intervals(label.distractor_quotes, anchor),
        roles=len(label.distractor_roles),
    )


def label_reading(label: S.Label) -> Reading:
    return Reading(label.statement_type, label.interval, label.certainty, label.stale)


# --------------------------------------------------------------------------------------------
# Item-level columns and the metrics of section 7.1
# --------------------------------------------------------------------------------------------


def letter_item(gold: Gold) -> bool:
    """Whether a gold item is a letter item (PLAN sections 7.1 and 13): its gold gives an
    interval and carries no distractor date."""
    return gold.reading.interval is not None and not gold.distractors


def columns(
    readings: Sequence[Reading],
    golds: Sequence[Gold],
    marked: Sequence[bool] | None = None,
    letter: Sequence[bool] | None = None,
) -> dict[str, np.ndarray]:
    """One number per item for everything the metrics sum. ``marked`` says which items belong
    to the TBD and silent strata (none when it is not given). ``letter`` says which items are
    letter items; when it is not given they are those of ``golds`` (:func:`letter_item`), and
    it is given where ``golds`` holds other labels than the gold (an annotator's)."""
    n = len(golds)
    marked = [False] * n if marked is None else list(marked)
    letter = [letter_item(gold) for gold in golds] if letter is None else list(letter)
    out = {
        name: np.zeros(n)
        for name in (
            "one",
            "parsed",
            "type_ok",
            "reader_abstains",
            "gold_abstains",
            "both_abstain",
            "gold_dated",
            "both_dated",
            "iou",
            "start_error",
            "end_error",
            "start_error_abs",
            "end_error_abs",
            "identical",
            "correct",
            "letter",
            "letter_correct",
            "false_commitment",
            "marked_gold_abstains",
            "marked_false_commitment",
            "reader_stale",
            "gold_stale",
            "both_stale",
            "stale_ok",
            "unflagged",
            "has_distractor",
            "uptake",
            "certainty_ok",
            "certainty_ok_parsed",
            *(f"reader_{c}" for c in CERTAINTY),
            *(f"gold_{c}" for c in CERTAINTY),
        )
    }
    for i, (reading, gold) in enumerate(zip(readings, golds, strict=True)):
        mine, theirs = reading.interval, gold.reading.interval
        overlap = iou(mine, theirs) if mine and theirs else 0.0
        type_ok = reading.statement_type == gold.reading.statement_type
        out["one"][i] = 1
        out["parsed"][i] = reading.parsed
        out["type_ok"][i] = type_ok
        out["reader_abstains"][i] = mine is None
        out["gold_abstains"][i] = theirs is None
        out["both_abstain"][i] = mine is None and theirs is None
        out["gold_dated"][i] = theirs is not None
        out["iou"][i] = overlap
        if mine and theirs:
            out["both_dated"][i] = 1
            out["start_error"][i] = (mine[0] - theirs[0]).days
            out["end_error"][i] = (mine[1] - theirs[1]).days
            out["start_error_abs"][i] = abs((mine[0] - theirs[0]).days)
            out["end_error_abs"][i] = abs((mine[1] - theirs[1]).days)
        out["identical"][i] = mine == theirs
        agree = (mine is None and theirs is None) or overlap >= IOU_CORRECT
        out["correct"][i] = type_ok and agree
        out["letter"][i] = letter[i]
        out["letter_correct"][i] = letter[i] and type_ok and agree
        committed = theirs is None and mine is not None
        out["false_commitment"][i] = committed
        out["marked_gold_abstains"][i] = theirs is None and marked[i]
        out["marked_false_commitment"][i] = committed and marked[i]
        out["reader_stale"][i] = reading.stale
        out["gold_stale"][i] = gold.reading.stale
        out["both_stale"][i] = reading.stale and gold.reading.stale
        out["stale_ok"][i] = reading.stale == gold.reading.stale
        out["unflagged"][i] = gold.reading.stale and mine is not None and not reading.stale
        if gold.distractors:
            out["has_distractor"][i] = 1
            taken = mine is not None and max(iou(mine, d) for d in gold.distractors) >= IOU_CORRECT
            out["uptake"][i] = taken and (theirs is None or overlap < IOU_CORRECT)
        same = reading.certainty == gold.reading.certainty
        out["certainty_ok"][i] = same
        if reading.parsed:
            out["certainty_ok_parsed"][i] = same
            out[f"reader_{reading.certainty}"][i] = 1
            out[f"gold_{gold.reading.certainty}"][i] = 1
    return out


def _share(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """``numerator / denominator``; not a number where the denominator is not positive."""
    safe = np.where(denominator > 0, denominator, 1.0)
    return np.where(denominator > 0, numerator / safe, np.nan)


def metrics(cols: Mapping[str, np.ndarray], weights: Any) -> dict[str, np.ndarray]:
    """The metrics of section 7.1 from weighted sums over items. ``weights`` holds one row of
    item weights for each estimate wanted (the items as they are, or bootstrap draws); every
    metric comes back with one value per row, not a number where it is undefined."""
    weights = np.atleast_2d(np.asarray(weights, dtype=float))
    total = {name: weights @ column for name, column in cols.items()}
    n, parsed = total["one"], total["parsed"]
    out = {
        "correct": _share(total["correct"], n),
        "statement_type_accuracy": _share(total["type_ok"], n),
        "interval_iou": _share(total["iou"], total["gold_dated"]),
        "interval_coverage": _share(total["both_dated"], total["gold_dated"]),
        "identical_interval": _share(total["identical"], n),
        "start_error_days": _share(total["start_error_abs"], total["both_dated"]),
        "end_error_days": _share(total["end_error_abs"], total["both_dated"]),
        "start_error_signed_days": _share(total["start_error"], total["both_dated"]),
        "end_error_signed_days": _share(total["end_error"], total["both_dated"]),
        "abstention_precision": _share(total["both_abstain"], total["reader_abstains"]),
        "abstention_recall": _share(total["both_abstain"], total["gold_abstains"]),
        "abstention_f1": _share(
            2 * total["both_abstain"], total["reader_abstains"] + total["gold_abstains"]
        ),
        "false_commitment": _share(total["false_commitment"], total["gold_abstains"]),
        "false_commitment_tbd_or_silent": _share(
            total["marked_false_commitment"], total["marked_gold_abstains"]
        ),
        "stale_accuracy": _share(total["stale_ok"], n),
        "stale_precision": _share(total["both_stale"], total["reader_stale"]),
        "stale_recall": _share(total["both_stale"], total["gold_stale"]),
        "stale_f1": _share(2 * total["both_stale"], total["reader_stale"] + total["gold_stale"]),
        "distractor_uptake": _share(total["uptake"], total["has_distractor"]),
        "certainty_accuracy": _share(total["certainty_ok"], n),
        "letter_accuracy": _share(total["letter_correct"], total["letter"]),
    }
    observed = _share(total["certainty_ok_parsed"], parsed)
    chance = sum(
        _share(total[f"reader_{c}"], parsed) * _share(total[f"gold_{c}"], parsed) for c in CERTAINTY
    )
    rest = np.where(chance < 1, 1 - chance, 1.0)
    out["certainty_kappa"] = np.where(chance < 1, (observed - chance) / rest, np.nan)
    return out


METRICS = (
    "correct",
    "statement_type_accuracy",
    "interval_iou",
    "interval_coverage",
    "identical_interval",
    "start_error_days",
    "end_error_days",
    "start_error_signed_days",
    "end_error_signed_days",
    "abstention_precision",
    "abstention_recall",
    "abstention_f1",
    "false_commitment",
    "false_commitment_tbd_or_silent",
    "stale_accuracy",
    "stale_precision",
    "stale_recall",
    "stale_f1",
    "distractor_uptake",
    "certainty_accuracy",
    "certainty_kappa",
    "letter_accuracy",
)
COUNTED = {
    "items": "one",
    "parsed": "parsed",
    "gold_interval": "gold_dated",
    "gold_abstain": "gold_abstains",
    "reader_abstain": "reader_abstains",
    "both_interval": "both_dated",
    "gold_stale": "gold_stale",
    "reader_stale": "reader_stale",
    "gold_with_distractor_date": "has_distractor",
    "gold_abstain_tbd_or_silent": "marked_gold_abstains",
    "letter_items": "letter",
}
"""The denominators of the metrics, reported as plain counts beside them."""


def number(value: Any) -> float | None:
    """A float of a result file; None where the value is undefined."""
    value = float(value)
    return value if np.isfinite(value) else None


def counts(cols: Mapping[str, np.ndarray], keep: Any = None) -> dict[str, int]:
    keep = np.ones(len(cols["one"]), dtype=bool) if keep is None else np.asarray(keep, dtype=bool)
    return {name: int(cols[column][keep].sum()) for name, column in COUNTED.items()}


def values(cols: Mapping[str, np.ndarray], weights: Any) -> dict[str, float | None]:
    """The metrics for one row of item weights, as numbers of a result file."""
    return {name: number(found[0]) for name, found in metrics(cols, weights).items()}


def interval95(
    draws: np.ndarray, ends: tuple[float, float] = (0.025, 0.975)
) -> dict[str, Any] | None:
    """The 95% percentile interval of a bootstrap distribution over the draws on which the
    statistic is defined, with their number; None when it is defined on none. ``ends`` are the
    two quantiles the interval runs between."""
    kept = np.asarray(draws, dtype=float)
    kept = kept[np.isfinite(kept)]
    if not len(kept):
        return None
    low, high = np.quantile(kept, list(ends))
    return {"low": float(low), "high": float(high), "draws": len(kept)}


def interval90(draws: np.ndarray) -> dict[str, Any] | None:
    """The 90% percentile interval, from the 5th to the 95th percentile: the interval that the
    letter part of the registered pattern reads (PLAN section 13)."""
    return interval95(draws, (0.05, 0.95))


def exact95(count: int, items: int) -> dict[str, float] | None:
    """The exact (Clopper-Pearson) 95% interval of a share of ``count`` in ``items``; None
    when there is no item."""
    if not items:
        return None
    low = 0.0 if count == 0 else float(stats.beta.ppf(0.025, count, items - count + 1))
    high = 1.0 if count == items else float(stats.beta.ppf(0.975, count + 1, items - count))
    return {"low": low, "high": high}


def exact_rates(cols: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """The rates of ``RATE_COLUMNS`` on the items as they are, without weights: the count, the
    items it is counted on, and the exact 95% interval of the share."""
    out = {}
    for name, (above, below) in RATE_COLUMNS.items():
        count, items = int(cols[above].sum()), int(cols[below].sum())
        out[name] = {"count": count, "items": items, "ci95": exact95(count, items)}
    return out


def cluster_codes(clusters: Sequence[str]) -> tuple[np.ndarray, int]:
    """Each item's cluster as its place among the sorted cluster ids, and their number."""
    names = sorted(set(clusters))
    if "" in names:
        raise ValueError("an item has no cluster")
    place = {name: k for k, name in enumerate(names)}
    return np.array([place[c] for c in clusters], dtype=int), len(names)


def item_draws(clusters: Sequence[str], draws: int | None = None, seed: int = SEED) -> np.ndarray:
    """How often each item is taken in each bootstrap draw of its clusters (draws by items),
    from the draws of ``predictors.cluster_draws`` over the sorted cluster ids."""
    codes, groups = cluster_codes(clusters)
    taken = P.cluster_draws(groups, DRAWS if draws is None else draws, seed)
    return taken[:, codes].astype(float)


def estimates(
    cols: Mapping[str, np.ndarray], base: np.ndarray, taken: np.ndarray
) -> dict[str, dict[str, Any]]:
    """Every metric under one weighting of the items: its value and its 95% interval."""
    point = metrics(cols, base)
    drawn = metrics(cols, taken * base[None, :])
    return {
        name: {"value": number(point[name][0]), "ci95": interval95(drawn[name])} for name in METRICS
    }


def mcnemar(first: Any, second: Any) -> dict[str, Any]:
    """The exact two-sided McNemar test of two readers' correctness on the same items: twice
    the smaller binomial tail of the discordant pairs at one half, at most 1."""
    a, b = np.asarray(first, dtype=bool), np.asarray(second, dtype=bool)
    only_first, only_second = int((a & ~b).sum()), int((~a & b).sum())
    discordant = only_first + only_second
    p = 1.0
    if discordant:
        tail = stats.binom.cdf(min(only_first, only_second), discordant, 0.5)
        p = float(min(1.0, 2 * tail))
    return {
        "items": len(a),
        "first_correct": int(a.sum()),
        "second_correct": int(b.sum()),
        "both_correct": int((a & b).sum()),
        "neither_correct": int((~a & ~b).sum()),
        "only_first_correct": only_first,
        "only_second_correct": only_second,
        "p": p,
    }


# --------------------------------------------------------------------------------------------
# Files, hashes and the stored runs
# --------------------------------------------------------------------------------------------


def read_jsonl(data: bytes, what: str) -> list[dict[str, Any]]:
    """The rows of an item file; each needs an id and a Date of update."""
    stopped = ""
    rows: list[dict[str, Any]] = []
    try:
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        for row in rows:
            item_anchor(row)
            if not isinstance(row["item_id"], str) or not row["item_id"]:
                raise TypeError("an item id that is not a text")
    except (ValueError, KeyError, TypeError) as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"{what} is not an item file of the reading harness ({stopped})")
    if len({row["item_id"] for row in rows}) != len(rows) or not rows:
        refuse(f"{what} is empty or holds an item twice")
    return rows


def read_table(data: bytes, needed: Sequence[str], what: str) -> list[dict[str, str]]:
    """The rows of a CSV read by code; refused when a column is missing or a row has more or
    fewer cells than the header."""
    stopped = ""
    rows: list[dict[str, str]] = []
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    except (ValueError, csv.Error) as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"{what} cannot be read as a table ({stopped})")
    missing = [name for name in needed if rows and name not in rows[0]]
    if missing or not rows:
        refuse(f"{what} has no rows or lacks the columns {missing}")
    ragged = sum(1 for row in rows if None in row or None in row.values())
    if ragged:
        refuse(f"{what} has {ragged} rows with more or fewer cells than its header")
    return rows


def gold_bytes(path: Path, expected: str | None, flag: str, what: str, why: str) -> bytes:
    """The bytes of a gold file behind its hash. Refused, in this order: when the file is not
    there, when no hash was given, and when the file is not the one of the hash."""
    if not path.is_file():
        refuse(f"{what} is not there ({path.as_posix()}): {why}")
    wanted = sealed_counts.expected_hash(expected, flag)
    data = sealed_counts.file_bytes(path, what)
    sealed_counts.require_hash(data, wanted, what)
    return data


def declared(
    pairs: Sequence[str], models: Sequence[str], templates: Sequence[str] = ()
) -> dict[str, str]:
    """``--not-run MODEL=REASON`` as a mapping; the model must be a reader of the experiment.
    Where the experiment reads a model under several templates, ``MODEL/TEMPLATE=REASON``
    declares the run of one of them alone."""
    out: dict[str, str] = {}
    for value in pairs:
        name, _, reason = value.partition("=")
        model, slash, template = name.partition("/")
        known = model in models and (template in templates if slash else True)
        overlap = name in out or model in out
        overlap = overlap or (not slash and any(key.startswith(model + "/") for key in out))
        if not known or not reason.strip() or overlap:
            also = f"; or MODEL/TEMPLATE=REASON for one of {list(templates)}" if templates else ""
            refuse(f"--not-run takes MODEL=REASON, once for a model of {list(models)}{also}")
        out[name] = "declared on the command line: " + reason.strip()
    return out


def declaration_of(skipped: Mapping[str, str], model: str, template: str) -> str | None:
    """The name under which the run of a model under a template is declared not run (the
    model, or the model and the template), if it is."""
    return next((name for name in (model, f"{model}/{template}") if name in skipped), None)


def why_not_read(skipped: Mapping[str, str], model: str, template: str) -> str | None:
    """The declaration that covers the run of a model under a template, if there is one."""
    name = declaration_of(skipped, model, template)
    return None if name is None else skipped[name]


@dataclass
class Runs:
    """The stored readings of the lines of one experiment, by model and line, and what the
    check found on the lines declared not run."""

    readings: dict[tuple[str, str], dict[str, Reading]]
    records: dict[str, dict[str, Any]]
    plan_sha256: str
    checked: dict[str, dict[str, Any]]


def checked_line(
    plan: Mapping[str, Any],
    out_root: Path,
    model: str,
    line: str,
    template: str,
    ids: Sequence[str],
) -> tuple[list[str], dict[str, Reading], dict[str, Any], dict[str, str]]:
    """One line of one model through the evaluator's own check: what stands in the way of
    scoring it, and, when nothing does, its readings and its record; and the state of each of
    its runs as the launcher sees it. A stop inside the check (a plan, a manifest or a stored
    row that is not as the launcher and the harness write them, or a run that is being
    written) is one more problem, named by the type of the error alone."""
    stopped = ""
    found: list[str] = []
    given: dict[str, Reading] = {}
    record: dict[str, Any] = {}
    states: dict[str, str] = {}
    try:
        for run in lp.select(plan, [PHASE], models=[model]):
            if run["line"] == line:
                states[run["run"]] = lp.run_state(plan, run)
        group = ev.read_group(plan, out_root, PHASE, model, line, ids)
        found = list(group.problems)
        if not found and group.template != template:
            found.append(
                f"{model} {line}: planned under {group.template}, registered under {template}"
            )
        if not found:
            given = {i: stored_reading(group.rows[i]) for i in group.rows}
            record = {"line": line, **group.record}
    except Exception as error:  # the message may quote a stored row: the type alone
        stopped = type(error).__name__
    if stopped:
        found = [
            f"{model} {line}: the check of its runs stopped ({stopped}): the plan or the "
            "stored files are not as the launcher and the harness write them, or a run is "
            "being written"
        ]
    return found, given, record, states


def gather(
    out_root: Path,
    lines: Mapping[str, str],
    models: Sequence[str],
    skipped: Mapping[str, str],
    key: str,
    ids: Sequence[str],
    what: str,
    item_data: bytes,
) -> Runs:
    """The readings of every model on every line (``lines``: line by registered template),
    through the evaluator's own check of a line. ``item_data`` holds the bytes of the item
    file given: the runs must have read a file with those bytes. One problem is a refusal; a
    refusal names runs and gives counts, never an item. A line declared not run is checked
    too and not scored; when every line of a declaration could be scored, the declaration is
    refused."""
    plan, sha, problems = ev.read_plan(out_root)
    if plan is None:
        refuse("; ".join(problems))
    problems = list(problems) + ev.list_problems(plan, LISTS[key], ids, what)
    if (plan["lists"].get(LISTS[key]) or {}).get("sha256") != sealed_counts.sha256(item_data):
        problems.append(
            f"the item file given is not the file of the plan's item list {LISTS[key]!r}, "
            "which the runs read"
        )
    readings: dict[tuple[str, str], dict[str, Reading]] = {}
    records: dict[str, dict[str, Any]] = {}
    checked: dict[str, dict[str, Any]] = {}
    for model in models:
        for template, line in lines.items():
            found, given, record, states = checked_line(plan, out_root, model, line, template, ids)
            name = declaration_of(skipped, model, template)
            if name is not None:
                checked.setdefault(name, {})[line] = {"runs": states, "found": found}
                continue
            problems += found
            if not found:
                readings[model, template] = given
                records.setdefault(model, {})[template] = record
    scorable = [
        f"{name} ({sum(len(entry['runs']) for entry in by_line.values())} runs)"
        for name, by_line in checked.items()
        if not any(entry["found"] for entry in by_line.values())
    ]
    if scorable:
        refuse(
            "--not-run names runs that are complete on the registered item list, route and "
            "template, and such runs are scored: " + ", ".join(scorable)
        )
    if problems:
        refuse(
            "no score before every run of the experiment is complete on its registered item "
            "list, route and template: " + "; ".join(problems)
        )
    return Runs(readings, records, sha, checked)


def frozen_rules() -> None:
    """Refuse when ``rules.py`` is not the frozen rule reader (PLAN, standing rules and section
    17): the rule reader is the comparator of the registered tests of E2, and it reads the
    distractor dates of both golds."""
    found = sealed_counts.sha256(sealed_counts.file_bytes(Path(R.__file__), "rules.py"))
    if not found.startswith(F.RULES_SHA256):
        refuse(f"rules.py is not the frozen rule reader (sha256 prefix {F.RULES_SHA256})")


def code_record() -> dict[str, str]:
    """The sha256 of the code the numbers depend on."""
    modules = {"literal_scores.py": __file__, "rules.py": R.__file__, "read.py": rd.__file__}
    modules |= {"audit_sample.py": S.__file__, "evaluate.py": ev.__file__}
    modules |= {"forms.py": F.__file__, "corpus.py": C.__file__, "predictors.py": P.__file__}
    return {
        name: sealed_counts.sha256(sealed_counts.file_bytes(Path(path), name))
        for name, path in modules.items()
    }


def registered_record() -> dict[str, Any]:
    return {
        "seed": SEED,
        "draws": DRAWS,
        "alpha": ALPHA,
        "iou_correct": IOU_CORRECT,
        "positive_result_bars": {"iou_lead": IOU_LEAD, "false_commitment": FALSE_COMMITMENT_BAR},
        "gee": {
            "tolerance": f"{GEE_TOLERANCE:g}",
            "steps": GEE_STEPS,
            "variance_floor": f"{GEE_VARIANCE_FLOOR:g}",
        },
        "primaries": list(PRIMARIES),
        "e2": {"lines": dict(E2_LINES), "models": list(E2_MODELS), "test_template": E2_TEMPLATE},
        "e5": {"line": E5_LINE, "template": E5_TEMPLATE, "models": list(E5_MODELS)},
        "templates_sha256": {t: rd.FROZEN_SHA256[t] for t in E2_LINES},
    }


# --------------------------------------------------------------------------------------------
# E2: the frame, the gold, the readers
# --------------------------------------------------------------------------------------------


@dataclass
class Frame:
    """What the events table and the guide say of the literal items and of their frame."""

    stratum: dict[str, str]
    episode: dict[str, str]
    day: dict[str, str]
    events: dict[str, int]
    templates: dict[str, int]
    order: tuple[str, ...]


def frame_of(events: Path, guide: Path, ids: Iterable[str]) -> Frame:
    """The stratum, episode and date of the statement behind each item id, and the statements
    and distinct masked templates of each stratum in the frame (shortage listing, Current when
    first seen) without the statements the guide excludes: the sampler's own table."""
    stopped = ""
    inputs = None
    try:
        inputs = S.load_inputs(argparse.Namespace(captures=None, events=events, guide=guide))
    except (OSError, ValueError, KeyError, EOFError, zlib.error) as error:
        stopped = type(error).__name__
    if inputs is None:
        refuse(
            f"the events table or the guide cannot be read as the sampler reads them ({stopped})"
        )
    wanted = set(ids)
    behind = {S.item_id(s["id"]): s for s in inputs.table}
    missing = len(wanted - set(behind))
    if missing:
        refuse(f"{missing} items are of no statement of the events table given")
    framed = [s for s in inputs.table if s["in_frame"] and s["id"] not in inputs.excluded]
    seen: dict[str, set[str]] = {}
    for s in framed:
        seen.setdefault(s["stratum"], set()).add(s["template"])
    return Frame(
        stratum={i: behind[i]["stratum"] for i in wanted},
        episode={i: behind[i]["episode"] for i in wanted},
        day={i: behind[i]["event_date"] for i in wanted},
        events=dict(Counter(s["stratum"] for s in framed)),
        templates={name: len(found) for name, found in seen.items()},
        order=tuple(inputs.alloc.names),
    )


def key_problems(path: Path, frame: Frame) -> int | None:
    """How many items the sampler's key puts in another stratum than the events table given;
    None when there is no key to compare with."""
    if not path.is_file():
        return None
    rows = read_table(sealed_counts.file_bytes(path, "the key"), ("item_id", "stratum"), "the key")
    listed = {row["item_id"]: row["stratum"] for row in rows}
    return sum(1 for item, name in frame.stratum.items() if listed.get(item) != name)


def marked_items(path: Path, expected: str | None, known: Iterable[str]) -> dict[str, Any]:
    """The ids of the gold items whose reading rests on a convention the prompt does not state:
    one id per line (a line that is ``item_id`` or starts with ``#`` is skipped), in a file
    held to its sha256. Refused when the file is not there or no hash is given: the plan keeps
    a list in every case, with its header alone when no item rests on such a convention."""
    if not path.is_file():
        refuse(
            f"the list of convention items is not there ({path.as_posix()}): E2 is also "
            "reported without those items, and a list that holds its header alone says that "
            "there is none"
        )
    wanted = sealed_counts.expected_hash(expected, "--expect-convention-sha256")
    data = sealed_counts.file_bytes(path, "the list of convention items")
    sha = sealed_counts.require_hash(data, wanted, "the list of convention items")
    stopped = ""
    lines: list[str] = []
    try:
        lines = [line.strip().strip('"') for line in data.decode("utf-8-sig").splitlines()]
    except ValueError as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"the list of convention items cannot be read ({stopped})")
    ids = [line for line in lines if line and line != "item_id" and not line.startswith("#")]
    unknown = len(set(ids) - set(known))
    if unknown or len(set(ids)) != len(ids):
        refuse(
            f"the list of convention items names {unknown} ids that are not gold items, or an "
            "id twice"
        )
    return {"ids": set(ids), "sha256": sha, "path": path.as_posix()}


def manifest_gold_sha256(audit: Path) -> str | None:
    """The sha256 of the gold as the manifest of the audit folder records it (written by
    ``audit_agreement gold``); None when the folder has no manifest or the manifest no gold,
    which is the state of the folder before the gold is fixed. A manifest that is there and
    cannot be read is a refusal."""
    path = audit / S.MANIFEST
    if not path.is_file():
        return None
    stopped = ""
    record: Any = None
    try:
        record = json.loads(sealed_counts.file_bytes(path, "the audit manifest").decode("utf-8"))
    except ValueError as error:
        stopped = type(error).__name__
    if stopped or not isinstance(record, dict):
        refuse(f"the audit manifest cannot be read ({stopped or 'not an object'})")
    entry = record.get("gold")
    found = entry.get("sha256") if isinstance(entry, dict) else None
    return found if isinstance(found, str) and found else None


def annotator_labels(audit: Path) -> tuple[dict[str, dict[str, S.Label]] | None, str]:
    """Both annotators' labels from the submitted sheets under ``audit``, when both are there
    with the sha256 the audit manifest records; otherwise None and why."""
    manifest: Any = {}
    if (audit / S.MANIFEST).is_file():
        try:
            manifest = A.load_manifest(audit)
        except (OSError, ValueError):
            manifest = None
        manifest = manifest.get("submitted", {}) if isinstance(manifest, Mapping) else None
        if not isinstance(manifest, Mapping):
            return None, "the manifest of the audit folder cannot be read"
    labels = {}
    for annotator in ANNOTATORS:
        name = f"{A.SUBMITTED_DIR}/literal_{annotator}.csv"
        path = audit / name
        if not path.is_file():
            return None, f"the submitted sheet of {annotator} is not under the audit folder"
        if manifest.get(name) != sealed_counts.sha256(path.read_bytes()):
            return None, f"the submitted sheet of {annotator} is not the one the manifest records"
        labels[annotator] = S.check_file(path, None, audit).labels
    return labels, ""


def stratum_weights(
    strata: Sequence[str], sizes: Mapping[str, int], what: str
) -> tuple[np.ndarray, list[str]]:
    """The weight of each item when a stratum weighs ``sizes`` (its statements or its templates
    in the frame): the size of its stratum over the scored items of that stratum."""
    scored = Counter(strata)
    lost = sorted(name for name in scored if not sizes.get(name))
    if lost:
        refuse(f"the frame holds no {what} for the strata {lost} of the scored items")
    return np.array([sizes[name] / scored[name] for name in strata]), sorted(scored)


@dataclass
class Scope:
    """One set of scored items, in id order, with what every reader's block needs."""

    ids: list[str]
    golds: list[Gold]
    strata: list[str]
    marked: list[bool]
    bases: dict[str, np.ndarray]
    taken: np.ndarray


def scope_of(ids: Sequence[str], frame: Frame, golds: Mapping[str, Gold] | None = None) -> Scope:
    """The scope of a set of items. ``golds`` is left out for a set that is not scored against
    the gold (every item both annotators labelled): such a scope holds no gold."""
    ids = sorted(ids)
    strata = [frame.stratum[i] for i in ids]
    by_event, _ = stratum_weights(strata, frame.events, "statement")
    by_template, _ = stratum_weights(strata, frame.templates, "template")
    return Scope(
        ids=ids,
        golds=[] if golds is None else [golds[i] for i in ids],
        strata=strata,
        marked=[name in TBD_OR_SILENT for name in strata],
        bases={
            "sample": np.ones(len(ids)),
            "weighted_by_event": by_event,
            "weighted_by_template": by_template,
        },
        taken=item_draws([frame.episode[i] for i in ids]),
    )


Measured = dict[str, tuple[dict[str, np.ndarray], dict[str, np.ndarray]]]
"""The metrics of one reader under each weighting of a scope: at the items as they are, and in
every draw of the scope."""


def measured(scope: Scope, cols: Mapping[str, np.ndarray]) -> Measured:
    """Every metric of one reader under each weighting of the scope, and in each of its draws."""
    return {
        name: (metrics(cols, base), metrics(cols, scope.taken * base[None, :]))
        for name, base in scope.bases.items()
    }


def block(
    scope: Scope, cols: Mapping[str, np.ndarray], order: Sequence[str], held: Measured | None = None
) -> dict[str, Any]:
    """The results of one reader on one item set: counts, the exact intervals of the rates
    that have one, every metric pooled over the sample, weighted by event and weighted by
    template (each with its interval), and per stratum. ``held`` is what :func:`measured`
    gives for the reader, when it is already at hand."""
    out: dict[str, Any] = {"n": counts(cols), "exact": exact_rates(cols)}
    for name, (point, drawn) in (measured(scope, cols) if held is None else held).items():
        out[name] = {
            metric: {"value": number(point[metric][0]), "ci95": interval95(drawn[metric])}
            for metric in METRICS
        }
    strata = np.array(scope.strata)
    out["by_stratum"] = {
        name: {"n": counts(cols, strata == name), **values(cols, (strata == name).astype(float))}
        for name in order
        if (strata == name).any()
    }
    return out


def lead(
    scope: Scope, first: Mapping[str, np.ndarray], second: Mapping[str, np.ndarray], keep: Any
) -> dict[str, Any]:
    """The mean IoU of two readers and their difference over the kept items whose gold gives
    an interval, with the 95% interval of the difference from the draws of the scope."""
    dated = first["gold_dated"] * np.asarray(keep, dtype=float)
    n = dated.sum()
    if not n:
        return {"items": 0, "first": None, "second": None, "difference": None, "ci95": None}
    gap = (first["iou"] - second["iou"]) * dated
    drawn = _share(scope.taken @ gap, scope.taken @ dated)
    return {
        "items": int(n),
        "first": float((first["iou"] * dated).sum() / n),
        "second": float((second["iou"] * dated).sum() / n),
        "difference": float(gap.sum() / n),
        "ci95": interval95(drawn),
    }


def margin(first: Measured, second: Measured) -> dict[str, Any]:
    """How far the first reader stands above the second on false commitment and on distractor
    uptake (``MARGIN_METRICS``), under each weighting of their scope: the two figures, their
    difference, and its 95% interval over the draws of the scope. Each reader's figure is its
    own metric on its own columns (the two may be scored against different labels, and so on
    different denominators); they are paired by the draw alone, and a draw that leaves either
    undefined is left out."""
    out: dict[str, Any] = {}
    for weighting, (a, many_a) in first.items():
        b, many_b = second[weighting]
        out[weighting] = {
            name: {
                "first": number(a[name][0]),
                "second": number(b[name][0]),
                "difference": number(a[name][0] - b[name][0]),
                "ci95": interval95(many_a[name] - many_b[name]),
            }
            for name in MARGIN_METRICS
        }
    return out


def letter_gap(
    scope: Scope, first: Mapping[str, np.ndarray], second: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    """The letter accuracy of two readers on the letter items of the scope and its difference,
    first minus second, under each weighting, with the 90% and the 95% percentile interval of
    the difference over the draws of the scope. Pooled without weights (``sample``) and with
    the rule reader second, it is the letter reading of E2 (PLAN section 5, E2, "Test"). Both
    readers are scored against the same gold, so they share their letter items; a draw that
    holds none is left out. The difference of a draw is one division of two sums, so that a
    draw exactly 0.10 apart reads 0.10."""
    out: dict[str, Any] = {"items": int(first["letter"].sum())}
    gap = first["letter_correct"] - second["letter_correct"]
    for name, base in scope.bases.items():
        below = first["letter"] * base
        n = below.sum()
        if not n:
            out[name] = dict.fromkeys(("first", "second", "difference", "ci90", "ci95"))
            continue
        drawn = _share(scope.taken @ (gap * base), scope.taken @ below)
        out[name] = {
            "first": float((first["letter_correct"] * base).sum() / n),
            "second": float((second["letter_correct"] * base).sum() / n),
            "difference": float((gap * base).sum() / n),
            "ci90": interval90(drawn),
            "ci95": interval95(drawn),
        }
    return out


def versus(
    scope: Scope, first: Mapping[str, np.ndarray], second: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    """One reader against another on the same items: the McNemar counts on ``correct`` over
    the items outside the month-and-year stratum (the registered pooling), inside it, over all
    and per stratum, the same on the items both parsed, the lead in IoU, and the difference
    in letter accuracy."""
    strata = np.array(scope.strata)
    a, b = first["correct"] > 0, second["correct"] > 0
    both = (first["parsed"] > 0) & (second["parsed"] > 0)
    outside = strata != MONTH_YEAR
    names = sorted(set(scope.strata))
    return {
        "outside_month_year": mcnemar(a[outside], b[outside]),
        "month_year": mcnemar(a[~outside], b[~outside]),
        "all": mcnemar(a, b),
        "outside_month_year_both_parsed": mcnemar(a[outside & both], b[outside & both]),
        "by_stratum": {name: mcnemar(a[strata == name], b[strata == name]) for name in names},
        "iou": {
            "all": lead(scope, first, second, np.ones(len(a))),
            MONTH_YEAR: lead(scope, first, second, ~outside),
            **{
                name: lead(scope, first, second, strata == name)
                for name in (*LEAD_STRATA, *BESIDE_THE_LEAD, *DISTRACTOR_STRATA)
            },
            DISTRACTOR_ROWS: lead(scope, first, second, np.isin(strata, DISTRACTOR_STRATA)),
            "gold_with_distractor_date": lead(scope, first, second, first["has_distractor"] > 0),
        },
        "letter_accuracy": letter_gap(scope, first, second),
    }


def family(tests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Holm over the p-values of a family, in the order given."""
    adjusted = holm([entry["p"] for entry in tests])
    return [
        entry | {"p_holm": float(p), "holds": bool(p < ALPHA)}
        for entry, p in zip(tests, adjusted, strict=True)
    ]


def score_e2(
    ids: Sequence[str],
    golds: Mapping[str, Gold],
    frame: Frame,
    items: Mapping[str, Mapping[str, Any]],
    readings: Mapping[tuple[str, str], Mapping[str, Reading]],
    skipped: Mapping[str, str],
    humans: Mapping[str, Mapping[str, S.Label]] | None = None,
) -> dict[str, Any]:
    """Everything E2 reports on one set of gold items."""
    scope = scope_of(ids, frame, golds)
    order = frame.order

    def cols_of(given: Mapping[str, Reading]) -> dict[str, np.ndarray]:
        return columns([given[i] for i in scope.ids], scope.golds, scope.marked)

    rules = cols_of({i: rule_reading(items[i]) for i in scope.ids})
    rules_drawn = measured(scope, rules)
    readers: dict[str, Any] = {RULES: block(scope, rules, order, rules_drawn)}
    against: dict[str, Any] = {}
    templates: dict[str, Any] = {}
    flags: dict[str, list[list[Any]]] = {RULES: flag_rows(scope.ids, rules)}
    held: dict[tuple[str, str], dict[str, np.ndarray]] = {}
    drawn: dict[tuple[str, str], Measured] = {}
    for (model, template), given in sorted(readings.items()):
        cols = held[model, template] = cols_of(given)
        mine = drawn[model, template] = measured(scope, cols)
        readers.setdefault(model, {})[template] = block(scope, cols, order, mine)
        against.setdefault(model, {})[template] = versus(scope, cols, rules) | {
            "margins": margin(mine, rules_drawn)
        }
        flags[f"{model} {template}"] = flag_rows(scope.ids, cols)
    for model in sorted({model for model, _ in held}):
        if all((model, template) in held for template in E2_LINES):
            first, second = (held[model, template] for template in E2_LINES)
            templates[model] = versus(scope, first, second)
    tests = []
    for model in PRIMARIES:
        entry: dict[str, Any] = {"model": model, "template": E2_TEMPLATE, "against": RULES}
        why = why_not_read(skipped, model, E2_TEMPLATE)
        if why:
            tests.append(entry | {"evaluable": False, "why": why, "p": 1.0})
            continue
        found = against[model][E2_TEMPLATE]["outside_month_year"]
        more = found["only_first_correct"] - found["only_second_correct"]
        favours = "the model" if more > 0 else "the rule reader" if more < 0 else "neither"
        tests.append(entry | {"evaluable": True, **found, "favours": favours})
    out = {
        "items": len(scope.ids),
        "episodes": len({frame.episode[i] for i in scope.ids}),
        "items_by_stratum": {
            name: scope.strata.count(name) for name in order if name in scope.strata
        },
        "readers": readers,
        "tests": family(tests),
        "versus_rules": against,
        "literal_v1_versus_literal_free_v1": templates,
        "positive_result": positive_result(readers, against),
    }
    letter = [letter_item(gold) for gold in scope.golds]
    out["literal_ceiling"], annotators = ceiling(scope, humans, order, letter)
    beside: dict[str, Any] = {"computed": humans is not None}
    if humans is not None:
        for (model, template), mine in drawn.items():
            beside.setdefault(model, {})[template] = {
                name: margin(mine, theirs) for name, theirs in annotators.items()
            }
    out["versus_ceiling"] = beside
    return out | {"flags": flags}


def flag_rows(ids: Sequence[str], cols: Mapping[str, np.ndarray]) -> list[list[Any]]:
    """Per item, its id and two flags: correct by the E2 rule, and parsed."""
    return [[item, int(cols["correct"][k]), int(cols["parsed"][k])] for k, item in enumerate(ids)]


def ceiling(
    scope: Scope,
    humans: Mapping[str, Mapping[str, S.Label]] | None,
    order: Sequence[str],
    letter: Sequence[bool],
) -> tuple[dict[str, Any], dict[str, Measured]]:
    """Each annotator scored against the other one's labels on the items of the scope: the
    block of each, and its metrics in every draw, for the margins of the models over it.
    ``letter`` says which items of the scope are letter items of the gold: the adjudicated gold
    fixes that set (PLAN section 13), also where the other annotator's label stands in the
    place of the gold."""
    if humans is None:
        return {"computed": False}, {}
    out: dict[str, Any] = {"computed": True}
    held: dict[str, Measured] = {}
    first, second = ANNOTATORS
    for reader, reference in ((first, second), (second, first)):
        readings = [label_reading(humans[reader][i]) for i in scope.ids]
        golds = [label_gold(humans[reference][i]) for i in scope.ids]
        cols = columns(readings, golds, scope.marked, letter)
        mine = held[f"{reader}_against_{reference}"] = measured(scope, cols)
        out[f"{reader}_against_{reference}"] = block(scope, cols, order, mine)
    return out, held


def labelled_ceiling(
    humans: Mapping[str, Mapping[str, S.Label]] | None, golds: Mapping[str, Gold], frame: Frame
) -> dict[str, Any]:
    """The literal ceiling of PLAN section 8: each annotator scored against the other one's
    labels on every item of the item file that both labelled, in the gold or left out of it
    (an item left out of the gold is one the two labelled apart). An item without a gold is no
    letter item."""
    if humans is None:
        return {"computed": False}
    first, second = ANNOTATORS
    ids = sorted(set(humans[first]) & set(humans[second]) & set(frame.stratum))
    if not ids:
        return {"computed": False, "why": "no item of the item file is labelled by both"}
    scope = scope_of(ids, frame)
    letter = [i in golds and letter_item(golds[i]) for i in scope.ids]
    out, _ = ceiling(scope, humans, frame.order, letter)
    return out | {"items": len(ids), "items_left_out_of_the_gold": len(set(ids) - set(golds))}


def positive_result(readers: Mapping[str, Any], against: Mapping[str, Any]) -> dict[str, Any]:
    """The three figures of the plan's "positive result" of E2 under ``literal-v1``, as
    descriptions, on the item sets the plan names: correctness of rules and model on
    month-and-year text; the lead in IoU on the three strata of ``LEAD_STRATA`` and on the two
    distractor rows together, each against ``IOU_LEAD``, with the lead on the relative stratum
    beside them and against no bar; and false commitment on the gold-ABSTAIN items of the TBD
    and silent strata against ``FALSE_COMMITMENT_BAR``, with the rate over every gold-ABSTAIN
    item beside it and against no bar."""
    out: dict[str, Any] = {}
    for model, by_template in against.items():
        found = by_template.get(E2_TEMPLATE)
        if found is None:
            continue
        leads = {name: found["iou"][name]["difference"] for name in (*LEAD_STRATA, DISTRACTOR_ROWS)}
        sample = readers[model][E2_TEMPLATE]["sample"]
        rate = sample["false_commitment_tbd_or_silent"]
        out[model] = {
            "month_year": {
                "items": found[MONTH_YEAR]["items"],
                "model_correct": found[MONTH_YEAR]["first_correct"],
                "rules_correct": found[MONTH_YEAR]["second_correct"],
                "iou_difference": found["iou"][MONTH_YEAR]["difference"],
            },
            "iou_lead": leads,
            "leads_by_0.15": {
                name: None if value is None else bool(value >= IOU_LEAD)
                for name, value in leads.items()
            },
            "iou_lead_beside": {name: found["iou"][name]["difference"] for name in BESIDE_THE_LEAD},
            "false_commitment_tbd_or_silent": rate,
            "false_commitment_above_0.05": None
            if rate["value"] is None
            else bool(rate["value"] > FALSE_COMMITMENT_BAR),
            "false_commitment_every_gold_abstain": sample["false_commitment"],
        }
    return out


def e2_lines(report: Mapping[str, Any]) -> list[str]:
    """The short table of an E2 result: one line per reader on every gold item, and the tests
    of every item set."""
    whole = report["item_sets"]["all"]
    names = ("correct", "statement_type_accuracy", "interval_iou", "false_commitment")
    lines = [
        f"E2: {whole['items']} gold items in {whole['episodes']} episodes; strata weighted by "
        "their frame statements",
        f"{'reader':36s} {'correct':>8s} {'type':>8s} {'IoU':>8s} {'false c.':>8s} {'failed':>7s}",
    ]

    def row(name: str, found: Mapping[str, Any], failed: str) -> str:
        cells = " ".join(_cell(found["weighted_by_event"][m]["value"]) for m in names)
        return f"{name:36s} {cells} {failed:>7s}"

    lines.append(row(RULES, whole["readers"][RULES], "-"))
    for model in E2_MODELS:
        for template in E2_LINES:
            found = whole["readers"].get(model, {}).get(template)
            if found is not None:
                rate = report["runs"][model][template]["parse_failure_rate"]
                lines.append(row(f"{model} {template}", found, _cell(rate).strip()))
    if not whole["literal_ceiling"]["computed"]:
        why = whole["literal_ceiling"].get("why", "no labels of the annotators")
        lines.append(f"literal ceiling: not computed ({why})")
    for name, scored in report["item_sets"].items():
        if not scored.get("computed", True):
            lines.append(f"{name}: not computed ({scored['why']})")
            continue
        for test in scored["tests"]:
            if not test["evaluable"]:
                lines.append(f"{name}: {test['model']} against the rules: not run, p = 1")
                continue
            lines.append(
                f"{name}: {test['model']} against the rules outside month and year, "
                f"{test['items']} items: {test['only_first_correct']} against "
                f"{test['only_second_correct']} discordant, p = {test['p']:.4f}, Holm "
                f"{test['p_holm']:.4f}{' *' if test['holds'] else ''}"
            )
    return lines


def _cell(value: Any) -> str:
    return f"{'-':>8s}" if value is None else f"{value:8.3f}"


def run_e2(args: argparse.Namespace) -> int:
    gold_data = gold_bytes(
        args.gold,
        args.expect_gold_sha256,
        "--expect-gold-sha256",
        "the gold of the literal task",
        "no reading is compared with the items of the literal task before their gold is fixed",
    )
    frozen_rules()
    out, _ = ev.output_paths(args.out)
    skipped = declared(args.not_run, E2_MODELS, tuple(E2_LINES))
    item_data = sealed_counts.file_bytes(args.items, "the item file of the literal task")
    items = {row["item_id"]: row for row in read_jsonl(item_data, "the item file")}
    rows = read_table(gold_data, A.GOLD_COLUMNS, "the gold of the literal task")
    frame = frame_of(args.events, args.guide, items)
    moved = sum(1 for i, row in items.items() if item_anchor(row).isoformat() != frame.day[i])
    if moved:
        refuse(f"{moved} items carry another date than their statement in the events table")
    golds: dict[str, Gold] = {}
    bad = 0
    for row in rows:
        try:
            item = items[row["item_id"]]
            golds[row["item_id"]] = gold_of(row["item_id"], row, item_anchor(item))
        except (KeyError, ValueError):
            bad += 1
    faults = {
        "rows of no item or that cannot be read": bad,
        "rows of a repeated item": len(rows) - bad - len(golds),
        "items with a decision that is not agree, slip or gap": sum(
            1 for g in golds.values() if g.decision not in DECISIONS
        ),
    }
    if any(faults.values()):
        found = "; ".join(f"{n} {fault}" for fault, n in faults.items() if n)
        refuse(f"the gold is not the gold of the item file: {found}")
    recorded = manifest_gold_sha256(args.audit_dir)
    if recorded is None:
        refuse(
            "the audit manifest holds no record of a gold "
            f"({(args.audit_dir / S.MANIFEST).as_posix()}): the gold of the literal task is the "
            "file that audit_agreement gold writes and records there, and no reading is "
            "compared with another"
        )
    if recorded != sealed_counts.sha256(gold_data):
        refuse(
            "the gold is not the one the audit manifest records: its sha256 is "
            f"{sealed_counts.sha256(gold_data)}, and the manifest holds {recorded[:64]}; a "
            "gold changed by a dated amendment is written again by audit_agreement gold"
        )
    marks = marked_items(args.convention_items, args.expect_convention_sha256, golds)
    differs = key_problems(args.key, frame)
    if differs:
        refuse(f"the key of the sample puts {differs} items in another stratum than the table")
    runs = gather(
        args.out_root,
        E2_LINES,
        E2_MODELS,
        skipped,
        "e2",
        list(items),
        "the literal items",
        item_data,
    )
    humans, why_not = annotator_labels(args.audit_dir)
    if humans is not None and not all(set(golds) <= set(humans[a]) for a in ANNOTATORS):
        humans, why_not = None, "a submitted sheet lacks a gold item"
    whole_ceiling = labelled_ceiling(humans, golds, frame)
    if humans is None:
        whole_ceiling["why"] = why_not
    sets: dict[str, Any] = {"all": sorted(golds)}
    sets["without_gap"] = sorted(i for i in golds if golds[i].decision != GAP)
    sets["without_convention_items"] = sorted(set(golds) - marks["ids"])
    readings = {key: {i: given[i] for i in golds} for key, given in runs.readings.items()}
    scored: dict[str, Any] = {}
    flags: dict[str, Any] = {}
    for name, ids in sets.items():
        if not ids:
            scored[name] = {"computed": False, "why": "no gold item is left"}
            continue
        scored[name] = score_e2(ids, golds, frame, items, readings, skipped, humans)
        found = scored[name].pop("flags")
        flags = found if name == "all" else flags
        if humans is None:
            scored[name]["literal_ceiling"]["why"] = why_not
            scored[name]["versus_ceiling"]["why"] = why_not
    report = {
        "about": ABOUT_E2,
        "registered": registered_record(),
        "inputs": {
            "gold": args.gold.as_posix(),
            "gold_sha256": sealed_counts.sha256(gold_data),
            "gold_sha256_in_the_audit_manifest": recorded,
            "items": args.items.as_posix(),
            "items_sha256": sealed_counts.sha256(item_data),
            "item_ids_sha256": lp.ids_sha256(items),
            "events": args.events.as_posix(),
            "events_sha256": sealed_counts.sha256(args.events.read_bytes()),
            "guide_sha256": sealed_counts.sha256(args.guide.read_bytes()),
            "plan_sha256": runs.plan_sha256,
            "convention_items": marks["path"],
            "convention_items_sha256": marks["sha256"],
            "key_compared": differs is not None,
            "code": code_record(),
        },
        "gold": {
            "items_in_the_item_file": len(items),
            "gold_items": len(golds),
            "not_in_the_gold": len(items) - len(golds),
            "by_decision": dict(sorted(Counter(g.decision for g in golds.values()).items())),
            "hard": sum(g.hard for g in golds.values()),
            "convention_items": len(marks["ids"]),
            "with_distractor_roles": sum(1 for g in golds.values() if g.roles),
            "with_a_distractor_date": sum(1 for g in golds.values() if g.distractors),
        },
        "frame": {
            name: {
                "statements": frame.events.get(name, 0),
                "templates": frame.templates.get(name, 0),
            }
            for name in frame.order
        },
        "runs": runs.records,
        "not_run": {**NORMALISERS_NOT_RUN, **skipped},
        "not_run_checked": runs.checked,
        "item_sets": scored,
        "literal_ceiling_on_every_labelled_item": whole_ceiling,
        "per_item": {
            "columns": ["item_id", "correct", "parsed"],
            "item_set": "all",
            "readers": flags,
        },
        "where_the_plan_is_silent": list(WHERE_THE_PLAN_IS_SILENT),
    }
    ev.write_new(out, report_text(report))
    print("\n".join(e2_lines(report)))
    print(f"wrote {out.as_posix()}")
    return 0


# --------------------------------------------------------------------------------------------
# E5: errors, the GEE and its fallback
# --------------------------------------------------------------------------------------------


def error_flags(cols: Mapping[str, np.ndarray], factors: Sequence[str]) -> dict[str, np.ndarray]:
    """The error of each reading (PLAN section 5, E5, "Target") and its three parts: not correct
    by the E2 rule; a wrong certainty class; a wrong stale flag. ``error`` holds an item to the
    criterion of its own factor: the second part counts for the items of the certainty factor
    only, the third for those of the stale factor only, and neither for an unedited seed item.
    Under each level of ``SEED_ROWS`` stands the error of every reading by the criterion of
    that level's factor, which is what an unedited seed item is held to in the contrast of the
    factor."""
    factor = np.array(list(factors))
    wrong = cols["correct"] == 0
    parts = {"certainty_wrong": cols["certainty_ok"] == 0, "stale_wrong": cols["stale_ok"] == 0}
    error = wrong.copy()
    for name, part in OWN_FIELD.items():
        error |= (factor == name) & parts[part]
    under = {SEED_ROWS[name]: wrong | parts[part] for name, part in OWN_FIELD.items()}
    return {"error": error, "not_correct": wrong, **parts, **under}


def seed_cell(factor: str) -> str:
    """The seed cell that the items of a factor are compared with: the seed rows under that
    factor's criterion."""
    return SEED_ROWS.get(factor, SEED_FACTOR)


def held_to(flags: Mapping[str, np.ndarray], cell: str) -> np.ndarray:
    """The error of every reading by the criterion of one seed cell. On the items of a factor
    that is compared with the cell it is their own error, so both sides of a contrast are
    read from this one column."""
    return flags["not_correct"] if cell == SEED_FACTOR else flags[cell]


def long_table(factors: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """The rows of one reader in the model of E5 (PLAN section 5, E5, "Test"): every item once,
    under its factor, and every unedited seed item twice more, under the two levels of
    ``SEED_ROWS``. Gives the place of the item behind each row, and the level of each row."""
    factor = np.array(list(factors))
    plain = np.flatnonzero(factor == SEED_FACTOR)
    item = np.concatenate([np.arange(len(factor)), *(plain for _ in SEED_ROWS)])
    level = np.concatenate([factor, *(np.full(len(plain), name) for name in SEED_ROWS.values())])
    return item, level


def long_outcome(
    flags: Mapping[str, np.ndarray], item: np.ndarray, level: np.ndarray
) -> np.ndarray:
    """The error of each row of :func:`long_table` for one reader: an item under its own
    factor's criterion, and each further seed row under the criterion of its level."""
    y = flags["error"][item].astype(float)
    for name in SEED_ROWS.values():
        rows = level == name
        y[rows] = flags[name][item[rows]]
    return y


def design(
    factors: Sequence[str],
    models: Sequence[str],
    factor_levels: Sequence[str],
    model_levels: Sequence[str],
) -> tuple[np.ndarray, list[str]]:
    """The design of "factor and model with their interaction", in treatment coding: an
    intercept, one column for each factor but the first level (the unedited seed), one for each
    model but the first, and one for each pair of those."""
    factor, model = np.array(list(factors)), np.array(list(models))
    names = ["intercept"]
    cols = [np.ones(len(factor))]
    for f in factor_levels[1:]:
        names.append(f"factor[{f}]")
        cols.append((factor == f).astype(float))
    for m in model_levels[1:]:
        names.append(f"model[{m}]")
        cols.append((model == m).astype(float))
    for f in factor_levels[1:]:
        for m in model_levels[1:]:
            names.append(f"factor[{f}]:model[{m}]")
            cols.append(((factor == f) & (model == m)).astype(float))
    return np.stack(cols, axis=1), names


def gee(y: Any, x: Any, clusters: Sequence[str]) -> dict[str, Any]:
    """A logistic GEE with the independence working correlation: the coefficients solve the
    score equations of the logistic fit (Newton steps from zero), and their robust covariance
    is ``A^-1 B A^-1`` with ``A = X' W X`` and ``B`` the sum over clusters of the outer product
    of the cluster's score ``X_g' (y_g - p_g)``. ``converged`` is false when a step cannot be
    taken or the steps do not settle."""
    y, x = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    codes, groups = cluster_codes(clusters)
    beta = np.zeros(x.shape[1])
    failed = {"converged": False, "beta": None, "covariance": None, "clusters": groups}
    for _ in range(GEE_STEPS):
        p = special.expit(x @ beta)
        bread = x.T @ (x * (p * (1 - p))[:, None])
        try:
            step = np.linalg.solve(bread, x.T @ (y - p))
        except np.linalg.LinAlgError:
            return failed
        beta = beta + step
        if not np.isfinite(beta).all():
            return failed
        if np.abs(step).max() < GEE_TOLERANCE:
            break
    else:
        return failed
    p = special.expit(x @ beta)
    bread = x.T @ (x * (p * (1 - p))[:, None])
    scores = np.zeros((groups, x.shape[1]))
    np.add.at(scores, codes, x * (y - p)[:, None])
    try:
        inverse = np.linalg.inv(bread)
    except np.linalg.LinAlgError:
        return failed
    covariance = inverse @ (scores.T @ scores) @ inverse
    return {"converged": True, "beta": beta, "covariance": covariance, "clusters": groups}


def wald(fit: Mapping[str, Any], weights: np.ndarray) -> dict[str, Any] | None:
    """The Wald test of a linear contrast of a fitted GEE; None when it has no finite positive
    variance (``GEE_VARIANCE_FLOOR``)."""
    if not fit["converged"]:
        return None
    estimate = float(weights @ fit["beta"])
    variance = float(weights @ fit["covariance"] @ weights)
    if not np.isfinite(variance) or variance <= GEE_VARIANCE_FLOOR or not np.isfinite(estimate):
        return None
    z = estimate / variance**0.5
    return {
        "log_odds_difference": estimate,
        "se": variance**0.5,
        "z": z,
        "p": float(2 * stats.norm.sf(abs(z))),
    }


def drawn_contrast(
    error: np.ndarray, edited: np.ndarray, seed: np.ndarray, taken: np.ndarray
) -> dict[str, Any]:
    """The contrast of two error rates over bootstrap draws of the clusters: the difference
    ``d`` of the rate of the edited items and the rate of the seed items, and the same
    difference ``d*`` in each draw. ``taken`` holds how often each item is taken in each draw;
    a draw with no item on one side is left out, and ``B`` is the number of draws left.

    ``p`` is the p-value of the fallback of E5 (PLAN section 5, E5, "Fallback"), two-sided on
    the centred draws: ``(1 + #{|d* - d| >= |d|}) / (B + 1)``. ``p_percentile`` is the
    two-sided percentile p-value of PLAN section 6 on the sign of ``d*``; it is reported
    beside the first and enters no rule. Both are counted on whole numbers, without a
    division, so that a draw exactly as far from ``d`` as ``d`` is from zero counts, as the
    formula has it: with ``d = a / b`` and ``d* = a* / b*`` (``b`` and ``b*`` positive), a
    draw is that far when ``a*`` is zero or of the other sign than ``a``, or when
    ``|a*| b >= 2 |a| b*``."""
    e_f, n_f = taken @ (error * edited), taken @ edited
    e_s, n_s = taken @ (error * seed), taken @ seed
    kept = (n_f > 0) & (n_s > 0)
    drawn, drawn_scale = (e_f * n_s - e_s * n_f)[kept], (n_f * n_s)[kept]
    draws = len(drawn)
    if not draws:
        return {"draws": 0, "p": 1.0, "p_percentile": 1.0, "ci95": None}
    seen = float((error * edited).sum() * seed.sum() - (error * seed).sum() * edited.sum())
    scale = float(edited.sum() * seed.sum())
    side = np.sign(seen)
    far = (side * drawn <= 0) | (side * drawn * scale >= 2 * side * seen * drawn_scale)
    below = (1 + int((drawn <= 0).sum())) / (draws + 1)
    above = (1 + int((drawn >= 0).sum())) / (draws + 1)
    difference = e_f[kept] / n_f[kept] - e_s[kept] / n_s[kept]
    return {
        "draws": draws,
        "p": float((1 + int(far.sum())) / (draws + 1)),
        "p_percentile": float(min(1.0, 2 * min(below, above))),
        "ci95": interval95(difference),
    }


def rate(errors: Any, keep: Any) -> dict[str, Any]:
    keep = np.asarray(keep, dtype=bool)
    n, k = int(keep.sum()), int(np.asarray(errors, dtype=bool)[keep].sum())
    return {"items": n, "errors": k, "rate": k / n if n else None}


def log_odds_gap(first: Mapping[str, Any], second: Mapping[str, Any]) -> float | None:
    """The difference of the log odds of two error rates: the maximum-likelihood contrast of
    two cells of the model. None when a rate is 0 or 1, where it is not finite."""
    odds = []
    for cell in (first, second):
        if not 0 < cell["errors"] < cell["items"]:
            return None
        odds.append(cell["errors"] / (cell["items"] - cell["errors"]))
    return float(np.log(odds[0]) - np.log(odds[1]))


def error_table(
    flags: Mapping[str, np.ndarray], factors: Sequence[str], levels: Sequence[str]
) -> dict[str, Any]:
    """Error rates of one reader by factor and by level, with the three parts of the error."""
    factor, level = np.array(list(factors)), np.array(list(levels))
    out: dict[str, Any] = {"by_factor": {}, "by_level": {}}
    for f in (SEED_FACTOR, *FACTORS):
        here = factor == f
        if not here.any():
            continue
        out["by_factor"][f] = rate(flags["error"], here) | {
            part: int(flags[part][here].sum())
            for part in ("not_correct", "certainty_wrong", "stale_wrong")
        }
        out["by_level"][f] = {
            name: rate(flags["error"], here & (level == name)) for name in sorted(set(level[here]))
        }
    return out


def standing(
    cols: Mapping[str, np.ndarray], error: np.ndarray, factor: np.ndarray, name: str
) -> dict[str, Any]:
    """What the standing part of the registered pattern reads of one reader and one standing
    factor beside its test (PLAN section 13): the error rate on the items of the two letter
    factors taken together, under the criterion of the factor (``error`` is the error of every
    reading under it); the rate of the factor's own error on the items of the factor on which
    it can occur (``OWN_ERROR``); and how many of the errors on the items of the factor are of
    another kind, with their share. The own error is always an error under the criterion of
    its factor."""
    here = factor == name
    occurs, can_occur = (cols[column] > 0 for column in OWN_ERROR[name])
    own = rate(occurs, here & can_occur)
    errors = int(error[here].sum())
    other = errors - own["errors"]
    return {
        "letter_factors": rate(error, np.isin(factor, LETTER_FACTORS)),
        "own_error": own,
        "errors_of_another_kind": {"errors": other, "share": other / errors if errors else None},
    }


def score_e5(
    ids: Sequence[str],
    golds: Mapping[str, Gold],
    info: Mapping[str, Mapping[str, Any]],
    readings: Mapping[str, Mapping[str, Reading]],
    skipped: Mapping[str, str],
    rules: Mapping[str, Reading] | None = None,
) -> dict[str, Any]:
    """Everything E5 reports. ``info`` gives each item its seed, factor and level; ``readings``
    the readings of each model that ran."""
    ids = sorted(ids)
    seeds = [str(info[i]["seed_id"]) for i in ids]
    factors = [str(info[i]["factor"]) for i in ids]
    levels = [str(info[i]["level"]) for i in ids]
    gold = [golds[i] for i in ids]
    factor = np.array(factors)
    within_seed = np.array(seeds)
    taken = item_draws(seeds)
    models = [m for m in E5_MODELS if m in readings]
    cols = {m: columns([readings[m][i] for i in ids], gold) for m in models}
    flags = {m: error_flags(cols[m], factors) for m in models}
    errors = {m: error_table(flags[m], factors, levels) for m in models}
    section = {}
    for m in models:
        by_factor = {
            f: {"n": counts(cols[m], factor == f), **values(cols[m], (factor == f).astype(float))}
            for f in (SEED_FACTOR, *FACTORS)
            if (factor == f).any()
        }
        section[m] = {
            "n": counts(cols[m]),
            "all": estimates(cols[m], np.ones(len(ids)), taken),
            "by_factor": by_factor,
        }
    out: dict[str, Any] = {
        "items": len(ids),
        "seeds": len(set(seeds)),
        "items_by_factor": {f: factors.count(f) for f in (SEED_FACTOR, *FACTORS) if f in factors},
        "errors": errors,
        "metrics": section,
    }
    if rules is not None:
        mine = columns([rules[i] for i in ids], gold)
        out["rule_reader"] = error_table(error_flags(mine, factors), factors, levels)

    # the GEE, reader by reader: the model of factor and model with their interaction has a
    # cell for every factor and reader, so the fit of a reader's rows on factor alone gives
    # that reader's coefficients and the robust variance of its contrasts. The rows are those
    # of the long table: each unedited seed item three times, once under each criterion. A
    # cell whose error rate is 0 or 1 has no finite coefficient and is left out of the fit of
    # its reader; the intercept is the first seed cell that is left in
    present = [f for f in (SEED_FACTOR, *FACTORS) if f in factors]
    item, level = long_table(factors)
    within = np.array(seeds)[item]
    cells = [c for c in (*SEED_CELLS, *FACTORS) if (level == c).any()]
    fits: dict[str, dict[str, Any]] = {}
    names: dict[str, list[str]] = {}
    flat: dict[str, list[str]] = {}
    reference: dict[str, str] = {}
    for m in models:
        y = long_outcome(flags[m], item, level)
        found = {c: rate(y, level == c) for c in cells}
        flat[m] = [c for c in cells if found[c]["errors"] in (0, found[c]["items"])]
        fitted = [c for c in cells if c not in flat[m]]
        if not fitted or fitted[0] not in SEED_CELLS:
            continue
        keep = np.isin(level, fitted)
        x, names[m] = design(level[keep], [m] * int(keep.sum()), fitted, [m])
        fits[m], reference[m] = gee(y[keep], x, list(within[keep])), fitted[0]

    def contrast(f: str, m: str) -> dict[str, Any] | None:
        """The Wald test of a factor against the seed rows under its criterion in one model;
        None where one of the two cells has no coefficient, or the contrast no finite positive
        variance."""
        if m not in fits:
            return None
        weights = np.zeros(len(names[m]))
        for cell, sign in ((f, 1.0), (seed_cell(f), -1.0)):
            if cell == reference[m]:
                continue
            if f"factor[{cell}]" not in names[m]:
                return None
            weights[names[m].index(f"factor[{cell}]")] = sign
        return wald(fits[m], weights)

    entries = []
    for m in E5_MODELS:
        for f in FACTORS:
            entry: dict[str, Any] = {"model": m, "factor": f, "primary": m in PRIMARIES}
            if m not in flags or f not in present or SEED_FACTOR not in present:
                reason = skipped.get(m, "no item of the factor, or no unedited seed item")
                entries.append(entry | {"evaluable": False, "why": reason, "p": 1.0})
                continue
            edited, plain = (factor == f).astype(float), (factor == SEED_FACTOR).astype(float)
            # a side that lies on one seed is the same in every draw that holds it, and adds
            # nothing to a robust variance: the seeds are counted side by side
            entry["seeds"] = {
                side: len(set(within_seed[items > 0]))
                for side, items in (("edited", edited), ("unedited", plain))
            }
            if min(entry["seeds"].values()) < 2:
                why_not = "the edited items, or the unedited items, lie on fewer than two seeds"
                entries.append(entry | {"evaluable": False, "why": why_not, "p": 1.0})
                continue
            # one definition of error on both sides: the criterion of the factor
            error = held_to(flags[m], seed_cell(f)).astype(float)
            here, there = rate(error, edited), rate(error, plain)
            entry |= {
                "evaluable": True,
                "against": seed_cell(f),
                "edited": here,
                "unedited": there,
                "difference": here["rate"] - there["rate"],
                "log_odds_difference": log_odds_gap(here, there),
                "gee": contrast(f, m),
                "bootstrap": drawn_contrast(error, edited, plain, taken),
            }
            if f in STANDING_FACTORS:
                entry |= standing(cols[m], error, factor, f)
            entries.append(entry)

    # the procedure of the twelve: the cells and the fits of the primaries decide it, and no
    # other model's
    primaries = [m for m in PRIMARIES if m in flags]
    tested = [e for e in entries if e["evaluable"] and e["primary"]]
    flat_cells = sum(len(flat[m]) for m in primaries)
    why = ""
    if SEED_FACTOR not in present or not primaries:
        why = "no unedited seed item, or no primary that ran"
    elif flat_cells:
        why = f"the error rate is 0 or 1 in {flat_cells} cells of factor by primary"
    elif not all(fits[m]["converged"] for m in primaries):
        why = "the fit of a primary does not converge"
    elif any(e["gee"] is None for e in tested):
        why = "a contrast of a primary has no finite positive variance"
    usable = not why
    for entry in entries:
        if entry["evaluable"]:
            wald_stands = usable if entry["primary"] else entry["gee"] is not None
            entry["p_from"] = "gee" if wald_stands else "bootstrap"
            entry["p"] = float(entry[entry["p_from"]]["p"])
    registered = family([e for e in entries if e["primary"]])
    out["gee"] = {
        "computed": bool(usable),
        "why_not": why or None,
        "method_in_force": "the GEE with its robust variance"
        if usable
        else "maximum likelihood with a cluster bootstrap over seeds",
        "observations": len(level) * len(primaries),
        "clusters": len(set(seeds)),
        "cells_at_0_or_1": {m: lost for m, lost in flat.items() if lost},
        "reference_cell": {m: reference[m] for m, fit in fits.items() if fit["converged"]},
        "coefficients": {
            m: dict(zip(names[m], map(float, fit["beta"]), strict=True))
            for m, fit in fits.items()
            if fit["converged"]
        },
    }
    out["tests"] = registered
    out["other_models"] = [e for e in entries if not e["primary"]]
    plain = factor == SEED_FACTOR
    out["seed_items"] = {
        m: {
            **{
                part: rate(flags[m][part], plain)
                for part in ("not_correct", "certainty_wrong", "stale_wrong")
            },
            "cells": {cell: rate(held_to(flags[m], cell), plain) for cell in SEED_CELLS},
        }
        for m in models
    }
    out["flags"] = {
        m: [[i, int(flags[m]["error"][k]), int(cols[m]["parsed"][k])] for k, i in enumerate(ids)]
        for m in models
    }
    return out


def e5_lines(report: Mapping[str, Any]) -> list[str]:
    """The short table of an E5 result: error rates by factor and model, and the twelve tests."""
    names = [f for f in (SEED_FACTOR, *FACTORS) if f in report["items_by_factor"]]
    lines = [
        f"E5: {report['items']} items of {report['seeds']} seeds; {report['gee']['method_in_force']}",
        f"{'error rate':18s} " + " ".join(f"{name[:9]:>9s}" for name in names),
    ]
    for model, table in report["errors"].items():
        cells = " ".join(f"{table['by_factor'][name]['rate']:9.3f}" for name in names)
        lines.append(f"{model:18s} {cells}")
    for test in report["tests"]:
        if not test["evaluable"]:
            lines.append(f"{test['model']} {test['factor']}: not evaluable, p = 1")
            continue
        lines.append(
            f"{test['model']} {test['factor']}: {test['edited']['rate']:.3f} against "
            f"{test['unedited']['rate']:.3f} unedited, p = {test['p']:.4f}, Holm "
            f"{test['p_holm']:.4f}{' *' if test['holds'] else ''}"
        )
    return lines


def run_e5(args: argparse.Namespace) -> int:
    gold_data = gold_bytes(
        args.gold,
        args.expect_gold_sha256,
        "--expect-gold-sha256",
        "the gold of the minimal pairs",
        "the generator writes it to the key folder",
    )
    frozen_rules()
    out, _ = ev.output_paths(args.out)
    skipped = declared(args.not_run, E5_MODELS)
    item_data = sealed_counts.file_bytes(args.items, "the item file of the minimal pairs")
    items = {row["item_id"]: row for row in read_jsonl(item_data, "the item file")}
    rows = read_table(gold_data, MP.GOLD_COLUMNS, "the gold of the minimal pairs")
    golds: dict[str, Gold] = {}
    bad = 0
    for row in rows:
        try:
            item = items[row["item_id"]]
            same = all(
                str(item[name]) == row[name] for name in ("seed_id", "factor", "level")
            ) and row["factor"] in (SEED_FACTOR, *FACTORS)
            seedless = not row["seed_id"]
            if not same or seedless or (row["factor"] == SEED_FACTOR) != bool(item["is_seed"]):
                raise ValueError("another seed, factor or level than the item file")
            golds[row["item_id"]] = gold_of(row["item_id"], row, item_anchor(item), row["stale"])
        except (KeyError, ValueError):
            bad += 1
    faults = {
        "rows of no item, of another seed, factor or level, or that cannot be read": bad,
        "rows of a repeated item": len(rows) - bad - len(golds),
        "items without a gold row": len(set(items) - set(golds)),
    }
    if any(faults.values()):
        found = "; ".join(f"{n} {fault}" for fault, n in faults.items() if n)
        refuse(f"the gold is not the gold of the item file: {found}")
    runs = gather(
        args.out_root,
        {E5_TEMPLATE: E5_LINE},
        E5_MODELS,
        skipped,
        "e5",
        list(items),
        "the minimal pairs",
        item_data,
    )
    readings = {model: given for (model, _), given in runs.readings.items()}
    rules = {i: rule_reading(item) for i, item in items.items()}
    scored = score_e5(list(items), golds, items, readings, skipped, rules)
    flags = scored.pop("flags")
    late = sum(1 for item in items.values() if item.get("seed_period") == "test")
    report = {
        "about": ABOUT_E5,
        "registered": registered_record(),
        "inputs": {
            "gold": args.gold.as_posix(),
            "gold_sha256": sealed_counts.sha256(gold_data),
            "items": args.items.as_posix(),
            "items_sha256": sealed_counts.sha256(item_data),
            "item_ids_sha256": lp.ids_sha256(items),
            "plan_sha256": runs.plan_sha256,
            "code": code_record(),
        },
        "items_of_test_period_seeds": late,
        "runs": {model: found[E5_TEMPLATE] for model, found in runs.records.items()},
        "not_run": dict(skipped),
        "not_run_checked": runs.checked,
        **scored,
        "per_item": {
            "columns": ["item_id", "error", "parsed"],
            "error": "an edited item by the criterion of its factor, an unedited item by the "
            "E2 rule",
            "readers": flags,
        },
        "where_the_plan_is_silent": list(WHERE_THE_PLAN_IS_SILENT),
    }
    ev.write_new(out, report_text(report))
    print("\n".join(e5_lines(report)))
    print(f"wrote {out.as_posix()}")
    return 0


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = sealed_counts.Parser(
        prog="python -m analysis.coling.literal_scores",
        description=(__doc__ or "").splitlines()[0],
        allow_abbrev=False,
    )
    commands = ap.add_subparsers(dest="command", required=True, parser_class=sealed_counts.Parser)

    def common(
        sub: argparse.ArgumentParser, gold: Path | None, items: Path | None, not_run: str
    ) -> None:
        sub.add_argument("--expect-gold-sha256", help="sha256 of the gold file")
        sub.add_argument("--gold", type=Path, default=gold, help="the gold file")
        sub.add_argument("--items", type=Path, default=items, help="the registered item file")
        sub.add_argument("--out-root", type=Path, default=lp.OUT_ROOT, help="the reading runs")
        sub.add_argument("--out", type=Path, help="the result file to write; it must not exist")
        sub.add_argument("--not-run", action="append", default=[], metavar=not_run)

    e2 = commands.add_parser("e2", allow_abbrev=False, help="literal reading against the gold")
    common(e2, None, None, "MODEL[/TEMPLATE]=REASON")
    e2.add_argument("--audit-dir", type=Path, default=S.OUT, help="the folder of the literal task")
    e2.add_argument("--key", type=Path, default=None, help="the sampler's key of the sample")
    e2.add_argument("--events", type=Path, default=S.EVENTS, help="the open events table")
    e2.add_argument("--guide", type=Path, default=S.GUIDE, help="the guide")
    e2.add_argument("--convention-items", type=Path, default=None)
    e2.add_argument("--expect-convention-sha256", default=None)
    e2.set_defaults(run=run_e2)

    e5 = commands.add_parser("e5", allow_abbrev=False, help="minimal pairs")
    common(e5, E5_GOLD, E5_ITEMS, "MODEL=REASON")
    e5.set_defaults(run=run_e5)
    args = ap.parse_args(None if argv is None else list(argv))
    if args.command == "e2":  # the files of the literal task lie under its folder
        args.gold = args.gold or args.audit_dir / A.GOLD
        args.items = args.items or args.audit_dir / E2_ITEMS
        args.key = args.key or args.audit_dir / S.KEYS_DIR / E2_KEY
        args.convention_items = args.convention_items or args.audit_dir / E2_CONVENTION_ITEMS
    for name, value in sorted(vars(args).items()):
        if name != "out" and isinstance(value, Path) and sealed_counts.in_sealed_folder(value):
            refuse(f"--{name.replace('_', '-')} lies in a sealed folder; no sealed file is read")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = arguments(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
