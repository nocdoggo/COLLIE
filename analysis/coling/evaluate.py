"""The registered evaluator of the COLING 2027 study: the dev losses behind the one registered
model selection, and the confirmatory results over the sealed test outcomes (PLAN.md sections 4,
5 (E3 and E4), 6, 7.2, 8 and 13).

It is the one program that reads ``external_data/sealed/outcomes_test.csv.gz`` after the
counts-only code. It never prints or writes anything about a single statement: every output is a
count, a mean, an interval or a p-value over statements and shortage episodes.

What is registered here, as one constant each (set once before registration; every result file
records which value was in force):

* ``P_VALUE_SOURCE``: where the registered p-values come from (``P_VALUE_SOURCES``). With
  ``S_g`` and ``n_g`` the sum of the paired differences and the number of statements of episode
  ``g``, ``G`` episodes, ``N`` statements, ``delta = sum S_g / N``, the cluster-robust standard
  error ``se = sqrt(G / (G - 1) * sum (S_g - delta n_g)^2) / N`` and ``t = delta / se``:

  - ``percentile``: the percentile p-values of the draft, now a sensitivity analysis of PLAN
    section 6 (``predictors.p_values`` on the draws of ``predictors.bootstrap_means``):
    one-sided ``(1 + #{delta* <= 0}) / (B + 1)``, two-sided twice the smaller of that and its
    mirror image, at most 1. ``delta*`` is the mean of the paired differences over the drawn
    episodes, which is the difference of the two mean losses; a draw whose differences sum to
    zero up to rounding is zero and counts on both sides (``drawn_deltas``);
  - ``studentised``: the bootstrap-t on the same draws, ``t* = (delta* - delta) / se*`` with
    ``delta*`` and ``se*`` computed on the drawn episodes; one-sided ``(1 + #{t* >= t}) / (B +
    1)``, two-sided equal-tailed (twice the smaller one-sided p-value, at most 1);
  - ``studentised_symmetric``: the same draws, two-sided ``(1 + #{|t*| >= |t|}) / (B + 1)``; its
    one-sided p-values are those of ``studentised``;
  - ``sign_flip_t``: the studentised sign-flip test (the wild cluster bootstrap-t with the null
    imposed and signs as weights): each sign pattern ``s`` gives the data ``s_g S_g`` and their
    statistic ``t° = delta° / se°``, computed as ``t``; one-sided ``#{t° >= t}`` and two-sided
    ``#{|t°| >= |t|}`` over the patterns, counted as the sign-flip test counts;
  - ``larger_of_studentised_and_sign_flip_t``: on each side the larger of the ``studentised``
    and the ``sign_flip_t`` one-sided p-values, so that a test rejects only when both do; its
    two-sided p-value is twice the smaller of the two, at most 1.

  A draw or a pattern whose standard error is zero gives a statistic of plus or minus infinity,
  by the sign of its numerator, and of zero when the numerator is zero too. Every procedure is
  computed and reported for every contrast, with ``sign_flip``, the cluster sign-flip test on
  the episode sums (one of the sensitivity analyses of PLAN section 6); the constant says
  which one enters Holm and the probe rule. The bootstrap draws are those of the plan (10,000,
  seed 20261001); the sign patterns are every one of the ``2^G`` with at most 13 episodes,
  else 10,000 drawn with the same seed (``(1 + #) / (B + 1)``; the exact share when every
  pattern is used). The p-values are those of ``size_check.py`` on the same differences, but
  where rounding settles a statistic. ``size_check.py`` divides without the tolerance for a
  zero (``rounding_tolerance``), so when a standard error is zero only up to rounding
  (differences without variance) its statistic is whatever the division leaves, and this
  file's is the plan's; and when the value tested is the estimate itself, so that the observed
  statistic is zero up to rounding, the two can count the draws that tie with it differently.

  The constant also says how the intervals of the six confirmatory contrasts and of
  ``Delta_GBM`` are made (``interval_method``; every result records it as ``interval_method``):

  - under ``larger_of_studentised_and_sign_flip_t`` they hold the values ``delta0`` that the
    registered test does not reject (``larger_of_interval``): at coverage ``1 - a`` the
    interval runs from the smallest ``delta0`` whose one-sided p-value for a larger contrast
    is not below ``a / 2`` to the largest ``delta0`` whose one-sided p-value for a smaller
    contrast is not below ``a / 2``. A value ``delta0`` is tested as zero is, on the sums ``S_g
    - delta0 n_g`` (``larger_of_at``). Each end is found by bisection between ``delta`` and
    the value 50 standard errors away, in 60 halvings, and is the last value not rejected. An
    end is written as unbounded when the test does not reject 50 standard errors away (it may
    reject further away, which the interval does not show): None here, null in the result
    file, ``-inf`` or ``inf`` in the printout. Differences without any variance have one
    p-value at every value but the estimate: an end is then the estimate itself when a value
    one unit away (or the size of the estimate, if that is more) is rejected, and unbounded
    when it is not. The coverage is 95%; H2 also carries its 90% interval;
  - under every other candidate they are the percentile intervals of the bootstrap draws, at
    95% and 90%, as in the draft of the plan.

  The percentile intervals are reported under ``percentile`` for every contrast given in full
  (the six tests and the probe), whatever the constant; a contrast given in short,
  ``Delta_GBM`` among them, carries its ``ci95`` alone. The losses of single predictors and
  every secondary but ``Delta_GBM`` keep 95% percentile intervals. They are descriptions,
  except in the overconfidence criterion, which the plan words on its percentile intervals.
* ``H3_COMPARATOR``: what the model's best condition is compared with in H3. ``base_rate`` is
  the base rate by listing age, the comparator of the plan (section 6, DECISIONS 26);
  ``gbm_structured`` is the structured-only gradient-boosted model, the comparator of the draft;
  ``better_on_dev`` is the one of the two with the lower primary loss on the scoreable dev
  statements, the rule that also picks the model's best condition. Whatever the rule, the
  contrast of the selected condition with each of the two is reported beside H3, on the same
  statements and the same draws: with the base rate in force, the contrast with the
  structured-only model is the plan's ``Delta_GBM`` (also under ``secondaries``, ``delta_gbm``).

Neither constant can be set from outside this file: no command takes an option for it and no
environment variable is read, and a value outside its candidates is a refusal. The comparator of
H3 is worked out from the constant and the dev losses a selection file records; a selection file
that names another one is refused.

Commands
--------
``dev --model M --out FILE``. Open data only. Reads the dev runs of ``M`` (the lines ``dev-a``,
``dev-b`` and ``dev-c`` of the launcher's plan), fits every model-free predictor on the fit
split (``power.fit_and_predict``), and writes one small JSON: the primary loss of conditions
(a), (b) and (c) on the scoreable dev statements with its 95% interval, the bounds of section
7.2 over the dev statements the runs read, the dev outcome mix, the selection (the lowest
primary loss as the file records it, at six decimals; a tie goes to the earlier of a, b, c),
the dev losses of the model-free predictors and the comparator of H3 under the rule in force.
The file is what the freeze amendment records, with its sha256, and what ``confirmatory``
reads behind that sha256.

``baselines --out FILE``. Open data only. Refits every model-free predictor on fit and dev
together, predicts the eligible list, and writes the sha256 of those predictions (six decimals)
with the counts they rest on, so that the freeze amendment can hold the hash before any test
call. ``--table`` also writes the predictions themselves (they are not outcomes).

``check``. Says what is missing for a confirmatory evaluation: the plan, the eight confirmatory
runs, their item sets against the registered lists, the horizons they asked about, the item
files against the build, the two selection files (against their sha256 when
``--expect-selection-sha256 MODEL=H`` is given), and an episode and a company for every
eligible statement. It reads the first-sight columns of the statement table only, no outcome of
any period, and never touches the sealed file (not even to see whether it is there). Status 0
when nothing is missing, 3 otherwise.

``confirmatory --expect-sha256 H --expect-eligible-sha256 H --expect-baselines-sha256 H
--expect-selection-sha256 MODEL=H --expect-selection-sha256 MODEL=H --out FILE``. The four kinds
of hash are those the registration and the freeze amendment record: the sealed file, the
eligible list, the model-free predictions (as ``baselines`` prints them) and the selection file
of each primary (as written by ``dev``). All are required, a selection hash for every primary
that is not declared not evaluable; each is checked before the sealed file is read.
``--not-evaluable MODEL=REASON`` declares that a primary's confirmatory runs could not be
completed on its registered route (PLAN section 6, "Confirmatory runs"): its runs are not read
and its three tests stay in the family with p = 1. Without it a missing or partial run is a
refusal; with every primary declared no test of the family can be computed, and the command
refuses without opening the sealed file. In this order:

1. the open inputs (the eligible list behind its registered hash; the statement table, the
   events table and the counts file of one build);
2. the completeness check of ``check`` (below); a single problem is a refusal;
3. the refit of every model-free predictor on fit and dev and its predictions on the eligible
   list, held to the hash of the freeze; the predictions of every condition of both primaries
   from their stored readings;
4. only then the sealed file: read as bytes, hashed, and parsed only when the hash is the one
   given on the command line; its rows are checked against the events table and the list by
   the checks of ``sealed_counts.py``, and the outcomes are attached by
   ``dataset.attach_outcomes``;
5. the probe rule of E4 for each primary, decided from the probe alone;
6. the six tests, Holm, the bounds and the secondaries;
7. ``FILE`` (JSON) and a short table beside it (``.md``). Neither may exist: nothing is
   overwritten.

The completeness check (PLAN section 6, "Confirmatory runs" and "Evaluator"). The runs are
those the launcher's plan (``<out-root>/_launch/plan.json``) lists in its phase
``confirmatory`` for a primary: the lines ``e3-a``, ``e3-b``, ``e3-c`` and ``e4-probe``, every
shard of each. The readings are pooled by ``read.collect_readings`` over those run names and no
other, so a trial, dev or secondary run under the same condition is never mixed in. A group is
ready when:

* the plan names no path in a sealed folder (its output root, its item files, its track
  records): the check hashes the files a plan names, so such a plan is not followed at all;
* the plan's two item lists are the registered ones (the ids of the eligible list and of its
  probe subset) and their files are those the counts file of the dataset builder records;
* the plan holds the registered route (the model id and provider pin that are sent) and the
  frozen pin of the template;
* every run is finished by the launcher's own test (``launch.run_state``: the manifest says
  complete, for the model id and provider pin, the template and its pin, the shard, the item
  file and item set, and the track record the plan names), its item file and track record
  are still the files the plan was made with, and its readings file has the hash its manifest
  records;
* a run of a template that shows a track record read the record of its phase (the fit split
  for the dev runs, fit and dev for the confirmatory ones), by the plan and by its manifest;
* the pooled rows are of one model and condition, with no duplicate, one sample per item, an
  echo the harness accepts on every row (``read.echo_acceptable``), and exactly the items of
  the list;
* every row carries the registered model id and provider pin, the frozen template pin, no
  masking, shift or temperature, a status, reading and fallback flag that agree, a stored
  reading that the harness's own parser accepts (the schema of its kind and the semantic
  checks, on the stored object: ``reading_accepted``), no answer served as another model or,
  by its stored name, by another provider than the pinned one, no track record that reaches
  the item's date, and, for a predictive template, the horizons of the statement table (the
  stated end and 90 days later; 90 and 180 days after the statement date for the probe);
* each selection file is the one hashed at the freeze, of this model, this statement table and
  this comparator rule; it selects the condition its own dev losses give and names the
  comparator the rule in force gives;
* every eligible statement has a shortage episode and a company (the clusters of the
  resampling), so that nothing stops for it once the sealed rows are in memory.

The model-free predictors have no stored run: the command refits them itself and fixes their
predictions before the sealed file is read; ``--expect-baselines-sha256`` holds them to the hash
the ``baselines`` command printed, and a refit that gives other predictions (another
environment, say: PLAN section 8) is a refusal.

How readings become predictions (PLAN sections 4 and 8).

* Conditions (a) and (b) and the probe: the two probabilities and the five quantiles as given.
  An answer with ``P(E_end90)`` below ``P(E_end)`` is kept and counted.
* A predictive reading that failed (flag ``base_rate`` in the stored row) is replaced by the
  base-rate predictor's output for that statement at the same horizons, and counted.
* Condition (c): the end of the model's literal interval, in days from the statement date,
  goes through the slip calibrator (``SlipCalibrator.predict`` with ``reading_days``); the cell
  is the statement's own. A failed literal reading (flag ``abstain``) and an ``ABSTAIN``
  interval take the calibrator's no-date table.
* A literal interval given for a depletion or a discontinuation statement, or with no
  statement, is not a stated period (section 2.5: the period the text gives for recovery, or
  for the next delivery) and takes the no-date table too; such readings are counted
  (``PERIOD_TYPES``).
* The fit behind the base rate and the calibrator is the fit split for the dev command and fit
  and dev together for the confirmatory one.

The tests (PLAN section 6). Every contrast is the comparator's mean primary loss minus the
tested predictor's, on the scoreable statements of the item set, resampled by shortage episode
(10,000 draws, seed 20261001). H1 (one-sided): (a) against (b). H2 (two-sided): rules plus slip
against (c), with an equivalence reading (``equivalence``). Under the registered test the rule
is on two p-values: equivalence is declared when the p-value for a smaller contrast at ``delta0
= H2_MARGIN`` and the p-value for a larger contrast at ``delta0 = -H2_MARGIN`` are both below
0.05, the level at which the 90% interval is cut. As a rule of thumb that is the 90% interval
of the registered test lying strictly inside plus or minus ``H2_MARGIN``; the two can part
(``equivalence``), so the interval is reported beside the two p-values and its ends are not
what is read. Under a source with percentile intervals it is declared when the 90% percentile
interval lies strictly inside the margin. H3 (two-sided): the comparator against the model's
selected condition; beside it stand the contrasts of that condition with both predictors that
read no text, on the same statements and draws (``Delta_GBM`` among them), and the number of
its answers that were not parsed. Holm's step-down runs over the six p-values at 0.05, and a
hypothesis holds when its adjusted p is below 0.05. Every H3 entry carries the flag
``beats_both_comparators``: true only when H3 holds in favour of the text (adjusted p below
0.05 and ``delta`` above zero) and the 95% interval of the contrast with the other predictor
that reads no text (``Delta_GBM`` under the base rate), made as the registered source makes it,
lies above zero; an unbounded lower end does not. The plan lets the paper write "value beyond
the structured fields" only then; the flag never enters the family.

Beside every confirmatory p-value, and never in Holm's rule, stand the sensitivity analyses of
the plan: the percentile p-values of the draft with the 95% percentile interval
(``p_values.percentile``, ``percentile.ci95``); the two parts of the registered p-value, each
on its own (``p_values.studentised`` and ``p_values.sign_flip_t``); and the cluster sign-flip
test on the episode sums (``p_values.sign_flip``). The bootstrap-t intervals, equal-tailed and
symmetric, are reported too (null when a draw has no variance). H2 has the same loss on both
sides wherever the model's reading is the rule's, so it also carries ``losses_differ``: the
number of statements and of episodes on which the two losses differ, and how many of those
episodes have a positive and how many a negative sum of the paired differences; an episode
whose differences cancel is counted apart (``differing``).

The probe rule (PLAN section 5, E4). Pinball loss at 0.5 of the probe's median against the
base rate's, on the probe statements whose time to recovery is not right-censored before the
cap, as a one-sided paired contrast at 0.05 with the p-value source in force. A primary that
beats the base rate is evaluated on its post-cutoff slice (``sealed_counts.CUTOFF_MONTH_ENDS``);
a slice with fewer than 50 scoreable statements makes its three tests not evaluable, with p = 1
in the family. A contrast over fewer than two episodes is not evaluable either, and a probe
that cannot be tested for that reason leaves the switch undecided and the model's three tests
not evaluable. The item set of each primary is fixed before any test is computed.

The overconfidence criterion (PLAN section 13; a secondary with no multiplicity claim). For each
primary it is read on condition (a) and ``E_end``, over every statement of the item set the
probe fixed, for the model and for the base rate by listing age on those same statements. A
failed answer of condition (a) is in it as the base-rate output that replaced it. Every value
has a 95% percentile interval by episode on the registered draws (``overconfidence``). A primary
without an item set, whose three tests are not evaluable, has no reading.

* Against outcomes. The mean of ``P(E_end)`` minus the largest frequency of ``E_end`` that the
  captures allow, every undetermined ``E_end`` counted as yes, whatever the other horizon event
  of the statement is: the least value that calibration in the large can take on the item set.
  The greatest value counts every undetermined ``E_end`` as no. The part is met when the least
  value is positive and its interval excludes zero. No scoreable set enters.
* Against a predictor that reads no text. The mean of ``P(E_end)`` minus the mean ``P(E_end)``
  of the base rate on the same statements, met when it is positive and its interval excludes
  zero. No outcome enters.
* The reading, one of five tried in the plan's order (``OVERCONFIDENCE_READINGS``): 1, the
  greatest value is negative with an interval that excludes zero (underconfident, and nothing
  else is written); 2, both parts are met; 3, only the second; 4, only the first; 5, neither.
  ``met`` is true for reading 2 alone.
* Beside it, for condition (a) and for the base rate on the same statements: both parts for
  ``E_end90``; both parts on the statements whose answer parsed (withheld when they would give
  the horizon events of a few statements: ``few``); calibration in the large on the scoreable
  statements with its interval, and the difference of the two predictors there with its
  interval; and the coverage of the 80% interval. The mean of ``P(E_end)`` minus the Turnbull
  share recovered by the stated end is left to a secondary scorer.

Wherever a predictor has its calibration in the large (``losses``), it also has the least and
the greatest value over every statement of its item set (``calibration_all_statements``), and
the base rate's on the same statements beside both (``beside_base_rate``).

Where the plan is silent, this file decides as follows, and the result file says so
(``WHERE_THE_PLAN_IS_SILENT``).

* The cluster sign-flip test on the episode sums counts as the studentised sign-flip test
  does: the exact share when every sign pattern is used, and a flipped statistic that falls
  short of the observed one by less than 1e-9 times the largest finite absolute flipped
  statistic counts as reaching it.
* The bootstrap-t part is also reported with a symmetric two-sided p-value, and with its own
  equal-tailed and symmetric intervals (``studentised``).
* Under ``percentile``, ``studentised``, ``studentised_symmetric`` and ``sign_flip_t`` the
  confirmatory contrasts and ``Delta_GBM`` carry percentile intervals: the plan words an
  interval of the test for the larger-of procedure only. Every contrast says which interval
  it carries (``interval_method``); the intervals of single-predictor losses, of calibration
  in the large and of the overconfidence criterion (a difference of two mean probabilities
  among them) are percentile intervals and carry no such field.
* The interval of the registered test: an end the search does not find is unbounded, and
  written as null. That says only that the test does not reject 50 standard errors away. It
  may reject further away, and the margin of H2 can be among those values: equivalence is
  then declared beside an end that is null.
* Under a source with percentile intervals, H2 equivalence is read from the 90% percentile
  interval, which must lie strictly inside the margin.
* The rule and the interval can part where the p-value does not fall steadily with the distance
  from the estimate: within a few rounding steps of an end, where the count behind a p-value
  can go either way, and further away when a few episodes hold most of the statements between
  them, where the sign-flip p-value can rise again. The search then ends on one of the values
  at which the verdict changes, and the rule is the one that counts.
* Under the rule ``better_on_dev``, a tie between the two comparators of H3 goes to the
  structured-only model.
* Every eligible statement needs an episode and a company before the sealed file is read.
* The bounds beside a contrast set every undetermined horizon event of the item set to no,
  then to yes, for both predictors at once.
* In the overconfidence criterion an interval excludes zero when both of its ends lie on one
  side of zero, and an end on zero does not; a draw whose values sum to zero up to rounding
  counts as zero; an item set of a single episode has no interval, so that neither part is met
  and the reading is the fifth.
* Beside a predictor's calibration in the large stands the base rate's on the same statements
  (under ``base_rate``), except in the base rate's own record; a record without a scoreable
  statement holds no calibration in the large, and so no least or greatest value either.
* A primary without an item set has no reading of the overconfidence criterion, and its line
  in the table and in the printout gives the reason: the probe could not be tested, the model
  has no slice inside the test split, or its post-cutoff slice holds fewer than 50 scoreable
  statements; the criterion is not read on such a slice, although its first part uses no
  scoreable set; a primary declared not evaluable, whose runs are not read, has no entry and
  no line.
* Beside the overconfidence criterion, the two parts on the answers that parsed
  (``parsed_only``) are withheld, their three counts apart, when 1 to 4 answers of condition
  (a) failed on the item set, or 1 to 4 parsed: with the figures over every statement they
  would give the horizon events of those few statements; the contrast of a test on the
  statements that both of its sides parsed (``both_sides_parsed``) is withheld in the same
  way, its two counts apart, when it leaves out or rests on 1 to 4 scoreable statements.

Refusals (status 1, the reason alone on the error stream, nothing written). A missing or wrong
hash; an output that exists or lies in a sealed folder; an open input in a sealed folder; files
of different builds; a declaration ``--not-evaluable`` whose reason is not printable text on
one line; anything the completeness check finds; a selection file that is missing, not the one
hashed at the freeze, of another model, of another statement table or of another comparator
rule, or that contradicts its own dev losses or the rule in force; a plan or stored runs on
which the check itself stops, and readings that cannot be turned into predictions (the type of
the error alone is given); predictions that are not the ones hashed at the freeze, or a
statement left without one; every primary declared not evaluable; a sealed file that is not
the outcome table of this events table and this list; and any stop once the sealed rows are in
memory, inside the rules or in putting the results into the texts of the two files and of the
printout, whose message is withheld. Both texts are made, and shown to be writable as UTF-8,
before either file exists. Two stops are left as they are: when the table cannot be written
after the result file (the disk, say), the refusal leaves the result file without its table;
and when the printout itself fails after both files are written, the files are complete and
the error is not a refusal. A refusal names runs and gives counts, never an item.

The result file. ``registered`` (the constants in force, with how the intervals are made);
``inputs`` (the sha256 of every file read and of the code); ``refit``; ``h3`` (the comparator
and the two selections); ``not_evaluable_by_declaration``; ``runs`` (the sha256 of each
readings file, rows, statuses, echoes, parse and refusal rates and fallback counts per model
and condition); ``items`` (counts on the eligible list);
``probe`` and ``item_sets`` per primary; ``family`` (six entries in the order H1, H2, H3 for
each primary: comparator, tested, sides, item set, statements, episodes, the two losses,
``delta``, ``ci95``, ``ci90`` (under the interval of the registered test: for H2 only),
``interval_method`` (how ``ci95`` and ``ci90`` were made), ``percentile`` (the 95% and 90%
percentile intervals), ``p_values`` of every procedure, ``studentised``, ``sign_flip``, ``p``,
``p_holm``, ``holds``, ``reading``, ``bounds``, ``both_sides_parsed``,
``scoreable_not_parsed``, for H2 ``equivalence`` and ``losses_differ``, and for H3 ``beside``
and ``beats_both_comparators``). Every other contrast is given in short, with its own
``interval_method`` beside its ``ci95``. An interval end that is null is unbounded on that
side. ``secondaries`` (the model-free contrasts, H2 on the
month-and-year form, ``Delta_GBM``, H3 with each condition in place of the selected one, the
post-cutoff slice, statements first captured by the stated end, clusters by company, the two
other statement-level brackets, definition A, the decomposition of E3, and under
``overconfidence_of_condition_a`` the overconfidence criterion of section 13 for each primary
with an item set: ``criterion``, ``items``, ``statements``, ``episodes``;
``against_outcomes`` and ``against_base_rate``, each by ``E_end`` and ``E_end90``;
``reading`` (1 to 5), ``reading_in_words`` and ``met``; and, reported beside the criterion,
``scoreable``, ``parsed_only`` and ``coverage_80``; the key ``base_rate`` inside a block holds
the same quantities for the base rate on the same statements; ``parsed_only`` holds
``not_parsed``, ``statements``, ``episodes`` and ``withheld`` alone when its figures are
withheld); ``losses`` (every score of section 7.2 per predictor: the model-free ones on every
eligible statement, the conditions of a primary on its item set;
``calibration_in_the_large`` on the scoreable statements and ``calibration_all_statements``
with the least and the greatest value over all of them);
``where_the_plan_is_silent``; ``not_computed_here`` (what the plan registers and this file
does not compute: the descriptives of E1, the secondary models and lists, and the rest).

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.evaluate dev --model llama-3.3-70b \\
        --out analysis/coling/out/h3_selection_llama-3.3-70b.json
    PYTHONPATH=. python -m analysis.coling.evaluate baselines \\
        --out analysis/coling/out/baseline_predictions.json
    PYTHONPATH=. python -m analysis.coling.evaluate check
    PYTHONPATH=. python -m analysis.coling.evaluate confirmatory \\
        --expect-sha256 <sha256 of the sealed file> \\
        --expect-eligible-sha256 <sha256 of analysis/coling/out/eligible_e3.csv> \\
        --expect-baselines-sha256 <sha256 the baselines command printed> \\
        --expect-selection-sha256 llama-3.3-70b=<sha256 of its selection file> \\
        --expect-selection-sha256 deepseek-v3=<sha256 of its selection file> \\
        --out analysis/coling/out/confirmatory.json
    PYTHONPATH=. python -m pytest analysis/coling/test_evaluate.py -q -p no:cacheprovider
"""

from __future__ import annotations

import argparse
import io
import json
import os
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pandas as pd
import sklearn

from analysis.coling import dataset, forms, gbm, power, sealed_counts
from analysis.coling import launch as lp
from analysis.coling import predictors as P
from analysis.coling import read as rd

SEED = P.SEED
DRAWS = P.DRAWS
FAMILY_ALPHA = power.FAMILY_ALPHA
TESTS = power.TESTS
P_VALUE_SOURCES = (
    "percentile",
    "studentised",
    "studentised_symmetric",
    "sign_flip_t",
    "larger_of_studentised_and_sign_flip_t",
)
"""The candidates of ``P_VALUE_SOURCE`` (see the module docstring)."""
P_VALUE_SOURCE = "larger_of_studentised_and_sign_flip_t"
"""REGISTERED CONSTANT. The procedure whose p-values enter Holm and the probe rule: the
larger of the bootstrap-t and the studentised sign-flip p-values (PLAN section 6)."""
SENSITIVITY = "sign_flip"
"""The cluster sign-flip test on the episode sums: one of the sensitivity analyses of PLAN
section 6, reported for every contrast and never a source of the registered p-values."""
PROCEDURES = (*P_VALUE_SOURCES, SENSITIVITY)
"""Every procedure whose p-values are reported for every contrast."""
SIDES = ("one_sided", "one_sided_lower", "two_sided")
"""The p-values of a procedure: for ``delta > 0``, for ``delta < 0``, and two-sided."""
PERCENTILE_INTERVAL = "percentile"
"""An interval made from the quantiles of the bootstrap draws of the contrast."""
TEST_INTERVAL = "values_not_rejected_by_the_registered_test"
"""An interval made of the values of the contrast that the registered test does not reject."""
TEST_INTERVAL_SOURCES = ("larger_of_studentised_and_sign_flip_t",)
"""The p-value sources under which the confirmatory contrasts and ``Delta_GBM`` carry the
interval of their own test (PLAN section 6, "Intervals"). Under any other source they carry
percentile intervals."""
LEVELS = {"ci95": 0.95, "ci90": 0.90}
"""The intervals of a contrast and their coverage. Every confirmatory contrast carries the
first; H2 carries the second too, beside its equivalence reading."""
EQUIVALENCE_LEVEL = "ci90"
"""The key of the second interval H2 carries, the 90% one. Under the registered test
equivalence is read from two p-values at the level that cuts this interval (``tail_of``), and
the interval is reported beside them; under a source with percentile intervals the interval
itself is read."""
INTERVAL_REACH = 50.0
"""The interval of the registered test is searched this many standard errors either side of the
estimate. An end that is not found there is written as unbounded, although the test may reject
values further away."""
INTERVAL_STEPS = 60
"""Halvings of the search for each end of that interval."""
H3_COMPARATORS = ("gbm_structured", "base_rate", "better_on_dev")
H3_COMPARATOR = "base_rate"
"""REGISTERED CONSTANT. The rule that names the comparator of H3: ``base_rate`` (the base rate
by listing age) is the plan's wording since 1 October; ``gbm_structured`` was the draft's."""
COMPARATOR_CANDIDATES = ("gbm_structured", "base_rate")
"""The two predictors that read no text, which ``better_on_dev`` chooses between (a tie goes to
the first) and which both stand beside H3."""
H2_MARGIN = 0.02
PROBE_ALPHA = 0.05
PROBE_LEVEL = 0.5
MIN_SLICE = 50
"""A post-cutoff slice is analysed only with at least this many scoreable statements."""
MIN_SHOWN = 5
"""Fewer statements than this, and at least one, are a few (``few``). Beside the overconfidence
criterion, the figures on the answers that parsed are withheld when the answers that failed are
a few, or those that parsed are: next to the figures over every statement they would give the
horizon events of those statements."""
MIN_EPISODES = 2
EXACT_FLIPS_UP_TO = 13
"""With at most this many episodes the sign-flip test enumerates every sign pattern."""
PRIMARIES = rd.PRIMARIES
CONDITIONS = ("a", "b", "c")
PROBE = "probe"
PERIOD_TYPES = ("recovery", "next_delivery")
"""The statement types whose literal interval is a stated period (PLAN section 2.5)."""
STATUSES = ("ok", "repaired", "failed", "refused")
RULES = "rules_plus_slip"
BASE = "base_rate"
STRUCTURED = "gbm_structured"
MONTH_YEAR = "month_year"
LINES = {
    "dev": {"a": "dev-a", "b": "dev-b", "c": "dev-c"},
    "confirmatory": {"a": "e3-a", "b": "e3-b", "c": "e3-c", PROBE: "e4-probe"},
}
"""The lines of the run sheet that hold each condition, by phase of the launcher's plan."""
LISTS = {"dev": "dev", "e3": "e3", PROBE: "probe"}
"""The launcher's keys of the three item lists the evaluator reads runs on."""
SEALED = sealed_counts.SEALED
SELECTION_NAME = "h3_selection_{model}.json"
TRACK_OF_PHASE = {"dev": "fit", "confirmatory": "fit+dev"}
"""The track record a run of each phase shows, as the launcher names it and as the record names
its own split (PLAN section 5, E3, condition b)."""
CLUSTER_COLUMNS = ("episode_id", "company_name")
"""The first-sight cells the resampling takes its clusters from: every eligible statement needs
both (the company for the registered secondary that resamples by company)."""
ALL_ITEMS = "every eligible statement"
SLICE_ITEMS = "the post-cutoff slice"
EVENTS = (("E_end", "p_a", "y_a"), ("E_end90", "p_b", "y_b"))
"""The two horizon events, each with the column of its probability in a table of predictions
and the column of its outcome in the typed frame (1, 0, or missing when undetermined)."""
OVERCONFIDENCE_CRITERION = (
    "PLAN section 13, for condition (a) and E_end over every statement of the item set, each "
    "value with its 95% percentile interval by episode. Against outcomes: the mean of P(E_end) "
    "minus the largest frequency of E_end the captures allow (every undetermined E_end counted "
    "as yes; the least value of calibration in the large) is positive with an interval that "
    "excludes zero. Against a predictor that reads no text: the mean of P(E_end) minus the mean "
    "P(E_end) of the base rate by listing age on the same statements is positive with an "
    "interval that excludes zero. met: both parts hold (reading 2)"
)
"""What the entry of a primary under ``overconfidence_of_condition_a`` is, in its own words."""
OVERCONFIDENCE_READINGS = {
    1: "the readings are underconfident relative to outcomes",
    2: "the readings are overconfident relative to outcomes",
    3: "the model states higher probabilities than the base rate, and the captures do not "
    "decide whether it is overconfident",
    4: "the model's probabilities exceed every frequency the captures allow; they were not "
    "shown to exceed the base rate's, and the excess is not put down to the reading",
    5: "overconfidence was not detected, which does not say that the readings are calibrated",
}
"""The five readings of the overconfidence criterion in the order PLAN section 13 tries them,
each in the words the plan gives the paper: (1) the greatest value of calibration in the large
(every undetermined ``E_end`` counted as no) is negative with an interval that excludes zero,
and nothing else of the list is written; (2) both parts hold; (3) only the second; (4) only the
first; (5) neither."""
MODEL_FREE_PAIRS = (
    ("base_rate", "gbm_text"),
    ("base_rate", "rules_plus_slip"),
    ("gbm_structured", "gbm_text"),
    ("gbm_structured", "rules_plus_slip"),
    ("base_rate", "gbm_structured"),
)
"""The registered model-free secondaries of H3 (PLAN section 6), as (comparator, tested): the
text-trained model and rules plus slip, each against the base rate and against the
structured-only model, and the structured-only model against the base rate."""
NOT_COMPUTED_HERE = (
    "the descriptives of E1 (hold rate, slip distribution by form and revision, bracket widths, "
    "counts by year, form, statement type and company)",
    "the H1 and H2 contrasts, the H3 contrast per condition and every metric of the six "
    "secondary models",
    "the accuracy of the rule reading on the 100-statement check, reported beside H2",
    "the minimum detectable differences reported beside a null (from the power code at the gate)",
    "the TBD, silent and stale-at-issue lists (stale-value uptake; TBD and silent against the "
    "base rate)",
    "sampled against verbalised quantiles (20 samples) and prompt variance (paraphrases)",
    "the name and date 2x2 of E4",
    "the fit that leaves out the dominant company, and the full-follow-up refit",
    "the sensitivity analyses of the recovery rule: the BL definition, leaving the list, and "
    "the Date Discontinued cell",
    "selective prediction (loss against abstention rate)",
    "the mean of P(E_end) minus the Turnbull share recovered by the stated end, reported beside "
    "the overconfidence criterion (a secondary scorer)",
    "the analysis by statement type of section 5, E3: the contrasts, the losses, calibration in "
    "the large and the overconfidence criterion on the recovery statements and on the "
    "next-delivery statements apart (a secondary scorer)",
    "E2, E5 and E7",
)
WHERE_THE_PLAN_IS_SILENT = (
    "the cluster sign-flip test on the episode sums, one of the sensitivity analyses, counts as "
    "the studentised sign-flip test does: the exact share when every sign pattern is used, and a "
    "flipped statistic short of the observed one by less than 1e-9 times the largest finite "
    "absolute flipped statistic reaches it",
    "the bootstrap-t part is also reported with a symmetric two-sided p-value, and with its own "
    "equal-tailed and symmetric intervals under studentised (null when a draw has no finite "
    "statistic)",
    "under a p-value source other than the larger-of procedure the confirmatory contrasts and "
    "Delta_GBM carry percentile intervals; every contrast says in interval_method which interval "
    "it carries; the intervals of single-predictor losses, of calibration in the large and of "
    "the overconfidence criterion (a difference of two mean probabilities among them) are "
    "percentile intervals and carry no such field",
    "an end of the interval of the registered test that the search does not find is unbounded "
    "and written as null: the test does not reject the value 50 standard errors from the "
    "estimate; it may still reject values further away, which the interval does not show, and "
    "when the margin of H2 is among them equivalence is declared beside an end that is null",
    "under a p-value source with percentile intervals, H2 equivalence is read from the 90% "
    "percentile interval and needs both ends strictly inside the margin",
    "the p-value of the registered test need not fall steadily with the distance from the "
    "estimate (the sign-flip part can rise again when a few episodes hold most of the statements "
    "between them): "
    "the search for an end of the interval then stops on one of the values at which the verdict "
    "changes, and the equivalence rule, which tests the margin itself, can differ from the "
    "interval",
    "under the rule better_on_dev, a tie between the two comparators of H3 goes to the "
    "structured-only model",
    "every eligible statement needs an episode and a company before the sealed file is read",
    "beats_both_comparators is false whenever H3 does not hold in favour of the text, including "
    "when it is not evaluable; the interval it reads is that of the registered source, and an "
    "unbounded lower end does not lie above zero",
    "the bounds beside a contrast set every undetermined horizon event of the item set to no, "
    "then to yes, for both predictors at once",
    "Murphy's decomposition cuts the statements, ordered by probability and then by id, into "
    "ten runs of equal length; the coverage of the 80% interval treats a bracket as closed",
    "definition A is one of the outcome variants that keep the item set the probe fixed",
    "in the overconfidence criterion an interval excludes zero when both of its ends lie on one "
    "side of zero, and an end on zero does not; a draw whose values sum to zero up to rounding "
    "counts as zero; an item set of a single episode has no interval, so that neither part is "
    "met and the reading is the fifth",
    "beside a predictor's calibration in the large stands the base rate's on the same statements "
    "(under base_rate), except in the base rate's own record; a record without a scoreable "
    "statement holds no calibration in the large, and so no least or greatest value either",
    "a primary without an item set has no reading of the overconfidence criterion, and its line "
    "in the table and in the printout gives the reason: the probe could not be tested, the model "
    f"has no slice inside the test split, or its post-cutoff slice holds fewer than {MIN_SLICE} "
    "scoreable statements; the criterion is not read on such a slice, although its first part "
    "uses no scoreable set; a primary declared not evaluable, whose runs are not read, has no "
    "entry and no line",
    "beside the overconfidence criterion, the two parts on the answers that parsed (parsed_only) "
    f"are withheld, their three counts apart, when 1 to {MIN_SHOWN - 1} answers of condition (a) "
    f"failed on the item set, or 1 to {MIN_SHOWN - 1} parsed: with the figures over every "
    "statement they would give the horizon events of those few statements; the contrast of a "
    "test on the statements that both of its sides parsed (both_sides_parsed) is withheld in "
    f"the same way, its two counts apart, when it leaves out or rests on 1 to {MIN_SHOWN - 1} "
    "scoreable statements",
)
"""The decisions every result file carries as ``where_the_plan_is_silent`` (see the module
docstring)."""
CODE = {
    f"{module.__name__.rsplit('.', 1)[-1]}.py": module.__file__
    for module in (dataset, forms, gbm, power, P, rd, lp, sealed_counts)
}
CODE = {"evaluate.py": __file__, **CODE}
ABOUT_DEV = (
    "Dev losses of one model's three conditions and the selection of its best condition for H3 "
    "(PLAN.md section 6). Train-period outcomes only; predictors fitted on the fit split."
)
ABOUT_BASELINES = (
    "The test predictions of the model-free predictors after the refit on fit and dev (PLAN.md "
    "sections 6 and 8), as a hash. Open data only."
)
ABOUT_RESULTS = (
    "Confirmatory results of the registered evaluator (PLAN.md section 6): the probe rule, six "
    "tests under Holm, bounds and secondaries. No value of a single statement."
)


def refuse(reason: str) -> NoReturn:
    """Stop with status 1; the reason is the only thing printed (on the error stream)."""
    raise SystemExit(f"refused: {reason}")


# --------------------------------------------------------------------------------------------
# Resampling: the p-value procedures and Holm
# --------------------------------------------------------------------------------------------


def holm(p: Sequence[float]) -> list[float]:
    """Holm's step-down adjusted p-values, in the order given: the k-th smallest of m is
    multiplied by m - k + 1, kept at most 1 and never below an earlier one."""
    order = sorted(range(len(p)), key=lambda i: (p[i], i))
    adjusted, running = [0.0] * len(p), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adjusted[i] = running
    return adjusted


def _ratio(numerator: Any, denominator: Any, tolerance: float) -> np.ndarray:
    """``numerator / denominator``; where the denominator is zero, 0 for a zero numerator and
    an infinity of the numerator's sign otherwise."""
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.asarray(denominator, dtype=float)
    flat = denominator <= tolerance
    safe = np.where(flat, 1.0, denominator)
    limit = np.where(np.abs(numerator) <= tolerance, 0.0, np.copysign(np.inf, numerator))
    return np.where(flat, limit, numerator / safe)


def rounding_tolerance(sums: np.ndarray) -> float:
    """What counts as zero among sums of paired differences: 1e-12 times the largest absolute
    cluster sum (at least 1e-12). The rounding of a few thousand additions stays far below it;
    a sum that is not zero, of losses from probabilities given to a few decimals, stays far
    above it."""
    return 1e-12 * max(1.0, float(np.abs(sums).max()))


def drawn_deltas(
    difference: np.ndarray, clusters: Sequence[str], draws: int = DRAWS, seed: int = SEED
) -> np.ndarray:
    """The contrast in each bootstrap draw of the clusters (``predictors.bootstrap_means`` on
    the paired differences): the mean of the differences over the statements of the drawn
    clusters, which is the comparator's mean loss minus the tested predictor's on that draw.

    A draw whose differences sum to zero is exactly zero here, also when rounding leaves a sum
    of 1e-17 (``rounding_tolerance``): the percentile p-values count such a draw on both sides
    (``<= 0`` and ``>= 0``), and the sign of a rounding error must not decide on which one."""
    sums, sizes = P.cluster_sums(difference, clusters)
    means = P.bootstrap_means(difference, clusters, draws, seed)[:, 0]
    totals = P.cluster_draws(len(sizes), draws, seed).astype(float) @ sums[:, 0]
    return np.where(np.abs(totals) <= rounding_tolerance(sums[:, 0]), 0.0, means)


def robust_t(sums: np.ndarray, sizes: np.ndarray, tolerance: float) -> tuple[float, float, float]:
    """``delta``, its cluster-robust standard error ``se = sqrt(G / (G - 1) * sum_g e_g^2) / N``
    with ``e_g = sums_g - delta * sizes_g`` (as ``power.clustered_variance``), and ``t = delta /
    se`` (``_ratio``: infinite or zero when ``se`` is zero)."""
    groups, n = len(sizes), float(sizes.sum())
    delta = float(sums.sum()) / n
    se = float(np.sqrt(groups / (groups - 1) * ((sums - delta * sizes) ** 2).sum())) / n
    return delta, se, float(_ratio(delta, se, tolerance))


def studentised(sums: np.ndarray, sizes: np.ndarray, taken: np.ndarray) -> dict[str, Any]:
    """The bootstrap-t of a mean of paired differences from its cluster sums and sizes.

    The statistic is ``t = delta / se`` (``robust_t``). Each row of ``taken`` (how often a draw
    takes each cluster) gives ``t* = (delta* - delta) / se*``, with ``delta*`` and ``se*``
    computed on the draw in the same way. One-sided p for ``delta > 0``: ``(1 + #{t* >= t}) /
    (B + 1)``, and for ``delta < 0`` with ``<=``; two-sided: equal-tailed, twice the smaller
    one-sided p (at most 1), and symmetric, ``(1 + #{|t*| >= |t|}) / (B + 1)``. The
    equal-tailed interval at coverage ``1 - a`` is ``delta - q(1 - a / 2) * se`` to ``delta -
    q(a / 2) * se``, with ``q`` the quantiles of ``t*``; the symmetric one is ``delta`` plus or
    minus ``r * se``, ``r`` the quantile of ``|t*|`` at ``1 - a``. They are None when a draw has
    no finite statistic (a draw without variance whose mean is not the observed one)."""
    groups = len(sizes)
    tolerance = rounding_tolerance(sums)
    delta, se, t = robust_t(sums, sizes, tolerance)
    totals = taken @ sizes
    means = (taken @ sums) / totals
    spread = (taken * (sums[None, :] - means[:, None] * sizes[None, :]) ** 2).sum(axis=1)
    ses = np.sqrt(groups / (groups - 1) * spread) / totals
    draws = _ratio(means - delta, ses, tolerance)
    count = len(draws) + 1
    upper = (1 + int((draws >= t).sum())) / count
    lower = (1 + int((draws <= t).sum())) / count
    beyond = (1 + int((np.abs(draws) >= abs(t)).sum())) / count
    intervals: dict[str, list[float] | None] = {}
    for name, coverage in (("95", 0.95), ("90", 0.90)):
        intervals[f"ci{name}"] = intervals[f"ci{name}_symmetric"] = None
        if np.isfinite(draws).all():  # a draw with no variance has no finite statistic
            tail = (1.0 - coverage) / 2
            low, high = np.quantile(draws, [tail, 1.0 - tail])
            reach = float(np.quantile(np.abs(draws), coverage))
            intervals[f"ci{name}"] = [float(delta - high * se), float(delta - low * se)]
            intervals[f"ci{name}_symmetric"] = [delta - reach * se, delta + reach * se]
    return {
        "one_sided": float(upper),
        "one_sided_lower": float(lower),
        "two_sided": float(min(1.0, 2 * min(upper, lower))),
        "two_sided_symmetric": float(beyond),
        "se": se,
        "t": t,
        **intervals,
    }


def sign_patterns(groups: int, draws: int = DRAWS, seed: int = SEED) -> tuple[np.ndarray, bool]:
    """The sign patterns of the sign-flip tests (one row of plus and minus ones per pattern),
    and whether they are all ``2^groups`` of them: every pattern when there are at most
    ``EXACT_FLIPS_UP_TO`` clusters, ``draws`` random ones (seeded) otherwise."""
    exact = groups <= EXACT_FLIPS_UP_TO
    if exact:
        bits = (np.arange(2**groups)[:, None] >> np.arange(groups)[None, :]) & 1
    else:
        bits = np.random.default_rng(seed).integers(0, 2, size=(draws, groups))
    return 1.0 - 2.0 * bits, exact


def flip_p_values(flipped: np.ndarray, observed: float, exact: bool) -> dict[str, float]:
    """The p-values of an observed statistic among the flipped ones: the exact share when every
    pattern is used, ``(1 + #) / (B + 1)`` with random patterns (the observed one is counted
    with them). A flipped statistic that falls short of the observed one by less than 1e-9 times
    the largest finite absolute flipped statistic counts as reaching it."""
    finite = np.abs(flipped[np.isfinite(flipped)])
    slack = 1e-9 * max(float(finite.max()) if finite.size else 0.0, 1e-300)
    extra = 0 if exact else 1
    count = len(flipped) + extra
    return {
        "one_sided": (extra + int((flipped >= observed - slack).sum())) / count,
        "one_sided_lower": (extra + int((flipped <= observed + slack).sum())) / count,
        "two_sided": (extra + int((np.abs(flipped) >= abs(observed) - slack).sum())) / count,
    }


def sign_flip(sums: np.ndarray, draws: int = DRAWS, seed: int = SEED) -> dict[str, Any]:
    """The cluster sign-flip test on the cluster sums of the paired differences. Under the null
    each sum is as likely to have either sign, so the observed total is compared with the
    totals under flipped signs (``sign_patterns``, ``flip_p_values``): one-sided for a positive
    and for a negative total, two-sided on absolute totals."""
    sums = np.asarray(sums, dtype=float)
    signs, exact = sign_patterns(len(sums), draws, seed)
    flipped = signs @ sums
    return flip_p_values(flipped, float(sums.sum()), exact) | {
        "patterns": len(flipped),
        "exact": exact,
    }


def sign_flip_t(
    sums: np.ndarray,
    sizes: np.ndarray,
    draws: int = DRAWS,
    seed: int = SEED,
    patterns: tuple[np.ndarray, bool] | None = None,
) -> dict[str, Any]:
    """The studentised sign-flip test (the wild cluster bootstrap-t with the null imposed and
    signs as weights): each sign pattern ``s`` gives the cluster sums ``s_g * sums_g`` and their
    statistic ``t° = delta° / se°`` (``robust_t``), to which the observed ``t`` is compared as
    in ``sign_flip``. The patterns are those of ``sign_flip``; ``patterns`` hands them over when
    they are made already (``sign_patterns`` for this number of clusters, draws and seed)."""
    sums, sizes = np.asarray(sums, dtype=float), np.asarray(sizes, dtype=float)
    groups, n = len(sums), float(sizes.sum())
    tolerance = rounding_tolerance(sums)
    _, _, t = robust_t(sums, sizes, tolerance)
    signs, exact = sign_patterns(groups, draws, seed) if patterns is None else patterns
    flipped = signs * sums[None, :]
    means = flipped.sum(axis=1) / n
    spread = ((flipped - means[:, None] * sizes[None, :]) ** 2).sum(axis=1)
    ses = np.sqrt(groups / (groups - 1) * spread) / n
    return flip_p_values(_ratio(means, ses, tolerance), t, exact) | {
        "patterns": len(signs),
        "exact": exact,
    }


def larger_of(first: Mapping[str, float], second: Mapping[str, float]) -> dict[str, float]:
    """Two procedures read together: on each side the larger one-sided p-value, so that a test
    rejects only when both do; two-sided, twice the smaller of the two, at most 1."""
    upper = max(first["one_sided"], second["one_sided"])
    lower = max(first["one_sided_lower"], second["one_sided_lower"])
    return {
        "one_sided": float(upper),
        "one_sided_lower": float(lower),
        "two_sided": float(min(1.0, 2 * min(upper, lower))),
    }


def interval_method(source: str | None) -> str:
    """How the intervals of a confirmatory contrast are made under the p-value source
    ``source``: from the registered test itself (``TEST_INTERVAL_SOURCES``), or as percentile
    intervals of the bootstrap draws. None is for a contrast that is not a confirmatory one."""
    return TEST_INTERVAL if source in TEST_INTERVAL_SOURCES else PERCENTILE_INTERVAL


def tail_of(coverage: float) -> float:
    """The level of each one-sided test that cuts an interval of ``coverage``: half of what the
    interval leaves out, rounded to twelve decimals so that the registered levels are 0.025 and
    0.05 exactly and not the floats next to them that ``(1 - coverage) / 2`` gives. A value is
    rejected when its p-value is below the level; a p-value that equals it is not."""
    return round((1.0 - coverage) / 2, 12)


def larger_of_at(
    sums: np.ndarray,
    sizes: np.ndarray,
    taken: np.ndarray,
    null: float,
    draws: int = DRAWS,
    seed: int = SEED,
    patterns: tuple[np.ndarray, bool] | None = None,
) -> dict[str, float]:
    """The p-values of the larger-of procedure for the hypothesis that the contrast is ``null``:
    the test of zero on the cluster sums of the differences minus ``null`` (``sums_g - null *
    sizes_g``). ``taken`` holds the bootstrap draws and ``patterns`` the sign patterns, as for
    ``studentised`` and ``sign_flip_t``."""
    moved = np.asarray(sums, dtype=float) - null * np.asarray(sizes, dtype=float)
    return larger_of(
        studentised(moved, sizes, taken), sign_flip_t(moved, sizes, draws, seed, patterns)
    )


def larger_of_interval(
    sums: np.ndarray,
    sizes: np.ndarray,
    taken: np.ndarray,
    coverage: float,
    draws: int = DRAWS,
    seed: int = SEED,
) -> list[float | None]:
    """The values of the contrast that the larger-of procedure does not reject, at coverage
    ``1 - a`` (PLAN section 6, "Intervals"): from the smallest value whose one-sided p-value
    for a larger contrast is not below ``a / 2`` (``tail_of``) to the largest whose one-sided
    p-value for a smaller contrast is not below ``a / 2``. Each end rests on that one p-value.

    Each end is found by bisection between the estimate and the value ``INTERVAL_REACH``
    standard errors away, in ``INTERVAL_STEPS`` halvings, and is the last value not rejected.
    An end is None, which is unbounded, when the test does not reject at that distance: too few
    episodes for the sign patterns to reach the level, too many bootstrap draws without
    variance on that side, or too many whose statistic is finite and still beyond the reach
    (fewer than about three episodes hold nearly all of the difference). None says that there
    is no end within the reach, not that no value is rejected: in the last case the test can
    reject values further away. Differences without any variance have one p-value at every
    value but the estimate, so one value on each side decides: it lies one unit away, or the
    size of the estimate if that is more, and the end is the estimate itself when it is
    rejected.

    The p-value need not fall steadily with the distance from the estimate: the sign-flip part
    can rise again when a few episodes hold most of the statements between them. The search
    then ends on one
    of the values at which the verdict changes, and values nearer the estimate may be rejected
    or values further away not."""
    sums, sizes = np.asarray(sums, dtype=float), np.asarray(sizes, dtype=float)
    tail = tail_of(coverage)
    tolerance = rounding_tolerance(sums)
    delta, se, _ = robust_t(sums, sizes, tolerance)
    patterns = sign_patterns(len(sizes), draws, seed)
    flat = se <= tolerance
    reach = max(1.0, abs(delta)) if flat else INTERVAL_REACH * se
    ends: list[float | None] = []
    steps = 0 if flat else INTERVAL_STEPS  # without variance the end is the estimate itself
    for side, direction in (("one_sided", -1.0), ("one_sided_lower", 1.0)):
        inside, outside = delta, delta + direction * reach
        if larger_of_at(sums, sizes, taken, outside, draws, seed, patterns)[side] >= tail:
            ends.append(None)
            continue
        for _ in range(steps):
            middle = (inside + outside) / 2
            if larger_of_at(sums, sizes, taken, middle, draws, seed, patterns)[side] >= tail:
                inside = middle
            else:
                outside = middle
        ends.append(float(inside))
    return ends


def differing(comparator: Any, tested: Any, clusters: Sequence[str]) -> dict[str, int]:
    """Where the losses of two predictors differ (reported beside H2: PLAN section 6,
    "Sensitivity"): the statements on which they differ, the episodes that hold such a
    statement, and how many of those episodes have a positive and how many a negative sum of
    the paired differences (comparator minus tested); in the others the differences cancel. A
    difference or a sum within the ``rounding_tolerance`` of the episode sums is a zero."""
    difference = np.asarray(comparator, dtype=float) - np.asarray(tested, dtype=float)
    ids = list(clusters)
    names = (
        "statements",
        "episodes",
        "episodes_with_a_positive_sum",
        "episodes_with_a_negative_sum",
        "episodes_whose_differences_cancel",
    )
    if not ids:
        return dict.fromkeys(names, 0)
    every, _ = P.cluster_sums(difference, ids)
    tolerance = rounding_tolerance(every[:, 0])
    apart = np.abs(difference) > tolerance
    holding, _ = P.cluster_sums(apart, ids)
    sums = every[holding[:, 0] > 0, 0]
    positive, negative = int((sums > tolerance).sum()), int((sums < -tolerance).sum())
    counts = (int(apart.sum()), len(sums), positive, negative, len(sums) - positive - negative)
    return dict(zip(names, counts, strict=True))


def contrast(
    comparator: Any,
    tested: Any,
    clusters: Sequence[str],
    draws: int = DRAWS,
    seed: int = SEED,
    source: str | None = None,
    levels: Sequence[str] = (),
    margin: float | None = None,
) -> dict[str, Any]:
    """The comparator's mean loss minus the tested predictor's on the same statements, with
    its intervals and the p-values of every procedure (``PROCEDURES``). ``evaluable`` is false,
    with the reason, when there is no statement or fewer than ``MIN_EPISODES`` clusters.

    ``ci95`` and ``ci90`` are the percentile intervals of the bootstrap draws, which
    ``percentile`` always holds as well. A confirmatory contrast names the registered p-value
    ``source``: when the intervals of that source are those of its own test
    (``interval_method``), the contrast carries the intervals named in ``levels`` (keys of
    ``LEVELS``) as the values that test does not reject (``larger_of_interval``; an end that is
    None is unbounded) and no other; and with ``margin`` it carries ``at_the_margin``, the
    p-value for a smaller contrast at ``margin`` and the one for a larger contrast at minus
    ``margin``, from which equivalence is read. ``interval_method`` says which kind ``ci95``
    and ``ci90`` are."""
    comparator = np.asarray(comparator, dtype=float)
    tested = np.asarray(tested, dtype=float)
    ids = list(clusters)
    out: dict[str, Any] = {"statements": len(ids), "episodes": len(set(ids))}
    if not ids:
        return out | {"evaluable": False, "reason": "no scoreable statement"}
    sums, sizes = P.cluster_sums(comparator - tested, ids)
    sums = sums[:, 0]
    out |= {
        "loss_comparator": float(comparator.mean()),
        "loss_tested": float(tested.mean()),
        "delta": float((comparator - tested).mean()),
    }
    if len(sizes) < MIN_EPISODES:
        return out | {"evaluable": False, "reason": "fewer than two episodes"}
    delta = drawn_deltas(comparator - tested, ids, draws, seed)
    taken = P.cluster_draws(len(sizes), draws, seed).astype(float)
    by_t = studentised(sums, sizes, taken)
    flips = sign_flip(sums, draws, seed)
    flips_t = sign_flip_t(sums, sizes, draws, seed)
    draft = P.p_values(delta)
    bootstrap_t = {side: by_t[side] for side in SIDES}
    p_values = {
        "percentile": {
            "one_sided": draft["one_sided"],
            "one_sided_lower": P.p_values(-delta)["one_sided"],
            "two_sided": draft["two_sided"],
        },
        "studentised": bootstrap_t,
        "studentised_symmetric": bootstrap_t | {"two_sided": by_t["two_sided_symmetric"]},
        "sign_flip_t": {side: flips_t[side] for side in SIDES},
        "larger_of_studentised_and_sign_flip_t": larger_of(bootstrap_t, flips_t),
        SENSITIVITY: {side: flips[side] for side in SIDES},
    }
    percentile = {name: P.interval(delta, coverage) for name, coverage in LEVELS.items()}
    method = interval_method(source)
    shown: dict[str, Any] = dict(percentile)
    if method == TEST_INTERVAL:
        shown = {
            name: larger_of_interval(sums, sizes, taken, LEVELS[name], draws, seed)
            for name in LEVELS
            if name in levels
        }
        if margin is not None:
            above = larger_of_at(sums, sizes, taken, margin, draws, seed)
            below = larger_of_at(sums, sizes, taken, -margin, draws, seed)
            shown["at_the_margin"] = {
                "p_smaller_at_the_margin": above["one_sided_lower"],
                "p_larger_at_minus_the_margin": below["one_sided"],
            }
    intervals = ("ci95", "ci90", "ci95_symmetric", "ci90_symmetric")
    return out | {
        "evaluable": True,
        **shown,
        "interval_method": method,
        "percentile": percentile,
        "p_values": {name: p_values[name] for name in PROCEDURES},
        "studentised": {key: by_t[key] for key in ("se", "t", *intervals)},
        "sign_flip": {key: flips[key] for key in ("patterns", "exact")},
    }


def registered_p(result: Mapping[str, Any], sides: int, source: str) -> float:
    """The p-value of a contrast under the procedure ``source`` (a candidate of the registered
    constant): one-sided for ``delta > 0``, or two-sided."""
    if source not in P_VALUE_SOURCES or sides not in (1, 2):
        raise ValueError(f"unknown p-value source {source!r} or sides {sides!r}")
    return float(result["p_values"][source]["one_sided" if sides == 1 else "two_sided"])


def lowest(losses: Mapping[str, float], names: Sequence[str]) -> str:
    """The name with the lowest loss; a tie goes to the earlier name."""
    return min(names, key=lambda name: (losses[name], names.index(name)))


def comparator_choice(losses: Mapping[str, float], rule: str) -> str:
    """The comparator of H3 under ``rule``; ``better_on_dev`` takes the candidate with the
    lower primary loss on the scoreable dev statements (``losses``)."""
    if rule not in H3_COMPARATORS:
        raise ValueError(f"unknown H3 comparator rule {rule!r}")
    return lowest(losses, COMPARATOR_CANDIDATES) if rule == "better_on_dev" else rule


def constants_problem() -> str | None:
    """What is wrong with the registered constants: a value outside its candidates."""
    for value, candidates in ((P_VALUE_SOURCE, P_VALUE_SOURCES), (H3_COMPARATOR, H3_COMPARATORS)):
        if value not in candidates:
            return f"a registered constant has a value outside its candidates: {value!r}"
    return None


def recorded_lowest(losses: Any, names: Sequence[str]) -> str | None:
    """``lowest`` on losses read back from a file; None when one is missing or not a number."""
    values = [losses.get(name) for name in names] if isinstance(losses, Mapping) else [None]
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        return None
    return lowest(losses, names)


def recorded_comparator(losses: Any, rule: str) -> str | None:
    """The comparator of H3 that ``rule`` gives: the rule's own name when it names a predictor,
    else the better of the two on the dev losses a selection file records (None when the file
    does not hold them)."""
    return rule if rule in COMPARATOR_CANDIDATES else recorded_lowest(losses, COMPARATOR_CANDIDATES)


def registered_record() -> dict[str, Any]:
    """The constants in force."""
    return {
        "p_value_source": P_VALUE_SOURCE,
        "p_value_source_candidates": list(P_VALUE_SOURCES),
        "p_value_procedures_reported": list(PROCEDURES),
        "intervals": {
            "of_the_confirmatory_contrasts_and_delta_gbm": interval_method(P_VALUE_SOURCE),
            "of_the_other_contrasts_and_single_predictors_of_the_evaluator": PERCENTILE_INTERVAL,
            "coverage": LEVELS["ci95"],
            "coverage_for_the_equivalence_of_h2": LEVELS[EQUIVALENCE_LEVEL],
            "sources_with_the_interval_of_their_own_test": list(TEST_INTERVAL_SOURCES),
            "search_reach_in_standard_errors": INTERVAL_REACH,
            "search_halvings": INTERVAL_STEPS,
            "an_end_that_is_null": "unbounded: the test does not reject at the reach of the search",
        },
        "sign_flip_patterns": {"every_pattern_up_to_episodes": EXACT_FLIPS_UP_TO, "drawn": DRAWS},
        "h3_comparator": H3_COMPARATOR,
        "h3_comparator_rules": list(H3_COMPARATORS),
        "h3_comparator_candidates": list(COMPARATOR_CANDIDATES),
        "familywise_alpha": FAMILY_ALPHA,
        "tests_in_the_family": TESTS,
        "h2_margin": H2_MARGIN,
        "probe_alpha": PROBE_ALPHA,
        "probe_pinball_level": PROBE_LEVEL,
        "min_slice_scoreable": MIN_SLICE,
        "min_episodes": MIN_EPISODES,
        "draws": DRAWS,
        "seed": SEED,
        "stated_period_statement_types": list(PERIOD_TYPES),
        "primaries": list(PRIMARIES),
        "cutoff_month_ends": {
            model: sealed_counts.CUTOFF_MONTH_ENDS[model].isoformat() for model in PRIMARIES
        },
    }


# --------------------------------------------------------------------------------------------
# Files and hashes
# --------------------------------------------------------------------------------------------


def table_of(data: bytes, gzipped: bool) -> pd.DataFrame:
    """A CSV held in memory, every cell as text."""
    return pd.read_csv(
        io.BytesIO(data), dtype=str, keep_default_na=False, compression="gzip" if gzipped else None
    )


def output_paths(path: Path | None, table: bool = False) -> tuple[Path, Path | None]:
    """The file ``--out`` names and, with ``table``, the Markdown file beside it. Refused when
    one is not given, lies in a sealed folder, exists already, or its folder does not exist."""
    if path is None or not path.name:
        refuse("--out is required: the file to write, which must not exist yet")
    beside = path.with_suffix(".md") if table else None
    for target in (path, *([beside] if beside is not None else [])):
        if sealed_counts.in_sealed_folder(target):
            refuse("--out lies in a sealed folder; results are written outside it")
        if target.exists() or target.is_symlink():
            refuse(f"the output is already there, and nothing is overwritten: {target.as_posix()}")
    if beside == path:
        refuse("--out cannot end in .md: the table is written beside it under that name")
    if not path.parent.is_dir():
        refuse(f"the folder of the output does not exist: {path.parent.as_posix()}")
    return path, beside


def write_new(path: Path, text: str) -> None:
    """Write a file that must not exist yet."""
    stopped = ""
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"the output cannot be written ({stopped}): {path.as_posix()}")


def code_record() -> dict[str, str]:
    """The sha256 of the code the numbers depend on, and the versions of the libraries."""
    record = {
        name: sealed_counts.sha256(sealed_counts.file_bytes(Path(path), name))
        for name, path in CODE.items()
    }
    record |= {
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    return record


def report_text(report: Mapping[str, Any]) -> str:
    """A report as JSON, floats at six decimals; a number that is not finite is null."""

    def finite(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: finite(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [finite(item) for item in value]
        if isinstance(value, float | np.floating) and not np.isfinite(value):
            return None
        return value

    return power.report_text(finite(report))


# --------------------------------------------------------------------------------------------
# The plan of the runs and the stored readings
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Group:
    """The readings of one model on one line of the run sheet, pooled over its runs."""

    model: str
    line: str
    template: str
    rows: Mapping[str, dict]
    """The stored reading row of each item."""
    record: Mapping[str, Any]
    """Counts for the report: runs, rows, statuses, echoes."""
    problems: tuple[str, ...]


def is_sealed(path: Any, sealed: Any = None) -> bool:
    """Whether a path is the sealed file (``sealed``, or ``SEALED``; compared as text, nothing
    on disk is looked at for it) or lies in a sealed folder."""
    same = os.path.abspath(path) == os.path.abspath(sealed or SEALED)
    return same or sealed_counts.in_sealed_folder(Path(path))


def read_plan(out_root: Path, sealed: Path | None = None) -> tuple[dict | None, str, list[str]]:
    """The launcher's plan under ``out_root``, its sha256, and what is wrong with it. A plan
    that names a path in a sealed folder (its output root, an item file or a track record) is
    not used at all: the completeness check hashes the files a plan names, and no sealed file
    is opened for that."""
    path = lp.plan_path(out_root)
    if not path.is_file():
        return None, "", [f"no plan of the runs at {path.as_posix()} (launch.py plan writes it)"]
    data = path.read_bytes()
    sha = sealed_counts.sha256(data)
    try:
        plan = json.loads(data)
        made_for = str(plan["options"]["out_root"])
        files = [record for key in ("lists", "tracks") for record in plan[key].values()]
        named = [made_for, *(str(record["path"]) for record in files)]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, sha, [f"the file at {path.as_posix()} is not a plan of launch.py"]
    if any(is_sealed(name, sealed) for name in named):
        why = "the plan of the runs names a path in a sealed folder; none of its files is read"
        return None, sha, [why]
    problems = []
    if Path(made_for).resolve() != out_root.resolve():
        problems.append("the plan was made for another output root than the one given")
    return plan, sha, problems


def sent(route: Mapping[str, Any]) -> dict[str, Any]:
    """What a route sends: the model id and the provider pin (``read.provider_object``). The
    launcher holds a run to these two and to nothing else of a route row, whose price and
    accepted echo names may be corrected after a run."""
    pin = rd.Route(route["model_id"], route["provider"], route["quantization"])
    return {"model_id": route["model_id"], "provider_object": rd.provider_object(pin)}


def registered_route(model: str) -> dict[str, Any]:
    """What the registered route of a model sends."""
    return sent(asdict(rd.ROUTES[model]))


def reading_accepted(reading: Any, kind: str) -> bool:
    """Whether a stored reading is one the harness's parser accepts (``read.parse_reading``):
    the schema of its kind on the stored object itself, then the semantic checks (real calendar
    dates, a start not after the end, quantiles that do not decrease), on a copy, because the
    predictive check rewrites the quantiles of what it is given."""
    if rd.validate(reading, rd.SCHEMAS[kind]):
        return False
    held = json.loads(json.dumps(reading))
    if kind == "literal":
        errors, _ = rd._literal_checks(held, None)
    else:
        errors, _ = rd._predictive_checks(held)
    return not errors


def row_faults(row: Mapping[str, Any], model: str, template: str) -> list[str]:
    """What makes a stored row unusable: another route, template or decoding than the
    registered ones, flags that contradict one another, a reading that the harness's parser
    would have rejected (``reading_accepted``: the harness stores none, so such a row was not
    written by this harness), an answer served as another model or, by the provider names
    stored with it, by another provider than the pinned one (``read.provider_problem``), or a
    track record in context that is not wholly before the item (the harness's own warning)."""
    route, kind = rd.ROUTES[model], rd.TEMPLATES[template].kind
    found = []
    served = (row.get("model"), row.get("model_id"), row.get("provider_pin"))
    if served != (model, route.model_id, route.provider):
        found.append("another model id or provider pin than the registered route")
    if (row.get("template"), row.get("template_sha256")) != (
        template,
        rd.FROZEN_SHA256.get(template),
    ):
        found.append("another template or pin than the frozen one")
    if row.get("mask_names") or row.get("shift_years") or row.get("temperature"):
        found.append("masked names, shifted dates or a temperature above zero")
    status, parsed = row.get("status"), row.get("reading") is not None
    if (
        status not in STATUSES
        or parsed != (status in ("ok", "repaired"))
        or row.get("fallback") != rd.fallback_for(kind, str(status))
    ):
        found.append("a status, a reading and a fallback flag that contradict one another")
    if parsed and not reading_accepted(row["reading"], kind):
        found.append("a stored reading that the harness's parser does not accept")
    accepted = rd.served_as(model)
    answered = [a for a in row.get("attempts") or () if not a.get("refused")]
    if any(a.get("served_model") not in (None, *accepted) for a in answered):
        found.append("an answer served as another model")
    named = [n for a in answered for n in str(a.get("served_provider") or "").split(" | ") if n]
    if named and rd.provider_problem(route, named):
        found.append("an answer served by another provider than the pinned one")
    if "track_record_not_before_item" in (row.get("warnings") or ()):
        found.append("a track record that reaches the date of the item")
    return found


def track_problems(phase: str, run: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    """Whether a run showed the track record of its phase (PLAN section 5, E3, condition b):
    the fit split for a dev run, fit and dev for a confirmatory one, and none under a template
    that shows no record. Looked at twice: what the plan names for the run, and what the record
    the run read said of itself (the manifest keeps its split)."""
    wanted = TRACK_OF_PHASE[phase] if rd.TEMPLATES[run["template"]].needs_track else None
    said = f"the {wanted} one" if wanted else "none"
    found = []
    if run.get("track") != wanted:
        found.append(f"run {run['run']} is planned with another track record than {said}")
    if manifest and manifest.get("track_record_split") != wanted:
        found.append(f"run {run['run']} showed another track record than {said}")
    return found


def read_group(
    plan: Mapping[str, Any],
    out_root: Path,
    phase: str,
    model: str,
    line: str,
    expected: Iterable[str],
    first: pd.DataFrame | None = None,
) -> Group:
    """The readings of ``model`` on ``line``, from the runs the plan lists for it in ``phase``
    and from no other run (``read.collect_readings`` with the run filter), with everything that
    stands in the way of scoring them. ``first`` (the first-sight cells of the expected
    statements, by id) lets the horizons a predictive run asked about be checked against the
    registered ones. Problems are counts and names of runs, never items."""
    name = f"{model} {line}"
    runs = [run for run in lp.select(plan, [phase], models=[model]) if run["line"] == line]
    if not runs:
        return Group(model, line, "", {}, {}, (f"{name}: the plan holds no run",))
    template = runs[0]["template"]
    if any(run["template"] != template for run in runs) or template not in rd.TEMPLATES:
        why = f"{name}: the plan holds runs under several templates, or one the harness lacks"
        return Group(model, line, template, {}, {"runs": len(runs)}, (why,))
    problems, hashes = [], {}
    if sent(plan["routes"][model]) != registered_route(model):
        problems.append(f"{name}: the plan was made for another route than the registered one")
    if plan["templates"].get(template) != rd.FROZEN_SHA256.get(template):
        problems.append(f"{name}: the plan holds another pin of {template} than the frozen one")
    for run in runs:
        problems += [f"{name}: {gap}" for gap in lp.plan_gaps(plan, run)]
        problems += [f"{name}: {gap}" for gap in lp.file_problems(plan, run)]
        manifest = lp.manifest_of(plan, run)
        problems += [f"{name}: {gap}" for gap in track_problems(phase, run, manifest)]
        state = lp.run_state(plan, run)
        if state != "finished":
            other = lp.manifest_differences(plan, run, manifest) if state == "mismatch" else []
            detail = f": {', '.join(other)}" if other else ""
            problems.append(f"{name}: run {run['run']} is not finished ({state}{detail})")
        stored = out_root / run["run"] / "readings.jsonl"
        written = sealed_counts.sha256(stored.read_bytes()) if stored.is_file() else None
        hashes[run["run"]] = written
        if manifest and manifest.get("readings_sha256") != written:
            problems.append(
                f"{name}: the readings of run {run['run']} are not those of its manifest"
            )
    pooled = rd.collect_readings(out_root, [run["run"] for run in runs])
    if len(pooled) != 1:
        problems.append(f"{name}: readings under {len(pooled)} conditions where one is planned")
        return Group(model, line, template, {}, {"runs": len(runs)}, tuple(problems))
    ((answered_by, condition), group) = next(iter(pooled.items()))
    if answered_by != model or condition.split("|")[0] != template:
        problems.append(f"{name}: the readings are of another model or template")
    if group["incomplete_runs"]:
        problems.append(f"{name}: {len(group['incomplete_runs'])} runs are not complete")
    if group["duplicates"]:
        problems.append(f"{name}: {len(group['duplicates'])} items were answered twice")
    if group["samples"] != 1:
        problems.append(f"{name}: {group['samples']} samples per item where one is planned")
    refused_echo = sum(n for echo, n in group["by_echo"].items() if not rd.echo_acceptable(echo))
    if refused_echo:
        problems.append(f"{name}: {refused_echo} rows whose served model or provider is not ok")
    wanted = set(expected)
    missing, extra = len(wanted - group["item_ids"]), len(group["item_ids"] - wanted)
    if missing or extra:
        problems.append(
            f"{name}: the item set is not the registered list ({missing} items missing, "
            f"{extra} not on the list)"
        )
    rows = {item_id: row for (item_id, sample), row in group["rows"].items() if sample == 0}
    faults: dict[str, int] = {}
    for row in rows.values():
        for fault in row_faults(row, model, template):
            faults[fault] = faults.get(fault, 0) + 1
    problems += [f"{name}: {n} rows with {fault}" for fault, n in sorted(faults.items())]
    asked = rd.TEMPLATES[template]
    if first is not None and asked.kind == "predictive":
        wrong = asked_elsewhere(rows, first, asked.probe)
        if wrong:
            problems.append(f"{name}: {wrong} rows asked about other horizons than the registered")
    status = group["by_status"]
    record = {
        "runs": len(runs),
        "readings_sha256": hashes,
        "template": template,
        "condition": condition,
        "rows": len(rows),
        "by_status": dict(status),
        "by_echo": dict(group["by_echo"]),
        "parse_failure_rate": status.get("failed", 0) / len(rows) if rows else None,
        "refusal_rate": status.get("refused", 0) / len(rows) if rows else None,
    }
    return Group(model, line, template, rows, record, tuple(problems))


def list_problems(plan: Mapping[str, Any], key: str, ids: Iterable[str], what: str) -> list[str]:
    """Whether the plan's item list ``key`` is the list of ``ids``."""
    if (plan["lists"].get(key) or {}).get("item_ids_sha256") != dataset.ids_sha256(ids):
        return [f"the plan's item list {key!r} is not {what}"]
    return []


def item_file_problems(
    plan: Mapping[str, Any], counts: Mapping[str, Any], keys: Sequence[str]
) -> list[str]:
    """Whether the item files the runs read (the plan holds their hashes, and every manifest is
    checked against the plan) are the ones the dataset builder wrote with the statement table:
    the counts file of the build records the hash of each."""
    written = (counts.get("outputs") or {}).get(dataset.ITEMS.name) or {}
    problems = []
    for key in keys:
        name = f"{lp.LIST_BY_KEY[key].stem}.jsonl"
        read = str((plan["lists"].get(key) or {}).get("sha256") or "-")
        if not read.startswith((written.get(name) or {}).get("sha256") or "+"):
            problems.append(
                f"the item file of list {key!r} in the plan is not the one the counts file of "
                "the dataset builder records"
            )
    return problems


# --------------------------------------------------------------------------------------------
# Readings as predictions (PLAN sections 4 and 8)
# --------------------------------------------------------------------------------------------


def probe_horizons(day: str) -> tuple[str, str]:
    """The two horizons of a probe item: 90 and 180 days after the statement date."""
    a, b, _ = dataset.horizons(dataset.FALLBACK_FORMS[0], "", day)
    return a, b


def asked_elsewhere(rows: Mapping[str, dict], first: pd.DataFrame, probe: bool = False) -> int:
    """How many stored rows of a predictive condition asked about other horizons than the
    registered ones: the statement's stated end and 90 days later, or, for the probe, 90 and
    180 days after the statement date. ``first`` holds the first-sight cells of the statements,
    indexed by statement id; a row of no statement of ``first`` is not looked at."""
    wrong = 0
    cells = zip(
        first.index, first["event_date"], first["horizon_a"], first["horizon_b"], strict=True
    )
    for item_id, day, a, b in cells:
        if item_id in rows:
            wanted = (*probe_horizons(day), "probe") if probe else (a, b, "stated_end")
            asked = rows[item_id].get("horizons") or {}
            wrong += (asked.get("a"), asked.get("b"), asked.get("rule")) != wanted
    return wrong


def predictive(
    rows: Mapping[str, dict], first: pd.DataFrame, base: pd.DataFrame
) -> tuple[pd.DataFrame, pd.Series, dict[str, int]]:
    """The predictions of a predictive condition for the statements of ``first`` (first-sight
    cells, indexed by statement id): each stored answer as given, and the base-rate output of
    ``base`` where the reading failed. Returns the predictions, which statements were parsed,
    and counts: readings replaced, and answers that put ``P(E_end90)`` below ``P(E_end)``."""
    values, parsed = [], []
    counts = {"replaced_by_base_rate": 0, "p_b_below_p_a": 0}
    for item_id in first.index:
        row = rows[item_id]
        reading = row["reading"]
        parsed.append(reading is not None)
        if reading is None:
            counts["replaced_by_base_rate"] += 1
            values.append(base.loc[item_id, list(P.PREDICTION_COLUMNS)].tolist())
            continue
        p_a, p_b = float(reading["p_by_horizon_a"]), float(reading["p_by_horizon_b"])
        counts["p_b_below_p_a"] += p_b < p_a
        days = reading["days_to_recovery"]
        values.append([p_a, p_b, *(float(days[key]) for key in P.QUANTILE_KEYS)])
    frame = pd.DataFrame(values, index=first.index, columns=list(P.PREDICTION_COLUMNS), dtype=float)
    return frame, pd.Series(parsed, index=first.index, dtype=bool), counts


def literal_days(
    rows: Mapping[str, dict], first: pd.DataFrame
) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    """The end of each literal reading's period in days from the statement date (missing for a
    reading that gives no stated period: ABSTAIN, a failed reading, or an interval of another
    statement type than recovery or next delivery), which statements were parsed, and counts."""
    days, parsed = [], []
    counts = {"failed_counted_as_abstain": 0, "abstain": 0, "period_of_another_statement_type": 0}
    for item_id, day in zip(first.index, first["event_date"], strict=True):
        reading = rows[item_id]["reading"]
        parsed.append(reading is not None)
        end = float("nan")
        if reading is None:
            counts["failed_counted_as_abstain"] += 1
        elif not isinstance(reading["interval"], Mapping):
            counts["abstain"] += 1
        elif reading["statement_type"] not in PERIOD_TYPES:
            counts["period_of_another_statement_type"] += 1
        else:
            end = float(dataset.days_between(day, reading["interval"]["end"]))
        days.append(end)
    index = first.index
    return pd.Series(days, index=index, dtype=float), pd.Series(parsed, index=index), counts


def model_predictions(
    groups: Mapping[str, Group],
    fitted: Mapping[str, Any],
    rows: pd.DataFrame,
    first: pd.DataFrame,
    base: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series], dict[str, dict], list[str]]:
    """The predictions of conditions (a), (b) and (c) of one model on ``rows`` (the typed
    first-sight rows; ``first`` holds the same statements as text): by condition, the
    predictions, the parsed flags and the counts, and the reasons to refuse the readings."""
    predictions, parsed, counts, problems = {}, {}, {}, []
    for condition in ("a", "b"):
        predictions[condition], parsed[condition], counts[condition] = predictive(
            groups[condition].rows, first, base
        )
    days, parsed["c"], counts["c"] = literal_days(groups["c"].rows, first)
    predictions["c"] = fitted[RULES].predict(rows, days)
    for condition, frame in predictions.items():
        if frame.isna().any().any():
            problems.append(f"{groups[condition].line}: a statement is left without a prediction")
    return predictions, parsed, counts, problems


def predictions_text(predictions: Mapping[str, pd.DataFrame]) -> str:
    """Predictions as one CSV, a row per statement and a column per predictor and output, at
    six decimals: the text whose sha256 the freeze amendment holds."""
    table = pd.concat(dict(predictions), axis=1)
    table.columns = [f"{name}.{column}" for name, column in table.columns]
    return table.to_csv(float_format="%.6f", lineterminator="\n", index_label="statement_group_id")


# --------------------------------------------------------------------------------------------
# Scores of one predictor
# --------------------------------------------------------------------------------------------


def calibration(p: Any, y: Any, clusters: Sequence[str], draws: int, seed: int) -> dict[str, Any]:
    """Calibration in the large: the mean probability minus the observed frequency, with its
    95% interval by episode bootstrap (None with fewer than two episodes)."""
    gap = np.asarray(p, dtype=float) - np.asarray(y, dtype=float)
    out: dict[str, Any] = {"mean_p_minus_frequency": float(gap.mean()), "ci95": None}
    if len(set(clusters)) >= MIN_EPISODES:
        out["ci95"] = P.interval(P.bootstrap_means(gap, clusters, draws, seed)[:, 0], 0.95)
    return out


def episode_intervals(
    values: np.ndarray, clusters: Sequence[str], draws: int, seed: int
) -> list[list[float] | None]:
    """For each column of ``values`` (statements by quantities), the 95% percentile interval of
    its mean over draws of the episodes ``clusters``, every column on the same draws
    (``predictors.cluster_draws``, as ``predictors.bootstrap_means`` takes them). None for each
    column when the statements lie in one episode, or when there is none.

    The overconfidence criterion asks whether such an interval excludes zero, so a draw whose
    values sum to zero up to rounding is exactly zero, as for a contrast (``drawn_deltas``,
    ``rounding_tolerance``): the sign of a rounding error must not put an end on one side of
    zero."""
    values = np.asarray(values, dtype=float)
    if len(set(clusters)) < MIN_EPISODES:
        return [None] * values.shape[1]
    sums, sizes = P.cluster_sums(values, clusters)
    taken = P.cluster_draws(len(sizes), draws, seed).astype(float)
    totals = taken @ sums
    slack = np.array([rounding_tolerance(column) for column in sums.T])
    means = np.where(np.abs(totals) <= slack, 0.0, totals / (taken @ sizes)[:, None])
    return [P.interval(column, 0.95) for column in means.T]


def excludes_zero(interval: Sequence[float] | None) -> bool:
    """Whether an interval excludes zero: both of its ends lie on one side of zero. An end on
    zero does not exclude it, and an interval that could not be made (None) excludes nothing."""
    return interval is not None and (interval[0] > 0 or interval[1] < 0)


def calibration_limits(
    p: Any, y: Any, clusters: Sequence[str], draws: int, seed: int
) -> dict[str, Any]:
    """The limits of calibration in the large over every statement given, whatever the captures
    leave open (PLAN 7.2). ``y`` holds the event of each statement as 1, 0, or missing when it
    is undetermined. ``least``: the mean probability minus ``largest_frequency``, the frequency
    of the event with every undetermined one counted as yes. ``greatest``: the mean probability
    minus ``smallest_frequency``, with every undetermined one counted as no. Each limit has its
    95% percentile interval by episode (``episode_intervals``). No scoreable set enters.
    Without a statement every value is None."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    unknown = np.isnan(y)
    limits = (("least", "largest_frequency", 1.0), ("greatest", "smallest_frequency", 0.0))
    keys = [key for name, frequency, _ in limits for key in (frequency, name, f"{name}_ci95")]
    out: dict[str, Any] = {"undetermined": int(unknown.sum()), **dict.fromkeys(("mean_p", *keys))}
    if not len(p):
        return out
    out["mean_p"] = float(p.mean())
    events = [np.where(unknown, counted_as, y) for _, _, counted_as in limits]
    gaps = np.stack([p - event for event in events], axis=1)
    intervals = episode_intervals(gaps, clusters, draws, seed)
    for (name, frequency, _), event, interval in zip(limits, events, intervals, strict=True):
        out[frequency], out[name] = float(event.mean()), float((p - event).mean())
        out[f"{name}_ci95"] = interval
    return out


def probability_gap(
    p: Any, base: Any, clusters: Sequence[str], draws: int, seed: int
) -> dict[str, Any]:
    """The mean probability of a predictor minus the mean probability of the base rate by
    listing age on the same statements (``p`` and ``base``, one value per statement), with its
    95% percentile interval by episode (``episode_intervals``). No outcome enters. Without a
    statement every value is None."""
    p, base = np.asarray(p, dtype=float), np.asarray(base, dtype=float)
    out: dict[str, Any] = dict.fromkeys(("mean_p_model", "mean_p_base_rate", "difference", "ci95"))
    if not len(p):
        return out
    out["mean_p_model"], out["mean_p_base_rate"] = float(p.mean()), float(base.mean())
    out["difference"] = float((p - base).mean())
    (out["ci95"],) = episode_intervals((p - base)[:, None], clusters, draws, seed)
    return out


def coverage80(pred: pd.DataFrame, rows: pd.DataFrame) -> dict[str, Any]:
    """Coverage of the 80% interval ``[q10, q90]``, counted on the statements whose bracket of
    the capped time to recovery lies wholly inside or wholly outside it (a target censored
    before the cap has the bracket from its lower bound to the cap)."""
    censored = (rows["ttr_kind"] == "right_censored").to_numpy()
    low = rows["ttr_lower"].to_numpy(dtype=float)
    high = np.where(censored, float(P.CAP_DAYS), rows["ttr_upper"].to_numpy(dtype=float))
    q10, q90 = pred["q10"].to_numpy(dtype=float), pred["q90"].to_numpy(dtype=float)
    inside = (q10 <= low) & (high <= q90)
    outside = (high < q10) | (low > q90)
    counted = int(inside.sum() + outside.sum())
    return {
        "inside": int(inside.sum()),
        "outside": int(outside.sum()),
        "bracket_straddles_the_interval": len(rows) - counted,
        "coverage": float(inside.sum() / counted) if counted else None,
    }


def murphy(p: Any, y: Any, bins: int = 10) -> dict[str, Any]:
    """Murphy's decomposition of the Brier score of one horizon event with ``bins`` equal-count
    bins: the statements are ordered by probability (ties in the order given) and cut into
    ``bins`` runs of equal length, to within one."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    cuts = np.array_split(np.argsort(p, kind="stable"), min(bins, len(p)))
    rate = float(y.mean())
    reliability = sum(len(k) * (p[k].mean() - y[k].mean()) ** 2 for k in cuts) / len(p)
    resolution = sum(len(k) * (y[k].mean() - rate) ** 2 for k in cuts) / len(p)
    return {
        "bins": len(cuts),
        "reliability": float(reliability),
        "resolution": float(resolution),
        "uncertainty": rate * (1.0 - rate),
    }


def calibration_scores(
    rows: pd.DataFrame, pred: pd.DataFrame, draws: int = DRAWS, seed: int = SEED
) -> dict[str, Any]:
    """Calibration in the large of one predictor on the statements of ``rows`` (PLAN 7.2), for
    each horizon event: on the scoreable statements (``calibration_in_the_large``), and over
    every statement with its least and its greatest value (``calibration_all_statements``:
    ``calibration_limits``). ``rows`` must hold a scoreable statement."""
    scoreable = rows[rows["scoreable"]]
    mine, clusters = pred.loc[scoreable.index], list(scoreable["episode_id"])
    whole, every = pred.loc[rows.index], list(rows["episode_id"])
    return {
        "calibration_in_the_large": {
            event: calibration(mine[p], scoreable[y], clusters, draws, seed)
            for event, p, y in EVENTS
        },
        "calibration_all_statements": {
            event: calibration_limits(whole[p], rows[y], every, draws, seed)
            for event, p, y in EVENTS
        },
    }


def predictor_record(
    rows: pd.DataFrame, pred: pd.DataFrame, draws: int = DRAWS, seed: int = SEED
) -> dict[str, Any]:
    """Every registered score of one predictor on the statements of ``rows`` (PLAN 7.2): the
    record of ``power.predictor_record`` (primary Brier on the scoreable ones with its 95%
    interval, the two horizon events apart, the bounds and the pinball losses over all rows),
    calibration in the large (on the scoreable statements, and its least and greatest value
    over all rows: ``calibration_scores``), Murphy's decomposition and the coverage of the 80%
    interval. Without a scoreable statement the record holds that count alone."""
    pred = pred.loc[rows.index]
    scoreable = rows[rows["scoreable"]]
    if not len(scoreable):
        return {"scoreable_statements": 0}
    mine, clusters = pred.loc[scoreable.index], list(scoreable["episode_id"])
    loss = P.primary_loss(mine["p_a"], mine["p_b"], scoreable["y_a"], scoreable["y_b"])
    several = len(set(clusters)) >= MIN_EPISODES
    means = P.bootstrap_means(loss, clusters, draws, seed)[:, 0] if several else np.array(loss)
    record = power.predictor_record(rows, pred, np.asarray(loss), means)
    record["bounds_all_statements"] = record.pop("bounds_all_dated")
    record["pinball_all_statements"] = record.pop("pinball_all_dated")
    return {
        "scoreable_statements": len(scoreable),
        "scoreable_episodes": len(set(clusters)),
        "statements": len(rows),
        **record,
        "ci95": record["ci95"] if several else None,
        **calibration_scores(rows, pred, draws, seed),
        "murphy": {event: murphy(mine[p], scoreable[y]) for event, p, y in EVENTS},
        "coverage_80": coverage80(pred, rows),
    }


def beside_base_rate(
    record: Mapping[str, Any],
    rows: pd.DataFrame,
    base: pd.DataFrame,
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """The record of ``predictor_record`` on ``rows`` with the base rate's calibration in the
    large beside the predictor's own (PLAN 7.2: "the same quantities for the base rate by
    listing age on the same events"): every event of ``calibration_in_the_large`` and of
    ``calibration_all_statements`` gains ``base_rate``, what ``calibration_scores`` gives for
    the base rate's predictions ``base`` on the same statements. A record without a scoreable
    statement holds no calibration in the large and is returned as it is."""
    if not record["scoreable_statements"]:
        return dict(record)
    beside = calibration_scores(rows, base, draws, seed)
    return {
        **record,
        **{
            key: {
                event: {**record[key][event], "base_rate": theirs}
                for event, theirs in found.items()
            }
            for key, found in beside.items()
        },
    }


def criterion_parts(
    rows: pd.DataFrame, pred: pd.DataFrame, base: pd.DataFrame, draws: int, seed: int
) -> dict[str, Any]:
    """Both parts of the overconfidence criterion of PLAN section 13 over every statement of
    ``rows``, for each horizon event, for the predictions ``pred`` and the base rate's
    predictions ``base`` on the same statements.

    ``against_outcomes``: the limits of calibration in the large (``calibration_limits``). The
    part is ``met`` when the least value is positive and its interval excludes zero. The limits
    of the base rate stand under ``base_rate``; no verdict is read from them.

    ``against_base_rate``: the mean probability minus the base rate's (``probability_gap``).
    The part is ``met`` when the difference is positive and its interval excludes zero."""
    clusters = list(rows["episode_id"])
    mine, theirs = pred.loc[rows.index], base.loc[rows.index]
    outcomes, no_text = {}, {}
    for event, p, y in EVENTS:
        limits = calibration_limits(mine[p], rows[y], clusters, draws, seed)
        limits["met"] = excludes_zero(limits["least_ci95"]) and limits["least"] > 0
        limits["base_rate"] = calibration_limits(theirs[p], rows[y], clusters, draws, seed)
        gap = probability_gap(mine[p], theirs[p], clusters, draws, seed)
        gap["met"] = excludes_zero(gap["ci95"]) and gap["difference"] > 0
        outcomes[event], no_text[event] = limits, gap
    return {
        "statements": len(rows),
        "episodes": len(set(clusters)),
        "against_outcomes": outcomes,
        "against_base_rate": no_text,
    }


def overconfidence_reading(outcomes: Mapping[str, Any], no_text: Mapping[str, Any]) -> int:
    """Which of the five readings of PLAN section 13 applies (``OVERCONFIDENCE_READINGS``), from
    the two parts of the criterion for ``E_end`` (``criterion_parts``), tried in the plan's
    order: 1 when the greatest value of calibration in the large is negative with an interval
    that excludes zero, whatever else holds; 2 when both parts are met; 3 when only the part
    against the base rate is; 4 when only the part against outcomes is; 5 otherwise."""
    if excludes_zero(outcomes["greatest_ci95"]) and outcomes["greatest"] < 0:
        return 1
    if no_text["met"]:
        return 2 if outcomes["met"] else 3
    return 4 if outcomes["met"] else 5


def few(count: int) -> bool:
    """Whether a number of statements is a few: 1 to ``MIN_SHOWN`` - 1. A figure on outcomes
    that would give the horizon events of so few statements is withheld (over none there is
    nothing to give)."""
    return 0 < count < MIN_SHOWN


def overconfidence(
    rows: pd.DataFrame,
    pred: pd.DataFrame,
    base: pd.DataFrame,
    parsed: pd.Series,
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """The overconfidence criterion of PLAN section 13 on ``rows``, the typed statements of an
    item set with their outcomes. ``pred`` holds the predictions of condition (a), in which a
    failed answer is already the base-rate output; ``base`` the base rate's predictions;
    ``parsed`` which answers of condition (a) parsed. Every interval is a 95% percentile
    interval by episode on the draws of ``draws`` and ``seed``.

    The criterion is read on ``E_end``: ``against_outcomes`` and ``against_base_rate``
    (``criterion_parts``), ``reading`` (1 to 5: ``overconfidence_reading``) with
    ``reading_in_words``, and ``met``, which is true when both parts hold (reading 2).

    Beside it, for condition (a) and, under ``base_rate``, for the base rate on the same
    statements: both parts for ``E_end90`` (in the same two blocks); ``scoreable``, calibration
    in the large on the scoreable statements with, under ``against_base_rate``, the difference
    of the two predictors there (the scoreable statements have one frequency, so it is the
    difference of the two mean probabilities); ``parsed_only``, both parts on the statements
    whose answer parsed, after the number of answers that did not; and ``coverage_80``.

    ``parsed_only`` holds its three counts and ``withheld`` alone when the answers that failed
    are a few, or those that parsed are (``few``). The frequencies and the counts of
    undetermined events over every statement and over the parsed ones give, by subtraction,
    the horizon events of the statements between them, and the answers that failed can be told
    from the stored runs; over a few parsed answers the figures would give their events
    outright."""
    parts = criterion_parts(rows, pred, base, draws, seed)
    number = overconfidence_reading(
        parts["against_outcomes"]["E_end"], parts["against_base_rate"]["E_end"]
    )
    scoreable = rows[rows["scoreable"]]
    clusters = list(scoreable["episode_id"])
    mine, theirs = pred.loc[scoreable.index], base.loc[scoreable.index]
    on_scoreable: dict[str, Any] = {"statements": len(scoreable), "episodes": len(set(clusters))}
    if len(scoreable):  # calibration in the large needs a frequency
        for event, p, y in EVENTS:
            on_scoreable[event] = {
                **calibration(mine[p], scoreable[y], clusters, draws, seed),
                "base_rate": calibration(theirs[p], scoreable[y], clusters, draws, seed),
                "against_base_rate": probability_gap(mine[p], theirs[p], clusters, draws, seed),
            }
    kept = rows[parsed.loc[rows.index].to_numpy()]
    failed = len(rows) - len(kept)
    if few(failed) or few(len(kept)):
        on_parsed: dict[str, Any] = {
            "statements": len(kept),
            "episodes": len(set(kept["episode_id"])),
            "withheld": True,
        }
    else:
        on_parsed = criterion_parts(kept, pred, base, draws, seed)
    return {
        "criterion": OVERCONFIDENCE_CRITERION,
        **parts,
        "reading": number,
        "reading_in_words": OVERCONFIDENCE_READINGS[number],
        "met": number == 2,
        "scoreable": on_scoreable,
        "parsed_only": {"not_parsed": failed, **on_parsed},
        "coverage_80": {
            **coverage80(pred.loc[rows.index], rows),
            "base_rate": coverage80(base.loc[rows.index], rows),
        },
    }


# --------------------------------------------------------------------------------------------
# The dev command: losses of the three conditions and the selection
# --------------------------------------------------------------------------------------------


def group_record(group: Group, counts: Mapping[str, int]) -> dict[str, Any]:
    return {"line": group.line, **group.record, **{key: int(n) for key, n in counts.items()}}


def dev_report(
    model: str,
    table: pd.DataFrame,
    counts: Mapping[str, Any],
    plan: Mapping[str, Any],
    out_root: Path,
    draws: int = DRAWS,
) -> dict[str, Any]:
    """The dev losses of the three conditions of ``model`` and the selection (see the module
    docstring). ``table`` is the open statement table and ``counts`` the counts file of its
    build; refused when a dev run is not ready."""
    frame = P.prepare(table)
    dev = power.dev_rows(frame)
    record = plan["lists"].get(LISTS["dev"]) or {}
    if not record.get("on_disk"):
        refuse("the plan was made without the dev item list on disk; plan again")
    wrong_file = item_file_problems(plan, counts, (LISTS["dev"],))
    if wrong_file:
        refuse("; ".join(wrong_file))
    listed = sorted(item.item_id for item in rd.load_items(Path(record["path"])))
    scoreable_ids = set(dev.index[dev["scoreable"]])
    if not scoreable_ids <= set(listed) or not set(listed) <= set(dev.index):
        refuse(
            "the dev item list must hold every scoreable dev statement and dated dev statements "
            f"only ({len(scoreable_ids - set(listed))} scoreable ones are not on it, "
            f"{len(set(listed) - set(dev.index))} of its items are not dated dev statements)"
        )
    first = table.set_index("statement_group_id").loc[listed]
    groups = {
        condition: read_group(plan, out_root, "dev", model, line, listed, first)
        for condition, line in LINES["dev"].items()
    }
    problems = [problem for group in groups.values() for problem in group.problems]
    if problems:
        refuse("the dev runs are not ready: " + "; ".join(problems))
    fitted, _, free = power.fit_and_predict(frame)
    rows = dev.loc[listed]
    free = {name: pred.loc[listed] for name, pred in free.items()}
    predictions, _, counts, problems = model_predictions(groups, fitted, rows, first, free[BASE])
    if problems:
        refuse("the dev runs cannot be scored: " + "; ".join(problems))
    scoreable = rows[rows["scoreable"]]
    everything = {**predictions, **free}
    losses = power.primary_losses(scoreable, everything)
    means = P.bootstrap_means(losses.to_numpy(), scoreable["episode_id"], draws, SEED)
    scores = {}
    for k, (name, pred) in enumerate(everything.items()):
        entry = power.predictor_record(rows, pred, losses[name].to_numpy(), means[:, k])
        entry["bounds_statements_read"] = entry.pop("bounds_all_dated")
        entry["pinball_statements_read"] = entry.pop("pinball_all_dated")
        scores[name] = entry
    # as the file records them: the selection can then be checked against the file itself
    mean_loss = {name: round(float(losses[name].mean()), 6) for name in everything}
    return {
        "model": model,
        "registered": registered_record(),
        "dev": {
            "dated_statements": len(dev),
            "statements_read": len(rows),
            "dated_statements_not_read": len(dev) - len(rows),
            "scoreable_statements": len(scoreable),
            "scoreable_episodes": int(scoreable["episode_id"].nunique()),
            "read_with_a_horizon_event_undetermined": len(rows) - len(scoreable),
            "scoreable_by_E_end_and_E_end90": power.outcome_mix(scoreable),
        },
        "fitted_on": {"split": "fit", "statements": int((frame["split"] == "fit").sum())},
        "bootstrap": {"draws": draws, "seed": SEED, "clusters": "shortage episodes"},
        "conditions": {
            condition: {**group_record(groups[condition], counts[condition]), **scores[condition]}
            for condition in CONDITIONS
        },
        "selection": {
            "rule": "the lowest primary loss on the scoreable dev statements, at six decimals; a "
            "tie goes to the earlier of a, b, c",
            "primary_brier": {condition: mean_loss[condition] for condition in CONDITIONS},
            "selected": lowest(mean_loss, CONDITIONS),
        },
        "model_free": {name: scores[name] for name in free},
        "h3_comparator": {
            "rule": H3_COMPARATOR,
            "primary_brier": {name: mean_loss[name] for name in COMPARATOR_CANDIDATES},
            "selected": comparator_choice(mean_loss, H3_COMPARATOR),
            "under_each_rule": {
                rule: comparator_choice(mean_loss, rule) for rule in H3_COMPARATORS
            },
        },
    }


def dev_lines(report: Mapping[str, Any]) -> list[str]:
    dev, chosen = report["dev"], report["selection"]
    lines = [
        f"dev, {report['model']}: {dev['scoreable_statements']} scoreable statements in "
        f"{dev['scoreable_episodes']} episodes; mix {dev['scoreable_by_E_end_and_E_end90']}"
    ]
    for condition in CONDITIONS:
        entry = report["conditions"][condition]
        low, high = entry["ci95"]
        lines.append(
            f"  condition {condition}: primary Brier {entry['primary_brier']:.4f} "
            f"[{low:.4f}, {high:.4f}]"
        )
    lines.append(f"selected for H3: condition {chosen['selected']}")
    lines.append(f"H3 comparator ({H3_COMPARATOR}): {report['h3_comparator']['selected']}")
    return lines


# --------------------------------------------------------------------------------------------
# Before the sealed file: completeness, selections, predictions
# --------------------------------------------------------------------------------------------


@dataclass
class Gathered:
    """What the completeness check found, without any outcome."""

    problems: list[str] = field(default_factory=list)
    groups: dict[str, dict[str, Group]] = field(default_factory=dict)
    """By model and condition (a, b, c, probe)."""
    selections: dict[str, dict[str, Any]] = field(default_factory=dict)
    comparator: str = ""
    plan_sha256: str = ""
    probe_ids: list[str] = field(default_factory=list)


def read_selection(
    path: Path, model: str, statements_sha: str, expected: str | None = None
) -> tuple[dict, list[str]]:
    """The H3 selection the dev command recorded for ``model``, and what is wrong with it: a
    file that is not the one of ``expected`` (the sha256, or its first characters, recorded at
    the freeze; both hashes are then shown at the length of the one given, so that they can be
    compared), of another model, statement table or comparator rule, or one that contradicts
    itself (a selected condition that is not the lowest of its own dev losses, or a comparator
    that is not the one the rule in force gives on its own dev losses)."""
    if not path.is_file():
        return {}, [f"{model}: no H3 selection at {path.as_posix()} (the dev command writes it)"]
    data = path.read_bytes()
    sha = sealed_counts.sha256(data)
    problems = []
    if expected is not None and not sha.startswith(expected):
        problems.append(
            f"{model}: {path.name} is not the selection file hashed at the freeze (its sha256 "
            f"starts with {sha[: len(expected)]}, expected {expected})"
        )
    try:
        record = json.loads(data)
    except ValueError:
        record = None
    record = record if isinstance(record, dict) else {}
    chosen, rule = record.get("selection") or {}, record.get("h3_comparator") or {}
    selected, comparator = chosen.get("selected"), rule.get("selected")
    if record.get("model") != model or selected not in CONDITIONS:
        problems.append(f"{model}: {path.name} is not a selection for this model")
    elif selected != recorded_lowest(chosen.get("primary_brier"), CONDITIONS):
        problems.append(
            f"{model}: {path.name} does not select the condition with the lowest of its own dev "
            "losses"
        )
    if (record.get("registered") or {}).get("h3_comparator") != H3_COMPARATOR:
        problems.append(f"{model}: {path.name} was recorded under another H3 comparator rule")
    if comparator not in COMPARATOR_CANDIDATES:
        problems.append(f"{model}: {path.name} names no H3 comparator")
    elif comparator != recorded_comparator(rule.get("primary_brier"), H3_COMPARATOR):
        problems.append(
            f"{model}: {path.name} names another H3 comparator than the rule in force gives"
        )
    if (record.get("inputs") or {}).get("statements_sha256") != statements_sha:
        problems.append(f"{model}: {path.name} was made on another statement table")
    found = {
        "file": path.name,
        "sha256": sha,
        "checked_against_the_freeze": expected is not None,
        "selected": selected,
        "dev_primary_brier": chosen.get("primary_brier"),
        "comparator": comparator,
        "comparator_dev_primary_brier": rule.get("primary_brier"),
    }
    return found, problems


def cluster_problems(first: pd.DataFrame, ids: Sequence[str]) -> list[str]:
    """Whether every eligible statement has the cells its clusters are taken from (an episode
    and a company), so that the resampling cannot stop on one once the sealed rows are read."""
    cells = first.reindex(list(ids))
    blank = np.zeros(len(cells), dtype=bool)
    for column in CLUSTER_COLUMNS:
        values = cells[column] if column in cells.columns else pd.Series("", index=cells.index)
        blank |= (values.fillna("").astype(str).str.strip() == "").to_numpy()
    if blank.any():
        return [
            f"{int(blank.sum())} eligible statements have no shortage episode or no company: the "
            "resampling has no cluster for them"
        ]
    return []


def gather(
    out_root: Path,
    eligible: pd.DataFrame,
    first: pd.DataFrame | None,
    counts: Mapping[str, Any],
    selections: Path,
    statements_sha: str,
    skipped: Mapping[str, str],
    expected_selections: Mapping[str, str] | None = None,
    sealed: Path | None = None,
) -> Gathered:
    """The completeness check of PLAN section 6 ("Confirmatory runs", "Evaluator"): the plan,
    the confirmatory runs of every primary that is not declared not evaluable, their item sets
    against the registered lists, the horizons they asked about against those of the statement
    table (``first``: the first-sight cells of the eligible statements by id; None skips this
    and the next), the cells the clusters are taken from, the item files against the build,
    and the selection files (against ``expected_selections``, the sha256 of each primary's
    file, when given). No outcome is read; ``sealed`` is the sealed file when it is not the
    default one, so that a plan that names it is not followed (``read_plan``)."""
    found = Gathered()
    ids = list(eligible["statement_group_id"])
    found.probe_ids = sorted(eligible.loc[eligible[PROBE] == "1", "statement_group_id"])
    if first is not None:
        found.problems += cluster_problems(first, ids)
    plan, found.plan_sha256, problems = read_plan(out_root, sealed)
    found.problems += problems
    if plan is None:
        return found
    found.problems += list_problems(plan, LISTS["e3"], ids, "the registered eligible list")
    found.problems += list_problems(
        plan, LISTS[PROBE], found.probe_ids, "the probe subset of the eligible list"
    )
    found.problems += item_file_problems(plan, counts, (LISTS["e3"], LISTS[PROBE]))
    expected = {**dict.fromkeys(CONDITIONS, ids), PROBE: found.probe_ids}
    comparators = set()
    for model in PRIMARIES:
        if model in skipped:
            continue
        found.groups[model] = {
            condition: read_group(
                plan, out_root, "confirmatory", model, line, expected[condition], first
            )
            for condition, line in LINES["confirmatory"].items()
        }
        for group in found.groups[model].values():
            found.problems += group.problems
        path = selections / SELECTION_NAME.format(model=model)
        frozen = (expected_selections or {}).get(model)
        found.selections[model], problems = read_selection(path, model, statements_sha, frozen)
        found.problems += problems
        comparators.add(found.selections[model].get("comparator"))
    if len(comparators) > 1:
        found.problems.append("the selection files name different H3 comparators")
    found.comparator = next(iter(comparators)) if len(comparators) == 1 else ""
    return found


def gathered(*args: Any) -> Gathered:
    """``gather``, for the commands. A stop inside it (a plan or stored runs that are not as
    the launcher and the harness write them) is one more thing the check finds, named by the
    type of the error alone: its message may quote a stored row."""
    try:
        return gather(*args)
    except Exception as error:
        stopped = type(error).__name__
    why = (
        f"the completeness check stopped on the plan or the stored runs ({stopped}): they are "
        "not as the launcher and the harness write them"
    )
    return Gathered(problems=[why])


@dataclass
class Study:
    """Everything the evaluation needs besides the outcomes, fixed before the sealed file is
    read."""

    first: pd.DataFrame
    """First-sight cells of the eligible statements as text, indexed by statement id."""
    probe_ids: list[str]
    predictions: dict[str, pd.DataFrame]
    """By predictor: the model-free names, and ``<model>:<condition>``."""
    parsed: dict[str, pd.Series]
    probe: dict[str, pd.DataFrame]
    """Probe predictions by model, and the base rate's on the same statements."""
    selection: dict[str, str]
    comparator: str
    runs: dict[str, dict[str, Any]]
    not_evaluable: dict[str, str]
    refit: dict[str, Any]
    problems: list[str] = field(default_factory=list)


def refit(frame: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    """Every model-free predictor refitted on fit and dev together (PLAN section 3, "Final
    fits"), and what the fit rests on."""
    train = frame[frame["split"].isin(dataset.TRAIN_SPLITS)]
    sets = train["analysis_set"].value_counts()
    record = {
        "splits": "fit and dev",
        "statements_by_analysis_set": {name: int(sets.get(name, 0)) for name in P.SETS},
    }
    return gbm.fit_all(train), record


def free_predictions(
    frame: pd.DataFrame, ids: Sequence[str], probe_ids: Sequence[str]
) -> tuple[dict[str, Any], dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    """The refitted predictors, their predictions on the eligible statements, the base rate's
    predictions at the probe horizons on the probe statements, and the record of the fit."""
    missing = len(set(ids) - set(frame.index))
    if missing:
        refuse(f"{missing} eligible statements are not in the frame of the predictors")
    fitted, record = refit(frame)
    rows = frame.loc[list(ids)]
    predictions = {name: model.predict(rows) for name, model in fitted.items()}
    a, b = (float(days) for days in dataset.FALLBACK_DAYS)
    probe_base = fitted[BASE].predict(rows.loc[list(probe_ids)].assign(h_a=a, h_b=b))
    return fitted, predictions, probe_base, record


def baseline_hash(predictions: Mapping[str, pd.DataFrame], probe_base: pd.DataFrame) -> str:
    """The sha256 of the model-free predictions: the eligible list, then the probe base rate."""
    free = {name: predictions[name] for name in gbm.PREDICTORS}
    text = predictions_text(free) + predictions_text({f"{BASE}_at_probe_horizons": probe_base})
    return sealed_counts.sha256(text.encode("utf-8"))


def open_study(
    table: pd.DataFrame, listed: pd.DataFrame, found: Gathered, skipped: Mapping[str, str]
) -> tuple[Study, str]:
    """The study without its outcomes: the refit, the model-free predictions, and the
    predictions of every condition of every primary from its readings. Returns it with the
    hash of the model-free predictions."""
    frame = P.prepare(table)
    ids = list(listed["statement_group_id"])
    first = listed.set_index("statement_group_id")
    fitted, predictions, probe_base, record = free_predictions(frame, ids, found.probe_ids)
    rows = frame.loc[ids]
    study = Study(
        first=first,
        probe_ids=found.probe_ids,
        predictions=dict(predictions),
        parsed={},
        probe={BASE: probe_base},
        selection={m: found.selections[m]["selected"] for m in found.groups},
        comparator=found.comparator,
        runs={},
        not_evaluable=dict(skipped),
        refit=record,
    )
    for model, groups in found.groups.items():
        made, parsed, counts, problems = model_predictions(
            groups, fitted, rows, first, predictions[BASE]
        )
        probe, probe_parsed, probe_counts = predictive(
            groups[PROBE].rows, first.loc[found.probe_ids], probe_base
        )
        study.problems += [f"{model} {problem}" for problem in problems]
        for condition in CONDITIONS:
            study.predictions[f"{model}:{condition}"] = made[condition]
            study.parsed[f"{model}:{condition}"] = parsed[condition]
        study.probe[model] = probe
        study.parsed[f"{model}:{PROBE}"] = probe_parsed
        counts[PROBE] = probe_counts
        study.runs[model] = {
            condition: group_record(group, counts[condition]) for condition, group in groups.items()
        }
    return study, baseline_hash(predictions, probe_base)


# --------------------------------------------------------------------------------------------
# With the outcomes: the probe rule, the family and the secondaries
# --------------------------------------------------------------------------------------------


def typed_outcomes(filled: pd.DataFrame, variant: str = "") -> pd.DataFrame:
    """The typed frame of ``predictors.prepare`` for eligible test statements with their
    outcomes attached (``dataset.attach_outcomes``). ``prepare`` refuses an outcome cell on a
    statement of the test period, by design; the evaluator is the one place that may hold them,
    so the rows carry the label of the train period through that call and get their own back.
    ``variant`` scores the horizon events of another statement-level bracket (``_all``,
    ``_any``) in place of the displayed presentation's."""
    shown = filled.copy()
    for name in ("E_end", "E_end90", "scoreable") if variant else ():
        shown[name] = shown[f"{name}{variant}"]
    frame = P.prepare(shown.assign(period="train"))
    frame["period"] = "test"
    return frame


def bounds(
    rows: pd.DataFrame, predictions: Mapping[str, pd.DataFrame], comparator: str, tested: str
) -> dict[str, Any]:
    """The bounds of PLAN 7.2 beside a contrast: both mean losses and their difference over
    every statement of ``rows``, with each undetermined horizon event set to no, then to yes."""
    out: dict[str, Any] = {
        "statements": len(rows),
        "with_a_horizon_event_undetermined": int((~rows["scoreable"]).sum()),
    }
    if not len(rows):
        return out
    each = {
        name: P.brier_bounds(
            predictions[name].loc[rows.index, "p_a"],
            predictions[name].loc[rows.index, "p_b"],
            rows["y_a"],
            rows["y_b"],
        )
        for name in (comparator, tested)
    }
    for fill in each[comparator]:
        out[fill] = {
            "loss_comparator": each[comparator][fill],
            "loss_tested": each[tested][fill],
            "delta": each[comparator][fill] - each[tested][fill],
        }
    return out


def paired_losses(
    rows: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    comparator: str,
    tested: str,
    cluster: str = "episode_id",
) -> tuple[pd.Series, pd.Series, list[str]]:
    """The primary losses of two predictors on the scoreable statements of ``rows``, and the
    cluster of each of those statements."""
    scoreable = rows[rows["scoreable"]]
    pair = {name: predictions[name] for name in (comparator, tested)}
    losses = power.primary_losses(scoreable, pair)
    return losses[comparator], losses[tested], list(scoreable[cluster])


def scored(
    rows: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    comparator: str,
    tested: str,
    cluster: str = "episode_id",
    draws: int = DRAWS,
    seed: int = SEED,
    source: str | None = None,
    levels: Sequence[str] = (),
    margin: float | None = None,
) -> dict[str, Any]:
    """The contrast of two predictors on the scoreable statements of ``rows``. ``source``,
    ``levels`` and ``margin`` are those of ``contrast``: they are given for a confirmatory
    contrast, which carries the intervals of the registered source."""
    pair = paired_losses(rows, predictions, comparator, tested, cluster)
    return contrast(*pair, draws, seed, source, levels, margin)


def short(result: Mapping[str, Any], sides: int, source: str) -> dict[str, Any]:
    """A contrast in short, for the secondaries: sizes, the estimate, its 95% interval with the
    way it was made, and the p-value of the procedure in force."""
    keys = ("statements", "episodes", "evaluable", "reason", "delta", "ci95", "interval_method")
    out = {key: result[key] for key in keys if key in result}
    out["p"] = registered_p(result, sides, source) if result["evaluable"] else None
    return out


def probe_test(
    model: str, study: Study, rows: pd.DataFrame, draws: int, seed: int, source: str
) -> dict[str, Any]:
    """The probe test of E4 for one model: pinball loss at 0.5 of the probe's median against
    the base rate's, one-sided, on the probe statements whose target is not right-censored
    before the cap. ``beats_base_rate`` is None when the test cannot be made."""
    shown = rows.loc[study.probe_ids]
    kept = shown[shown["ttr_kind"] != "right_censored"]
    target = kept["ttr_mid"].to_numpy(dtype=float)
    mine, base = study.probe[model], study.probe[BASE]
    result = contrast(
        P.pinball(base.loc[kept.index, "q50"], target, PROBE_LEVEL),
        P.pinball(mine.loc[kept.index, "q50"], target, PROBE_LEVEL),
        list(kept["episode_id"]),
        draws,
        seed,
    )
    p = registered_p(result, 1, source) if result["evaluable"] else None
    return {
        "probe_statements": len(shown),
        "left_out_right_censored": len(shown) - len(kept),
        **result,
        "pinball_base_rate": P.pinball_scores(base.loc[shown.index, "q50"], shown, PROBE_LEVEL),
        "pinball_model": P.pinball_scores(mine.loc[shown.index, "q50"], shown, PROBE_LEVEL),
        "p": p,
        "alpha": PROBE_ALPHA,
        "beats_base_rate": None if p is None else bool(p < PROBE_ALPHA),
    }


def item_set(
    model: str, beaten: bool | None, first: pd.DataFrame, rows: pd.DataFrame
) -> tuple[pd.Index | None, dict[str, Any]]:
    """The statements a primary's three tests are evaluated on, from the probe alone (PLAN
    section 5, E4): every eligible statement, or its post-cutoff slice when the probe beat the
    base rate. None, with the reason, when the tests are not evaluable: the switch could not
    be decided, the model has no slice, or the slice holds fewer than ``MIN_SLICE`` scoreable
    statements. Nothing that is computed on a primary's item set is then computed for it, the
    overconfidence criterion included, however many statements the slice holds."""
    cutoff = sealed_counts.CUTOFF_MONTH_ENDS[model]
    has_slice = sealed_counts.has_slice(cutoff)
    after = (first.loc[rows.index, "event_date"] > cutoff.isoformat()).to_numpy() & has_slice
    part = rows[after]
    scoreable = int(part["scoreable"].sum())
    record: dict[str, Any] = {
        "cutoff_month_end": cutoff.isoformat(),
        "slice_inside_the_test_split": has_slice,
        "slice_statements": len(part),
        "slice_scoreable": scoreable,
        "slice_scoreable_episodes": int(part.loc[part["scoreable"], "episode_id"].nunique()),
        "slice_analysed": scoreable >= MIN_SLICE,
        "switched": bool(beaten),
    }
    if beaten is None:
        return None, record | {"evaluable": False, "reason": "the probe could not be tested"}
    if not beaten:
        return rows.index, record | {"evaluable": True, "items": ALL_ITEMS}
    if not has_slice:
        why = "the probe beat the base rate and the model has no slice inside the test split"
        return None, record | {"evaluable": False, "reason": why}
    if scoreable < MIN_SLICE:
        why = (
            f"the probe beat the base rate and the post-cutoff slice holds fewer than "
            f"{MIN_SLICE} scoreable statements"
        )
        return None, record | {"evaluable": False, "reason": why}
    return part.index, record | {"evaluable": True, "items": SLICE_ITEMS}


def tests_of(model: str, study: Study) -> list[tuple[str, str, str, int]]:
    """The three tests of a primary, as (hypothesis, comparator, tested, sides)."""
    best = study.selection.get(model, "best")
    return [
        ("H1", f"{model}:a", f"{model}:b", 1),
        ("H2", RULES, f"{model}:c", 2),
        ("H3", study.comparator or H3_COMPARATOR, f"{model}:{best}", 2),
    ]


def other_comparators(comparator: str) -> list[str]:
    """The predictors that read no text other than the comparator in force: the structured-only
    model under the registered rule, whose contrast with the selected condition is the plan's
    ``Delta_GBM``."""
    return [name for name in COMPARATOR_CANDIDATES if name != comparator]


def reading_of(entry: Mapping[str, Any]) -> str:
    """One sentence on what a test of the family says. For H3 in favour of the tested condition
    it also says whether the other predictor that reads no text was beaten
    (``beats_both_comparators``)."""
    if not entry["evaluable"]:
        return f"not evaluable ({entry['reason']}); counted as not rejected"
    if not entry["holds"]:
        return "not rejected"
    if entry["sides"] == 1:
        return "holds: the tested condition has the lower loss"
    if entry["delta"] <= 0:
        return "rejected in favour of the comparator"
    said = "rejected in favour of the tested predictor"
    if "beats_both_comparators" not in entry:
        return said
    others = " and ".join(other_comparators(entry["comparator"]))
    if entry["beats_both_comparators"]:
        return f"{said}; the 95% interval against {others} also lies above zero"
    return f"{said}; the 95% interval against {others} does not lie above zero"


def beats_both(entry: Mapping[str, Any]) -> bool:
    """The flag ``beats_both_comparators`` of an H3 entry (PLAN section 6, "Reading"): whether
    the paper may claim value beyond both predictors that read no text. True only when H3 holds
    in favour of the text (Holm-adjusted p below 0.05 and a positive contrast) and the 95%
    interval of the contrast with the other one (``Delta_GBM``, under the registered rule) lies
    above zero. That interval is the one the registered p-value source gives (``beside`` holds
    it, with its ``interval_method``); a lower end that is None is unbounded and does not lie
    above zero. The flag can only withhold a claim: it never enters the family."""
    if not (entry["evaluable"] and entry["holds"] and entry["delta"] > 0):
        return False
    beside = entry.get("beside") or {}
    intervals = [
        (beside.get(name) or {}).get("ci95") for name in other_comparators(entry["comparator"])
    ]
    return all(
        interval is not None and interval[0] is not None and interval[0] > 0
        for interval in intervals
    )


def equivalence(entry: Mapping[str, Any], margin: float = H2_MARGIN) -> dict[str, Any]:
    """The equivalence reading of an H2 entry (PLAN section 6).

    Under the registered test the rule is on two p-values, those of the entry's
    ``at_the_margin`` (``contrast``, given the same ``margin``): equivalence is declared when
    the p-value for a smaller contrast at the margin and the p-value for a larger one at minus
    the margin are both below the level at which the 90% interval is cut (``tail_of``: 0.05).
    The ends of the interval are reported and not read. They say the same only where the
    p-value falls steadily with the distance from the estimate and the margin lies within the
    reach of the search: an end is the last value the test does not reject, so the interval
    ends before the margin when the margin is rejected, and an end on the margin goes with a
    margin that is not rejected. The two can part in two ways, and the rule decides. Where the
    p-value does not fall steadily (``larger_of_interval``), the interval can reach past a
    margin that is rejected, or end inside one that is not. And an end is None whenever the
    value ``INTERVAL_REACH`` standard errors away is not rejected, although the test may reject
    values further away: with the margin among those, equivalence is declared beside an
    unbounded end.

    Under a source with percentile intervals it is declared when the 90% percentile interval
    lies strictly inside plus or minus ``margin``."""
    low, high = entry[EQUIVALENCE_LEVEL]
    out = {
        "margin": margin,
        EQUIVALENCE_LEVEL: [low, high],
        "interval_method": entry["interval_method"],
    }
    if entry["interval_method"] != TEST_INTERVAL:
        return out | {"declared": bool(low > -margin and high < margin)}
    level = tail_of(LEVELS[EQUIVALENCE_LEVEL])
    smaller = entry["at_the_margin"]["p_smaller_at_the_margin"]
    larger = entry["at_the_margin"]["p_larger_at_minus_the_margin"]
    return out | {
        "p_smaller_at_the_margin": smaller,
        "p_larger_at_minus_the_margin": larger,
        "level": level,
        "declared": bool(smaller < level and larger < level),
    }


def evaluate(
    study: Study,
    rows: pd.DataFrame,
    variants: Mapping[str, pd.DataFrame],
    source: str,
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """The probe rule, the six tests under Holm and the secondaries, with the p-values of the
    procedure ``source``. ``rows`` is the typed frame of the eligible statements with the
    primary outcome; ``variants`` holds the same statements under other outcome definitions,
    for the sensitivity analyses."""
    first, predictions = study.first, study.predictions
    models = [model for model in PRIMARIES if model not in study.not_evaluable]

    # E4 first: the item set of each primary is fixed by its probe, before any test.
    probes = {model: probe_test(model, study, rows, draws, seed, source) for model in models}
    sets: dict[str, pd.Index | None] = {}
    set_records: dict[str, dict[str, Any]] = {}
    for model in models:
        sets[model], set_records[model] = item_set(
            model, probes[model]["beats_base_rate"], first, rows
        )

    def both_parsed(ids: pd.Index, names: Sequence[str]) -> pd.Index:
        keep = np.ones(len(ids), dtype=bool)
        for name in names:
            if name in study.parsed:
                keep &= study.parsed[name].loc[ids].to_numpy()
        return ids[keep]

    family = []
    for model in PRIMARIES:
        for hypothesis, comparator, tested, sides in tests_of(model, study):
            entry: dict[str, Any] = {
                "hypothesis": hypothesis,
                "model": model,
                "comparator": comparator,
                "tested": tested,
                "sides": sides,
            }
            ids = sets.get(model)
            if model in study.not_evaluable:
                entry |= {"evaluable": False, "reason": study.not_evaluable[model]}
            elif ids is None:
                entry |= {"evaluable": False, "reason": set_records[model]["reason"]}
            else:
                entry["items"] = set_records[model]["items"]
                chosen = rows.loc[ids]
                h2 = hypothesis == "H2"  # the one test read for equivalence as well
                entry |= scored(
                    chosen,
                    predictions,
                    comparator,
                    tested,
                    draws=draws,
                    seed=seed,
                    source=source,
                    levels=("ci95", EQUIVALENCE_LEVEL) if h2 else ("ci95",),
                    margin=H2_MARGIN if h2 else None,
                )
                if h2:
                    entry["losses_differ"] = differing(
                        *paired_losses(chosen, predictions, comparator, tested)
                    )
                entry["bounds"] = bounds(chosen, predictions, comparator, tested)
                parsed = rows.loc[both_parsed(ids, (comparator, tested))]
                both = short(
                    scored(parsed, predictions, comparator, tested, draws=draws, seed=seed),
                    sides,
                    source,
                )
                # beside the contrast on every scoreable statement, the one on those both sides
                # parsed would give the summed loss difference of the few it leaves out
                if few(entry["statements"] - both["statements"]) or few(both["statements"]):
                    both = {key: both[key] for key in ("statements", "episodes")}
                    both["withheld"] = True
                entry["both_sides_parsed"] = both
                kept = chosen.index[chosen["scoreable"].to_numpy()]
                entry["scoreable_not_parsed"] = {
                    name: len(kept) - len(both_parsed(kept, (name,)))
                    for name in (comparator, tested)
                }
                if hypothesis == "H3":  # the same statements and draws as the test itself
                    entry["beside"] = {
                        name: short(
                            scored(
                                chosen,
                                predictions,
                                name,
                                tested,
                                draws=draws,
                                seed=seed,
                                source=source,
                                levels=("ci95",),
                            ),
                            sides,
                            source,
                        )
                        for name in COMPARATOR_CANDIDATES
                    }
            entry["p"] = registered_p(entry, sides, source) if entry["evaluable"] else 1.0
            family.append(entry)
    for entry, adjusted in zip(family, holm([entry["p"] for entry in family]), strict=True):
        entry["p_holm"] = adjusted
        entry["holds"] = bool(entry["evaluable"] and adjusted < FAMILY_ALPHA)
        if entry["hypothesis"] == "H2" and entry["evaluable"]:
            entry["equivalence"] = equivalence(entry)
            entry.pop("at_the_margin", None)  # the reading holds the two p-values
        if entry["hypothesis"] == "H3":  # read after Holm; it never enters the family
            entry["beats_both_comparators"] = beats_both(entry)
        entry["reading"] = reading_of(entry)

    def rerun(
        frame: pd.DataFrame,
        keep: Callable[[str, pd.Index], pd.Index] = lambda model, ids: ids,
        cluster: str = "episode_id",
        only: Sequence[str] = ("H1", "H2", "H3"),
    ) -> dict[str, Any]:
        """The tests of the family again on other statements, outcomes or clusters."""
        out = {}
        for model in models:
            ids = sets[model]
            if ids is None:
                continue
            chosen = frame.loc[keep(model, ids)]
            for hypothesis, comparator, tested, sides in tests_of(model, study):
                if hypothesis in only:
                    result = scored(chosen, predictions, comparator, tested, cluster, draws, seed)
                    out[f"{hypothesis} {model}"] = short(result, sides, source)
        return out

    def after_cutoff(model: str, ids: pd.Index) -> pd.Index:
        day = sealed_counts.CUTOFF_MONTH_ENDS[model].isoformat()
        return ids[(first.loc[ids, "event_date"] > day).to_numpy()]

    sliced = [m for m in models if set_records[m].get("items") == ALL_ITEMS]
    sliced = [m for m in sliced if set_records[m]["slice_analysed"]]
    scoreable = rows[rows["scoreable"]]
    secondaries: dict[str, Any] = {
        "model_free_contrasts": [
            {"comparator": comparator, "tested": tested}
            | short(
                scored(rows, predictions, comparator, tested, draws=draws, seed=seed), 2, source
            )
            for comparator, tested in MODEL_FREE_PAIRS
        ],
        "h2_on_the_month_and_year_form": rerun(
            rows, lambda _, ids: ids[(first.loc[ids, "form"] == MONTH_YEAR).to_numpy()], only=["H2"]
        ),
        "post_cutoff_slice": {
            key: value
            for key, value in rerun(rows, after_cutoff).items()
            if key.split(" ", 1)[1] in sliced
        },
        "first_captured_by_the_stated_end": rerun(
            rows, lambda _, ids: ids[(first.loc[ids, "delayed_entry"] != "True").to_numpy()]
        ),
        "clusters_by_company": rerun(rows, cluster="company"),
        "delta_gbm": {
            entry["model"]: {"comparator": STRUCTURED, "tested": entry["tested"]}
            | entry["beside"][STRUCTURED]
            for entry in family
            if entry["hypothesis"] == "H3" and "beside" in entry
        },
        "h3_with_each_condition": {
            f"{model}:{condition}": short(
                scored(
                    rows.loc[sets[model]],
                    predictions,
                    study.comparator,
                    f"{model}:{condition}",
                    draws=draws,
                    seed=seed,
                ),
                2,
                source,
            )
            for model in models
            if sets[model] is not None
            for condition in CONDITIONS
        },
        **{name: rerun(frame) for name, frame in variants.items()},
    }
    decomposition = {}
    for model in models:
        ids = sets[model]
        if ids is None:
            continue
        parts = {
            "content_value_of_the_text": (BASE, RULES),
            "content_value_against_the_structured_model": (STRUCTURED, RULES),
            "reading_loss": (f"{model}:c", RULES),
            "trust_loss": (f"{model}:a", f"{model}:c"),
        }
        decomposition[model] = {
            name: {"minuend": pair[0], "subtrahend": pair[1]}
            | short(scored(rows.loc[ids], predictions, *pair, draws=draws, seed=seed), 2, source)
            for name, pair in parts.items()
        }
    secondaries["decomposition"] = decomposition

    def scores(ids: pd.Index, name: str) -> dict[str, Any]:
        """Every score of one predictor on the statements ``ids``, with the base rate's
        calibration in the large on the same statements beside its own."""
        chosen = rows.loc[ids]
        record = predictor_record(chosen, predictions[name], draws, seed)
        if name == BASE:
            return record
        return beside_base_rate(record, chosen, predictions[BASE], draws, seed)

    losses = {name: scores(rows.index, name) for name in gbm.PREDICTORS}
    overconfident = {}
    for model in models:
        ids = sets[model]
        if ids is None:
            continue
        for condition in CONDITIONS:
            losses[f"{model}:{condition}"] = scores(ids, f"{model}:{condition}")
        # the criterion is read on the item set the probe fixed, for both predictors
        zero_shot = f"{model}:a"
        overconfident[model] = {
            "items": set_records[model]["items"],
            **overconfidence(
                rows.loc[ids],
                predictions[zero_shot],
                predictions[BASE],
                study.parsed[zero_shot],
                draws,
                seed,
            ),
        }
    secondaries["overconfidence_of_condition_a"] = overconfident

    return {
        "items": {
            "eligible_statements": len(rows),
            "eligible_episodes": int(rows["episode_id"].nunique()),
            "scoreable_statements": len(scoreable),
            "scoreable_episodes": int(scoreable["episode_id"].nunique()),
            "with_a_horizon_event_undetermined": len(rows) - len(scoreable),
            "scoreable_by_E_end_and_E_end90": power.outcome_mix(scoreable),
        },
        "probe": probes,
        "item_sets": set_records,
        "family": family,
        "secondaries": secondaries,
        "losses": losses,
        "where_the_plan_is_silent": list(WHERE_THE_PLAN_IS_SILENT),
        "not_computed_here": list(NOT_COMPUTED_HERE),
    }


def unseal(
    sealed: bytes, events: pd.DataFrame, listed: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """The typed frame of the eligible statements with the primary outcome (the bracket of the
    displayed presentation under B), and the frames of the registered outcome variants: all
    covered presentations, any covered presentation, and the recovery definition A."""
    outcomes = sealed_counts._checked_rows(table_of(sealed, True), events)
    sealed_counts._same_build(listed, outcomes)
    filled = dataset.attach_outcomes(listed, outcomes)
    if not filled["scoreable"].isin(sealed_counts.FLAGS).all():
        raise ValueError("an eligible statement has no horizon event")
    variants = {
        "all_covered_presentations": typed_outcomes(filled, "_all"),
        "any_covered_presentation": typed_outcomes(filled, "_any"),
    }
    if "outcome_A" in outcomes.columns:
        under_a = dataset.attach_outcomes(listed, outcomes, "A")
        variants["recovery_definition_A"] = typed_outcomes(under_a)
    return typed_outcomes(filled), variants


# --------------------------------------------------------------------------------------------
# The printout and the table
# --------------------------------------------------------------------------------------------


def _number(value: Any, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _interval(pair: Any) -> str:
    """An interval for the printout; an end that is None is unbounded on its side."""
    if not pair:
        return "n/a"
    low = "-inf" if pair[0] is None else _number(pair[0])
    high = "inf" if pair[1] is None else _number(pair[1])
    return f"[{low}, {high}]"


def unbounded_note(registered: Mapping[str, Any], shown: Iterable[Any]) -> list[str]:
    """The line that says what an end printed as ``-inf`` or ``inf`` is, when one of the
    intervals ``shown`` in a text has such an end, and no line otherwise. Only an interval of
    the registered test can lack an end; the reach of its search is read from the record."""
    made = registered["intervals"]
    by_test = made["of_the_confirmatory_contrasts_and_delta_gbm"] == TEST_INTERVAL
    if not by_test or not any(pair is not None and None in pair for pair in shown):
        return []
    reach = made["search_reach_in_standard_errors"]
    return [
        "An end shown as -inf or inf is unbounded: the registered test does not reject the "
        f"furthest value searched on that side ({reach:g} standard errors from Delta; with a "
        "standard error of zero, one unit from Delta, or the size of Delta if that is more). It "
        "may reject values further away."
    ]


def overconfidence_lines(report: Mapping[str, Any]) -> list[str]:
    """One line for each primary whose runs were read: the reading of the overconfidence
    criterion (PLAN section 13) by its number and in the plan's words, then the numbers it
    rests on. Those are, for ``P(E_end)`` under condition (a) over every statement of the item
    set: the least and the greatest value of calibration in the large, each with the frequency
    taken away and its 95% interval, and the difference from the base rate's mean probability
    with its 95% interval; each part is said to be met or not. A primary without an item set
    has no reading, and its line says why."""
    lines = []
    found = report["secondaries"]["overconfidence_of_condition_a"]
    met = {True: "part met", False: "part not met"}
    for model, chosen in report["item_sets"].items():
        head = f"Overconfidence of condition (a), {model}"
        if model not in found:
            lines.append(f"{head}: no reading ({chosen['reason']}).")
            continue
        entry = found[model]
        first, second = entry["against_outcomes"]["E_end"], entry["against_base_rate"]["E_end"]
        lines.append(
            f"{head}: reading {entry['reading']} of {len(OVERCONFIDENCE_READINGS)}: "
            f"{entry['reading_in_words']}. P(E_end) on {entry['items']} ({entry['statements']} "
            f"statements in {entry['episodes']} episodes, {first['undetermined']} with E_end "
            f"undetermined): mean {_number(first['mean_p'])}. Against outcomes: least value of "
            f"calibration in the large {_number(first['least'])} "
            f"{_interval(first['least_ci95'])} (every undetermined E_end counted as yes: "
            f"frequency {_number(first['largest_frequency'])}), greatest "
            f"{_number(first['greatest'])} {_interval(first['greatest_ci95'])} (counted as no: "
            f"frequency {_number(first['smallest_frequency'])}); {met[first['met']]}. Against "
            f"the base rate (mean P(E_end) {_number(second['mean_p_base_rate'])}): difference "
            f"{_number(second['difference'])} {_interval(second['ci95'])}; {met[second['met']]}."
        )
    return lines


def markdown(report: Mapping[str, Any]) -> str:
    """The short table of the confirmatory results. Under the registered test the line of H2
    leads with the rule on the two p-values at the margin, which decides, and gives the 90%
    interval beside it; the counts beside it add up to the episodes that differ. After the
    probe lines stands the reading of the overconfidence criterion for each primary
    (``overconfidence_lines``). A last line says what an unbounded end is, when one is shown
    (``unbounded_note``)."""
    registered = report["registered"]
    made = registered["intervals"]["of_the_confirmatory_contrasts_and_delta_gbm"]
    lines = [
        "# Confirmatory results (PLAN.md section 6)",
        "",
        f"Registered p-values: {registered['p_value_source']}. Intervals of the six contrasts "
        f"and of Delta_GBM: {made}. H3 comparator rule: "
        f"{registered['h3_comparator']}. Holm over {registered['tests_in_the_family']} tests at "
        f"{registered['familywise_alpha']}; {registered['draws']} draws by shortage episode, seed "
        f"{registered['seed']}. Delta is the comparator's mean primary Brier minus the tested "
        "predictor's.",
        "",
        "| Test | Model | Comparator | Tested | Items | Statements | Episodes | Delta | 95% "
        "interval | p | Holm p | Reading |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in report["family"]:
        cells = [
            entry["hypothesis"],
            entry["model"],
            entry["comparator"],
            entry["tested"],
            entry.get("items", "n/a"),
            str(entry.get("statements", "n/a")),
            str(entry.get("episodes", "n/a")),
            _number(entry.get("delta")),
            _interval(entry.get("ci95")),
            _number(entry["p"]),
            _number(entry["p_holm"]),
            entry["reading"],
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    shown = [entry.get("ci95") for entry in report["family"]]
    for entry in report["family"]:
        if "equivalence" in entry:
            found, apart = entry["equivalence"], entry["losses_differ"]
            said = "declared" if found["declared"] else "not declared"
            shown.append(found["ci90"])
            how = f"{said} (90% interval {_interval(found['ci90'])}, margin {H2_MARGIN})"
            if "level" in found:  # the registered test at the margin decides, not the interval
                how = (
                    f"{said} by the rule, which needs both one-sided p-values below "
                    f"{_number(found['level'], 2)} at the margin of {H2_MARGIN}: "
                    f"{_number(found['p_larger_at_minus_the_margin'])} at {-H2_MARGIN} and "
                    f"{_number(found['p_smaller_at_the_margin'])} at {H2_MARGIN} (90% interval, "
                    f"reported beside the rule and not read for it: {_interval(found['ci90'])})"
                )
            lines.append(
                f"H2 equivalence, {entry['model']}: {how}. The two losses differ on "
                f"{apart['statements']} statements in {apart['episodes']} episodes: "
                f"{apart['episodes_with_a_positive_sum']} with a positive sum, "
                f"{apart['episodes_with_a_negative_sum']} with a negative one, "
                f"{apart['episodes_whose_differences_cancel']} whose differences cancel."
            )
        for name, beside in entry.get("beside", {}).items():
            if name == entry["comparator"]:
                continue  # that one is the row of the table itself
            shown.append(beside.get("ci95"))
            flag = "yes" if entry["beats_both_comparators"] else "no"
            lines.append(
                f"Beside H3, {entry['model']}: {name} minus {entry['tested']}: delta "
                f"{_number(beside.get('delta'))}, 95% interval {_interval(beside.get('ci95'))}; "
                f"beats both comparators: {flag}; answers of the tested condition not parsed: "
                f"{entry['scoreable_not_parsed'][entry['tested']]}."
            )
    for model, probe in report["probe"].items():
        chosen = report["item_sets"][model]
        where = chosen.get("items") or f"not evaluable ({chosen.get('reason')})"
        lines.append(
            f"Probe, {model}: delta {_number(probe.get('delta'))} days of pinball loss at 0.5 "
            f"(base rate minus probe), p {_number(probe['p'])}; tests on: {where}."
        )
    lines += overconfidence_lines(report)
    lines += unbounded_note(registered, shown)
    return "\n".join(lines) + "\n"


def summary_lines(report: Mapping[str, Any]) -> list[str]:
    items = report["items"]
    made = report["registered"]["intervals"]["of_the_confirmatory_contrasts_and_delta_gbm"]
    lines = [
        f"eligible: {items['eligible_statements']} statements in {items['eligible_episodes']} "
        f"episodes; scoreable: {items['scoreable_statements']} in {items['scoreable_episodes']}",
        f"p-values: {report['registered']['p_value_source']}; intervals of the six contrasts "
        f"and of Delta_GBM: {made}; H3 comparator: "
        f"{report['h3']['comparator']} (rule {report['registered']['h3_comparator']})",
    ]
    shown = []
    for entry in report["family"]:
        shown.append(entry.get("ci95"))
        lines.append(
            f"  {entry['hypothesis']} {entry['model']:15s} delta {_number(entry.get('delta'))} "
            f"{_interval(entry.get('ci95'))} p {_number(entry['p'])} Holm {_number(entry['p_holm'])}"
            f": {entry['reading']}"
        )
        for name in other_comparators(entry["comparator"]) if "beside" in entry else ():
            beside = entry["beside"][name]
            shown.append(beside.get("ci95"))
            flag = "yes" if entry["beats_both_comparators"] else "no"
            lines.append(
                f"     beside: {name} minus the tested condition, delta "
                f"{_number(beside.get('delta'))} {_interval(beside.get('ci95'))}; beats both "
                f"comparators: {flag}"
            )
    lines += [f"  {line}" for line in overconfidence_lines(report)]
    return lines + unbounded_note(report["registered"], shown)


# --------------------------------------------------------------------------------------------
# The commands
# --------------------------------------------------------------------------------------------


def open_paths(args: argparse.Namespace, names: Sequence[str]) -> None:
    """Refuse an open input or folder that lies in a sealed folder or is the sealed file: a
    sealed file is read only as ``--sealed``, behind its hash. The sealed path itself is
    compared as text; nothing on disk is looked at for it."""
    sealed = getattr(args, "sealed", None)
    for name in names:
        if is_sealed(getattr(args, name), sealed):
            refuse(
                f"--{name.replace('_', '-')} would be read from a sealed folder; only --sealed "
                "names a sealed file"
            )


def selection_hashes(values: Sequence[str]) -> dict[str, str]:
    """``--expect-selection-sha256 MODEL=SHA256`` as a mapping: once at most for each primary,
    each a sha256 or its first 16 or more hex characters."""
    out: dict[str, str] = {}
    for value in values:
        model, _, digest = value.partition("=")
        if model not in PRIMARIES or model in out:
            refuse(
                "--expect-selection-sha256 takes MODEL=SHA256, once for each primary model of "
                f"{list(PRIMARIES)}"
            )
        out[model] = sealed_counts.expected_hash(digest, "--expect-selection-sha256")
    return out


def skipped_models(values: Sequence[str]) -> dict[str, str]:
    """``--not-evaluable MODEL=REASON`` as a mapping; the model must be a primary, and the
    reason printable text on one line: it is written into the result file and the table, and a
    byte of the command line that was no text could not be written there."""
    out = {}
    for value in values:
        model, _, reason = value.partition("=")
        if model not in PRIMARIES or not reason.strip():
            refuse(f"--not-evaluable takes MODEL=REASON with a primary model of {list(PRIMARIES)}")
        if not reason.isprintable():  # a line break, or a byte that was no text
            refuse("--not-evaluable takes a REASON of printable text, on one line")
        out[model] = "declared on the command line: " + reason.strip()
    return out


def same_build(counts: Mapping[str, Any], hashes: Mapping[str, str]) -> None:
    """Refuse unless the statement table, the eligible list and, when the counts file names
    it, the events table are the files the dataset builder's counts file records."""
    outputs, inputs = counts.get("outputs") or {}, counts.get("inputs") or {}
    recorded = {
        "the statement table": (outputs.get(dataset.STATEMENTS.name) or {}).get("sha256"),
        "the eligible list": (outputs.get(dataset.ELIGIBLE.name) or {}).get("sha256"),
    }
    if "events_sha256" in inputs:
        recorded["the events table"] = inputs["events_sha256"]
    recorded = {what: value for what, value in recorded.items() if what in hashes}
    other = [what for what, value in recorded.items() if not hashes[what].startswith(value or "-")]
    if other:
        refuse(f"not the files the counts file of the dataset builder records: {', '.join(other)}")


def run_dev(args: argparse.Namespace) -> int:
    wrong = constants_problem()
    if wrong:
        refuse(wrong)
    if args.model not in PRIMARIES:
        refuse(f"--model takes a primary model of {list(PRIMARIES)}")
    open_paths(args, ("statements", "counts", "out_root"))
    out, _ = output_paths(args.out)
    statements = sealed_counts.file_bytes(args.statements, "the statement table")
    counts = sealed_counts.file_bytes(args.counts, "the counts file")
    hashes = {"the statement table": sealed_counts.sha256(statements)}
    same_build(json.loads(counts), hashes)
    plan, plan_sha, problems = read_plan(args.out_root)
    if plan is None or problems:
        refuse("; ".join(problems))
    table = table_of(statements, True)
    report = dev_report(args.model, table, json.loads(counts), plan, args.out_root)
    inputs = {
        "statements": args.statements.name,
        "statements_sha256": hashes["the statement table"],
        "dataset_counts_sha256": sealed_counts.sha256(counts),
        "plan_sha256": plan_sha,
        "code_sha256": code_record(),
    }
    command = (
        f"PYTHONPATH=. python -m analysis.coling.evaluate dev --model {args.model} --out <file>"
    )
    full = {"about": ABOUT_DEV, "command": command, "inputs": inputs, **report}
    write_new(out, report_text(full))
    print("\n".join(dev_lines(report)))
    print(f"wrote {out.as_posix()}")
    return 0


def open_tables(
    args: argparse.Namespace, expected_eligible: str | None
) -> tuple[dict[str, bytes], dict[str, str]]:
    """The bytes and the sha256 of the open inputs of one build: the eligible list (behind its
    expected hash when one is given), the statement table, the events table and the counts."""
    data = {
        "the eligible list": sealed_counts.file_bytes(args.eligible, "the eligible list"),
        "the statement table": sealed_counts.file_bytes(args.statements, "the statement table"),
        "the events table": sealed_counts.file_bytes(args.events, "the events table"),
        "the counts file": sealed_counts.file_bytes(args.counts, "the counts file"),
    }
    hashes = {what: sealed_counts.sha256(raw) for what, raw in data.items()}
    if expected_eligible is not None:
        sealed_counts.require_hash(
            data["the eligible list"], expected_eligible, "the eligible list"
        )
    same_build(json.loads(data["the counts file"]), hashes)
    return data, hashes


def run_baselines(args: argparse.Namespace) -> int:
    open_paths(args, ("statements", "eligible", "events", "counts"))
    out, _ = output_paths(args.out)
    if args.table is not None:
        output_paths(args.table)
    data, hashes = open_tables(args, None)
    table = table_of(data["the statement table"], True)
    eligible = table_of(data["the eligible list"], False)
    listed = sealed_counts.listed_statements(table, eligible)
    ids = list(listed["statement_group_id"])
    probe_ids = sorted(eligible.loc[eligible[PROBE] == "1", "statement_group_id"])
    _, predictions, probe_base, record = free_predictions(P.prepare(table), ids, probe_ids)
    report = {
        "about": ABOUT_BASELINES,
        "command": "PYTHONPATH=. python -m analysis.coling.evaluate baselines --out <file>",
        "inputs": {
            "statements_sha256": hashes["the statement table"],
            "eligible_sha256": hashes["the eligible list"],
            "code_sha256": code_record(),
        },
        "refit": record,
        "predictors": list(gbm.PREDICTORS),
        "eligible_statements": len(ids),
        "probe_statements": len(probe_ids),
        "predictions_sha256": baseline_hash(predictions, probe_base),
    }
    write_new(out, report_text(report))
    if args.table is not None:
        write_new(
            args.table, predictions_text({name: predictions[name] for name in gbm.PREDICTORS})
        )
    print(f"model-free predictions on {len(ids)} eligible statements")
    print(f"sha256 of the predictions: {report['predictions_sha256']}")
    print(f"wrote {out.as_posix()}")
    return 0


def first_sight_table(path: Path) -> tuple[pd.DataFrame, str]:
    """The first-sight columns of the statement table and the sha256 of the file. No outcome
    column is parsed."""
    data = sealed_counts.file_bytes(path, "the statement table")
    table = pd.read_csv(
        io.BytesIO(data),
        dtype=str,
        keep_default_na=False,
        compression="gzip",
        usecols=list(dataset.FIRST_SIGHT_COLUMNS),
    )
    return table, sealed_counts.sha256(data)


def run_check(args: argparse.Namespace) -> int:
    open_paths(args, ("statements", "eligible", "counts", "out_root", "selections"))
    skipped = skipped_models(args.not_evaluable)
    expected_selections = selection_hashes(args.expect_selection_sha256)
    table, statements_sha = first_sight_table(args.statements)
    eligible_bytes = sealed_counts.file_bytes(args.eligible, "the eligible list")
    eligible = table_of(eligible_bytes, False)
    counts = json.loads(sealed_counts.file_bytes(args.counts, "the counts file"))
    hashes = {
        "the statement table": statements_sha,
        "the eligible list": sealed_counts.sha256(eligible_bytes),
    }
    problems = [wrong] if (wrong := constants_problem()) else []
    if set(skipped) >= set(PRIMARIES):
        problems.append("every primary is declared not evaluable: no test can be computed")
    try:
        same_build(counts, hashes)
    except SystemExit as stop:
        problems.append(str(stop.code).removeprefix("refused: "))
    if args.expect_eligible_sha256:
        wanted = sealed_counts.expected_hash(
            args.expect_eligible_sha256, "--expect-eligible-sha256"
        )
        if not sealed_counts.sha256(eligible_bytes).startswith(wanted):
            problems.append("the eligible list is not the file of --expect-eligible-sha256")
    first = None
    try:
        first = sealed_counts.listed_statements(table, eligible).set_index("statement_group_id")
    except SystemExit as stop:
        problems.append(str(stop.code).removeprefix("refused: "))
    found = gathered(
        args.out_root,
        eligible,
        first,
        counts,
        args.selections,
        statements_sha,
        skipped,
        expected_selections,
    )
    problems += found.problems
    lines = [
        f"registered: p-values from {P_VALUE_SOURCE}; H3 comparator rule {H3_COMPARATOR}",
        f"eligible list: {len(eligible)} statements, {len(found.probe_ids)} in the probe subset",
    ]
    for model in PRIMARIES:
        if model in skipped:
            lines.append(f"{model}: not evaluable, {skipped[model]}")
            continue
        for condition, group in found.groups.get(model, {}).items():
            state = "ready" if not group.problems else "NOT ready"
            rows = group.record.get("rows", 0)
            lines.append(f"{model} {group.line or condition}: {rows} rows read; {state}")
        chosen = found.selections.get(model, {}).get("selected")
        lines.append(f"{model} H3 selection: {chosen or 'missing'}")
    lines += [f"missing: {problem}" for problem in problems]
    lines += [
        "not checked here: the sealed outcome file and its hash (the confirmatory command reads "
        "it last, behind --expect-sha256)",
        "not checked here: the refit of the model-free predictors (the confirmatory command "
        "makes it before the sealed file is read)",
        "nothing is missing for the confirmatory evaluation"
        if not problems
        else "NOT ready: no evaluation against test outcomes (PLAN section 6)",
    ]
    print("\n".join(lines))
    return 0 if not problems else 3


def run_confirmatory(args: argparse.Namespace) -> int:
    want_sealed = sealed_counts.expected_hash(args.expect_sha256, "--expect-sha256")
    want_eligible = sealed_counts.expected_hash(
        args.expect_eligible_sha256, "--expect-eligible-sha256"
    )
    want_baselines = sealed_counts.expected_hash(
        args.expect_baselines_sha256, "--expect-baselines-sha256"
    )
    want_selections = selection_hashes(args.expect_selection_sha256)
    wrong = constants_problem()
    if wrong:
        refuse(wrong)
    out, beside = output_paths(args.out, table=True)
    skipped = skipped_models(args.not_evaluable)
    if set(skipped) >= set(PRIMARIES):
        refuse(
            "every primary is declared not evaluable: no test of the family can be computed, and "
            "the sealed file is not opened for the secondaries alone"
        )
    unhashed = [
        model for model in PRIMARIES if model not in skipped and model not in want_selections
    ]
    if unhashed:
        refuse(
            f"--expect-selection-sha256 is required for {unhashed}: the H3 selections are held "
            "to the hashes of the freeze"
        )
    open_paths(args, ("statements", "eligible", "events", "counts", "out_root", "selections"))

    # open inputs, the completeness check and every prediction: before the sealed file
    data, hashes = open_tables(args, want_eligible)
    stopped = ""
    try:
        table = table_of(data["the statement table"], True)
        eligible = table_of(data["the eligible list"], False)
        events = table_of(data["the events table"], args.events.suffix == ".gz")
    except Exception as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"the open inputs are not as the builders write them ({stopped})")
    listed = sealed_counts.listed_statements(table, eligible)
    counts = json.loads(data["the counts file"])
    statements_sha = hashes["the statement table"]
    first = listed.set_index("statement_group_id")
    found = gathered(
        args.out_root,
        eligible,
        first,
        counts,
        args.selections,
        statements_sha,
        skipped,
        want_selections,
        args.sealed,
    )
    if found.problems:
        refuse(
            "no evaluation before every confirmatory run is complete (PLAN section 6): "
            + "; ".join(found.problems)
        )
    try:
        study, baselines_sha = open_study(table, listed, found, skipped)
    except Exception as error:
        stopped = type(error).__name__  # its message may name an item
    if stopped:
        refuse(f"the readings could not be turned into predictions ({stopped})")
    if study.problems:
        refuse("the readings cannot be scored: " + "; ".join(study.problems))
    if not baselines_sha.startswith(want_baselines):
        refuse(  # both at the length of the hash given, so that the two can be compared
            "the model-free predictions are not those hashed at the freeze: their sha256 "
            f"starts with {baselines_sha[: len(want_baselines)]}, expected {want_baselines}"
        )

    # the sealed file: hashed as bytes, parsed only when the hash is the expected one
    sealed = sealed_counts.file_bytes(args.sealed, "the sealed file")
    sealed_sha = sealed_counts.require_hash(sealed, want_sealed, "the sealed file")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # a warning may quote a cell
            rows, variants = unseal(sealed, events, listed)
            results = evaluate(study, rows, variants, P_VALUE_SOURCE)
        report = {
            "about": ABOUT_RESULTS,
            "command": "PYTHONPATH=. python -m analysis.coling.evaluate confirmatory "
            "--expect-sha256 <sealed file> --expect-eligible-sha256 <eligible list> "
            "--expect-baselines-sha256 <model-free predictions> --expect-selection-sha256 "
            "<model>=<selection file> (one for each primary) --out <file>",
            "registered": registered_record(),
            "inputs": {
                "sealed_outcomes_sha256": sealed_sha,
                "eligible_sha256": hashes["the eligible list"],
                "statements_sha256": hashes["the statement table"],
                "events_sha256": hashes["the events table"],
                "dataset_counts_sha256": hashes["the counts file"],
                "plan_sha256": found.plan_sha256,
                "baseline_predictions_sha256": baselines_sha,
                "baseline_predictions_checked_against_the_freeze": True,
                "code_sha256": code_record(),
            },
            "refit": study.refit,
            "h3": {"comparator": study.comparator, "selections": found.selections},
            "not_evaluable_by_declaration": skipped,
            "runs": study.runs,
            **results,
        }
        # every text is made before a file exists: a stop here must leave nothing behind
        record, table = report_text(report), markdown(report)
        printed = "\n".join(summary_lines(report))
        for text in (record, table):  # what cannot be written stops here too
            text.encode("utf-8")
    except Exception as error:
        stopped = type(error).__name__  # the error itself, and its message, go no further
    if stopped:
        refuse(
            f"the evaluation stopped on the sealed rows ({stopped}); the message is withheld "
            "because it may quote a sealed value"
        )
    write_new(out, record)
    assert beside is not None
    write_new(beside, table)
    print(printed)
    print(f"wrote {out.as_posix()} and {beside.as_posix()}")
    return 0


def arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = sealed_counts.Parser(
        prog="python -m analysis.coling.evaluate",
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

    dev = commands.add_parser("dev", allow_abbrev=False, help="dev losses and the H3 selection")
    dev.add_argument("--model", help="a primary model")
    dev.add_argument("--out", type=Path, help="the selection file to write; it must not exist")
    common(dev, "statements", "counts", "out-root")
    dev.set_defaults(run=run_dev)

    base = commands.add_parser("baselines", allow_abbrev=False, help="hash the model-free refit")
    base.add_argument("--out", type=Path, help="the record to write; it must not exist")
    base.add_argument("--table", type=Path, help="also write the predictions to this CSV")
    common(base, "statements", "eligible", "events", "counts")
    base.set_defaults(run=run_baselines)

    check = commands.add_parser("check", allow_abbrev=False, help="what is missing; no outcome")
    check.add_argument("--expect-eligible-sha256", help="sha256 of the eligible list")
    check.add_argument(
        "--expect-selection-sha256", action="append", default=[], metavar="MODEL=SHA256"
    )
    check.add_argument("--not-evaluable", action="append", default=[], metavar="MODEL=REASON")
    common(check, "statements", "eligible", "counts", "out-root", "selections")
    check.set_defaults(run=run_check)

    final = commands.add_parser("confirmatory", allow_abbrev=False, help="the six tests")
    final.add_argument("--expect-sha256", help="sha256 of the sealed file")
    final.add_argument("--expect-eligible-sha256", help="sha256 of the eligible list")
    final.add_argument("--expect-baselines-sha256", help="sha256 the baselines command printed")
    final.add_argument(
        "--expect-selection-sha256",
        action="append",
        default=[],
        metavar="MODEL=SHA256",
        help="sha256 of a primary's H3 selection file, as the freeze amendment records it",
    )
    final.add_argument("--out", type=Path, help="the result file to write; it must not exist")
    final.add_argument("--sealed", type=Path, default=SEALED, help="the sealed test outcomes")
    final.add_argument("--not-evaluable", action="append", default=[], metavar="MODEL=REASON")
    common(final, "statements", "eligible", "events", "counts", "out-root", "selections")
    final.set_defaults(run=run_confirmatory)
    return ap.parse_args(None if argv is None else list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = arguments(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
