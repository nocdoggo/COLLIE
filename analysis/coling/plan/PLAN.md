# Estimated Recovery: TBD. Study plan

**DRAFT (2026-09-29). Not registered.** This file becomes the study's registration when it is
committed and pushed with every **TBD-at-gate** value filled in by the rule written next to it
and the registration record (section 17) completed, before any language-model call of this study
(target: Saturday 3 October 2026; missing it is a hold trigger, section 12). Until then anything
here may change. After it, every change is a dated amendment at the end of this file (A1, A2, ...),
and the freeze of prompts, parsers, harness and the one registered model selection is amendment
F1, pushed before the first call on any test-period item.

Three markers are used:

- **TBD-at-gate**: depends on the Gate 1 counts (1 October); filled in before registration by the
  stated rule, never by looking at a test-period outcome.
- **TBD-at-registration**: a fact to confirm at its source before registration (model cutoffs,
  provider routes); it does not depend on the data.
- **TBD-at-F1**: fixed by amendment F1 (prompt text, code hashes, the H3 selection).

**Standing rules.**

- This study is separate from the UV 2026 paper's commitment study in `analysis/commitment/`.
  Nothing here changes a file under `analysis/commitment/`, `collie/`, `reports/` or `prereg/`;
  no arm, prompt, parser, alert bank, simulator, pool or result of that study is used (section
  15); `collie/data/alerts/templates/test.yaml` is never opened.
- *Sealing.* Outcomes of test-period statements (dated 2023-01-01 or later, including 2026) are
  computed by code and written only under `external_data/sealed/`. Before registration nobody
  prints, summarises or tabulates their values (hold rates, slips, recovery times, brackets).
  Counts of events, and of events with an observable outcome, may be printed. After
  registration they are read only by the test-period outcome audit (section 10), after every
  confirmatory run has finished, and by the registered evaluator. Outcomes of train-period
  statements (dated before 2023-01-01), followed only to the last capture before that date, may
  be examined at any time.
- *No paid calls* of any kind before registration.
- *No interim looks.* Nothing is evaluated against test-period outcomes until every
  confirmatory run (section 6) has finished.
- *Web requests* (collectors, gap filling) carry the project User-Agent
  `collie-research-fetch/0.1 (academic research; polite, cached)` and nothing personal in any
  header, URL or payload. At most one request per second, cached.
- *Budget.* A hard cap of $200 for the whole study (section 9).

## 1. Question

How do language models read forward-looking estimates in operational notices? The notices are
the FDA's public drug-shortage statements ("Next Delivery: July 2021; Estimated Recovery: Q4
2021", "Backordered. Next release mid-October", "Resupply TBD"). Each reading is scored three
ways:

1. against a human reading of the letter of the text;
2. against what actually happened, reconstructed from 2019 to 2026 archive captures;
3. by a decision loss.

The claim under test: models read the letter of an estimate correctly but not its pragmatics.
They copy optimistic dates, commit to a date where the text says TBD, and treat stale estimates
as live. The study also tests whether giving a model the issuer's track record in context closes
the gap.

The tests are registered so that either answer can be published (section 13). Issuer optimism
itself is not a claim: Chicoine and Griffin (2025) reported that estimated release dates slip, on
data under a non-disclosure agreement. Here the issuer's slip profile is descriptive context
(E1).

## 2. Data and units

### 2.1 Sources

- **FDA consolidated drug-shortage CSV via the Internet Archive** (the backbone):
  `accessdata.fda.gov/scripts/drugshortages/Drugshortages.cfm`, served as `text/csv`, a US
  federal government work.
  - On 29 September the archive's index listed 111 distinct capture days, from 20 October 2019
    to 27 September 2026 (2, 16, 10, 2, 9, 20, 16 and 36 per year, 2019 to 2026). Three long
    gaps: 308 days (November 2021 to October 2022), 184 days (May to November 2023) and 128 days
    (August to December 2025).
  - 65 captures were on disk when this draft was written. The manifest used, with the sha256 of
    every capture file, is **TBD-at-gate**.
  - Files are in `external_data/fda_wayback_csv/<timestamp>.csv`, fetched by
    `fetch_wayback_csv.py`.
- **FDA HTML detail pages via the archive**, used only to narrow outcome brackets inside the two
  test-period gaps (May to November 2023, August to December 2025), and only for ingredients
  with a test-period statement event. Same licence. The parser is frozen before registration;
  if the fill is not done by then, the gaps stay and the wider brackets are disclosed.
- **openFDA drug-shortage snapshots** (`api.fda.gov/drug/shortages.json`, CC0), one per day from
  28 September 2026, collected by `fetch_fda.py`. In October they serve only as a cross-check of
  the latest status. They are the prospective, leakage-free slice for the January version.
- **FAA Command Center advisories** (fly.faa.gov, US government works), April to September
  2026, collected in the background for E6 only.

The release (section 14) contains derived tables, statement texts and capture URLs. The Contact
Info column is dropped everywhere, including from prompts.

### 2.2 Parsing and harmonisation

Parsing and harmonisation are implemented in `corpus.py`, a draft frozen by hash at
registration.

**Decoding.** Each capture is decoded as utf-8-sig, falling back to latin-1. Leading blank lines
are skipped, and header names are stripped and mapped to canonical names.

**Malformed rows.** Rows with more cells than their header (unescaped quotes inside
Presentation or Related Information) are realigned by a fixed rule and flagged, and short rows
are padded. This draft's check found 34 such records in the 29 captures from 2019 to
2021 on disk; the count for every capture is reported.

**Field values.**

- Type of Update is snapped to New, Revised or Reverified by closest match, which catches
  "Reveriifed" and "Reverfied".
- Status is snapped to current, resolved or discontinued.
- Names are normalised: NFKC, lower case, quotes and dashes unified, whitespace collapsed.

**Presentation threads.**

- Rows are keyed by (listing, generic, company, presentation). The listing is either the
  shortage entry (status Current or Resolved) or the discontinuation entry (To Be Discontinued).
- Rows are linked from capture to capture, first on the exact key, then on overlapping package
  NDCs. The NDC link carries a thread through the FDA's reformatting of names, including its
  system change in November 2023 and relabelling after acquisitions.
- Generic names that are linked through threads share one `generic_id`.

**Availability.**

- A frozen rule classes the Availability Information as available or not. "Available" and
  "Inventory is currently available" are available; "limited", "allocation", "backorder" and
  "unavailable" are not.
- An author checks every distinct string that the rule classes as available. Each string is shown
  bare, without drug, company, date or capture, so the check reveals no statement's outcome.

### 2.3 Unit: the statement event

**Statement text.** A row's statement text is its Related Information, preceded by its
Availability Information whenever that field holds more than a bare availability label. Before
2023, estimates were often written in the Availability Information field; later it holds a
controlled label. Both raw fields are kept.

**Presentation events.** Within a thread, a new event starts when:

- the normalised statement text changes;
- the thread returns from Resolved to Current;
- the thread reappears, after missing at least one capture, with a different Date of Update.

A later row with the same text is a re-confirmation, not a new event. That covers a Reverified
re-stamp, and a Revised stamp with unchanged text.

The event is dated by the Date of Update of the row where it is first seen. If that date is
missing or later than the capture, the capture date is used instead. The event's revision index
counts the earlier events of its thread.

**Statement events: the unit of analysis.**

- The presentation events of one `generic_id` and company that share both normalised text and
  event date form one statement event. They are its *covered presentations*.
- This grouping keeps one sentence, repeated across many presentations, from being counted many
  times.

**At risk.** A statement event enters the outcome analyses only if it is on the shortage listing
and at risk when first seen:

- its status is Current;
- for definition B (section 2.5), it is also not available;
- its text carries a timing phrase, an explicit no-estimate phrase ("TBD", "unknown"), or no
  timing at all while the product is unavailable (*silent*).

**What a reader is shown.** The row as it stood at first sight:

- generic, company and presentation;
- Type of Update and Date of Update;
- Availability Information and Related Information;
- Reason for Shortage and Therapeutic Category;
- Status and Initial Posting Date.

Contact Info is never shown.

**What the events table holds.** Only what was known at first sight. Re-confirmation counts, the
next revision and every other fact from later captures are outcome information, and are stored
with the outcomes (sealed, for the test period).

**Size.** The design memo expects 800 to 1,500 distinct statement events over all years. The
actual counts are **TBD-at-gate**.

### 2.4 Clusters: shortage episodes

A *shortage episode* is one `generic_id`'s continuous listing. It runs from the generic's
Initial Posting Date (or its first appearance) to the capture at which its Status becomes
Resolved. A re-listing after resolution starts a new episode.

- Every statement event belongs to exactly one episode, whichever company issued it.
- Episodes are the resampling unit for every interval and every test.
- Effective sample sizes (the number of episodes, and events per episode) are reported with every
  estimate.
- The number of episodes is **TBD-at-gate**.

### 2.5 Outcomes

Outcomes are derived by rule, in `corpus.py`, and frozen before registration.

**Recovery, per covered presentation.** Each capture after the one where the event is first seen
gives every covered presentation a state under two definitions:

- **B, supply back (primary).** Recovered when the row's availability reads as available, or when
  A holds.
- **A, FDA resolved (secondary).** Recovered when the row has status Resolved, or when the row is
  absent while its generic is listed and Resolved.

B is never later than A.

**Recovery bracket.**

- The lower bound is the last capture at which the presentation was seen not recovered. It is no
  earlier than the capture where the event was first seen.
- The upper bound is the first capture that shows recovery.
- If neither recovery nor discontinuation has occurred by the last capture, the outcome is
  right-censored at the lower bound, with its reason: the presentation is still listed, or it
  left the list without a resolved generic.
- Sensitivity analyses: leaving the list without a resolution counts as recovery, and limited
  supply counts as available.

**Discontinuation** is a competing event, and it wins ties. A presentation is discontinued when it
newly appears in the discontinuation listing (by NDC overlap or the same text key), or when it
newly carries a Date Discontinued on or after the statement date.

**Statement-event level.**

- Primary: the event recovers when every covered presentation that is not discontinued has
  recovered, so `L_e = max L_p` and `U_e = max U_p`. If every covered presentation is
  discontinued, the event is discontinued.
- Sensitivity: the event recovers when any covered presentation has (`min` in place of `max`).

**Stated period.**

- The stated period is the period the text gives for recovery. If the text gives only a next
  delivery or release, that date is used, and the statement type is recorded as a covariate.
- The period comes from the *reference literal reading* (section 10), never from a predictor's
  own reading. The dataset builder supplies it to every predictor as `stated_end`.
- The conventions are those of `rules.py` and of the literal prompt, both frozen:
  - a month is the whole month;
  - a month with no year is its next occurrence on or after the anchor month;
  - early, mid and late are days 1 to 10, 11 to 20, and 21 to the month's end;
  - a quarter is the whole quarter;
  - a range runs from the start of its first element to the end of its last;
  - "by X", "until X" and "through X" are read as the period X, with the bound recorded;
  - when a text gives both a delivery date and a recovery date, the recovery date is used.
- `t_end` is the last day of the stated period.
- An event is *stale at issue* if `t_end < s`, where `s` is the statement date.

**Horizon events.** For a dated event that is not stale:

- `E_end`: recovered by `t_end`;
- `E_end90`: recovered by `t_end + 90 days`.

A horizon event at time `t` is *determined* when `U_e <= t` (answer yes) or `L_e >= t` (answer
no). Discontinuation counts as no at every horizon.

- An event is *scoreable* when both of its horizon events are determined. The scoreable events
  are E3's primary analysis set.
- An event is *observable*, in the Gate 1 sense of the design memo, when its recovery bracket
  under B is finite and no wider than 31 days. `corpus.py` records this as `observable31`.
- Gate 1 prints both counts.

**Time to recovery.**

- Measured in days from `s` to recovery, capped at 365. A discontinued event is given the cap.
- The target is interval-censored: `(L_e - s, U_e - s]`.
- It is defined for every event: dated, TBD or silent.

**Audit.** 100 derived outcomes are audited by hand (section 10).

### 2.6 Forms

Every event gets a *form class* from a frozen regex classifier built on the train split. The
provisional inventory, from distinct train-period strings:

- month and year ("Estimated Recovery: December 2022");
- a month with no year ("mid-October", "May 21");
- part of a month (early, mid, late);
- quarter ("Q4 2021");
- range ("February 2021 ... April 2021");
- relative ("late this week or early next week", "within 4 weeks");
- exact day;
- TBD or unknown ("To be determined", "the estimated duration is unknown");
- silent ("On long term backorder");
- distractor date present (expiry dating, "available until", depletion, launch);
- discontinuation.

Statement types are:

- next delivery or release;
- recovery;
- depletion;
- available until;
- discontinuation;
- none.

Certainty classes are provisionally those of `rules.py`: estimated, expected, anticipated, firm
and unknown. `AUDIT_GUIDE.md` fixes the final classes.

The final inventory, and the count per form and period, are **TBD-at-gate**. A form with fewer
than 15 events across all periods is merged into "other" for per-form tests. Templates are the
normalised texts with months and numbers masked; results are also reported weighted by template.

## 3. Splits

| Split | Statement dates | Use | Outcomes |
|---|---|---|---|
| Fit | before the dev boundary | rule normalisers, calibrator, GBMs, track-record table, in-context examples | open |
| Dev (validation) | dev boundary to 2022-12-31 | prompt development (format only), the H3 selection, power check | open |
| Test | 2023-01-01 to 2025-12-31 | E2 to E5 and E7 on test items; all confirmatory tests | **sealed** |
| Late | 2026-01-01 onward, with `t_end + 90` at or before the last capture | post-cutoff slices of the newest models only (descriptive) | **sealed** |

- **Dev boundary.** **TBD-at-gate**, by this rule: the latest month boundary in 2021 or 2022
  such that the dev split holds at least 150 scoreable dated events. If no boundary achieves
  this, 2021-07-01 is used and the shortfall is reported.
- **Final fits.** After the H3 selection, every model-free predictor is refitted on fit and dev
  together, before any test prediction.
- **Calendar overlap.** Train-period outcomes are followed only to the last capture before
  2023-01-01 (`corpus.py`): an event still open there is administratively censored
  (`end_of_train`), and no follow-up field reaches into the test period. Full follow-up would
  show how a thread stood in 2023 to 2026, which is the outcome of any test statement on the same
  thread, and a track-record table fitted on it would carry that into test predictions. The same
  train outcomes with full follow-up are sealed with the test outcomes
  (`outcomes_train_uncensored.csv.gz`); after unsealing, a sensitivity analysis refits every
  train-fitted component on them.
- **E3 eligibility.** All test events that are dated, not stale at issue, and have
  `t_end + 90` at or before the last capture used. Eligibility is selected by statement date and
  stated period, never by outcome. The primary analysis uses the scoreable ones.
  - The counts are **TBD-at-gate**: eligible events, scoreable events, and eligible events with
    a horizon event left undetermined.
  - TBD and silent test events enter E3's secondary analyses.
- **Post-cutoff slices.** For each model, the slice is the events dated after the last day of
  its training-cutoff month. The cutoff is the documented one (**TBD-at-registration**, from the
  model card). A model with no documented cutoff uses its release month (section 4). A slice is
  analysed only if it holds at least 50 scoreable events. The size of every slice is
  **TBD-at-gate**.

## 4. Models

Eight readers. Temperature 0 where the provider supports it. Provider defaults for reasoning,
recorded in F1. OpenRouter provider routing is pinned, and the served-model echo is checked on
every response. The prices are the dated list prices per 1M tokens retrieved 2026-09-28, as used
in the repository's ladder file. Reasoning and thinking tokens are billed as output.

| Model | Role | Route and id | Released | Training cutoff | $/1M in | $/1M out |
|---|---|---|---|---|---|---|
| llama-3.3-70b | **primary** | OpenRouter `meta-llama/llama-3.3-70b-instruct` | 2024-12 | December 2023 per the research digest; **TBD-at-registration** | 0.10 | 0.32 |
| deepseek-v3 | **primary** | OpenRouter `deepseek/deepseek-chat` | 2024-12 | **TBD-at-registration** | 0.257 | 1.029 |
| qwen-2.5-7b | secondary | OpenRouter `qwen/qwen-2.5-7b-instruct` | 2024-10 | **TBD-at-registration** | 0.10 | 0.20 |
| gemma-3-27b | secondary | OpenRouter `google/gemma-3-27b-it` | 2025-03 | **TBD-at-registration** | 0.08 | 0.45 |
| gpt-oss-20b | secondary | OpenRouter `openai/gpt-oss-20b` | 2025-08 | **TBD-at-registration** | 0.018 | 0.09 |
| gpt-4o-mini | secondary | OpenRouter `openai/gpt-4o-mini` | 2024-07 | **TBD-at-registration** | 0.15 | 0.60 |
| gemini-3.8-flash | secondary | Google `gemini-3.8-flash` | 2026-09 | **TBD-at-registration** | 0.75 | 3.75 |
| grok-4.20 | secondary | xAI `grok-4.20-0309-non-reasoning` | 2026-03 | **TBD-at-registration** | 1.25 | 2.50 |

- **Why these primaries.** Both are open-weight models with early documented or bounded cutoffs,
  which the memorisation controls need. The checkpoint is pinned through the provider route. The
  primaries alone enter the confirmatory family.
- **The secondaries.** They span size, openness and recency; they are reported descriptively
  along those axes.
- **Parse failures.**
  - An answer that fails the strict schema or the semantic checks gets exactly one repair call:
    a separate, cached request that shows the model its answer and the errors. If the repaired
    answer still fails, a literal reading counts as ABSTAIN, and a predictive reading is
    replaced by the base-rate predictor's output for that event (flagged).
  - Parse rates are reported per model and condition. A sensitivity analysis uses only the
    events that both compared conditions parsed.
- **Cleaning predictive outputs.** Non-monotone quantiles are sorted. Probabilities are clipped
  to [0, 1].

## 5. Experiments

"Must" is the October core. "Should" runs only if it passes its gate. "Could" runs only if time
remains, and otherwise moves to January. Call counts and costs are in section 9.

### E1. Build OpEst-FDA and describe the issuer (must; $0)

Build the statement events, clusters and outcomes of section 2.

**Descriptives, computed by the registered evaluator after every confirmatory run for the test
period, and at any time for the train period.**

- The hold rate of the stated period, `P(E_end)`.
- The slip distribution: recovery minus `t_end`, a Turnbull estimate by form and by revision
  index (1, 2, 3 or more).
- The distribution of bracket widths.
- Counts by year, form, statement type and company.

**Intervals.** Percentile bootstrap, 95%, clustered by episode.

**Standing.** None of this is in the confirmatory family. Optimistic or calibrated issuers are
both context for E3, and neither is a failure.

**Audit.** 100 outcomes are audited by hand, stratified by era (section 10).

### E2. Literal reading against human labels and rule normalisers (must; about $15)

**Items.**

- 300 distinct statements, stratified by form. Rare forms are oversampled, and so are 2019 to
  2021, whose text is richer.
- They are drawn from all periods, since a literal reading involves no outcome.
- Excluded: in-context examples, minimal-pair seeds and dev prompt items.
- The per-form allocation is **TBD-at-gate** (at least 15 per form where the form has that many).

**Gold.** Author labels, as described in section 10.

**Prompts.**

- One frozen literal prompt that states the conventions of section 2.5 (`literal-v1` in
  `read.py`).
- A convention-free variant, as a secondary (`literal-free-v1`).
- Both are pinned by SHA-256 and frozen at F1.

**Output schema.**

- statement type;
- an interval anchored to the Date of Update, or ABSTAIN;
- certainty class;
- stale flag.

**Readers.** All eight models, and the rule normalisers of section 8.

**Metrics.** See section 7.1. Results are reported by form, and weighted by event and by
template.

**Test (a secondary family with its own error control, separate from H1 to H3).**

- For each form with at least 15 items, and each primary model, an exact McNemar test compares
  the model with the rule baseline selected on the train split and frozen at F1.
- A reading is correct when the statement type is right and either both readings abstain or the
  interval IoU is at least 0.5.
- Holm's correction runs over all of these tests (forms × 2) at 0.05.
- Descriptive only: a mixed logistic model, correct ~ reader × form + (1 | template).

**Positive result.**

- Rules roughly equal the models on month-and-year text.
- The models lead by at least 0.15 IoU on vague, no-year, range and distractor forms.
- False commitment on TBD or silent items exceeds 5% for at least one model.

**Negative result.** Rules match the models everywhere. The paper then says that literal reading
is solved for this register, and its weight moves to E3.

### E3. Pragmatic reading against outcomes: the headline (must; about $40 to $60)

**Items.** Every E3-eligible test event (section 3). The primary analysis uses the scoreable
ones.

**Reader outputs.** For every event, each reader gives:

- `P(E_end)`;
- `P(E_end90)`;
- quantiles 0.1, 0.5, 0.8, 0.9 and 0.95 of the time to recovery in days, capped at 365.

For TBD and silent events, where no `t_end` exists, the readers give:

- `P(recovered within 90 days)`;
- `P(recovered within 180 days)`;
- the same quantiles.

**LLM conditions, for all eight models.**

- **(a) Zero-shot.** The notice alone (`predictive-v1`).
- **(b) Track record in context** (`predictive-track-v1`). The notice, plus the issuer's slip
  table by form (the E1 train-period descriptives), plus 10 resolved fit-split examples. For
  the dev runs of the H3 selection the table comes from the fit split alone; for test runs,
  from the whole train period (fit and dev). The examples are drawn by a frozen seeded rule,
  stratified by form, and are disjoint from dev and test.
- **(c) Literal reading plus calibrator.** The model's literal reading (`literal-v1`, run on the
  E3 items) is passed through the fixed empirical slip calibrator (section 8).

**Primaries only.**

- 20 samples at temperature 1 on a 300-item subset, to compare sampled quantiles with verbalised
  ones.
- 3 prompt paraphrases of (b) on a 200-item subset, to measure prompt variance.

Subsets are drawn by a frozen seeded rule, stratified by year.

**Baselines.** Section 8.

**Metrics.** Section 7.2.

**Confirmatory family.** Section 6.

**Descriptive decomposition.** For each model, on the scoreable events, with the loss taken as
the primary Brier (section 7.2):

- the text's content value: loss(structured-only) − loss(reference reading + calibrator);
- the reading loss: loss(model reading + calibrator) − loss(reference reading + calibrator);
- the trust loss: loss(condition a) − loss(model reading + calibrator).

**Secondaries (no multiplicity claim).**

- Every metric for all eight models and all conditions.
- The H1 to H3 contrasts for the six secondary models.
- Post-cutoff slices.
- The recovery definition A (FDA resolved).
- The "any presentation" outcome.
- The horizon-event bounds.
- Cluster resampling by company, and a fit that leaves out the dominant company (Hospira and
  Pfizer).
- The full-follow-up refit of every train-fitted component (after unsealing).
- Stale-at-issue events: stale-value uptake, which is the share of readers giving
  `P(E_end) > 0.5` for a period that has already passed.
- TBD and silent events against the base-rate predictor.
- Sampled against verbalised quantiles.
- Prompt variance.

### E4. Leakage and memory controls (must; about $10)

**No-notice probe (all eight models; `probe-v1`).** 300 test events are drawn by a frozen
seeded rule. Each
model is shown the generic, company, presentation, statement date and Initial Posting Date, but
no statement text, and gives time-to-recovery quantiles.

- *Test.* Pinball loss at 0.5, against the base-rate predictor by listing age. The comparison
  uses a one-sided paired cluster bootstrap at 0.05, not adjusted.
- *Rule.* A model that beats the base rate is excluded from outcome claims on events dated before
  its cutoff.
- *For a primary model,* its three confirmatory tests are then evaluated on its post-cutoff slice
  instead of on the full test set. This switch is decided by the probe alone, before any H test
  is computed, and the family keeps six tests.

**Name and date 2×2 (primaries, condition b, 300-item subset).**

- The factors are real against fictitious name, crossed with the true dates against all dates
  shifted by a whole number of years.
- Masking removes the generic, company, NDC and strength.
- Reported as descriptive: the change in primary loss, and the mean absolute change in
  `P(E_end)` and in the median, across cells.

**Post-cutoff slice for each model.** As in section 3.

**Negative result.** Heavy memorisation, which shrinks the headline to the post-cutoff slices.
That is reportable.

### E5. Minimal pairs from attested forms (must, reduced; about $15)

**Items.**

- About 800 items from about 100 real seeds. The seeds are stratified by form and disjoint from
  E2 and from in-context examples.
- Names are fictitious, and gold labels follow by construction.

**Factors, varied one at a time from the seed.**

- Certainty marker, attested only: estimated, expected, anticipated, TBD, "no estimated release
  date", "as it is released".
- Surface form.
- Granularity: early, mid or late, month ranges, "timeframe", quarters.
- Stale against fresh.
- Distractor date: depletion, "available until", expiry.
- Silent (no date given).

**Targets.**

- The literal output should not change when the meaning does not, and should change correctly
  when it does.
- Predictive widening is compared with two authors' predictive readings on 100 pairs, labelled
  "two author readers" and not described as norms. It is not compared with a ratio of 1.

**Test.**

- A mixed-effects logistic regression: error ~ factor × model + (1 | seed) + (1 | render).
  Firth's correction is used if the data separate. If the model does not converge, the
  registered fallback is a GEE clustered by seed.
- 100 items are audited by hand (section 10).

**Positive result.** Named factors (stale, distractor, TBD) cause errors in named models.

**Negative result.** Invariance holds, and the pairs become a robustness check.

### E6. Estimative terms at the FAA Command Center (should; gated on 4 October; about $15)

**Data.** Planned ground-stop and ground-delay lines, with their extension-probability fields,
from April to September 2026. Reissued plans are deduplicated to (element, initiative, window)
chains at their first issuance, with lead time as a covariate.

**Registration.** E6 is registered by its own amendment at its gate. The amendment fixes:

- the outcome codebook;
- the development months (provisionally April and May) and the test months (provisionally June
  to September);
- the term list.

This happens before any test month is linked.

**Linker gate.** At least 150 links checked by hand, at least 30 per term, and at least 90% of
checked links correct. The 90% threshold is a draft value for the owner to confirm.

**Readers.** All eight models give a probability for each term, in isolation and in context,
under two framings: what the writer conveys, and whether it will happen.

**Baselines.**

- A term-frequency lookup.
- A logistic model on airport × hour × programme type.
- A masked-hedge ablation, with the term replaced by [TERM].
- Perfect information.

**Metrics.** Three gaps, reported separately:

- the perception gap (model against author reading);
- issuer calibration (realised rate against the conventional meaning);
- the total gap.

Also the Brier decomposition, and the cost-loss expense at C/L of 0.2, 0.5 and 0.8, relative to
climatology.

**Test.** GEE clustered by day. MEDIUM against MODERATE is reported as confounded with programme
type.

**Positive result.** For at least one term, the realised rate differs from both readings by at
least 15 points, and in-context readings add resolution beyond the lookup.

**Negative result.** The models already track the register.

### E7. Pricing reading errors, after Crystal et al. 2005 (could, cut only after E6; $0)

This uses the E3 test events whose reference reading is an author label (section 10). For each
model, the gold literal reading is swapped in one error class at a time, with the calibrator
held fixed, and the change in primary Brier and in pinball loss is reported.

- **Positive result.** Named error classes carry most of the cost.
- **Negative result.** Reading errors are cheap next to the trust loss, which supports the
  headline.

### E8. Real revision threads (could; descriptive; about $15)

150 to 300 chains with at least 3 revisions, primaries only, condition (b).

- The full thread, in chronological and in latest-first order, is compared against the latest
  statement alone.
- Measured: stale-value uptake, the update ratio, and whether the thread's own slip history
  improves the primary loss.

### E9. Crowd norms for estimative terms (could; not run in October)

The owner chose an author audit with no crowd study (29 September). E9 moves to January, and
runs only with an ethics approval in hand. It would use 40 to 60 paid raters on about 20 terms,
in isolation and in context, plus about 40 vague FDA texts.

## 6. Confirmatory family

**Tests.** Six tests: H1, H2 and H3, each for llama-3.3-70b and for deepseek-v3.

**Holm.** Holm's step-down at a familywise 0.05 runs over all six. A hypothesis holds for a model
when its Holm-adjusted p is below 0.05.

**Items.** The scoreable E3 events, or a primary's post-cutoff slice under the E4 rule.

**Endpoint.** The primary Brier (section 7.2). Every contrast `Δ` is the comparator's mean loss
minus the tested predictor's mean loss, so that a positive `Δ` favours the tested predictor.

**H1: track-record uptake** (one-sided). `Δ = loss(m-a) − loss(m-b) > 0`. Condition (b) beats
condition (a).

**H2: reading in isolation** (two-sided). `Δ = loss(rules + calibrator) − loss(m-c) ≠ 0`. Both
sides share the same frozen calibrator, so only the literal reading differs.

- *Equivalence.* It is declared when the 90% interval lies inside ±0.02 Brier. This is part of
  the H2 reading, but not a separate test in the family. The 0.02 margin is a draft value for
  the owner to confirm.
- *Caveat.* On canonical forms the reference reading is the audited rule output (section 10),
  which favours the rules there. H2 is therefore also reported on the author-labelled
  (non-canonical) events, as a secondary.

**H3: value of the text** (two-sided). `Δ = loss(structured-only GBM) − loss(m-best) ≠ 0`.

- `m-best` is the one of `m`'s three conditions (a, b, c) with the lowest primary loss on the
  dev split.
- The selection is recorded in F1, before any test call.
- The text-trained GBM, and rules plus slip, are each compared with the structured-only GBM in
  the same way, as registered secondaries.

**Resampling.** A paired cluster bootstrap by shortage episode: 10,000 draws, seed 20261001. Each
draw resamples episodes with replacement and computes both predictors' mean losses on the same
draw.

**p-values.** They come from the bootstrap distribution of `Δ`.

- One-sided (H1): `(1 + #{Δ* <= 0}) / (B + 1)`.
- Two-sided (H2, H3): `min(1, 2 × min((1 + #{Δ* <= 0}) / (B + 1), (1 + #{Δ* >= 0}) / (B + 1)))`.

**Intervals.** Estimates carry 95% percentile intervals; H2 also carries its 90% interval.

**Sensitivity.** A cluster sign-flip test on the episode sums of the paired differences.

**Power.**

- The minimum detectable `Δ` for each hypothesis is **TBD-at-gate**. It is estimated before
  registration from dev-split outcomes (paired loss variances of the model-free predictors,
  scaled to the Gate 1 counts), at 80% power under the Holm worst case of 0.05/6.
- Low power does not stop the study. It is written into the paper.

**Confirmatory runs.** These must all finish before any evaluation:

- E3 conditions (a), (b) and (c) for both primaries on every eligible event;
- the E4 probe for both primaries;
- every model-free predictor of section 8 on the same events.

**Evaluator.** The registered evaluator (**TBD-at-F1**: file and hash) refuses a run that is
partial, a run whose echoed model differs from its registered id, and a run whose event set
differs from the eligible set.

## 7. Metrics

### 7.1 Literal (E2, E5, condition c)

- **Statement-type accuracy.**
- **Interval IoU**, in days.
- **Endpoint error** of the start and end, in days.
- **Abstention** precision, recall and F1. Abstention is correct when the gold reading gives no
  date.
- **False-commitment rate:** the share of gold-ABSTAIN items (TBD, unknown, silent) where the
  reader outputs a date.
- **Stale-flag** accuracy and F1.
- **Distractor uptake:** the share of items with a distractor date where the reader returns that
  date as delivery or recovery.
- **Certainty-class** accuracy and Cohen's kappa against gold.

Each is reported per form, weighted by event and by template.

### 7.2 Against outcomes (E3, E4, E7, E8)

- **Primary Brier.** For event `i`, the primary loss is `(BS_i(E_end) + BS_i(E_end90)) / 2`, where
  `BS = (p − y)^2`.
  - The primary analysis uses scoreable events (complete case).
  - *Bounds:* every undetermined horizon event is set to 0, and then to 1. Both results are
    reported.
- **Brier decomposition** into reliability, resolution and uncertainty (Murphy), with 10
  equal-count bins, for each horizon event.
- **Decision loss.** The pinball loss at τ 0.5, 0.8 and 0.95 on the time to recovery.
  - Pinball at the critical fractile τ = c_u / (c_u + c_o) is the expected cost of buffering
    stock until recovery. The three τ are generic cost ratios of 1:1, 4:1 and 19:1.
  - An interval-censored target is scored with the midpoint of its bracket. The loss bounds (the
    minimum and maximum over the bracket) are reported too.
  - A right-censored target beyond the cap is scored at the cap.
- **Coverage** of the 80% interval `[q0.1, q0.9]`, counted on events whose bracket lies wholly
  inside or wholly outside the interval.
- **Probe and 2×2 metrics** (E4): as defined in E4.
- **Selective prediction:** loss against abstention rate, for readers that abstain.

## 8. Baselines and conditions

**Freezing.** Every model-free component is fitted on the fit split, selected on dev, refitted on
fit and dev together, and frozen by hash before any test call.

**Rule normalisers.**

- HeidelTime and SUTime, with the document date set to the Date of Update, if both can be
  installed by F1. If either cannot, it is disclosed as not run.
- A regex normaliser with the conventions of section 2.5.

Coverage per form is reported honestly. The rule baseline used in E2 and H2 is the one with the
highest literal accuracy on the author-labelled train-period pilot items, recorded in F1.

**Empirical slip calibrator.** Turnbull estimates of slip, by form class and revision index (1,
2, 3 or more), from fit-split events.

- Given a literal reading with period end `ŝ`, `P(E_end) = F_slip(t_end − ŝ)`, and the quantiles
  are `ŝ − s` plus the slip quantiles.
- When the reading is ABSTAIN, the calibrator falls back to the no-date time-to-recovery
  distribution by listing age.

**Structured-only quantile GBM (the content-free control).**

- Features: reason, therapeutic category, time since posting, Status, company and calendar
  month. No free text.
- It gives quantiles at 0.05 to 0.95. The resulting CDF is read at each horizon.
- Censoring in fitting: bracket midpoints for interval-censored events. Right-censored fit events
  take their Turnbull conditional tail. The details are frozen by hash in F1.

**Text-trained quantile GBM.** TF-IDF on the availability and related text, plus the structured
features. This baseline is what makes H3 an NLP question.

**Other predictors.**

- **The stated date at face value** (the issuer as forecaster): `P(E_end) = P(E_end90) = 1`, with
  every quantile at `t_end − s`.
- **Base-rate remaining duration** by listing age.
- **Rules plus slip.**
- **The LLM literal reading plus slip**, which is condition (c).
- **The reference reading plus slip:** a perfect literal reader, used only in the decomposition.

**LLM conditions.**

- (a), (b) and (c).
- The masked-name and date-shifted cells (E4).
- The convention-free literal prompt (E2).
- 3 paraphrases (E3).
- 20 samples against verbalised quantiles (E3).

**Human references.**

- The double-labelled subset gives the literal ceiling, scored leave-one-out.
- The two author readers in E5.
- No crowd in October.

**FAA (E6).** The lookup, the airport × hour × programme model, the masked hedge, and perfect
information.

**Threads (E8).** The latest statement only, against the full thread in both orders.

## 9. Budget

The study-wide hard cap is **$200**. It covers every run, including dev runs and cost trials, and
`read.py` enforces it in two ways:

- A run does not start unless the spend recorded by every run so far, plus this run's own cap,
  fits within $200.
- Before every paid call, the call is refused if its projected cost would take the run past
  its cap.

Runs launched in parallel must split what remains of the $200 between their caps. Every call is
logged with its tokens and its price.

**Price of a call.** Input tokens × the input price per 1M, plus output tokens (including
reasoning or thinking) × the output price per 1M, at the prices in section 4.

**Estimate.** Per-call costs come from the commitment study's logs where they exist; otherwise
they are token counts times list prices. Every call count depends on the number of E3-eligible
events, which is **TBD-at-gate**; the figures below assume about 1,000.

| Model | Calls | Cost per call | Estimate | Cap |
|---|---|---|---|---|
| gemini-3.8-flash | ~7,000 | ~$0.011 (thinking billed; commitment-study logs) | ~$77 | $110 |
| grok-4.20 | ~7,000 | ~$0.0025 | ~$18 | $30 |
| deepseek-v3 | ~13,000 (with samples, paraphrases, dev, 2×2) | ~$0.0004 | ~$6 | $12 |
| llama-3.3-70b | ~13,000 | ~$0.00015 | ~$2 | $5 |
| qwen-2.5-7b, gemma-3-27b, gpt-oss-20b, gpt-4o-mini | ~7,000 each | ~$0.0001 to $0.00025 | ~$4 together | $3 each |
| **All** | **~68,000** | | **~$107** | caps $169; reserve $31 |

**Calls per model.**

- *Every model:*
  - E2: 600 (two prompts);
  - E3: three conditions × the eligible events;
  - E4 probe: 300;
  - E5: about 800;
  - E6: about 1,200, if it runs.
- *Primaries, in addition:*
  - dev runs for the H3 selection: 3 × the number of scoreable dev events (**TBD-at-gate**);
  - the 2×2: 900;
  - paraphrases: 600;
  - samples: 6,000.

**Cost trial.** After registration and before F1, each model runs 20 dev items per task type. The
trial's cost is scaled to the registered call counts and recorded in F1.

**If a projection exceeds a cap or the total**, the following apply in order until the
projection fits:

1. E6 is dropped for gemini-3.8-flash and grok-4.20.
2. gemini-3.8-flash runs only E2 and E3.
3. gemini-3.8-flash is dropped.

**Resuming a run.** A run stopped by its cap or by a provider error is resumed from its cache,
under the same name. Its cap may be raised within the reserve, and each resumption is logged as
an amendment. A run that cannot finish is reported as incomplete.

## 10. Annotation: author audit

**The annotators are the authors.** This is declared in the ARR Responsible NLP checklist; there
is no crowd study and no ethics review (owner decision, 29 September). The procedure, label
definitions and screens are in `AUDIT_GUIDE.md`, frozen by hash at registration.

**Blinding.** Every annotator is blind to outcomes, to later captures and to model outputs. They
see only the row as defined in section 2.3. Adjudication is done by an author who does not write
prompts.

**Tasks.**

1. **Pilot and guideline.** 30 items from all forms are double-labelled, followed by a guideline
   revision (v0 to v1) before registration.
   - Hold trigger: Krippendorff's alpha below 0.6 on endpoint offsets after the pilot and the
     revision.
2. **E2 gold.** One author labels the 300 E2 statements. A second author double-labels 60 vague,
   TBD or silent items among them.
   - Agreement is reported by form: Krippendorff's alpha (interval) on endpoint offsets in days
     from the anchor month, and Cohen's kappa on abstention and on certainty class.
3. **E3 reference readings.** These define `t_end` for every E3-eligible test event.
   - For a form class whose frozen rule output matches author labels on at least 95% of
     audited train-period items, the rule output is the reference. A random 100 of these test
     events are author-checked as well; if agreement falls below 95%, that form goes to author
     labelling.
   - Every other test event is labelled by an author.
   - The labelling load is **TBD-at-gate**: the count of eligible events in non-canonical forms.
   - The labels are finished and hashed before any E3 output is opened.
4. **Outcome audit.** 100 derived outcomes, stratified by era.
   - 50 are from the train period, audited before registration to check the rule.
   - 50 are from the test period, audited only after every confirmatory run has finished and
     before the evaluator runs.
   - Pass: at least 95% of audited brackets agree with the auditor's reading of the captures.
   - A failure fixes the rule (never single items), re-derives and re-seals the outcomes, and is
     logged with the new hash as an amendment.
5. **Minimal-pair audit.** 100 E5 items. At least 95% of labels must match the text. Otherwise
   the generator is fixed and a fresh 100 are audited, with the fix logged.
6. **E5 predictive readings.** Two authors on 100 pairs.
7. **E6 link checks**, if E6 runs: at least 150 links.

**Estimated load.** About 10 to 12 hours per author, plus the E3 reference labels
(**TBD-at-gate**).

## 11. Leakage controls

- **Temporal split.** By statement date. Test outcomes are sealed, with their hash recorded at
  registration.
- **Fitting.** Every fitted component and the track-record table come from the train period
  only (the fit split for dev runs; fit and dev for test runs), and the in-context examples
  from the fit split. No test item appears in any prompt.
- **Prompt development.** Only on dev items, with at most 3 variants per prompt, all disclosed.
  Prompts are selected by parse rate and format compliance, and never by an outcome loss. The
  one outcome-based choice is the H3 selection on dev, recorded in F1.
- **E4.** The no-notice probe and its exclusion rule, the name and date 2×2, and the post-cutoff
  slices.
- **Masking.** Generic, company, NDC and strength are masked in the 2×2. Minimal pairs use only
  fictitious names.
- **Checkpoints.** Pinned provider routes and served-model echo checks. A response that echoes a
  different model is refused.
- **Blinding and looks.** Annotators are blind (section 10). There are no interim looks, and the
  evaluator refuses partial runs.

## 12. Gates, schedule and cut order

| Day | Work |
|---|---|
| Tue 29 Sep | Collectors: CSV captures, the openFDA daily snapshot, FAA in the background. Guideline v0. This draft. |
| Wed 30 Sep | Parse and harmonise. Build statement events and clusters. Derive and seal the outcomes. Install the rule normalisers. |
| **Thu 1 Oct** | **Gate 1 (counts).** Form inventory. E2 sample and minimal-pair seeds drawn. 30-item pilot. Minimal-pair generator. |
| Fri 2 Oct | Guideline v1. Rules, calibrator and GBMs frozen on the train split. Power check on dev outcomes. Every TBD-at-gate value filled in. Registration pushed. |
| **Sat 3 Oct** | **Registration deadline.** Dev prompt development and 20-item cost trials. H3 selection. **F1 pushed.** E2 and E5 launched. Annotation runs 3 to 5 October. |
| Sun 4 Oct | E3 and E4 runs. **E6 linker gate.** Data and task sections drafted. |
| Mon 5 Oct | Annotation done and agreement computed. E6 if it passed. E8 if time allows. Test-period outcome audit after the confirmatory runs. |
| **Tue 6 Oct** | Registered evaluator. **Gate 2: submit or hold.** All numbers frozen. |
| Wed 7 Oct | Secondaries, figures, E7. An independent session reproduces every table. |
| 8 to 9 Oct | Write the 8 pages. |
| Sat 10 Oct | Limitations, ethics, datasheet, Responsible NLP checklist with the AI-assistance disclosure. Overlap check against the UV text. |
| Sun 11 Oct | Independent check of every number and claim. Anonymised supplement. |
| Mon 12 Oct | ARR submission (23:59 AoE). The UV camera-ready (due 15 October) wins any collision. |

**Gate 1 (1 October).** Counts only; no outcome value is printed. All four thresholds must hold:

- at least 600 distinct statement events dated 2023 to 2025 with a stated date;
- at least 250 of them observable (bracket of 31 days or less; the scoreable count is
  printed beside it);
- at least 100 shortage episodes among them;
- at least 150 observable events dated after llama-3.3-70b's documented cutoff.

**Hold triggers.** Any one of these moves the paper to ARR January 2027:

- Gate 1 fails;
- the pilot alpha stays below 0.6;
- the registration is not pushed by 3 October;
- numbers are not frozen by 6 October;
- the UV camera-ready needs more than 1.5 days before 12 October.

**Gate 2 (6 October).** Submit if:

- every confirmatory run is complete;
- the registered evaluator has run;
- the E2 agreement is computed;
- no hold trigger has fired.

Gate 2 never looks at the sign or significance of any result. A registered negative result is
submitted.

**Cut order.** Cuts are made in this order when time runs short:

1. E8;
2. E9;
3. E6;
4. E7;
5. fewer models, 8 down to 6. The two dropped are the secondary models whose runs are least
   complete at the time of the cut; ties go gemma-3-27b first, then gpt-4o-mini;
6. E5 down to 400 items.

E1, E2, E3 (with conditions b and c) and E4 are never cut.

**Plan B (ARR January 2027, for ACL 2027 or another ARR venue, not COLING).** The same paper,
plus:

- the openFDA prospective slice;
- FDA text from 2014;
- a full year of FAA data, with crowd norms;
- a second jurisdiction;
- an outcome-supervised small reader.

## 13. What counts as a result

**Positive, in the order the paper would state it.**

- Models read the letter well but not the pragmatics. False commitment on TBD or silent text, or
  stale-value or distractor uptake, is measurably above the rules or above the human ceiling for
  named models (E2, E5).
- The zero-shot predictive readings are overconfident relative to outcomes (E3).
- The models use an issuer's track record when it is given (H1 holds).
- The free text carries value beyond the structured fields (H3 holds in favour of the text).
- On H2, an LLM reading beats the rules (a reading effect), or equivalence holds (reading is not
  the bottleneck). Both are informative.

**Negative, publishable because registered.**

- The models do not use the track record even when shown it (H1 fails).
- The text adds nothing beyond the structured fields, or loses to them (H3 null or in favour of
  the structured model).
- Literal reading is solved for this register (E2).
- Invariance holds on the minimal pairs (E5).
- Memorisation confines the outcome claims to post-cutoff slices (E4).

The issuer's own optimism or calibration (E1) is context, never a result for or against the
claim.

**Expected, not evidence.**

- From Chicoine and Griffin (2025): a face-value reader will be overconfident on `E_end`, and
  condition (b) should reduce the primary Brier.
- H2 is expected to be small, because canonical forms dominate.
- H3 is open.

**Not claimed.**

- A new method.
- Issuer optimism as a new finding.
- "First" (the paper writes "to our knowledge").
- That models "understand" anything.
- The term "commitment" (the label layer is "certainty class").

## 14. Outputs and release

**Public outputs** go to `analysis/coling/out/`. Raw model outputs, caches and logs go to
`external_data/`, which git ignores. Sealed outcomes stay under `external_data/sealed/` until
evaluation.

**The release** is prepared as anonymised supplementary material. It contains:

- derived tables and texts, without Contact Info;
- capture URLs;
- author labels;
- minimal pairs;
- every model's raw outputs;
- a datasheet.

## 15. Relation to the UV 2026 paper

None of the UV paper's methods or results is used, restated or claimed. That means:

- no certify-then-hedge, e-process or exposure bound;
- no simulator or synthetic alert;
- no ShockSpec, arm, prompt or parser from `analysis/commitment/`;
- no model-ladder accuracy;
- no content-free-control result.

τ values are not justified by the UV paper's cost ratios. No negative result is framed as a
"real-data counterpart" of it.

**One citation.** The paper cites it once, in the third person, as motivation, and discloses it
on the ARR form with a statement of how the two differ. The reused text is checked with an
n-gram script against the UV text, with a target of near zero and a limit of 10% of tokens.

**Shared plumbing.** `read.py` imports some of the repository's shared infrastructure, unchanged.
None of it is a method of either paper.

- From `analysis/commitment/endpoints.py`: the model ladder, with its dated prices, and the
  served-model echo check.
- From `analysis/real_content_pilot/transport.py`: the guarded transport, which handles
  retries, the spend cap and the spend log.

## 16. Disclosed prior contact

Before this draft:

- **The design memo (29 September)** inspected five CSV captures, from 2020, 2021, 2024, January
  2025 and December 2025, for text yield. It found 341 distinct timing texts over 147 drugs, which
  reduce to 186 templates.
- **The design pilot** fetched 40 archived HTML detail pages from 2023 and read their timing
  snippets. This was text only; no outcome was derived.
- **FAA.** A 2024 FAA pilot sample.
- **openFDA snapshots** (28 and 29 September). The only aggregate read was that 7 of the first
  pull's 1,599 records were resolved.
- **Other pilot files** in `external_data/pilot/`: a July 2025 capture, one 2025 detail page,
  2026 list pages and the 2025 capture index, downloaded for format checks. Whether they were
  read beyond their format is not recorded.
- **This draft's author** read the field vocabulary of one 2020 capture and a random sample of
  distinct availability strings from the 29 captures of 2019 to 2021 (train period).

To our knowledge, no test-period outcome has been derived, printed or tabulated.

## 17. Registration record (to complete before pushing)

Hashes are the first 16 hex characters of sha256.

- **Capture manifest:** the file list and the hash of each capture. **TBD-at-gate.**
- **Code:** `corpus.py` (events, clusters, outcomes) and `rules.py` (the regex reader), plus
  the form classifier, the calibrator and the GBMs. Files not yet written, and every hash, are
  TBD.
- **Sealed outcome file** (`external_data/sealed/outcomes_test.csv.gz`, which `corpus.py`
  writes reproducibly): its hash. TBD.
- **E3 eligible event list:** its hash. **TBD-at-gate.**
- **`AUDIT_GUIDE.md`:** its hash. TBD.
- **Every TBD-at-gate value above**, with the Gate 1 counts.
- **Model cutoffs and routes.** **TBD-at-registration.**
- **At F1:**
  - the `read.py` templates and parsers, with their SHA-256 pins;
  - the hashes of `read.py` and of the evaluator;
  - the dev prompt variants tried;
  - the cost-trial projection;
  - the H3 selection for each primary;
  - the rule baseline chosen for E2 and H2;
  - provider pins.

## Amendments

None yet.
