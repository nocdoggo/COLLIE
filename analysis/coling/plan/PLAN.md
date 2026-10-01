# Estimated Recovery: TBD. Study plan

**DRAFT (2026-10-01). Not registered.** This file becomes the study's registration when all of
the following hold, before any language-model call of this study:

- every **TBD-at-gate** and **TBD-at-registration** marker is replaced by its value, by the rule
  written next to it;
- every **[owner to confirm]** tag is resolved (the rule confirmed or changed, and the tag
  removed);
- the registration record (section 17) is complete;
- this paragraph is replaced by the registration statement, and the commit is pushed and tagged
  (section 17, "Identity").

The target is Saturday 3 October 2026, 23:59 AoE; missing it is a hold trigger (section 12).
Until then anything here may change. What changed since the draft of 29 September, and what had
been seen when it changed, is listed in "Changes from the 29 September draft" near the end of
this file. After registration every change is a dated amendment at the end of this file (A1, A2,
...), and the freeze of prompts, parsers, harness and the one registered model selection is
amendment F1, pushed before the first call on any test-period item.

Four markers are used:

- **TBD-at-gate**: depends on the frozen corpus build, the form classifier, the dataset builder,
  the samples, the pilot or the model-free predictors. It is filled in before registration by the
  stated rule, never by looking at a test-period outcome value.
- **TBD-at-registration**: a fact confirmed at its source before registration (model release
  dates and cutoffs, provider endpoints and their prices). It does not depend on the data.
- **TBD-at-F1**: fixed by amendment F1 (final prompt pins, code hashes of the harness and the
  evaluator, fitted artefacts, the H3 selection).
- **[owner to confirm]**: a provisional rule written on 1 October that the owner has not yet
  confirmed.

The commit id and the push time of the registration cannot be written into the file they
identify, so they carry no marker; section 17 says where they are recorded.

All deadlines in this file are in Anywhere on Earth time (AoE, UTC−12): 23:59 AoE on a day is
11:59 UTC on the next day.

**Standing rules.**

- This study is separate from the UV 2026 paper's commitment study in `analysis/commitment/`.
  Nothing here changes a file under `analysis/commitment/`, `collie/`, `reports/` or `prereg/`;
  no arm, prompt, parser, alert bank, simulator, pool or result of that study is used (section
  15); `collie/data/alerts/templates/test.yaml` is never opened.
- *Sealing.* Outcomes of test-period statements (dated 2023-01-01 or later, including 2026) are
  computed by code and written only under `external_data/sealed/` (`outcomes_test.csv.gz`). The
  train-period outcomes with full follow-up (`outcomes_train_uncensored.csv.gz`) are sealed with
  them. From 1 October on, both files are written only by the freeze run of the corpus builder
  and by the one rerun that checks it (section 17); after registration, only by a rule fix
  that a failed test-period audit forces, logged as an amendment (section 10).
  - Before registration nobody prints, summarises or tabulates test-period outcome values (hold
    rates, slips, recovery times, brackets). The sealed files are read only by the counts-only
    code of section 3, run once at the freeze.
  - What may be printed: counts of events, of events with an observable outcome, and of events
    whose horizon events are determined (section 2.5). No count is broken down by an outcome
    value.
  - After registration the sealed outcomes are read only by the sampler and the sheets of the
    test-period outcome audit (section 10), after every confirmatory run has finished, and by
    the registered evaluator.
- *Open train outcomes.* Outcomes of train-period statements (dated before 2023-01-01) are
  followed only to the train horizon, the last capture before 2023-01-01 (2022-10-06), and may
  be examined at any time (section 3, "Calendar overlap").
- *Threads in the open events table.* The events table is open and holds every statement of
  every period as it stood at first sight. The later rows of a thread show that the thread was
  still listed, which is outcome information about its earlier statements. Before registration
  nothing is tabulated from the later rows of a thread, and every fitting script filters to the
  train period before any join.
- *No paid calls* of any kind before registration, and no API key in the environment of any
  build before the registration is pushed. Dry runs and scripted test clients only.
- *No interim looks.* Nothing is evaluated against test-period outcomes until every
  confirmatory run (section 6) has finished.
- *The rule reader is frozen.* `rules.py` is frozen at sha256 prefix `6a810bcb1ae277b9` (its
  state since 29 September). The pilot (section 10) may change the guide and the prompt text; a
  difference from `rules.py` that remains is disclosed, not patched.
- *Seeds.* Every random draw uses seed 20261001, with the items sorted by id before the draw.
- *Web requests.* The study's collectors carry the project User-Agent
  `collie-research-fetch/0.1 (academic research; polite, cached)` and nothing personal in any
  header, URL or payload. They keep what they download and wait between requests: 6 seconds
  for the capture fetcher, at least 1 second for the FAA collector. Two exceptions are
  disclosed. The openFDA collector sends the page requests of one snapshot (two, at the list's
  present size) with no pause between them. The model facts of section 4 were read on 1 October
  through a general page reader that sets its own User-Agent; nothing personal was sent.
- *No names.* The annotators are A1 and A2 in every file. No personal name or address is written
  to any file or sent in any request.
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
as live. The study also tests whether giving a model the track record of earlier estimates on
the same list closes the gap.

The tests are registered so that either answer can be published (section 13). Issuer optimism
itself is not a claim: Chicoine and Griffin (2025) reported that estimated release dates slip, on
data under a non-disclosure agreement. Here the slip profile of the list is descriptive context
(E1).

## 2. Data and units

### 2.1 Sources

- **FDA consolidated drug-shortage CSV via the Internet Archive** (the backbone):
  `accessdata.fda.gov/scripts/drugshortages/Drugshortages.cfm`, served as `text/csv`, a US
  federal government work. Files are in `external_data/fda_wayback_csv/<timestamp>.csv`, fetched
  by `fetch_wayback_csv.py`.
  - *The capture set is frozen at the 110 files on disk*, fetched on 29 September 2026. They
    cover 109 capture days from 2019-10-20 to 2026-09-26: 2, 17, 10, 2, 9, 20, 16 and 34 files
    for 2019 to 2026 (30 October 2020 has two). 31 files, on 30 days, precede 2023-01-01.
  - The archive's index, as read by the fetcher on 29 September, lists 115 captures on 111 days,
    the last on 27 September 2026. Five of them are not used, because the fetcher stores each
    distinct content once and their content digest repeats the capture before them:
    `20201030175604`, `20240718132655` and `20260316070704` fall on a day that has a file;
    `20260919234058` and `20260927234314` are the only captures of their days and repeat the
    previous day's content.
  - *Rule.* A capture whose content repeats the capture before it is not a capture of this
    study. The last capture used is therefore 2026-09-26, one day before the archive's last.
    Lower bounds of brackets and the cut "`t_end + 90` on or before the last capture" (section
    3) use the 110 files only. Captures the archive adds later are not used.
  - *Gaps.* The median gap between capture days is 9 days, and 81% of gaps are 31 days or
    less. Five gaps exceed 90 days: 95 days (2019-12-29 to 2020-04-02), 308 days (2021-11-30 to
    2022-10-04), 99 days across the train and test periods (2022-10-06 to 2023-01-13), 184 days
    (2023-05-14 to 2023-11-14) and 128 days (2025-08-03 to 2025-12-09).
  - *Manifest.* `analysis/coling/out/capture_manifest.csv` lists every file with its size and
    sha256 (`python -m analysis.coling.manifest`). The full build of the corpus stops when the
    folder does not match it. The manifest's own sha256 is in section 17.
- **FDA HTML detail pages via the archive.** Not used. The draft allowed a fill of the two
  test-period gaps (May to November 2023, August to December 2025) from archived detail pages.
  No fetcher or parser was written, so the fill is not done (owner decision, 1 October); the
  gaps stay, and the wider brackets are disclosed.
- **openFDA drug-shortage snapshots** (`api.fda.gov/drug/shortages.json`, CC0), collected by
  `fetch_fda.py`. Two snapshots are on disk, dated 28 and 29 September 2026. In October they
  serve only as a cross-check of the latest status. Daily collection was planned from 28
  September and has not run since the 29th. The October study does not depend on it; the
  snapshots are the prospective, leakage-free slice of the January version, which loses every
  day on which none is taken.
- **FAA Command Center advisories** (the advisory database at `www.fly.faa.gov/adv/`, US
  government works), for E6 only. The draft said they were being collected in the background;
  on 29 September only a 2024 pilot sample was on disk. `faa_fetch.py` started collecting the
  advisories of April to September 2026 on 1 October, into `external_data/faa_atcscc/2026/`.
  The months after the development months are not parsed or linked before E6's own amendment
  (section 5, E6).

The release (section 14) contains derived tables, statement texts and capture URLs. The Contact
Info column is dropped everywhere, including from prompts.

### 2.2 Parsing and harmonisation

Parsing and harmonisation are implemented in `corpus.py`, frozen by hash at registration.

**Decoding.** Each capture is decoded as utf-8-sig, falling back to latin-1. Leading blank lines
are skipped, and header names are stripped and mapped to canonical names.

**Malformed rows.** Rows with more cells than their header (unescaped quotes inside
Presentation or Related Information) are realigned by a fixed rule and flagged, and short rows
are padded. The builder prints the number of realigned rows for every capture; the registered
counts (rows kept, rows dropped as duplicate or without a status, rows realigned per capture)
are **TBD-at-gate**, from the freeze run.

**Field values.**

- Type of Update is snapped to New, Revised or Reverified by closest match, which catches
  misspellings such as "Reveriifed" and "Revisee".
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

- A fixed rule classes the Availability Information of a row as blank, unavailable, limited,
  available or other, checked in that order. "Unavailable", "backorder", "out of stock" and
  the like are unavailable; "limited", "allocation" and the like are limited.
- A string is *available* only when some mention of "available" or "in stock" reports supply
  on hand now. A mention does not count when it is negated ("no release date available at this
  time"), future or estimated ("will be available in June", "estimated date available"), or
  directly followed by a time ("available by 4/5/19", "available March 2019"). A string with no
  mention that counts is other.
- *Author check.* The adjudicator (section 10) checks the distinct strings behind the rule,
  from the list that `corpus.py` writes (`analysis/coling/out/availability_strings.csv`). Each
  string is shown bare, with its class and the number of capture rows that carry it, and
  nothing else: no drug, company, date or capture, so the check reveals no statement's outcome.
  - *Required:* every string that the rule classes as available, and every string that the
    rule change of 1 October moved out of available.
  - *Optional:* the strings classed limited. They matter for the BL sensitivity analysis
    (section 2.5), and for B only where a string in fact reports full supply. If they are not
    checked, the paper says so.
  - A string the checker rejects goes into a list frozen with `corpus.py` and is then classed
    other. A string that the rule moved out of available and the checker would keep is settled
    before the freeze run: the rule is changed, or the difference is recorded here.
- The check is done before the freeze run. Its date, the number of strings checked (required
  and optional) and the number rejected are **TBD-at-gate**.

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
missing, or later than the capture by more than one day, the capture date is used instead. The
event's revision index counts the earlier events of its thread, from 0.

**Statement events: the unit of analysis.**

- The presentation events of one listing, `generic_id` and company that share both normalised
  text and event date form one statement event (`statement_group_id`). They are its *covered
  presentations*.
- This grouping keeps one sentence, repeated across many presentations, from being counted many
  times.

**At risk.** A statement event enters the outcome analyses only if it is at risk when first
seen. Two conditions are applied by `corpus.py`, per covered presentation:

- it is on the shortage listing with status Current (at risk under definition A, section 2.5);
- for definition B, its availability class is also not available.

A statement event is at risk under a definition when at least one covered presentation is, and
its outcome follows the at-risk presentations only. A third condition is applied by the dataset
builder, from the form class of section 2.6:

- the text is *dated* (the frozen rule reading gives a recovery or next-delivery period: the
  nine dated forms), *TBD or unknown* (the form `tbd`), or *silent* (the form `silent`: no
  statement about timing and no date in another role). The form here is the classifier's own
  class, before any merge of small classes (section 2.6).

A statement at risk under B whose text is in none of these (a vague or undated statement, a
discontinuation statement, or a text whose only date is a distractor) stays in the outcome file
and enters no outcome analysis set. The count of such statements is **TBD-at-gate**.

**The display row.** Readers and annotators see one row per statement event. When the statement
covers several presentations, one of its presentations at risk under B is drawn by the seeded
rule (seed 20261001, members sorted by event id; no outcome field is used) and shown. A
statement with no presentation at risk under B, which can enter only the literal task, shows
its member with the smallest event id. The same draw is used everywhere: in every prompt, on
every annotation sheet and for the primary outcome (section 2.5).

**What a reader is shown.** The display row as it stood at first sight:

- generic name, company and presentation;
- Therapeutic Category and Initial Posting Date;
- Type of Update and Date of Update (the event date, in ISO form);
- Availability Information and Related Information;
- Reason for Shortage.

Status is not shown: it is Current on every at-risk statement. Contact Info is never shown.
These are the fields of the entry block of the prompt templates and of the annotation sheets;
Therapeutic Category and Initial Posting Date were added on 1 October, before the pilot sheets
are made, so that the models see what the structured baseline uses (section 8).

**What the events table holds.** Only what was known at first sight. Re-confirmation counts, the
next revision and every other fact from later captures are outcome information, and are stored
with the outcomes (sealed, for the test period).

**Size.** The counts of presentation-level events and of distinct statement events, by period
and split, are **TBD-at-gate**, from the freeze run and the dataset builder. The draft's
expectation of 800 to 1,500 statement events was too low by about a factor of ten (section 16
gives the counts printed so far).

### 2.4 Clusters: shortage episodes

A *shortage episode* is a run of consecutive captures in which a `generic_id` is Current, that
is, in which at least one of its shortage rows has status Current. A capture where the generic
is Resolved or not listed ends the run, and a later Current capture starts a new episode. The
episode is named by the generic and the date of the run's first capture. The Initial Posting
Date is not used.

- A statement event belongs to the episode of its generic at its first capture, whichever
  company issued it. Every statement that is Current at first sight has an episode, including
  one that is not at risk under B because it is available.
- A shortage-listing event that is Resolved at first sight has no episode, unless another row of
  its generic is Current in that capture. Discontinuation-listing events have none. Neither kind
  enters an outcome analysis.
- Episodes are the resampling unit for every interval and every test on outcomes. Agreement
  statistics on annotation resample items (section 10).
- Effective sample sizes (the number of episodes, and events per episode) are reported with every
  estimate.
- Episodes cross the split: an episode that began before 2023 can hold train and test
  statements. Train-fitted components and test items then share a cluster. Train censoring
  (section 3) removes the outcome overlap, not the shared cluster. The number of test episodes
  that also hold train statements is reported.
- The number of episodes in each analysis set, and the number that cross the split, are
  **TBD-at-gate**.

### 2.5 Outcomes

Outcomes are derived by rule, in `corpus.py`, and frozen before registration.

**Recovery, per covered presentation.** Each capture after the one where the event is first seen
gives every covered presentation a state under two definitions:

- **B, supply back (primary).** Recovered when the row's availability class is available
  (section 2.2), or when A holds.
- **A, FDA resolved (secondary).** Recovered when the row has status Resolved, or when the row is
  absent while its generic is listed and Resolved.

B is never later than A. A third definition, **BL**, counts limited supply as available and is a
sensitivity analysis for B. A capture where the row is absent while its generic is Current or
not listed says nothing.

**Recovery bracket.**

- The lower bound is the last capture at which the presentation was seen not recovered. It is no
  earlier than the capture where the event was first seen.
- The upper bound is the first capture that shows recovery or discontinuation.
- *The last capture an outcome may use.* For a test-period event it is the last capture of the
  archive (2026-09-26). For a train-period event it is the train horizon (2022-10-06), or the
  event's own first capture if that is later (section 3).
- If neither recovery nor discontinuation has occurred by that capture, the outcome is
  right-censored at the lower bound, with one of five reasons:
  - `end_of_train`: a train-period event still not recovered at its last usable capture;
  - `end_of_archive`: a test-period event still listed and not recovered at the last capture;
  - `no_followup`: a test-period event first seen at the last capture;
  - `absent_generic_current`: the row left the list while its generic stayed Current;
  - `absent_generic_unlisted`: the row left the list and its generic is no longer listed.
- Sensitivity analyses: leaving the list without a resolution counts as recovery at the first
  capture where the row is missing, and limited supply counts as available (BL).

**Discontinuation** is a competing event, and it wins ties. A presentation is discontinued when
it newly appears in the discontinuation listing (by NDC overlap or the same text key). A Date
Discontinued cell on a shortage row is not used: in the train captures it mostly repeats the
date of a resolution and appears on products that stayed on the market. The first capture where
such a cell newly appears is kept in the column `date_discontinued_on_row_date`, for a
sensitivity analysis.

**Statement-event level.**

- *Primary: the displayed presentation.* The outcome of a statement event is the bracket
  `(L, U]` of its display row (section 2.3) under B. The prompts ask about "this presentation",
  so the question and the score agree.
- *Secondary: all covered presentations.* The event recovers when every at-risk presentation
  that is not discontinued has recovered (`L = max L_p`, `U = max U_p`); it is censored when any
  such presentation is; it is discontinued when every one is.
- *Sensitivity: any covered presentation* (`min` in place of `max`).

**Stated period.**

- The stated period is the period the text gives for recovery. If the text gives only a next
  delivery or release, that date is used, and the statement type is recorded as a covariate.
- The period comes from the *frozen rule reading* (`rules.py`) for every form and every split:
  train, dev, test and late. It never comes from a predictor's own reading or from an author
  label. The dataset builder supplies its last day to every predictor as `stated_end`, and the
  predictive prompts print it as horizon A.
- The rule reading is checked, not replaced: the authors check 100 eligible test statements and
  the rule's accuracy is reported (section 10).
- The conventions are those of `rules.py`, which the literal prompt and the guide share:
  - a month is the whole month, and a year alone is the whole year;
  - a month, quarter or half with no year is its first occurrence that ends on or after the
    Date of Update;
  - early, mid and late are days 1 to 10, 11 to 20, and 21 to the month's end;
  - a quarter is the whole quarter, and a half is January to June or July to December;
  - a range runs from the start of its first element to the end of its last;
  - "by X" and "before X" run from the Date of Update to the end of X (or are X itself when X
    ends before the Date of Update); "until X" and "through X" are the period X; the bound is
    recorded;
  - a relative time counts from the Date of Update, with a week of 7 days and a month of 30;
  - a vague time ("a few months", "soon") gives no period;
  - when a text gives both a delivery date and a recovery date, the recovery date is used.
- `t_end` is the last day of the stated period.
- An event is *stale at issue* if `t_end < s`, where `s` is the statement date.

**Horizon events.** For a dated event that is not stale:

- `E_end`: recovered by `t_end`;
- `E_end90`: recovered by `t_end + 90 days`.

A horizon event at time `t` is *determined* when `U <= t` and the upper bound shows recovery
(answer yes), or when `L >= t` (answer no). Discontinuation counts as no at every horizon. For a
train-period event the horizon events are determined within its usable captures only.

- An event is *scoreable* when both of its horizon events are determined. The scoreable events
  are E3's primary analysis set. Scoreability depends on where the captures fall: a recovery
  inside a long gap between captures leaves a horizon event undetermined. The bounds of section
  7.2 are therefore reported beside every estimate on the scoreable set.
- An event is *observable* when its bracket, to recovery or to discontinuation, is finite and no
  wider than 31 days. `corpus.py` records this as `observable31`.

**Delayed entry.** A statement enters the corpus at the first capture after its date, and
enters the outcome analyses only if it is still not available at that capture. A statement
issued and resolved between two captures is never seen. Every hold rate and slip distribution
is therefore conditional on the shortage having lasted to first sight, and short estimates that
held are under-represented.

- A statement first captured after its stated period had ended stays eligible.
- A registered sensitivity analysis repeats the E3 analyses on the statements first captured on
  or before `t_end`.
- The count of eligible statements first captured after `t_end` is **TBD-at-gate**. No
  tabulation of this set by year, form or company is made before the evaluator runs.

**Time to recovery.**

- Measured in days from `s` to recovery, capped at 365. A discontinued event is given the cap.
- The target is interval-censored: `(L - s, U - s]`.
- It is defined for every event: dated, TBD or silent.

**Audit.** 100 derived outcomes are audited by hand (section 10).

### 2.6 Forms

Every statement event gets exactly one *form class* from a frozen classifier (`forms.py`). The
classifier adds no reading rule of its own: it runs the frozen rule reader and names the result,
so the form, the stated period and the eligibility of a statement all come from one reading. It
was developed on train-period text only. The classes are tested in a fixed order and the first
that fits is the form. The inventory as the classifier stands on 1 October, in that order:

1. relative: a time counted from the Date of Update ("within 4 weeks", "3-18 months");
2. range ("the March/April timeframe", "4Q 2021 to 1Q 2022");
3. exact day ("June 5, 2021");
4. part of a month ("late August", "mid-October", "week of 10/28");
5. half of a year ("1H 2022");
6. quarter ("Q4 2021", "early Q3");
7. year ("2023", "late 2020");
8. month with no year ("Next release December.");
9. month and year ("Estimated Recovery: December 2022");
10. TBD or unknown ("Estimated Recovery: TBD", "Shortage duration is unknown");
11. vague ("for few months", "long-term backorder");
12. no date: a delivery stated with no time at all ("Product will be made available as it is
    released");
13. discontinuation, dated or not;
14. distractor: no delivery, recovery or discontinuation statement, but a statement or a date
    in another role (a depletion or "available until" statement, dated or not; expiry dating;
    a past event);
15. silent: none of the above ("On backorder", "Check wholesalers for inventory").

Classes 1 to 9 are the *dated* forms: the target statement is a recovery or a next delivery and
has a period, whose last day is the stated end. Two flags are kept beside the class: whether
the period's year was not written and was taken from the Date of Update, and the number of
distractor dates beside the target (a text can carry one whatever its form).

A class with fewer than 15 train-period statements at risk under B is merged into a named
neighbour class, for per-form reporting and for every table or cell fitted by form (the
calibrator, the track-record table). The literal-task sample is stratified on the unmerged
classes. Templates are the normalised texts with months and numbers masked; results are also
reported weighted by template.

The final inventory and order, the merge map as applied, and the count per form and split are
**TBD-at-gate**, from the classifier on the frozen build (its hash is in section 17).

Statement types are the five of the literal answer schema:

- recovery;
- next delivery or release;
- depletion (which includes "available until");
- discontinuation;
- none.

Certainty classes are the four of the literal answer schema and the guide: asserted, estimated,
undetermined and no statement. `rules.py` keeps a sixth statement type and five certainty words
internally and maps them onto these.

## 3. Splits

| Split | Statement dates | Use | Outcomes |
|---|---|---|---|
| Fit | before 2021-01-01 | calibrator, GBMs, track-record table, in-context examples | open, followed to 2022-10-06 |
| Dev (validation) | 2021-01-01 to 2022-12-31 | prompt development (format only), the H3 selection, power check | open, followed to 2022-10-06 |
| Test | 2023-01-01 to 2025-12-31 | E2 to E5 on test items, and E7 if it runs; all confirmatory tests | **sealed** |
| Late | 2026-01-01 onward | literal items of E2 only; not read for outcomes in October | **sealed** |

The dataset builder assigns the four splits. The events table and the sealed file keep the
builder's two periods, train (before 2023-01-01) and test (from 2023-01-01, which includes
Late).

- **Dev boundary: 2021-01-01, a fixed date.** The draft's rule (the latest month boundary
  leaving at least 150 scoreable dev events) gives a dev split that is almost all "no" at both
  horizons, because train outcomes stop at 2022-10-06 and no capture exists between 2021-11-30
  and 2022-10-04 ("Changes from the 29 September draft", item 3). The numbers of scoreable dev
  and fit statements, their episodes, and the dev outcome mix (the counts of no/no, no/yes and
  yes/yes on the two horizon events) are **TBD-at-gate**, from the dataset builder.
- **Fit outcomes run past the dev boundary.** A fit statement is followed to 2022-10-06, through
  the dev period. A component fitted on the fit split for the dev runs therefore uses recoveries
  dated inside the dev period, and the H3 selection on dev is not a clean forecast evaluation.
  The test evaluation is clean: no train outcome is followed past the train horizon.
- **Final fits.** After the H3 selection, every model-free predictor is refitted on fit and dev
  together, before any test prediction.
- **Calendar overlap.** Train-period outcomes are followed only to the train horizon, the last
  capture before 2023-01-01, which is 2022-10-06. An event still open there is administratively
  censored (`end_of_train`), and no follow-up field reaches past it. Full follow-up would show
  how a thread stood in 2023 to 2026, which is the outcome of any test statement on the same
  thread, and a track-record table fitted on it would carry that into test predictions.
  - *One exception, which is first-sight information.* A train-period statement first archived
    in 2023 (dated late in 2022, first seen in the capture of 2023-01-13) has that capture as
    its only usable capture. It has no follow-up, is censored `end_of_train` there when at risk,
    and that capture date is the only test-period date in its row. The number of such
    statements is **TBD-at-gate**.
  - Statements dated after 2021-11-30 have at most two days of follow-up in the train period
    (the captures of 2022-10-04 and 2022-10-06), so the dev split scores almost only statements
    dated in 2021.
  - The same train outcomes with full follow-up are sealed with the test outcomes
    (`outcomes_train_uncensored.csv.gz`); after unsealing, a sensitivity analysis refits every
    train-fitted component on them.
- **E3 eligibility.** A test statement (2023-01-01 to 2025-12-31) is eligible when it is at
  risk under B at first sight, its frozen rule reading is dated (a recovery or next-delivery
  period), it is not stale at issue, and `t_end + 90` is on or before the last capture used
  (2026-09-26). Eligibility uses the statement date, first-sight fields and the stated period,
  never an outcome. The primary analysis uses the scoreable ones.
  - The eligible list is written by the dataset builder and hashed (section 17).
  - **TBD-at-gate**: the numbers of eligible statements and of their episodes; of scoreable
    statements; and of eligible statements with a horizon event left undetermined. The last two
    come from registered code that reads the sealed file and prints these counts only.
  - TBD, silent and stale-at-issue test statements at risk under B form three further item
    lists, each hashed, for E3's secondary analyses. Their sizes are **TBD-at-gate**.
- **Post-cutoff slices.** For each model, the slice is the eligible statements dated after the
  last day of its training-cutoff month.
  - The cutoff is the one documented by the model's maker. A model with no documented cutoff
    uses its release month, and the plan then calls the cutoff *bounded*, not documented
    (section 4).
  - Slices are taken inside the test split. The Late split is not read for outcomes in October,
    so a model whose cutoff month is December 2025 or later has no slice. [owner to confirm]
  - A slice is analysed only if it holds at least 50 scoreable statements. The size of every
    slice is **TBD-at-gate** (cutoffs from section 4; counts from the counts-only code).
- **Samples and their order.** Every sample is drawn by the seeded rule, in this order, so that
  no later sample can change an earlier one:
  1. the pilot, the check set, the reserve check set and the literal-task sample (section 10),
     in that order, from the events table and the form classifier only, with no outcome field;
  2. the train-half outcome-audit sample;
  3. the in-context examples, the dev prompt items and the minimal-pair seeds, in that order,
     which exclude everything drawn in steps 1 and 2 and one another;
  4. from the eligible list: the probe sample, the 20-sample subset, the paraphrase subset, the
     2×2 subset (section 5) and the 100 statements of the reference-reading check;
  5. the test-half outcome-audit sample, drawn under the sealed folder after every
     confirmatory run has finished (section 10).

  The statements used as examples in the guide and the fixed test item of the harness are
  excluded from every sample. The hash of every sample list drawn before registration (steps
  1 and 2 at least) is in section 17; a list of steps 3 and 4 drawn after it is hashed in F1,
  before any call that uses it.

## 4. Models

Eight readers. Temperature 0 where the provider supports it. Provider defaults for reasoning,
recorded in F1. Reasoning and thinking tokens are billed as output.

| Model | Role | Route and id | Released | Training cutoff | Pinned endpoint, precision | $/1M in | $/1M out |
|---|---|---|---|---|---|---|---|
| llama-3.3-70b | **primary** | OpenRouter `meta-llama/llama-3.3-70b-instruct` | **TBD-at-registration** | **TBD-at-registration** | **TBD-at-registration** | 0.10 | 0.32 |
| deepseek-v3 | **primary** | OpenRouter `deepseek/deepseek-chat` | **TBD-at-registration** | **TBD-at-registration** | **TBD-at-registration** | 0.257 | 1.029 |
| qwen-2.5-7b | secondary | OpenRouter `qwen/qwen-2.5-7b-instruct` | **TBD-at-registration** | **TBD-at-registration** | **TBD-at-registration** | 0.10 | 0.20 |
| gemma-3-27b | secondary | OpenRouter `google/gemma-3-27b-it` | **TBD-at-registration** | **TBD-at-registration** | **TBD-at-registration** | 0.08 | 0.45 |
| gpt-oss-20b | secondary | OpenRouter `openai/gpt-oss-20b` | **TBD-at-registration** | **TBD-at-registration** | **TBD-at-registration** | 0.018 | 0.09 |
| gpt-4o-mini | secondary | OpenRouter `openai/gpt-4o-mini` | **TBD-at-registration** | **TBD-at-registration** | **TBD-at-registration** | 0.15 | 0.60 |
| gemini-3.8-flash | secondary | Google `gemini-3.8-flash` | **TBD-at-registration** | **TBD-at-registration** | direct | 0.75 | 3.75 |
| grok-4.20 | secondary | xAI `grok-4.20-0309-non-reasoning` | **TBD-at-registration** | **TBD-at-registration** | direct | 1.25 | 2.50 |

- **How the table is filled.** Release dates, cutoffs, routes and endpoints are collected at
  source, each with its URL and retrieval date, and kept in `MODELS.md` in this folder, whose
  hash is in section 17. No model is called for this, and no key is used. The pages were read
  on 1 October (standing rules, "Web requests"). The owner reviews the entries of the two
  primaries before they enter the table.
- **Cutoff rule.** A cell reads "documented: month (source)" when the model's maker states a
  cutoff, and "bounded: release month" otherwise (section 3).
- **Prices.** The prices shown are the list prices per 1M tokens in the repository's ladder
  file, as in the 29 September draft: retrieved 2026-09-28 for the six OpenRouter models,
  2026-09-06 for gemini-3.8-flash and 2026-09-07 for grok-4.20. On OpenRouter a price belongs to
  one provider endpoint, so once an endpoint is pinned its price is the registered one. The
  prices of the pinned endpoints replace these at registration (**TBD-at-registration**). The
  harness carries its own table of the eight readers (route, endpoint, precision and price) and
  refuses a live run for any other model, or while a route is not yet set.
- **Provider pin.** The harness of the 29 September draft sent no provider preference:
  OpenRouter chose the provider and could fall back to another, and only the echoed model id
  was checked, which is the same for every provider of a model. Now each OpenRouter request
  names one provider endpoint with fallbacks off. The echoed model id and the provider that
  served the call are stored with every call, and a response from another model or another
  provider stops the run. The endpoint chosen for each model, with its precision, is
  **TBD-at-registration**. No test-period call is made before F1.
- **Why these primaries.** Both are open-weight models with early cutoffs, documented or
  bounded by the release month, which the memorisation controls need. Each is to be served by
  one named endpoint at a stated precision. The primaries alone enter the confirmatory family.
- **If deepseek-v3 cannot be tied to a dated checkpoint, or its maker documents no cutoff,** it
  stays a primary, its cutoff is bounded by its release month, and every statement about it says
  "bounded". [owner to confirm]
- **The secondaries.** They span size, openness and recency; they are reported descriptively
  along those axes.
- **Parse failures.**
  - Answers are parsed strictly: one JSON object that passes the schema and the semantic checks
    (real calendar dates, start not after end, quantiles that do not decrease, probabilities in
    [0, 1]). Nothing is sorted or clipped.
  - An answer that fails gets exactly one repair call: a separate, cached request that shows the
    model its answer and the errors. An empty response (a refusal) is not repaired and counts as
    a failure.
  - After a failure, a literal reading counts as ABSTAIN, and a predictive reading is replaced
    by the base-rate predictor's output for that event (flagged).
  - A predictive answer with `P(E_end90)` below `P(E_end)` is kept as given, and the number of
    such answers is reported per model and condition.
  - Parse and refusal rates are reported per model and condition. A sensitivity analysis uses
    only the events that both compared conditions parsed.

## 5. Experiments

E1 to E5 are the core of the October study. E6 is kept until its linker gate on 4 October, and
E7 follows it in the cut order (section 12). E8 and E9 are not run in October (owner decision,
1 October). Call counts and costs are in section 9.

### E1. Build OpEst-FDA and describe the issuers (must; no calls)

Build the statement events, clusters and outcomes of section 2.

**Descriptives, computed by the registered evaluator after every confirmatory run for the test
period, and at any time for the train period.**

- The hold rate of the stated period, `P(E_end)`, conditional on survival to first sight
  (section 2.5).
- The slip distribution: recovery minus `t_end`, a Turnbull estimate by form and by revision
  bucket (first, second, third or later statement of a thread).
- The distribution of bracket widths.
- Counts by year, form, statement type and company.

**Intervals.** Percentile bootstrap, 95%, clustered by episode.

**Standing.** None of this is in the confirmatory family. Optimistic or calibrated issuers are
both context for E3, and neither is a failure.

**Audit.** 100 outcomes are audited by hand (section 10).

### E2. Literal reading against human labels and the rule reader (must)

**Items.**

- 120 distinct statements, stratified by form, each labelled by both annotators. The owner
  was asked about this size on 1 October and did not object; it stands unless the owner says
  otherwise before registration. [owner to confirm]
- The frame is the statements on the shortage listing that are Current at first sight, from
  all periods, since a literal reading involves no outcome.
- They are drawn before every other sample except the pilot and the check sets (section 3).
- *Strata.* The form classes of section 2.6, grouped as in the guide's allocation table. A
  statement that carries a distractor date beside its target (any class but discontinuation)
  belongs to the distractor stratum, not to the stratum of its form. The *month-and-year
  stratum* is therefore the month-and-year statements with no distractor date.
- The allocation per stratum is **TBD-at-gate**: the quotas are fixed in the guide's
  allocation table before the draw, and a stratum with fewer statements than its quota gives
  all it has.

**Gold.** The adjudicated labels of the two annotators (section 10).

**Prompts.**

- `literal-v1`, which states the conventions of section 2.5.
- `literal-free-v1`, the convention-free variant, as a secondary.
- Both are pinned by SHA-256 (section 17).

**Output schema.**

- statement type;
- an interval anchored to the Date of Update, or ABSTAIN;
- certainty class;
- stale flag;
- the quoted words the reading rests on.

**Readers.** All eight models, and the rule reader (`rules.py`). HeidelTime and SUTime are not
run (section 8).

**Metrics.** See section 7.1. Results are reported by form, and weighted by event and by
template.

**Test (a secondary family with its own error control, separate from H1 to H3).**

- For each primary model, one exact McNemar test compares the model (`literal-v1`) with the
  rule reader, pooled over the items outside the month-and-year stratum. A month-and-year
  statement that carries a distractor date is in the distractor stratum, so it is in the test.
- A reading is correct when the statement type is right and either both readings abstain or the
  interval IoU is at least 0.5.
- Holm's correction runs over the two tests at 0.05.
- Per-form results are descriptive.

**Positive result.**

- Rules roughly equal the models on month-and-year text.
- The models lead by at least 0.15 IoU on part-of-month, no-year and range forms, and on items
  that carry a distractor date.
- False commitment on TBD or silent items exceeds 5% for at least one model.

**Negative result.** Rules match the models everywhere. The paper then says that literal reading
is solved for this register, and its weight moves to E3.

### E3. Pragmatic reading against outcomes: the headline (must)

**Items.** Every E3-eligible test statement (section 3). The primary analysis uses the scoreable
ones.

**Reader outputs.** For every event, each reader gives:

- `P(E_end)`;
- `P(E_end90)`;
- quantiles 0.1, 0.5, 0.8, 0.9 and 0.95 of the time to recovery in days, capped at 365.

For TBD and silent events, where no `t_end` exists (read by the primaries only; section 9),
the readers give:

- `P(recovered within 90 days)`;
- `P(recovered within 180 days)`;
- the same quantiles.

**LLM conditions, for all eight models, on every eligible statement.**

- **(a) Zero-shot.** The notice alone (`predictive-v1`).
- **(b) Track record in context** (`predictive-track-v1`). The notice, plus the list's
  track-record table, plus 10 resolved fit-split examples.
  - The table is the track record of the whole list, not of one company. It has one row for
    each form and revision bucket, with the calibrator's backoff (section 8): the number of
    statements the row rests on, the share recovered by the stated end, the share recovered by
    90 days after it, and the median days from update to recovery. The shares are Turnbull
    estimates, and the prompt says so. The entry's own form and revision bucket are named
    under the table.
  - For the dev runs of the H3 selection the table comes from the fit split alone; for test
    runs, from the whole train period (fit and dev).
  - The examples are drawn by the seeded rule, stratified by form, from fit statements outside
    the earlier samples (section 3). An example shown as "not recovered within 365 days" must
    have a lower bound at least 365 days after its date.
- **(c) Literal reading plus calibrator.** The model's literal reading (`literal-v1`, run on
  the E3 items) is passed through the fixed empirical slip calibrator (section 8).

**Primaries only.**

- 20 samples at temperature 1 of condition (a) on a 300-item subset. For each item, the sampled
  quantiles are the empirical quantiles (0.1, 0.5, 0.8, 0.9, 0.95) of the 20 sampled medians.
  They are compared with the verbalised quantiles of the temperature-0 answer by pinball loss
  and by coverage of the 80% interval.
- 3 prompt paraphrases of (b) on a 200-item subset, to measure prompt variance.
- The secondary item lists (TBD, silent and stale at issue; section 3) under conditions (a),
  (b) and (c).

Subsets are drawn from the eligible list by the seeded rule, stratified by statement year.

**Baselines.** Section 8.

**Metrics.** Section 7.2.

**Confirmatory family.** Section 6.

**Descriptive decomposition.** For each model, on the scoreable events, with the loss taken as
the primary Brier (section 7.2):

- the text's content value: loss(structured-only) − loss(rule reading + calibrator);
- the reading loss: loss(model reading + calibrator) − loss(rule reading + calibrator);
- the trust loss: loss(condition a) − loss(model reading + calibrator).

The rule reading is the reference reading (section 2.5), so "rule reading plus calibrator" is
both the reference of this decomposition and the "rules plus slip" baseline of section 8.

**Secondaries (no multiplicity claim).**

- Every metric for all eight models and all conditions.
- The H1 to H3 contrasts for the six secondary models.
- Post-cutoff slices.
- The recovery definition A (FDA resolved).
- The outcome over all covered presentations, and over any covered presentation.
- The horizon-event bounds.
- The delayed-entry sensitivity: statements first captured on or before `t_end`.
- Cluster resampling by company, and a fit that leaves out the dominant company (Hospira and
  Pfizer).
- The full-follow-up refit of every train-fitted component (after unsealing).
- Stale-at-issue events (primaries): stale-value uptake, which is the share of readings giving
  `P(E_end) > 0.5` for a period that has already passed.
- TBD and silent events (primaries) against the base-rate predictor.
- Sampled against verbalised quantiles.
- Prompt variance.

### E4. Leakage and memory controls (must)

**No-notice probe (seven models: all but gemini-3.8-flash; `probe-v1`).** 300 eligible
test statements are drawn by the seeded rule, stratified by statement year. Each model is shown
the generic, company, presentation, statement date, Therapeutic Category and Initial Posting
Date, but no statement text. It gives the two probabilities and the time-to-recovery quantiles.

- Probe items carry no stated period: their horizons are 90 and 180 days after the statement
  date, so nothing from the notice text reaches the probe.
- *Test.* Pinball loss at 0.5, against the base-rate predictor by listing age. The comparison
  uses a one-sided paired cluster bootstrap at 0.05, not adjusted.
- *Rule.* A model that beats the base rate is excluded from outcome claims on events dated before
  its cutoff.
- *For a primary model,* its three confirmatory tests are then evaluated on its post-cutoff slice
  instead of on the full test set. This switch is decided by the probe alone, before any H test
  is computed, and the family keeps six tests.
- *A switched primary with a small slice.* If that slice holds fewer than 50 scoreable
  statements, the model's three tests are reported as not evaluable. They stay in the family of
  six and count as not rejected. [owner to confirm]
- *gemini-3.8-flash is not probed* (section 9). Its E3 results are reported as descriptive, with
  the statement that its memory of the test period was not tested.

**Name and date 2×2 (primaries, condition b, 300-item subset).**

- The factors are real against fictitious name, crossed with the true dates against all dates
  shifted forward by 4 years.
- Masking replaces generic, brand and company names and NDC digits with fictitious ones, and
  rescales strengths.
- Reported as descriptive: the change in primary loss, and the mean absolute change in
  `P(E_end)` and in the median, across cells.

**Post-cutoff slice for each model.** As in section 3.

**Negative result.** Heavy memorisation, which shrinks the headline to the post-cutoff slices.
That is reportable.

### E5. Minimal pairs from attested forms (must, reduced)

**Items.**

- About 800 items from about 100 real seeds. The seeds are stratified by form and drawn after
  the samples of section 10 and the in-context examples, excluding them.
- Names are fictitious, and gold labels follow by construction.

**Factors, varied one at a time from the seed.**

- Certainty marker, attested only: estimated, expected, anticipated, TBD, "no estimated release
  date", "as it is released".
- Surface form.
- Granularity: early, mid or late, month ranges, "timeframe", quarters.
- Stale against fresh.
- Distractor date: depletion, "available until", expiry.
- Silent (no date given).

**Readers.** Seven models (all but gemini-3.8-flash), with `literal-v1`.

**Target.** The literal output should not change when the meaning does not, and should change
correctly when it does. A reading of an edited item is an *error* when it is not correct by the
E2 rule, or, for the certainty-marker factor, when its certainty class is wrong, or, for the
stale factor, when its stale flag is wrong.

**Test.**

- A logistic GEE of error on factor and model with their interaction, clustered by seed
  (independence working correlation, robust variance). If the robust variance cannot be
  computed, the same model is fitted by maximum likelihood with a cluster bootstrap over seeds
  (10,000 draws, seed 20261001).
- For each primary and each of the six factors, one test of "no effect of the factor on the
  error rate": the contrast between the items edited on that factor and the unedited seed
  items, which are among the items every reader gets. Holm's correction runs over the 12 tests
  at 0.05, as a secondary family of its own.
- 100 items are audited by hand (section 10).

The two authors' predictive readings of 100 pairs, in the draft, are cut for October.

**Positive result.** Named factors (stale, distractor, TBD) cause errors in named models.

**Negative result.** Invariance holds, and the pairs become a robustness check.

### E6. Estimative terms at the FAA Command Center (should; gated on 4 October)

E6 stays in the October study until its linker gate (owner decision, 1 October). It is first in
the cut order (section 12), and it is cut if the gate is not passed on 4 October.

**State on 1 October.** The collector (`faa_fetch.py`), the parser and statement builder
(`faa.py`) and the linker with its hand-check sheets (`faa_links.py`) were written on 1 October,
and the collection of the 2026 advisories started that day. No prompt for E6 exists yet.

**Data.** The estimative fields of the advisories of April to September 2026, each statement
taken at its first issuance, with lead time as a covariate:

- the probability of extension of a ground stop;
- the probability of extension of a reroute or a flow-constrained area;
- planned ground stops and delay programmes in the operations plan ("POSSIBLE", "PROBABLE",
  "EXPECTED"), one statement per airport, initiative and window.

**Development and test months.** April and May 2026 are the development months and June to
September the test months, both provisional until the amendment. The code refuses to parse or
link any month after the development months until the amendment is registered. Counting the
saved files per day is allowed for every month and reads no advisory.

**Registration.** E6 is registered by its own amendment at its gate, before any test month is
parsed or linked. The amendment fixes:

- the outcome codebook;
- the development and the test months;
- the term list;
- the prompts and the item sets;
- who gives the author reading of each term that the perception gap needs, and when.

**Linker gate.** On the development months: at least 150 links checked by hand, the required
number for every term (30, or all of a term's links when it has fewer), and at least 90% of the
checked links correct. A1 and A2 check the links on sheets drawn by the seeded rule; a link
checked by both is correct only when both say so, and "unclear" is not correct. The 90%
threshold is a draft value. [owner to confirm]

**Readers.** Seven models (all but gemini-3.8-flash; section 9) give a probability for each
term, in isolation and in context, under two framings: what the writer conveys, and whether it
will happen.

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

**Standing.** Secondary and descriptive; nothing in E6 enters the confirmatory family.

**Positive result.** For at least one term, the realised rate differs from both readings by at
least 15 points, and in-context readings add resolution beyond the lookup.

**Negative result.** The models already track the register.

### E7. Pricing reading errors, after Crystal et al. 2005 (could; cut only after E6; no calls)

E7 stays a "could" (owner decision, 1 October). It prices the literal reading errors of
condition (c): for each model, the reference reading is swapped in for the model's literal
reading one error class at a time, with the calibrator held fixed, and the change in primary
Brier and in pinball loss is reported.

- The draft took the reference from author labels on E3 test events. Those labels are not
  collected in October (section 10), so the reference is the frozen rule reading (section 2.5),
  on the scoreable E3 statements. E7 is also reported on the statements of the
  reference-reading check whose rule reading the annotators confirmed. [owner to confirm]
- The error classes are fixed in the evaluator at F1, before any test call.
- **Positive result.** Named error classes carry most of the cost.
- **Negative result.** Reading errors are cheap next to the trust loss, which supports the
  headline.

### E8. Real revision threads (cut for October)

Not run in October (owner decision, 1 October). The design is kept for the January version:
chains with at least 3 revisions, the full thread against the latest statement alone.

### E9. Crowd norms for estimative terms (not run in October)

The owner chose an author audit with no crowd study (29 September). E9 moves to January, and
runs only with an ethics approval in hand.

## 6. Confirmatory family

**Tests.** Six tests: H1, H2 and H3, each for llama-3.3-70b and for deepseek-v3.

**Holm.** Holm's step-down at a familywise 0.05 runs over all six. A hypothesis holds for a model
when its Holm-adjusted p is below 0.05. A test reported as not evaluable stays in the family
with p = 1.

**Items.** The scoreable E3 events, or a primary's post-cutoff slice under the E4 rule.

**Endpoint.** The primary Brier (section 7.2) on the primary outcome, the displayed
presentation's bracket under B (section 2.5). Every contrast `Δ` is the comparator's mean loss
minus the tested predictor's mean loss, so that a positive `Δ` favours the tested predictor.

**H1: track-record uptake** (one-sided). `Δ = loss(m-a) − loss(m-b) > 0`. Condition (b) beats
condition (a).

**H2: reading in isolation** (two-sided). `Δ = loss(rules + calibrator) − loss(m-c) ≠ 0`. Both
sides share the same frozen calibrator, so only the literal reading differs.

- *Equivalence.* It is declared when the 90% interval lies inside ±0.02 Brier. This is part of
  the H2 reading, but not a separate test in the family.
- *Caveat.* The stated period that defines the horizon events is the rule reading itself
  (section 2.5), which favours the rules: a model reading that is right where the rule is wrong
  is scored against the rule's horizon. The accuracy of the rule reading on the 100-statement
  check (section 10) is reported beside H2, and H2 is also reported on the month-and-year form
  alone, where the rule reading is least in doubt.

**H3: value of the text** (two-sided). `Δ = loss(structured-only GBM) − loss(m-best) ≠ 0`.

- `m-best` is the one of `m`'s three conditions (a, b, c) with the lowest primary loss on the
  scoreable dev statements.
- The selection is recorded in F1, before any test call, with the dev loss of all three
  conditions, their bounds (section 7.2) and the dev outcome mix. The dev split is dominated by
  "no" answers (section 3), which favours the condition that gives the lowest probabilities.
- The text-trained GBM, and rules plus slip, are each compared with the structured-only GBM in
  the same way, as registered secondaries.

**Resampling.** A paired cluster bootstrap by shortage episode: 10,000 draws, seed 20261001. Each
draw resamples episodes with replacement and computes both predictors' mean losses on the same
draw.

**p-values.** They come from the bootstrap distribution of `Δ`.

- One-sided (H1): `(1 + #{Δ* <= 0}) / (B + 1)`.
- Two-sided (H2, H3): `min(1, 2 × min((1 + #{Δ* <= 0}) / (B + 1), (1 + #{Δ* >= 0}) / (B + 1)))`.

**Intervals.** Estimates carry 95% percentile intervals; H2 also carries its 90% interval. The
bounds of section 7.2 are reported beside every confirmatory estimate.

**Sensitivity.** A cluster sign-flip test on the episode sums of the paired differences.

**Power.**

- The minimum detectable `Δ` for each hypothesis is **TBD-at-gate**, at 80% power under the Holm
  worst case of 0.05/6.
- Each hypothesis has a language model on one side, and no paid call precedes registration. The
  estimate therefore uses one pair of model-free predictors per hypothesis as a proxy: the
  paired loss variance of the pair on the scoreable dev statements, with its inflation from
  clustering, scaled to the registered numbers of scoreable test statements and episodes.
- The three pairs are fixed in the power code before it reads a dev outcome, and are listed here
  at registration (**TBD-at-gate**). The draft pairs: face value against rules plus slip (H1);
  rules plus slip against the base-rate predictor (H2); the structured-only GBM against the
  text-trained GBM (H3).
- The values are indicative, and the dev outcome mix is stated beside them. Low power does not
  stop the study. It is written into the paper.

**Confirmatory runs.** These must all finish before any evaluation:

- E3 conditions (a), (b) and (c) for both primaries on every eligible event;
- the E4 probe for both primaries;
- the test predictions of every model-free predictor of section 8 on the same events, after the
  refit on fit and dev.

If a primary's confirmatory runs cannot be completed on its registered route, its three tests
are reported as not evaluable and stay in the family. No other model takes its place without an
amendment made before any evaluation. [owner to confirm]

**Evaluator.** The registered evaluator (**TBD-at-F1**: file and hash) accepts a run stored in
several parts and refuses:

- a run that is partial;
- a run whose stored model id or serving provider differs from the registered route (the
  harness stores both with every call and stops at a mismatch);
- a run whose item set differs from its registered item list (the eligible list, or one of the
  secondary lists of section 3).

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
- **Distractor uptake:** among the gold items that carry a distractor date, the share where the
  reader returns an interval with IoU of at least 0.5 with a distractor's interval and below
  0.5 with the gold interval (or the gold abstains). A distractor's interval is its quoted
  words read by the conventions of section 2.5. The answer schema has no distractor field.
- **Certainty-class** accuracy and Cohen's kappa against gold, over the four classes.

Each is reported per form, weighted by event and by template.

### 7.2 Against outcomes (E3, E4, and E7 if it runs)

- **Primary Brier.** For event `i`, the primary loss is `(BS_i(E_end) + BS_i(E_end90)) / 2`, where
  `BS = (p − y)^2`.
  - The primary analysis uses scoreable events (complete case).
  - *Bounds:* every undetermined horizon event is set to 0, and then to 1. Both results are
    reported.
- **Brier decomposition** into reliability, resolution and uncertainty (Murphy), with 10
  equal-count bins, for each horizon event.
- **Calibration in the large:** the mean of `P(E_end)` minus the observed frequency of `E_end`
  on the scoreable events, and the same for `E_end90`, with 95% intervals by episode bootstrap.
- **Decision loss.** The pinball loss at τ 0.5, 0.8 and 0.95 on the time to recovery.
  - Pinball at the critical fractile τ = c_u / (c_u + c_o) is the expected cost of buffering
    stock until recovery. The three τ are generic cost ratios of 1:1, 4:1 and 19:1.
  - An interval-censored target is scored with the midpoint of its bracket. The loss bounds (the
    minimum and maximum over the bracket) are reported too.
  - A right-censored target beyond the cap is scored at the cap.
- **Coverage** of the 80% interval `[q0.1, q0.9]`, counted on events whose bracket lies wholly
  inside or wholly outside the interval.
- **Probe and 2×2 metrics** (E4): as defined in E4.
- **Selective prediction:** loss against abstention rate, for condition (c) and the rule reader
  only. The predictive answer schema has no abstain option.

## 8. Baselines and conditions

**Freezing.** The code of every model-free component is hashed at registration. Every component
is fitted on the fit split and selected on dev, then refitted on fit and dev together; the
fitted artefacts are hashed in F1, before any test call.

**Rule reader.** The regex reader `rules.py`, frozen (standing rules), with the conventions of
section 2.5. It is the rule baseline of E2 and H2 and the source of the stated period. Its
coverage per form is reported. HeidelTime and SUTime are disclosed as not run (owner decision,
1 October): neither was installed.

**Empirical slip calibrator.** Turnbull estimates of slip (recovery minus the stated end), from
fit statements for the dev runs and from fit and dev statements for the test runs.

- *Cells.* A statement's cell is its form class, after the merge of section 2.6, and its
  revision bucket (first, second, third or later statement of its thread; revision index 0, 1,
  2 or more). The cell is that of the statement and is the same for every reader.
- *Backoff.* The estimate of form by revision bucket is used when that cell holds at least 100
  dated statements in the fitting set; otherwise the estimate of the form; otherwise the
  estimate over all dated forms. Which cells meet the minimum is **TBD-at-gate**.
- Given a literal reading with period end `ŝ`: `P(E_end) = F_slip(t_end − ŝ)` and
  `P(E_end90) = F_slip(t_end + 90 − ŝ)`. The quantiles are `ŝ − s` plus the slip quantiles,
  kept within 0 to 365 days.
- When the reading is ABSTAIN, the calibrator falls back to the no-date time-to-recovery
  distribution by listing age.

**Structured-only quantile GBM (the content-free control).**

- Features: reason for shortage, therapeutic category, time since initial posting, company and
  calendar month. No free text. Status is not a feature: it is constant on at-risk statements.
- It gives quantiles at 0.05 to 0.95. The resulting CDF is read at each horizon.
- Censoring in fitting: an interval-censored fit event is given the midpoint of its bracket. A
  right-censored fit event is represented by the conditional tail of the pooled Turnbull
  estimate beyond its censoring time. The exact wording of this rule is **TBD-at-gate**: it is
  matched to the predictor code hashed in section 17.

**Text-trained quantile GBM.** TF-IDF on the availability and related text, plus the structured
features. This baseline is what makes H3 an NLP question.

**Other predictors.**

- **The stated date at face value** (the issuer as forecaster): `P(E_end) = P(E_end90) = 1`, with
  every quantile at `t_end − s`.
- **Base-rate remaining duration** by listing age.
- **Rules plus slip:** the rule reading through the calibrator. Under section 2.5 this is also
  the reference reading plus slip.
- **The LLM literal reading plus slip**, which is condition (c).

**LLM conditions.**

- (a), (b) and (c).
- The masked-name and date-shifted cells (E4).
- The convention-free literal prompt (E2).
- 3 paraphrases (E3).
- 20 samples against verbalised quantiles (E3).

**Human references.**

- The double-labelled literal items give the literal ceiling, scored leave-one-out.
- No crowd in October.

**FAA (E6, if it runs).** The lookup, the airport × hour × programme model, the masked hedge
and perfect information (section 5, E6).

## 9. Budget

The study-wide hard cap is **$200**. It covers every run, including dev runs and cost trials.
The rules, which the harness (`read.py`, frozen at F1) enforces:

- *One ledger.* Every paid run uses one output root, and declares its cap in the study ledger
  there before its first call.
- *Caps.* A cap belongs to a run: one model, one template and one condition under one run name
  (a run may be one part of an item list). A run is refused when the caps and recorded spend of
  its model's runs would pass the model's cap in the table below, or those of all runs would
  pass $200. Caps of runs in flight count, not only recorded spend.
- *Before every paid call,* the call is refused if its projected cost would take the run past
  its cap.
- *Registration first.* A paid call is refused unless the registration tag is an ancestor of the
  checkout; a call on a test-period or late-period item also needs the F1 tag (section 17).
- *The run sheet* lists every run with its model, template, item list and cap; the caps of a
  model's runs sum to that model's cap. It is **TBD-at-gate**.

Every call is logged with its tokens and its price.

**Price of a call.** Input tokens × the input price per 1M, plus output tokens (including
reasoning or thinking) × the output price per 1M, at the registered prices of section 4.

**Scope.**

- `gemini-3.8-flash` reads E2 and the E3 conditions on the eligible statements, and nothing
  else beyond its cost trial: no probe, no E5 and no E6.
- The TBD, silent and stale-at-issue secondaries are read by the two primaries only.
- The Late split is not read for outcomes. [owner to confirm]
- E6, if it passes its gate, is read by the seven other models. Its calls go through the same
  harness, ledger and caps; its prompts and item sets are fixed by its amendment.

**Calls per model.** `N_E` is the number of eligible statements, `N_S` the number of statements
in the three secondary lists together, and `N_D` the number of scoreable dev statements; all
three are **TBD-at-gate**.

| Item set | Calls | Read by |
|---|---|---|
| E2: 120 items, two templates | 240 | all eight |
| E3: conditions a, b, c on the eligible statements | 3 × `N_E` | all eight |
| E4 probe | 300 | seven (not gemini-3.8-flash) |
| E5: about 800 items | 800 | seven (not gemini-3.8-flash) |
| Cost trial: 20 dev items per template used | 100 (gemini-3.8-flash: 80) | all eight |
| E6, if it passes its gate | about 1,200 | seven (not gemini-3.8-flash) |
| E3 secondaries: conditions a, b, c on the secondary lists | 3 × `N_S` | primaries |
| Dev runs for the H3 selection | 3 × `N_D` | primaries |
| E4 2×2: three further cells on 300 items | 900 | primaries |
| E3 paraphrases: 3 on 200 items | 600 | primaries |
| E3 samples: 20 on 300 items | 6,000 | primaries |

Repair calls (at most one per failed answer) are not in these counts and count against the caps.

The table below gives the calls without E6; E6 adds about 1,200 to every model but
gemini-3.8-flash.

| Model | Calls | Cost per call | Estimate | Cap |
|---|---|---|---|---|
| gemini-3.8-flash | 320 + 3 `N_E` | ~$0.011 (thinking billed) | **TBD-at-gate** | $110 |
| grok-4.20 | 1,440 + 3 `N_E` | ~$0.0025 | **TBD-at-gate** | $30 |
| deepseek-v3 | 8,940 + 3 (`N_E` + `N_S` + `N_D`) | ~$0.0004 | **TBD-at-gate** | $12 |
| llama-3.3-70b | 8,940 + 3 (`N_E` + `N_S` + `N_D`) | ~$0.00015 | **TBD-at-gate** | $5 |
| qwen-2.5-7b, gemma-3-27b, gpt-oss-20b, gpt-4o-mini | 1,440 + 3 `N_E` each | ~$0.0001 to $0.00025 | **TBD-at-gate** | $3 each |
| **All** | | | **TBD-at-gate** | caps $169; reserve $31 |

The costs per call are those of the 29 September draft: from logged calls of the same models
where they exist, otherwise token counts times list prices. They are replaced by the cost trial.

**Check of the caps at the counts printed so far** (**TBD-at-gate**: this paragraph is replaced
by the table's estimates). With the provisional counts of section 16 and of "Changes", item 3
(`N_E` 2,585, `N_S` about 1,030, `N_D` 661), the formulas give about 8,100 calls and $89 for
gemini-3.8-flash, 9,200 calls and $23 for grok-4.20, 22,000 calls each for the primaries ($9
and $3), and 9,200 calls each for the four small models (under $3 each): about 98,000 calls and
$130 in all. E6 would add about 8,400 calls and $5, of which $3 for grok-4.20, which then
stands at about $26 of its $30. Every model is under its cap at these counts, with or without
E6.

**Cost trial.** After registration and before F1, each model runs 20 dev items per template it
uses. The trial's cost is scaled to the registered call counts and recorded in F1.

**If a projection exceeds a cap or the total**, the following apply in order until the
projection fits:

1. E6 is dropped for grok-4.20;
2. a cap is raised within the reserve, recorded in F1;
3. gemini-3.8-flash is dropped;
4. the cut order of section 12.

**Resuming a run.** A run stopped by its cap or by a provider error is resumed from its cache,
under the same name. Its cap may be raised within the reserve, and each resumption is logged as
an amendment. A run that cannot finish is reported as incomplete.

## 10. Annotation: author audit

**The annotators are two of the authors**, called A1 and A2, and a third author adjudicates.
This is declared in the ARR Responsible NLP checklist; there is no crowd study and no ethics
review (owner decision, 29 September). The procedure, label definitions and sheets are in
`AUDIT_GUIDE.md`, frozen by hash at registration. The two documents must agree at registration:
a difference found before then is settled in both before either is hashed.

**People** (owner decision, 1 October).

- A1 and A2 do all the labelling and both halves of the outcome audit. They do not write, tune
  or run the prompts. They read no output of a language model or of the rule reader on an item
  they label until the gold of that task is hashed.
- The owner is the adjudicator and does not label. The adjudicator settles disagreements,
  chairs the pilot meeting and does the availability-string check.
- The adjudicator may develop prompts and read model outputs. On the items of a task still to
  be adjudicated, the adjudicator looks only at aggregates (calls made and remaining,
  parse-failure and repair counts for the whole run, spend) until that task's gold is hashed.
  This limit is the guide's addition. [owner to confirm]
- If the adjudicator cannot do a task in time, A1 and A2 settle each item together by naming
  the deciding convention. An item they cannot settle that way is left out of the gold, and
  the number of such items is reported.
- Who A1 and A2 are is recorded by the owner outside the repository.

**Blinding.** While they label a statement, A1 and A2 know neither its outcome, nor any later
version of the notice, nor any reader's output on it. In the literal task they see only the
display row as defined in section 2.3; in the reference-reading check, that row and the rule
reading. In the outcome audit they see the capture rows of the audited thread, which for the
train half stop at the train horizon; the train-half sample leaves out every thread that
carries a statement they label.

**Tasks.**

1. **Availability-string check** (the adjudicator, before the freeze run): section 2.2.
2. **Pilot and check set** (before registration; Friday 2 October).
   - 20 train-period items are labelled by A1 and A2 independently under the guide's draft of
     1 October. A meeting of A1, A2 and the adjudicator settles every disagreement, and the
     guide is revised to v1.
   - A check set of 20 fresh train-period items from the dated forms is then labelled
     independently under v1.
   - *Gate.* Krippendorff's alpha (interval metric) on the month offset of the start, and on the
     month offset of the end, over the check set: both at least 0.6. The share of items with
     identical intervals is reported beside it and is not part of the gate. If fewer than 10
     check items have an interval from both annotators, or the offsets vary too little for
     alpha to be defined, the pilot items are pooled with the check items.
   - One further revision is allowed, with the 20 reserve items that are drawn with the check
     set. A second failure is a hold trigger (section 12).
   - The pilot may change the guide and the prompt text. It does not change `rules.py`; a
     difference that remains is disclosed.
   - Pilot, check and reserve items stay out of the gold and out of every other sample.
3. **Literal task (E2 gold; 3 to 5 October).** A1 and A2 each label the 120 E2 statements,
   independently.
   - Agreement is reported before adjudication, overall and by form: Krippendorff's alpha on
     the start and end month offsets (day offsets as a secondary), and Cohen's kappa on
     abstention, certainty class and statement type. Intervals resample items: 2,000 draws, seed
     20261001.
   - Disagreements are adjudicated. The gold file is hashed before any model output on those
     items is opened.
4. **Reference-reading check (E3).** 100 eligible test statements are drawn at random from the
   eligible list by the seeded rule. A1 and A2 check the rule reading's statement type and
   stated period against the text, blind to outcomes (45 statements each, and 10 checked by
   both).
   - Reported: the share correct with a Wilson 95% interval, and the disagreements by form.
   - The check does not change the reference: the stated period stays the rule reading for
     every statement. Author labels of the forms other than month and year, in the draft, are
     not collected in October.
   - The check starts after both literal sheets are submitted, because its sheet shows rule
     readings. Its sheets are returned and hashed before A1 or A2 see any E3 output and before
     the registered evaluator runs.
5. **Outcome audit.** 100 derived outcomes: brackets at presentation level, with the
   statement-level bracket shown beside them, each under definitions B and A. In each half, 20
   items go to each annotator and 10 to both.
   - 50 are from the train period, audited before registration to check the rule. Their sheets
     and capture traces stop at the train horizon. They are drawn after the pilot, check and
     literal samples and exclude them as the guide specifies; the audit is reported for the pool
     it was drawn from, with the size of that pool.
   - 50 are from the test period, audited only after every confirmatory run has finished and
     before the evaluator runs. Their sheets exist only under the sealed folder.
   - Each auditor also gets planted errors. Their key is scored by code after both sheets are
     in; no auditor opens it.
   - Pass, for each half: at most 2 confirmed errors among its 50 items, that is, at least 95%
     of the audited brackets agree with the auditor's reading of the captures, for B and
     separately for A.
   - A failure fixes the rule, never single items. For the train half that happens before the
     freeze run: the outcomes are derived again, and the affected items and 20 fresh ones are
     audited again. For the test half the outcomes are derived and sealed again, and the new
     hash is logged as an amendment before the evaluator runs.
6. **Minimal-pair audit.** 100 E5 items. At least 95% of labels must match the text. Otherwise
   the generator is fixed and a fresh 100 are audited, with the fix logged.
7. **E6 link checks**, if E6 is still in the study on 4 October: the hand check of at least
   150 links that is the linker gate (section 5, E6), by A1 and A2. Its sheets and its
   procedure come with the linker code and E6's amendment, not with the guide.

The draft's E5 predictive readings are cut.

**Estimated load.** **TBD-at-gate**: minutes per person, from the guide's hours table at the
rates the pilot and the train-half audit measure; the same figure here and in the guide. The
draft's figure (10 to 12 hours per author, plus reference labels) is withdrawn. The E6 link
checks are not in the guide's table and are added to the figure if E6 runs. The owner
confirmed on 1 October that A1 and A2 do the pilot and the train-half audit on Friday 2 October
and the main labelling on 3 to 5 October; the figure must fit the hours they can give.
[owner to confirm]

## 11. Leakage controls

- **Temporal split.** By statement date. Test outcomes are sealed, with their hash recorded at
  registration.
- **Fitting.** Every fitted component and the track-record table come from the train period
  only (the fit split for dev runs; fit and dev for test runs), and the in-context examples
  from the fit split. Train outcomes stop at the train horizon (section 3). No test item
  appears in any prompt's context.
- **Prompt development.** The text changes of 1 October are made before registration, with no
  model call: the two fields added to the entry block and the probe, and the wording of the
  track-record table. Two sentences of the literal prompts are settled at the pilot meeting
  and entered before registration: how "until X" and "through X" are read (`literal-v1`), and
  the certainty class of a statement that gives no date and has no unknown marker (both
  literal templates). After registration, development uses dev items only, with at most 3
  variants per prompt, all disclosed. Prompts are selected by parse rate and format compliance,
  and never by an outcome loss. The one outcome-based choice is the H3 selection on dev,
  recorded in F1. From F1 on, a changed prompt takes a new template id.
- **Test items wait for F1.** No test-period or late-period item is sent to a model before F1
  is pushed. The harness refuses such items unless the F1 tag is in place and a flag is passed
  (section 9).
- **E4.** The no-notice probe and its exclusion rule, the name and date 2×2, and the post-cutoff
  slices.
- **Masking.** Generic, brand and company names, NDC digits and strengths are replaced in the
  2×2. Minimal pairs use only fictitious names.
- **Checkpoints.** Each OpenRouter call names one provider endpoint with fallbacks off. The
  echoed model id and the serving provider are stored with every call, and a response from
  another model or provider stops the run (section 4).
- **Blinding and looks.** Annotators are blind (section 10). There are no interim looks, and the
  evaluator refuses partial runs.

## 12. Gates, schedule and cut order

**Where the 29 September schedule stands.**

| Planned day | Planned work | State on 1 October |
|---|---|---|
| Tue 29 Sep | Collectors, guideline v0, the draft | Done. Also done that day, ahead of plan: parsing, events, clusters, outcomes derived and sealed, the Gate 1 printout, the rule reader and the reading harness. The openFDA snapshot was taken on 28 and 29 September only; the FAA collection had not started. |
| Wed 30 Sep | Parse and build; install the rule normalisers | The build was done on the 29th. HeidelTime and SUTime were not installed. No build work was done on the 30th; the day went to a review of the plan, the guide and the code. |
| Thu 1 Oct | Gate 1, form inventory, E2 sample, minimal-pair seeds, 30-item pilot, minimal-pair generator | Gate 1 was printed on the 29th (see below). The rest slipped: on the morning of 1 October there was no form classifier, dataset builder, capture manifest, sampler, audit sheet, agreement code, calibrator, GBM, power check, minimal-pair generator or evaluator. |

The study is about two working days behind the draft's schedule. The schedule below is the
honest one from 1 October. It has no slack before registration and none before the freeze of
numbers.

| Day | Work |
|---|---|
| **Thu 1 Oct** | Decisions on scope and rules. Capture manifest. Availability-rule fix. Harness changes (fields shown, provider pin, study ledger). Form classifier, dataset builder, model-free predictors, samplers and audit sheets started. Model cutoffs and routes collected at source. FAA collector, parser and linker written; FAA collection started. Plan and guide revised. OpenReview profiles started for every author. |
| Fri 2 Oct | Availability-string check. Pilot, meeting, guide v1, check set, alpha gate. Train-half outcome audit. Freeze run of the corpus builder (the one sealed write). Counts-only code. Every gate value filled in. Power check. Independent check of every filled number against the code. |
| **Sat 3 Oct** | **Registration pushed and tagged, by 23:59 AoE.** Then: dev prompt development (format only), 20-item cost trials, dev runs. Literal task starts. |
| Sun 4 Oct | H3 selection. Refit on fit and dev. **F1 pushed** (one day later than the draft had it). Confirmatory runs: E3 conditions a, b, c and the probe, both primaries. Then E2, E5, the 2×2 and the secondaries, in cost order. **E6 linker gate**; if it passes, E6's amendment. |
| Mon 5 Oct | Runs finish. Literal task, reference-reading check and minimal-pair audit done; agreement computed; gold hashed. E6 runs, if it passed its gate. Test-half outcome audit, after the last confirmatory run. |
| **Tue 6 Oct** | Registered evaluator. **Gate 2: submit or hold. All numbers frozen by 23:59 AoE.** |
| Wed 7 Oct | Secondaries, figures, E7 if it is not cut, the full-follow-up refit. An independent check reproduces every table. |
| 8 to 9 Oct | Write the 8 pages. |
| Sat 10 Oct | Limitations, ethics, datasheet, Responsible NLP checklist (every item). Overlap check against the UV text. Literature check for work published since 12 July 2026. The no-ethics-review statement confirmed against institutional policy. |
| Sun 11 Oct | Independent check of every number and claim. Anonymised supplement, with the registered plan and guide (section 14). |
| Mon 12 Oct | ARR submission (23:59 AoE), with the service contributor named and every author's OpenReview profile complete. The UV camera-ready (due 15 October) wins any collision. |
| Wed 14 Oct | ARR reviewer registration. |

**The one relaxation** (owner decision, 1 October). It is used only if a human gate has to be
repeated before registration: the check-set gate after a second guide revision, or the
train-half outcome audit after a rule fix. The registration may then be pushed by Sunday 4
October, 23:59 AoE, and the freeze of numbers moves to Wednesday 7 October, 23:59 AoE; the
secondaries of 7 October merge into the writing days. A delay for any other reason does not
move the triggers. This is the only relaxation, it is written here before registration, and it
is not repeated.

**Gate 1.** Counts only; no outcome value is printed. The four thresholds, as registered in the
draft:

- at least 600 distinct statement events dated 2023 to 2025 with a stated date;
- at least 250 of them observable (bracket of 31 days or less);
- at least 100 shortage episodes among them;
- at least 150 observable events dated after llama-3.3-70b's documented cutoff.

*What the gate tested on 29 September.* The gate set was the shortage-listing events dated 2023
to 2025 that were Current at first sight and carried a date-like phrase, which includes expiry
and other distractor dates; it is wider than E3 eligibility. The first three thresholds were
met on that set (section 16 gives the counts). The fourth was tested on a weaker count, events
with any later capture of their thread, against a cutoff of 2023-12-31 that had not been
confirmed at source. No scoreable count was printed.

*The registered gate record* is **TBD-at-gate**, in two parts.

- From the freeze run of the builder, run with the cutoff confirmed in section 4: the four
  counts on the builder's gate set, as distinct statements with the statement-level bracket
  under B. Since 1 October the builder prints the fourth as worded, on observable events dated
  after the cutoff, and keeps the weaker count beside it.
- From the counts-only code: the same four counts on the E3-eligible statements (section 3),
  which have a stated date by the frozen rule reading, with the primary outcome (the displayed
  presentation, definition B); and the scoreable count.

The gate passes only if the thresholds hold in both parts. [owner to confirm]

**Hold triggers.** Any one of these moves the paper to ARR January 2027, which loses COLING 2027
(October is the last cycle it takes):

- Gate 1 fails on the freeze run;
- the check-set alpha stays below 0.6 after the one allowed revision;
- the registration is not pushed by 3 October, 23:59 AoE (4 October under the one relaxation);
- numbers are not frozen by 6 October, 23:59 AoE (7 October under the one relaxation);
- the UV camera-ready needs more than 1.5 days before 12 October.

**Gate 2 (6 October).** Submit if:

- every confirmatory run is complete;
- the registered evaluator has run;
- the E2 agreement is computed;
- no hold trigger has fired.

Gate 2 never looks at the sign or significance of any result. A registered negative result is
submitted.

**Cut order.** The first two cuts of the draft's order were taken on 1 October: E8 and E9
(owner decision). What remains, in order, when time runs short:

1. E6. It is also cut if its linker gate is not passed on 4 October;
2. E7;
3. fewer models, 8 down to 6. The two dropped are the secondary models whose runs are least
   complete at the time of the cut; ties go gemma-3-27b first, then gpt-4o-mini;
4. E5 down to 400 items.

E1, E2, E3 (with conditions b and c) and E4 are never cut.

**Plan B (ARR January 2027, for ACL 2027 or another ARR venue, not COLING).** The same paper,
plus:

- the openFDA prospective slice;
- FDA text from 2014;
- a full year of FAA data, with crowd norms (E9);
- E8, and whichever of E6 and E7 was cut;
- a second jurisdiction;
- an outcome-supervised small reader.

## 13. What counts as a result

**Positive, in the order the paper would state it.**

- Models read the letter well but not the pragmatics. False commitment on TBD or silent text, or
  stale-value or distractor uptake, is measurably above the rules or above the human ceiling for
  named models (E2, E5).
- The zero-shot predictive readings are overconfident relative to outcomes (E3). The registered
  criterion, a secondary with no multiplicity claim: for condition (a), calibration in the
  large on `E_end` (section 7.2) is positive with a 95% interval that excludes zero. The same
  quantity for `E_end90` and the coverage of the 80% interval are reported beside it. The claim
  is conditional on survival to first sight (section 2.5).
- The models use the list's track record when it is given (H1 holds).
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

The issuers' own optimism or calibration (E1) is context, never a result for or against the
claim.

**Expected, not evidence.**

- From Chicoine and Griffin (2025): a face-value reader will be overconfident on `E_end`, and
  condition (b) should reduce the primary Brier.
- H2 is expected to be small, because month-and-year forms dominate.
- H3 is open.

**Not claimed.**

- A new method.
- Issuer optimism as a new finding.
- "First" (the paper writes "to our knowledge").
- That models "understand" anything.
- The term "commitment" (the label layer is "certainty class").

## 14. Outputs and release

**Where outputs go.**

- Derived tables: `analysis/coling/out/` (tracked).
- Reading runs: parsed readings, spend logs, invocation logs and run manifests in
  `analysis/coling/out/read/<run>/`, with the study ledger beside them (tracked); raw responses
  in `results/coling/read/<run>/` and the one call cache in `results/coling/read/cache/`
  (ignored by git).
- Annotation: blank sheets and the manifest of submitted sheets in
  `analysis/coling/out/annotation/`; the train-half outcome-audit sheets and traces in
  `analysis/coling/out/audit_outcomes/`; sheets in progress and the planted-error keys under
  `external_data/annotation/` (ignored by git).
- E6: derived tables and link-check sheets in `analysis/coling/out/faa/`.
- Downloads: `external_data/` (ignored by git).
- Sealed outcomes, and the test-half audit sheets, traces and key: `external_data/sealed/`,
  until evaluation.

**The release** is prepared as anonymised supplementary material. It contains:

- derived tables and texts, without Contact Info;
- capture URLs and the capture manifest;
- author labels;
- minimal pairs;
- every model's raw outputs, exported from the run folders;
- a datasheet;
- the registered plan and guide (below).

**Anonymity and the evidence of registration** (owner decision, 1 October). The repository
that holds the registration stays public under the owner's account. ARR has no anonymity
period, and the submission does not link to the repository, so the registration commit itself
is not cited in the anonymous submission. The registration is evidenced by an anonymised copy
of the registered `PLAN.md` and `AUDIT_GUIDE.md` in the supplement, with their sha256 and the
push time. The paper says that the identified record is released on acceptance.

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
- From `collie.llm`: the disk cache, the cache key and the client types.

**One stray file pair.** `analysis/coling/dev_text_size.py` and
`analysis/coling/out/dev_text_size.json` are a development script of the earlier design and its
output. The script imports the commitment study's arms and simulator. Neither is part of this
study, nothing in the study calls them, and they are left out of the release; they are to be
moved out of the study folder before registration.

## 16. Disclosed prior contact

**Before the draft of 29 September.**

- **Design work (29 September)** inspected five CSV captures, from 2020, 2021, 2024,
  January 2025 and December 2025, for text yield. It found 341 distinct timing texts over 147
  drugs, which reduce to 186 templates.
- **The design pilot** fetched 40 archived HTML detail pages from 2023 and read their timing
  snippets. This was text only; no outcome was derived.
- **FAA.** A 2024 FAA pilot sample.
- **openFDA snapshots** (28 and 29 September). The only aggregate read was that 7 of the first
  pull's 1,599 records were resolved.
- **Other pilot files** in `external_data/pilot/`: a July 2025 capture, one 2025 detail page,
  2026 list pages and the 2025 capture index, downloaded for format checks. Whether they were
  read beyond their format is not recorded.
- **The draft's author** read the field vocabulary of one 2020 capture and a random sample of
  distinct availability strings from the 29 captures of 2019 to 2021 (train period).

**From 29 September to this revision (1 October).**

- **The full build (29 September).** `corpus.py` was run over all 110 captures. It wrote the
  open events table (every period, first-sight fields only), the open train outcomes, and the
  two sealed files. As far as is recorded, the sealed files have not been opened or listed
  since. They are overwritten by the freeze run, because the availability rule changed on 1
  October.
- **The Gate 1 printout of 29 September.** Counts only:
  - 225,289 capture rows kept; 22,727 presentation-level events (9,851 dated before 2023,
    12,876 from 2023); and, counted from the open events table it wrote, 13,325 distinct
    statements and 301 episodes;
  - the gate set (2023 to 2025, Current, date-like phrase): 4,328 events, 3,134 distinct
    statements, 123 episodes;
  - events with an observable outcome in the gate set: 2,008 events and 1,419 distinct
    statements under B; 590 and 405 under A;
  - dated after 2023-12-31: 2,679 events, 2,677 of them with a later capture of their thread
    (1,947 distinct statements).
- **The same report printed again on 1 October**, from rebuilds in memory that wrote nothing,
  with the availability rule as changed that day and no string rejected yet. The counts of
  rows, events, statements, episodes and of the gate set are unchanged. Changed or new:
  - events with an observable outcome in the gate set under B: 2,011 events and 1,422 distinct
    statements (under A, 590 and 405 as before);
  - the fourth threshold as worded, which the builder now prints: of the gate set dated after
    2023-12-31, 1,205 events and 834 distinct statements have an observable outcome under B,
    and 334 and 214 under A.

  All of these are counts of events and of events with an observable outcome, which the
  sealing rule allows. They are provisional: the freeze run replaces them.
- **Train outcomes were examined** (they are open): hold rates, slip distributions, censoring
  shares, Turnbull fits, clustering, and the outcome mix of candidate dev splits. The dev
  boundary and the calibrator rules were set with these in view ("Changes", items 3 and 12).
- **The rule reader was run over test-period texts, and event counts were printed.** During the
  review of 30 September and 1 October, `rules.py` (unchanged since 29 September, hash
  `6a810bcb1ae277b9`) read the statement texts of test-period events in the open events table.
  Printed were counts only, from texts, dates and first-sight fields:
  - 2,585 eligible statements in 114 episodes, by year 1,063, 931 and 591;
  - their split by the rule reading's granularity, and the number with a distractor date;
  - the numbers of TBD, silent and stale-at-issue statements (about 1,030 together);
  - the number of eligible statements after each candidate cutoff month;
  - the number covering more than one presentation (579), and the number in the top revision
    bucket;
  - the number first captured after their stated period, and the number whose horizons fall
    inside a long gap between captures;
  - the share of the dominant companies.

  No outcome field was read in these passes. The rule reader's own inventory mode reports the
  test split only in aggregate; whether it was run on the test split while the rules were still
  changing on 29 September is not recorded.
- **One deduction about test outcomes was written down (1 October).** A statement first captured
  after its stated period had ended was, by the at-risk rule, not recovered at that capture. Its
  first horizon event is therefore answered "no" by first-sight data alone. The review stated
  this for a counted set of eligible test statements (190 of the 2,585). This is the value of
  one horizon outcome for a subset of test statements, deduced without reading an outcome
  field. It is the only test-period outcome value known to have been stated. No tabulation of
  that set by year, form or company was made, and none is made before the evaluator runs. The
  rule that followed is in "Changes", item 11.
- **Availability strings of all periods were read** as bare strings, to design the rule fix of
  1 October ("Changes", item 9). No outcome was involved. The effect of the fix on the test
  period is reported only as the count of events whose at-risk flag changes. In the rebuild of
  1 October, before the author check, 55 presentation-level events in 33 statements became at
  risk under B (30 events dated before 2023 and 25 from 2023), and none left the at-risk set.
  The count after the author check is **TBD-at-gate**, from the freeze run, against the events
  table of 29 September.
- **FAA advisories of 2026 (from 1 October).** The advisories are collected from 1 October.
  The parser, the statement builder and the linker are developed on the 2024 pilot sample and
  on the development months (April and May 2026); the code refuses any later month until E6's
  amendment is registered.
- **An archive of results and downloaded data** made on 29 September lies untracked in another
  checkout of the repository. It may hold a copy of the sealed folder as built that day. It has
  not been opened. It is deleted, or moved under the sealed folder, before registration.
  [owner to confirm]

To our knowledge, no test-period outcome has been derived, printed or tabulated outside the
sealed folder, apart from the counts of events with an observable outcome and the one deduction
recorded above.

## 17. Registration record (to complete before pushing)

Hashes are the first 16 hex characters of sha256.

**Identity.**

- A file cannot hold its own hash, nor the id of the commit that holds it. The registration is
  identified by a commit and a tag: the commit on the study branch that holds this file with
  no marker and no owner tag left, together with the guide and the code listed below; and the
  annotated tag `coling-registration` on that commit. The tag `gate-1` that already exists in
  the repository belongs to the UV study and is not used.
- The commit id and the push time (UTC) are therefore not written here. They are recorded in
  amendment F1, with the sha256 of `PLAN.md` and of `AUDIT_GUIDE.md` at that commit, and in
  the supplement (section 14).
- F1 is identified in the same way, by its commit and the tag `coling-f1`. The harness checks
  both tags by these names (section 9).
- Before the push, an independent check runs the study's test files, reruns the corpus builder
  once and compares both sealed hashes with the freeze run's, and confirms every filled number
  against the code.

**Environment.** Python 3.12.11; the lock file `uv.lock`, hash `3308eeb43cb51580` on 1 October,
re-read at registration. Nothing is installed for this study. The bytes of the gzip tables
depend on the pandas version, so the environment is part of the record.

**Captures.**

- The capture manifest `analysis/coling/out/capture_manifest.csv` (110 files): hash
  `8104e4f23dd0c7b5` on 1 October, re-read at the freeze run
  (`python -m analysis.coling.manifest --check --pin 8104e4f23dd0c7b5`).

**Code (hashed at registration).**

- `corpus.py` (events, clusters, outcomes, with the frozen list of rejected availability
  strings): **TBD-at-gate**.
- `rules.py` (the rule reader): `6a810bcb1ae277b9`.
- `forms.py` (the form classifier) and `manifest.py` (the capture manifest): **TBD-at-gate**.
- The dataset builder, the counts-only code, the samplers, the sheet generators and the
  agreement code: file names and hashes, **TBD-at-gate**.
- The calibrator and both GBMs (code): **TBD-at-gate**. If the text-trained GBM is not ready,
  its code hash moves to F1 by an edit of this line before the push.

**Tables.**

- Sealed: `external_data/sealed/outcomes_test.csv.gz` and
  `external_data/sealed/outcomes_train_uncensored.csv.gz`, as printed by the freeze run.
  **TBD-at-gate.**
- Open: `analysis/coling/out/events.csv.gz` and `analysis/coling/out/outcomes_train.csv.gz`,
  each as the gzip file and as its decompressed content. **TBD-at-gate.**
- The E3 eligible list and the three secondary item lists. **TBD-at-gate.**
- The sample lists of section 3 that are drawn before registration. **TBD-at-gate.**

**Annotation.**

- `AUDIT_GUIDE.md` v1: its hash. **TBD-at-gate.**
- The pilot and check-set result (both alphas, the share of identical intervals) and the
  train-half outcome-audit result (confirmed errors for B and for A), with the hashes of the
  submitted sheets. **TBD-at-gate.**
- The availability-string check: its date and counts (section 2.2). **TBD-at-gate.**

**Counts.** Every gate value above, with the Gate 1 record (section 12).

**Models.** `MODELS.md` (cutoffs, release dates, routes, endpoints and prices, each with its
source and retrieval date): its hash, and the table of section 4. **TBD-at-registration.**

**Prompts.** The SHA-256 pins of the five templates (`literal-v1`, `literal-free-v1`,
`predictive-v1`, `predictive-track-v1`, `probe-v1`) as they stand at registration, after the
text changes of 1 October and the two pilot sentences: **TBD-at-gate**. No call has been made
under any of these ids, so the pins of 29 September are replaced under the same ids.

**E6.** Not part of this record. If E6 passes its gate, its own amendment records the hashes
of `faa_fetch.py`, `faa.py` and `faa_links.py`, the manifest of the collected advisories, the
gate result and what section 5 lists.

**At F1:**

- the final template ids and pins (until F1 an edit moves the pin under the same id; from F1
  on a changed prompt takes a new id), the three paraphrase templates, and the parsers;
- the hashes of `read.py` and of the evaluator;
- the dev prompt variants tried;
- the cost-trial projection, and any cap raised within the reserve;
- the H3 selection for each primary, with the dev losses of all three conditions;
- the hashes of the fitted model-free artefacts, after the refit on fit and dev;
- the provider pin as sent, the provider that served the cost-trial calls, and the reasoning
  setting each model served;
- the registration's commit id, tag, push time and file hashes ("Identity").

## Changes from the 29 September draft (1 October 2026)

The draft of 29 September is the previous committed version of this file. Between it and this
revision, train-period outcomes were examined freely (they are open); test-period texts and
first-sight fields were read and counted; and no test-period outcome field was read (section
16, which also records one deduction). Each changed rule is listed with what had been seen when
it changed: *train outcomes*, *test-period event counts*, or *nothing from the data*. Counts
quoted here are from the build of 29 September.

1. **Scope.** E8 is cut for October (E9 was already off). E6 is kept until its linker gate on
   4 October and E7 stays a "could", as the draft had them; E6 is now read by seven models, and
   E7's reference is the rule reading. HeidelTime and SUTime are disclosed as not run. The HTML
   gap fill is not done. *Seen:* nothing from the data. *Why:* none of the cut parts had data
   or code on 1 October, and the study is two days behind.
2. **Deadlines.** The hold-trigger dates get a time zone (AoE) and one relaxation of one day,
   usable only if a human gate has to be repeated. *Seen:* nothing from the data. *Why:* the
   draft gave no time zone, and the schedule has no slack for a repeated gate.
3. **Dev boundary.** Draft: the latest month boundary in 2021 or 2022 that leaves at least 150
   scoreable dated dev events. Now: 2021-01-01, fixed. *Seen:* train outcomes. The draft's rule
   gives 2021-10-01, with 178 scoreable dev statements of which 167 are "no" at both horizons.
   The fixed date gives 661 scoreable dev statements in 73 episodes (508 no/no, 81 no/yes, 72
   yes/yes) and leaves 799 for fit. *Why:* train outcomes stop at 2022-10-06 and no capture
   exists for the 308 days before 2022-10-04, so a late boundary scores almost only statements
   that had not recovered; the H3 selection and the power check would rest on that.
4. **Reference reading and eligibility.** Draft: the stated period came from the rule output
   for forms where it matched author labels on 95% of audited train items, and from author
   labels for every other test event. Now: the frozen rule reading for every form; the authors
   check 100 eligible statements and the accuracy is reported; no author labels on the other
   forms in October. *Seen:* test-period event counts (the eligible count, and its split by the
   rule reading's granularity: 418 of 2,585 eligible statements are not plain month and year).
   No test-period outcome. *Why:* the eligible list and the stated end printed in every
   predictive prompt must exist at registration, and the labels would have come after it; the
   labelling load did not fit the annotators' hours.
5. **Primary outcome unit.** Draft: the maximum over all presentations a statement covers. Now:
   the bracket of one displayed presentation, drawn by the seeded rule; the maximum is a
   secondary. *Seen:* test-period event counts (579 of 2,585 eligible statements cover more
   than one presentation). No test-period outcome. *Why:* the prompts show one presentation and
   ask about "this presentation".
6. **Fields shown.** Therapeutic Category and Initial Posting Date are added to the entry block
   and to the probe; Status is dropped from the list of shown fields and from the structured
   GBM. *Seen:* nothing from the data. *Why:* the structured baseline used two fields the
   models did not see, which confounded H3; Status is constant on at-risk statements.
7. **Literal task (E2).** Draft: 300 statements labelled by one author, 60 of them by a second;
   a 30-item pilot; a McNemar test per form with at least 15 items, with Holm over forms × 2.
   Now: 120 statements labelled by both; a 20-item pilot and a 20-item check set; one pooled
   exact McNemar test per primary over the items outside the month-and-year stratum; per-form
   results descriptive. *Seen:* event counts by form in all periods (texts only). *Why:*
   annotator hours; under the guide's quotas only one form reached 15 items, so the per-form
   family had no power.
8. **Budget scope.** gemini-3.8-flash reads E2 and the E3 conditions only (no probe, no E5, no
   E6); the TBD, silent and stale secondaries are read by the two primaries only; the Late
   split is not read for outcomes, where the draft kept it for descriptive post-cutoff slices
   of the newest models; the table is rebuilt from itemised counts. *Seen:* test-period event
   counts (2,585 eligible statements against the 1,000 the draft assumed). *Why:* the draft's
   scope passed the gemini-3.8-flash cap at the real counts.
9. **Availability rule and capture set.** Negated, future and estimated uses of "available",
   and a mention directly followed by a time, no longer class a row as available; strings the
   author rejects go in a frozen list; the capture set is frozen at the 110 files, with a
   manifest the builder checks. *Seen:* the availability strings of all periods, as bare text;
   train outcomes had been examined; no test-period outcome. *Why:* the old rule classed texts
   such as "available by 4/5/19" and "no release date available at this time" as available,
   which removes a statement from the at-risk set or records a false recovery under B.
10. **Agreement gate.** Draft: alpha on endpoint offsets in days over a 30-item pilot. Now:
    alpha on the start and on the end month offsets over a 20-item check set labelled under the
    revised guide, with the share of identical intervals beside it. *Seen:* nothing from the
    data. *Why:* the plan and the guide disagreed; the guide's check set had 10 items, on which
    one large disagreement decides the gate; month offsets are the guide's unit.
11. **Delayed entry.** Now explicit: a statement first captured after its stated period stays
    eligible, and a sensitivity analysis on statements first captured on or before `t_end` is
    registered. *Seen:* test-period event counts by first-sight dates, and the deduction of
    section 16. *Why:* the draft did not say how such statements are treated.
12. **Calibrator.** Now: form by revision bucket when the cell holds at least 100 statements,
    else form, else all dated forms; buckets first, second, third or later; the prompt's
    track-record table has the same cells and carries Turnbull shares. *Seen:* train outcomes
    (cell sizes and Turnbull fits), and the test-period count of statements per revision
    bucket. *Why:* most form-by-revision cells are too small, and the draft's "1, 2, 3 or more"
    did not match an index that starts at 0.
13. **Small rules.** The date shift is plus 4 years. The 20 samples use condition (a) and are
    scored as empirical quantiles of the sampled medians. The probe sample comes from the
    eligible list, stratified by year, and its items carry no stated period. The H2 margin of
    0.02 is confirmed. Parsing is strict: the draft's sentence that sorted quantiles and
    clipped probabilities is deleted. *Seen:* nothing from the data. *Why:* the draft left
    these open, or contradicted the harness.
14. **E5.** The authors' predictive readings are cut. The registered test is a GEE clustered by
    seed, with 12 tests under Holm; the draft's mixed model with Firth's correction is dropped.
    *Seen:* nothing from the data. *Why:* no library in the environment fits the mixed model,
    and the readings had no procedure or hours.
15. **What is hashed when.** Code of the form classifier, calibrator and GBMs at registration;
    fitted artefacts at F1. *Seen:* nothing from the data. *Why:* every component is refitted
    after the H3 selection, so no fitted artefact is final at registration.
16. **deepseek-v3.** It stays a primary with a cutoff bounded by its release month if no cutoff
    is documented. *Seen:* nothing from the data. *Why:* the draft assumed a documented cutoff.
17. **Evidence of registration.** Identity by commit and tag; an anonymised copy of the plan and
    guide in the supplement. *Seen:* nothing from the data. *Why:* the draft did not say how a
    file is identified without its own hash, or how the record is shown under anonymity.
18. **The rule reader is frozen now**, not at F1, and the pilot no longer changes it. *Seen:*
    the reader had been run over test-period texts for counts. *Why:* a rule change after those
    passes would no longer be blind to test-period text, and the eligible list depends on it.
19. **Sample order.** The pilot, check and literal samples are drawn first, and the in-context
    examples, dev prompt items and minimal-pair seeds exclude them; the draft excluded in the
    other direction. *Seen:* event counts. *Why:* the draft's order was circular.
20. **Rule baseline.** `rules.py` is the rule baseline; the draft chose the best of three
    normalisers on pilot items. *Seen:* nothing from the data. *Why:* the other two are not
    run.
21. **Small slices and unfinished runs.** A switched primary whose slice has fewer than 50
    scoreable statements, or a primary whose runs cannot finish, has its tests reported as not
    evaluable inside the family of six. *Seen:* test-period event counts after candidate cutoff
    months. *Why:* the draft had no rule.
22. **Forms.** The inventory has 15 classes in a fixed order, with year alone, half of a year,
    vague and undated statements as classes of their own. A class with fewer than 15
    train-period statements at risk under B is merged into a named neighbour; the draft merged
    a form with fewer than 15 events in all periods into "other". *Seen:* counts of statements
    by form in every split (texts only); the merge uses train counts. *Why:* the draft's 11
    forms overlapped and had no order.
23. **New definitions.** The power proxies; the criterion for "overconfident"; distractor
    uptake; selective prediction limited to condition (c) and the rules; the E5 error and the
    contrast of each E5 test; the evaluator's three refusals in terms of what the harness
    stores; bounds beside every confirmatory estimate. *Seen:* nothing from the data beyond the
    items above. *Why:* the draft named these without defining them.
24. **Roles.** Draft: the annotators are the authors, and adjudication is by an author who does
    not write prompts. Now: A1 and A2 do all the labelling and both outcome audits; the owner
    adjudicates, does not label, and may write prompts and read model outputs, within a stated
    limit on items still to be adjudicated. *Seen:* nothing from the data. *Why:* under the
    draft one person would have labelled items and followed the runs on them.
25. **Gate 1 record.** Draft: four thresholds on "statement events with a stated date". Now:
    the thresholds must hold both on the builder's gate set (a date-like phrase, the
    statement-level bracket) and on the E3-eligible statements with the primary outcome; the
    builder prints the fourth threshold as worded. *Seen:* the counts of section 16, which
    include counts of test-period events with an observable outcome. *Why:* the printout of 29
    September tested a wider set than the analysis set, and a weaker fourth count.
26. **Availability check.** Draft: an author checks every string the rule classes as
    available. Now: the adjudicator checks those strings and the ones the rule change moved out
    of available; the strings classed limited are added as an optional part. *Seen:* the
    availability strings, as bare text. *Why:* the rule change needs a check in both
    directions; the strings classed limited (about 650) bear mainly on a sensitivity analysis.
27. **Sealing rule.** Now explicit: before registration the sealed files are read once, by the
    counts-only code at the freeze, which prints the numbers of scoreable and undetermined
    statements and no outcome value; the files are written by the freeze run and its one
    checking rerun only. The draft allowed counts of events with an observable outcome and had
    Gate 1 print a scoreable count, without saying what code reads the sealed file. *Seen:*
    nothing from the data. *Why:* several builds share one sealed folder.

**Status of these changes.** The owner confirmed on 1 October the scope (item 1), the deadlines
and their one relaxation (item 2), the roles (item 24), and the public repository with an
anonymised copy of the plan and guide in the supplement (item 17). The other items are
provisional rules of 1 October: each stands as written unless the owner changes it, and each
is confirmed or changed before this file is registered. [owner to confirm]

**Corrections of the text to the code as it stood on 29 September** (the builder did not change
for these; the draft described it wrongly). *Seen:* train outcomes; the builder had been tested
on the train period.

- The train horizon is the last capture before 2023, or the event's first capture if later;
  the sealing rule names the uncensored train file.
- Episodes are runs of captures with the generic Current; the Initial Posting Date is not used;
  an event whose generic is not Current at its first capture has no episode.
- Five censoring reasons, and the last usable capture per period.
- The Date Discontinued cell on a shortage row is not a discontinuation.
- The event date falls back to the capture date only when the Date of Update is later by more
  than one day.
- "By X" runs from the Date of Update to the end of X.
- Observable brackets include brackets to discontinuation.
- The third at-risk condition is applied by the dataset builder, and a statement is at risk
  when any covered presentation is.
- Five statement types and four certainty classes, as in the answer schema and the guide.
- The capture counts (110 files on 109 days, not 111 days and 65 on disk), two further gaps
  of more than 90 days, and the count of realigned rows (the draft's 34 came from an earlier
  check).
- Provider routing was described as pinned; the harness of 29 September sent no provider
  preference. The pin, the stored provider and the study ledger were added on 1 October.
- Output paths, the shared modules, and the two prices with earlier dates.
- The FAA advisories were described as being collected in the background; the collection
  started on 1 October. The openFDA snapshot was described as daily; two were taken.
- What Gate 1 tested (section 12).

## Amendments

None yet.
