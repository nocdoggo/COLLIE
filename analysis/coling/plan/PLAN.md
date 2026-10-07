# Estimated Recovery: TBD. Study plan

**Registered on 6 October 2026 (anywhere on Earth; 7 October in UTC).**
This file is the registration of the study. It was completed, pushed and tagged
(`coling-registration`; section 17, "Identity") before any language-model call of this study,
and while the outcomes of every test-period statement were sealed:

- every value that depended on the frozen corpus, the samples, the pilot or the model-free
  predictors is filled in, by the rule written next to it; the result of the check set and
  the estimated load that follows from it were not available and belong to amendment F1
  (section 10, task 2);
- every fact about a model was confirmed at its source;
- every provisional rule was confirmed by the owner;
- the registration record (section 17) is complete.

The first target was Saturday 3 October 2026, 23:59 AoE. It was missed: the annotators returned
the pilot and the train-half outcome audit on 5 October. The owner moved the target to Tuesday
6 October 2026, 23:59 AoE, and kept the submission to the October cycle (section 12, "The
schedule from 5 October"). What changed since the draft of 29 September, and what had been seen
when it changed, is listed in "Changes from the 29 September draft" near the end of this file.
From here on every change is a dated amendment at the end of this file (A1, A2, ...), and the
freeze of prompts, parsers, harness and the one registered model selection is amendment F1,
pushed before the first call on any test-period item.

While this file was a draft it used four markers. The first, the second and the fourth are
resolved everywhere; only the third is left, where a value belongs to amendment F1:

- **TBD-at-gate**: depends on the frozen corpus build, the form classifier, the dataset builder,
  the samples, the pilot or the model-free predictors. It is filled in before registration by the
  stated rule, never by looking at a test-period outcome value.
- **TBD-at-registration**: a fact confirmed at its source before registration (model release
  dates and cutoffs, provider endpoints and their prices). It does not depend on the data.
- **TBD-at-F1**: fixed by amendment F1 (final prompt pins, code hashes of the harness and the
  evaluator, the hash of the model-free test predictions, the H3 selection).
- **[owner to confirm]**: a provisional rule, written on 1 October or, for the later items
  of the change list, on 5 and 6 October, that the owner has not yet confirmed.

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
  - A count that would let a small number be worked out is masked. The counts-only code prints
    a count below 5 as `<5`, and where an exact count together with an open total would give a
    count below 5 by subtraction, it prints a lower bound (`>N`) or `withheld`. A masked count
    is registered as printed.
  - After registration the sealed outcomes are read only by the sampler and the sheets of the
    test-period outcome audit (section 10), by the registered evaluator, and by the secondary
    scorers. None of them reads a sealed file before every confirmatory run has finished or,
    for a primary whose runs cannot be completed, has been declared so (section 6). The
    evaluator runs after the test-half outcome audit (section 10). A secondary scorer runs
    only after the evaluator has written its result file, and only when every run that it
    scores is complete. The registered evaluator is `evaluate.py`, hashed in F1; it computes
    the six tests and what section 6 lists under "Evaluator". A secondary scorer is a script
    that computes a registered secondary analysis from a sealed file. Each one is named, with
    its hash, in F1 or in a later dated amendment that is pushed before the script first
    reads a sealed file; a scorer changed after it has read one takes a new amendment, which
    gives the reason. The evaluator reads the sealed rows through the checked reader of the
    counts-only code (`_checked_rows` and `_same_build` of `sealed_counts.py`), behind its
    own hash check, reads no stored file that leads into a sealed folder through a link, and
    prints no character of a sealed file's hash where it refuses the file for its hash; a
    scorer that reads the test outcomes reads them in the same way, applies
    the refusals of section 6 to the runs it scores, and writes no value of a single
    statement. The evaluator and every scorer withhold a secondary figure, its counts apart,
    where it rests on 1 to 4 statements, and where the same figure is also written on a set
    that differs from its own by 1 to 4 statements, so that the two together would give back
    the outcomes of those few (a slice within its whole, the answers that parsed within all,
    one outcome definition beside another). The second check is made on pairs of sets. In the
    tables of E1 it is also made on the cells written with their whole (section 5, E1). A count
    is withheld too where it says, by itself or by subtraction from a count beside it, how
    many of 1 to 4 statements are scoreable or have a determined event. Sections 2.5, 4, 5 (E1
    and E4), 6 and 13 name the cases known at
    registration. The six confirmatory contrasts are never withheld. The same contrasts of the
    six secondary models on every eligible statement are never withheld on the second ground:
    the figure that stands beside one of them is the one withheld. Where the two sides of such
    a contrast differ on 1 to 4 statements, it gives the loss difference of those few, and for
    H2 the paper says how many differ (section 6).
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
- *Seeds.* Every random choice uses seed 20261001. A sample of section 3 is drawn by ordering
  the candidate ids by the sha256 of the seed, a tag that names the draw, and the id, and
  taking them from the top (within each stratum, and under the caps, where a sample has them).
  The result does not depend on the order of the input, and an id keeps its place when other
  ids come or go. Resampling (bootstrap draws, sign flips) uses the same seed in a
  random-number generator.
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

1. against a human reading of the text, its letter and its standing (the literal task);
2. against what actually happened, reconstructed from 2019 to 2026 archive captures;
3. by a decision loss.

The claim under test: models read the letter of a notice but not its pragmatics. The *letter*
of an estimate is what its words denote under the conventions of section 2.5: the kind of event
they name (the statement type) and its period. The *standing* of an estimate is whether that
period is on offer as a live estimate: whether the notice gives a period at all, which date in
the notice is the estimate, how firmly it is put (the certainty class), and whether it had
passed at the Date of Update (the stale flag). The *literal reading* is the answer to the
literal task and holds the letter and the standing together: "literal" names the task (E2, E5,
section 7.1) and not the letter. The *predictive reading* is the forecast of what will happen.
*Pragmatics* names two things and nothing else: the standing, which the literal task scores,
and the predictive reading, which is scored against outcomes (E3). The claim names three
failures: a date given where the text says TBD and a stale estimate treated as live (standing),
and optimistic dates copied (predictive reading). The terms are operational: every standing
judgement follows from the words of the notice and its date by the conventions of the guide,
the rule reader makes it by rule, and `literal-v1` states those conventions to the model. The
study also tests whether giving a model the track record of earlier estimates on the same list
closes the gap.

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

**Malformed rows.** Rows with more cells than their header (unescaped quotes inside Presentation
or Related Information) are realigned by a fixed rule and flagged, and short rows are padded.
The builder prints the number of realigned rows for every capture. The registered counts, from
the freeze run: 225,289 rows kept over the 110 captures; 634 rows dropped as duplicate or
without a status; 7 rows realigned among those kept, in 3 captures (5 in `20191020223457`, 1 in
`20221004081320` and 1 in `20221006172748`) and none in the other 107.

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
    (section 2.5), and for B only where a string in fact reports full supply.
  - A string the checker rejects goes into a list frozen with `corpus.py` and is then classed
    other. A string that the rule moved out of available and the checker would keep is settled
    before the freeze run: the rule is changed, or the difference is recorded here.
- *The check was done on 1 October 2026.* The adjudicator read the whole list as `corpus.py`
  wrote it that day: 910 distinct strings, of which the rule classes 233 as available and 647
  as limited, and 30 that the rule change moved out of available. The strings classed limited
  were read too, so the optional part is done. No string was rejected and no change to the
  rule was asked for, so the frozen list of rejected strings is empty. The record of the check
  is this paragraph and the sha256 of the list as read (`da0bde1baac48473`).
- At the freeze the list is written again by its own command (it reads the captures only) and
  its hash is compared with the one above. If it differs, the strings that differ are checked
  before the outcomes are sealed, and what was checked is recorded here.

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
and enters no outcome analysis set. The count of such statements is 245: 35 in the fit split, 10
in dev, 163 in test and 37 in late.

**The display row.** Readers and annotators see one row per statement event. When the statement
covers several presentations, one of its presentations at risk under B is drawn by the seeded
rule of the standing rules (the tag is made from the statement's id; no outcome field is used)
and shown. A
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

**Size.** The freeze run gives 22,727 presentation-level events (9,851 of the train period and
12,876 of the test period, which includes Late) in 6,866 threads of 1,207 generics, and the
dataset builder groups them into 13,325 distinct statement events. By split (Train is Fit and
Dev together):

| | Fit | Dev | Test | Late | Train | All |
|---|---|---|---|---|---|---|
| Presentation-level events | 5,516 | 4,335 | 10,165 | 2,711 | 9,851 | 22,727 |
| on the shortage listing | 4,298 | 3,722 | 8,910 | 2,397 | 8,020 | 19,327 |
| at risk under A | 3,860 | 3,379 | 8,637 | 2,386 | 7,239 | 18,262 |
| at risk under B | 2,264 | 2,297 | 5,636 | 1,717 | 4,561 | 11,914 |
| Statement events | 2,838 | 2,687 | 6,024 | 1,776 | 5,525 | 13,325 |
| on the shortage listing | 2,333 | 2,351 | 5,462 | 1,628 | 4,684 | 11,774 |
| at risk under A | 2,193 | 2,242 | 5,349 | 1,623 | 4,435 | 11,407 |
| at risk under B | 1,482 | 1,639 | 3,772 | 1,225 | 3,121 | 8,118 |
| at risk under B: dated, not stale at issue | 1,163 | 1,334 | 2,667 | 861 | 2,497 | 6,025 |
| at risk under B: dated, stale at issue | 9 | 14 | 16 | 5 | 23 | 44 |
| at risk under B: TBD or unknown | 116 | 134 | 376 | 206 | 250 | 832 |
| at risk under B: silent | 159 | 147 | 550 | 116 | 306 | 972 |
| at risk under B: in no analysis set | 35 | 10 | 163 | 37 | 45 | 245 |

The draft's expectation of 800 to 1,500 statement events was too low by about a factor of ten
(section 16 gives the counts printed before the freeze run).

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
- The freeze build holds 301 shortage episodes. 237 hold a train-period statement and 153 a
  statement dated 2023 or later; 89 hold both, and so cross the split. The dated statements at
  risk under B that are not stale at issue lie in 123 episodes in the fit split, 121 in dev, 116
  in test and 53 in late. The E3-eligible statements lie in 115 episodes, 73 of which also hold
  train statements; the three secondary lists lie in 76 (TBD), 96 (silent) and 13 (stale at
  issue), of which 52, 59 and 9 also hold train statements. The scoreable statements lie in 106
  episodes in fit and 74 in dev; the episodes of the scoreable test statements are in section 3.

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
  capture where the row is missing, and limited supply counts as available (BL). A contrast
  under a sensitivity analysis or under another outcome definition (definition A; the outcome
  over all or over any covered presentation) that gives 1 to 4 statements of its item set
  another horizon event, or 1 to 4 of those scoreable under either definition, is withheld with
  its two
  scenarios, and the number of statements with another horizon event is given: beside
  the same contrast under the primary outcome it would give the change of the losses of those
  few.

**Discontinuation** is a competing event, and it wins ties. A presentation is discontinued when
it newly appears in the discontinuation listing (by NDC overlap or the same text key). A Date
Discontinued cell on a shortage row is not used: in the train captures it mostly repeats the
date of a resolution and appears on products that stayed on the market. The first capture where
such a cell newly appears is kept in the column `date_discontinued_on_row_date`, for a
sensitivity analysis. In that analysis the cell counts as a discontinuation at that capture: a
displayed presentation that is censored, or whose recovery is first shown at that capture or a
later one, is discontinued there (discontinuation wins ties); one that had recovered at an
earlier capture keeps its recovery.

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
  For such a statement the horizon events ask whether supply was back by the period the notice
  gives for a delivery, which is more than the notice states; E3 reports its outcome results
  by statement type (section 5, E3, "Secondaries").
- The period comes from the *frozen rule reading* (`rules.py`) for every form and every split:
  train, dev, test and late. It never comes from a predictor's own reading or from an author
  label. The dataset builder supplies its last day to every predictor as `stated_end`, and the
  predictive prompts print it as horizon A.
- The rule reading is checked, not replaced: the authors check 100 eligible test statements and
  the rule's accuracy is reported (section 10).
- The conventions are those of `rules.py`, which the literal prompt and the guide share:
  - a month is the whole month, and a year alone is the whole year;
  - a month or a quarter with no year is its first occurrence that ends on or after the Date
    of Update; a half of a year written with no year is not read, and such a text has no
    stated period;
  - early, mid and late in a month are days 1 to 10, 11 to 20, and 21 to the month's end; in a
    quarter they are its first, second and third month; in a year, its first, second and last
    four months;
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
  are E3's primary analysis set. Scoreability depends on the outcome as well as on where the
  captures fall: a recovery inside a gap between captures that contains a horizon leaves that
  event undetermined. The two scenarios of section 7.2 are therefore reported beside every
  confirmatory estimate, in every record of a primary loss (section 7.2), beside each quantity
  of the analysis by statement type (section 5, E3), and beside the primary-loss estimates of
  the secondary scorers. Where 1 to 4 statements of a set are not scoreable, the figures over
  every statement of the set that fill its undetermined horizon events (the two scenarios, and
  the two limits of calibration in the large) are withheld: beside the figures on its
  scoreable statements they would give the events of those few. The mean probabilities and
  the calibration in the large on the scoreable statements, which name the few that are not,
  are then withheld too. The same holds where only 1 to 4 statements of a set are scoreable.
  The pinball losses and the coverage stay.
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
- The count of eligible statements first captured after `t_end` is 194, of 2,593. No tabulation
  of this set by year, form or company is made before the evaluator runs.

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
calibrator, the track-record table). A class that is still too small after it has received
another is merged on in turn; month and year, and silent, are never merged away. The
literal-task sample is stratified on the unmerged classes, and the reports of the literal task
(the agreement of section 10, and E2) are given by stratum of the guide's allocation table,
not by the merged classes: "by form" and "per form" mean that there. Templates are the
normalised texts with months and numbers masked; results are also reported weighted by
template.

The final inventory and order are the fifteen classes above, from the classifier on the frozen
build (its hash is in section 17). Five classes hold fewer than 15 train-period statements at
risk under B: relative (5), half of a year (3), vague (6), discontinuation (10) and distractor
(10). Taken in the order above, four of them are merged, each into its named neighbour: relative
into range; half of a year into quarter; vague into no date; discontinuation into distractor.
Distractor then holds 20 and stays. Year holds 15 and stays a class of its own. Per-form
reports of the outcome experiments, the calibrator and the track-record table therefore use
eleven classes, in this order:
range (relative or range), exact day, part of a month, quarter (half of a year or quarter),
year, month with no year, month and year, TBD or unknown, no date (vague or no date), distractor
(discontinuation or distractor), silent. No statement has covered presentations of different
forms. The count per form and split, as distinct statements at risk under B (Train is Fit and
Dev together):

| | Form | Fit | Dev | Test | Late | Train | All | Merged into |
|---|---|---|---|---|---|---|---|---|
| 1 | relative | 4 | 1 | 13 | 12 | 5 | 30 | range |
| 2 | range | 43 | 41 | 63 | 6 | 84 | 153 |  |
| 3 | exact day | 20 | 24 | 18 | 28 | 44 | 90 |  |
| 4 | part of a month | 87 | 98 | 124 | 44 | 185 | 353 |  |
| 5 | half of a year | 1 | 2 | 0 | 0 | 3 | 3 | quarter |
| 6 | quarter | 38 | 49 | 165 | 23 | 87 | 275 |  |
| 7 | year | 8 | 7 | 19 | 2 | 15 | 36 |  |
| 8 | month with no year | 20 | 20 | 63 | 3 | 40 | 106 |  |
| 9 | month and year | 951 | 1,106 | 2,218 | 748 | 2,057 | 5,023 |  |
| 10 | TBD or unknown | 116 | 134 | 376 | 206 | 250 | 832 |  |
| 11 | vague | 5 | 1 | 2 | 0 | 6 | 8 | no date |
| 12 | no date | 16 | 3 | 13 | 2 | 19 | 34 |  |
| 13 | discontinuation | 9 | 1 | 46 | 27 | 10 | 83 | distractor |
| 14 | distractor | 5 | 5 | 102 | 8 | 10 | 120 |  |
| 15 | silent | 159 | 147 | 550 | 116 | 306 | 972 |  |
| | **All** | 1,482 | 1,639 | 3,772 | 1,225 | 3,121 | 8,118 | |

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
  and 2022-10-04 ("Changes from the 29 September draft", item 3). From the dataset builder,
  on the displayed presentation: the dev split holds 1,334 dated statements in 121 episodes, of
  which 644 are scoreable, in 74 episodes; 690 have a horizon event left undetermined. The dev
  outcome mix on the two horizon events is 486 no/no, 82 no/yes and 76 yes/yes. The fit split
  holds 1,163 dated statements in 123 episodes, of which 803 are scoreable, in 106 episodes (453
  no/no, 180 no/yes, 170 yes/yes).
- **Fit outcomes run past the dev boundary.** A fit statement is followed to 2022-10-06, through
  the dev period. A component fitted on the fit split for the dev runs therefore uses recoveries
  dated inside the dev period, and the H3 selection on dev is not a clean forecast evaluation.
  The same holds for condition (b) in the dev runs. Its table rests on the same fit outcomes,
  and its examples can show a recovery or follow-up date later than the dev item's own date.
  A fit statement can also be an earlier statement of a dev item's thread: its bracket is then
  the dev item's own outcome, which the table counts and an example can show (no example shows
  the drug, the company or the presentation). No statement is left out for this. The numbers,
  from the manifest of the track-record builder: 741 of the 1,438 fit statements behind the
  table have a bracket date on or after 2021-01-01; 6 of the 10 examples show such a date; the
  table follows the thread of 167 of the 644 scoreable dev statements past their date (473 of
  all 2,687 dev statements); and an example follows the thread of 4 of the scoreable ones (10 of
  all dev statements; 3 of the 10 examples do so).
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
    and that capture date is the only test-period date in its row. There are 119 such statements
    on the shortage listing (295 presentation-level events), of which 52 are at risk under B (86
    events); the track record of fit and dev holds those 52, each censored at its first capture.
    Every such statement of the shortage listing is first seen in the capture of 2023-01-13.
    The open events table also holds 38 such statements of the discontinuation listing, which
    enter no outcome analysis; three of them are first seen in later captures of 2023.
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
  - The eligible list holds 2,593 statements in 115 shortage episodes (1,069, 933 and 591
    statements dated 2023, 2024 and 2025). Of these, 1,903 statements are scoreable, in 106
    episodes, and 690 have a horizon event left undetermined. These three counts come from
    registered code (`sealed_counts.py`) that read the sealed file once, in the freeze run of
    5 October, and printed only these counts, the scoreable count of each post-cutoff slice,
    and the two observable counts of the Gate 1 record (section 12), each under the masking
    rule of the standing rules. No count needed a mask.
  - TBD, silent and stale-at-issue test statements at risk under B form three further item
    lists, each hashed, for E3's secondary analyses. Their sizes are 376 (TBD), 550 (silent) and
    16 (stale at issue), 942 together, in 76, 96 and 13 episodes.
- **Post-cutoff slices.** For each model, the slice is the eligible statements dated after the
  last day of its training-cutoff month.
  - The cutoff is the one documented by the model's maker. A model with no documented cutoff
    uses its release month, and the plan then calls the cutoff *bounded*, not documented
    (section 4).
  - Slices are taken inside the test split. The Late split is not read for outcomes in October,
    so a model whose cutoff month is December 2025 or later has no slice.
  - With the cutoffs of section 4, six slices start after these days: 2023-10-31
    (gpt-4o-mini), 2023-12-31 (llama-3.3-70b), 2024-06-30 (gpt-oss-20b), 2024-08-31
    (gemma-3-27b), 2024-09-30 (qwen-2.5-7b) and 2024-12-31 (deepseek-v3). gemini-3.8-flash and
    grok-4.20, both of March 2026, have no slice.
  - A slice is analysed only if it holds at least 50 scoreable statements. The six slices hold
    1,670, 1,524, 943, 845, 761 and 591 eligible statements, in the order above, of which
    1,253, 1,121, 679, 607, 549 and 411 are scoreable (cutoffs from section 4; counts from the
    counts-only code, each an exact count). Every slice meets the rule. The masking rule would
    have allowed a size to be registered as a lower bound, with a bound above 49 meeting the
    rule, or to be withheld and decided by the evaluator from the exact count after unsealing;
    neither was needed.
- **Samples and their order.** Every sample is drawn by the seeded rule, in this order, so that
  no later sample can change an earlier one:
  1. the pilot, the check set, the reserve check set and the literal-task sample (section 10),
     in that order, from the events table and the form classifier only, with no outcome field;
  2. the train-half outcome-audit sample;
  3. the in-context examples, the dev prompt items and the minimal-pair seeds, in that order,
     which exclude everything drawn in steps 1 and 2 and one another, and every statement that
     reads like an item of step 1: one whose whole text is that of an item, whatever the drug
     or company, and one of the same drug and company, dated the same day, for which the rule
     reader finds the same statement type and period (guide, section 10). The seeds of the
     relative form are statements dated 2023-01-01 or later, text only, and no model is called
     on their pairs before F1;
  4. from the eligible list: the probe sample, the 20-sample subset, the paraphrase subset, the
     2×2 subset (section 5) and the 100 statements of the reference-reading check. Each is a
     draw of its own, so the subsets may overlap. The reference-reading check leaves out the
     statements of step 1, so that no annotator is shown the rule reading of a statement they
     labelled (section 10);
  5. the test-half outcome-audit sample, drawn under the sealed folder after every
     confirmatory run has finished (section 10).

  The statements used as examples in the guide and the fixed test item of the harness are
  excluded from every sample. A statement whose whole text is, word for word and punctuation aside, a phrase of three or
  more words
  quoted in section 3 or 7 of the guide, or whose two text fields are each such a phrase, is
  excluded from every sample of statements that are read (guide, appendix A.4); the
  outcome-audit samples do not apply this rule. The hash of every sample list drawn before registration (steps
  1 and 2 at least) is in section 17; a list of steps 3 and 4 drawn after it is hashed in F1,
  before any call that uses it.

## 4. Models

Eight readers. Temperature 0 where the provider supports it. Provider defaults for reasoning,
recorded in F1. Reasoning and thinking tokens are billed as output.

| Model | Role | Route and id | Released | Training cutoff | Pinned endpoint, precision | $/1M in | $/1M out |
|---|---|---|---|---|---|---|---|
| llama-3.3-70b | **primary** | OpenRouter `meta-llama/llama-3.3-70b-instruct` | 2024-12 | documented: December 2023 (model card) | `deepinfra/turbo`, fp8 | 0.10 | 0.32 |
| deepseek-v3 | **primary** | OpenRouter `deepseek/deepseek-chat` | 2024-12 | bounded: December 2024 | `deepinfra/fp4`, fp4 | 0.32 | 0.89 |
| qwen-2.5-7b | secondary | OpenRouter `qwen/qwen-2.5-7b-instruct` | 2024-09 | bounded: September 2024 | `phala`, precision not stated | 0.10 | 0.20 |
| gemma-3-27b | secondary | OpenRouter `google/gemma-3-27b-it` | 2025-03 | documented: August 2024 (model card) | `deepinfra/fp8`, fp8 | 0.08 | 0.16 |
| gpt-oss-20b | secondary | OpenRouter `openai/gpt-oss-20b` | 2025-08 | documented: June 2024 (model card) | `deepinfra/bf16`, bf16 | 0.03 | 0.14 |
| gpt-4o-mini | secondary | OpenRouter `openai/gpt-4o-mini` (alias of the only snapshot, `gpt-4o-mini-2024-07-18`) | 2024-07 | documented: October 2023 (provider model page) | `openai`, not applicable | 0.15 | 0.60 |
| gemini-3.8-flash | secondary | Google `gemini-3.8-flash` | 2026-09 | documented: March 2026 (model card; January 2025 in some domains) | direct | 0.75 | 3.75 |
| grok-4.20 | secondary | xAI `grok-4.20-0309-non-reasoning` | 2026-03 | bounded: March 2026 | direct | 1.25 | 2.50 |

- **How the table is filled.** Release dates, cutoffs, routes and endpoints are collected at
  source, each with its URL and retrieval date, and kept in `MODELS.md` in this folder, whose
  hash is in section 17. No model is called for this, and no key is used. The pages were read
  on 1 October (standing rules, "Web requests"). They were read again on 5 October, twice and
  independently, because registration had moved to 6 October; every registered value held. The owner reviews the entries of the two
  primaries before they enter the table.
- **Cutoff rule.** A cell reads "documented: month (source)" when the model's maker states a
  cutoff, and "bounded: release month" otherwise (section 3).
- **Prices.** The prices shown are the list prices per 1M tokens of the pinned endpoints (of
  the makers' own routes for gemini-3.8-flash and grok-4.20), read at source on 2026-10-01.
  On OpenRouter a price belongs to one provider endpoint, so the registered price is the pinned
  endpoint's. The 29 September draft took its prices from the repository's ladder file, which
  holds one price per model id; for three models that was the price of another endpoint, and
  the pin changes it: deepseek-v3 (was 0.257 / 1.029), gemma-3-27b (was 0.08 / 0.45) and
  gpt-oss-20b (was 0.018 / 0.09). The gemini-3.8-flash price holds through 2026-12-31, and the
  grok-4.20 price holds for prompts under 200,000 tokens, which every prompt of this study is.
  The harness carries its own table of the eight readers (route, endpoint, precision and price)
  and refuses a live run for any other model, or while a route is not yet set.
- **Provider pin.** The harness of the 29 September draft sent no provider preference:
  OpenRouter chose the provider and could fall back to another, and only the echoed model id
  was checked, which is the same for every provider of a model. Now each OpenRouter request
  names one provider endpoint with fallbacks off. The echoed model id and the provider that
  served the call are stored with every call, and a response from another model or another
  provider stops the run. The endpoint chosen for each model, with its precision, is in the
  table. With fallbacks off, an outage of the pinned endpoint is a failed attempt to retry
  later, never a reason to change the route. No test-period call is made before F1.
- **Why these primaries.** Both are open-weight models with early cutoffs, which the
  memorisation controls need. Each is served by one named endpoint at a stated precision. The
  primaries alone enter the confirmatory family. Three facts qualify this:
  - Only llama-3.3-70b has a cutoff documented by its maker (December 2023). The maker of
    deepseek-v3 documents none, so its cutoff is bounded by its release month (December 2024).
  - Neither pin serves the precision of the released weights: llama-3.3-70b is released in BF16
    and pinned at fp8, and DeepSeek-V3 is released in FP8 and pinned at fp4. No endpoint serves
    the December 2024 DeepSeek-V3 at FP8. The paper's model table prints the precision.
  - `deepseek/deepseek-chat` has no dated id. OpenRouter's record and the host's own page tie
    the route to the December 2024 weights (`MODELS.md` section 5), which is as far as a check
    without a call can go. The maker no longer serves that model itself.
- **deepseek-v3 stays a primary** under these conditions, its cutoff is bounded by its release
  month, and every statement about it says "bounded". The owner chose the endpoint
  `deepinfra/fp4` over `streamlake` on 1 October, because its host names the checkpoint and
  states the precision (`MODELS.md` section 5).
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
  - Under condition (c), a literal interval given for a depletion or a discontinuation
    statement, or for no statement, is not a stated period: the calibrator's no-date table is
    used, and such readings are counted.
  - A predictive answer with `P(E_end90)` below `P(E_end)` is kept as given, and the number of
    such answers is reported per model and condition.
  - Two rates are reported per model and condition, and they do not overlap: the share of
    answers still invalid after the repair call, and the share of refusals. A sensitivity
    analysis uses only the events that both compared conditions parsed. Its contrast is
    withheld, its counts apart, when it leaves out or rests on 1 to 4 scoreable statements:
    beside the contrast on every scoreable statement it would give the loss difference of
    those few. Where the failed answers of one side, or of both, number 1 to 4, its counts
    are withheld as well, since they would say how many of those few are scoreable.

## 5. Experiments

E1 to E5 are the core of the October study. E6 was kept until its linker gate on 4 October and
was cut on 5 October; E7 is the next in the cut order (section 12). E8 and E9 are not run in
October (owner decision, 1 October). Call counts and costs are in section 9.

### E1. Build OpEst-FDA and describe the issuers (must; no calls)

Build the statement events, clusters and outcomes of section 2.

**Descriptives, computed by a secondary scorer: for the test period only after the evaluator
has written its result file (standing rules), and at any time for the train period.**

- The hold rate of the stated period, `P(E_end)`, conditional on survival to first sight
  (section 2.5), over all dated statements and by statement type.
- The slip distribution: recovery minus `t_end`, a Turnbull estimate by form, by statement
  type and by revision bucket (first, second, third or later statement of a thread). Its
  intervals use the first 1,000 of the 10,000 registered draws, since every draw needs a fit
  of its own. In the tables of the hold rate and of the slip, a further cell is withheld and
  marked where the cells written and the whole would otherwise give back the figure on 1 to
  4 statements.
- The distribution of bracket widths.
- Counts by year, form, statement type and company.

**Intervals.** Percentile bootstrap, 95%, clustered by episode.

**Status.** None of this is in the confirmatory family. Optimistic or calibrated issuers are
both context for E3, and neither is a failure.

**Audit.** 100 outcomes are audited by hand (section 10).

### E2. Literal reading against human labels and the rule reader (must)

**Items.**

- 120 distinct statements, stratified by form, each labelled by both annotators. The owner
  was asked about this size on 1 October and did not object; it stands unless the owner says
  otherwise before registration.
- The frame is the statements on the shortage listing that are Current at first sight, from
  all periods, since a literal reading involves no outcome.
- They are drawn before every other sample except the pilot and the check sets (section 3).
- *Strata.* The form classes of section 2.6, grouped as in the guide's allocation table. A
  statement that carries a distractor date beside its target (any class but discontinuation)
  leaves the stratum of its form: for the stratum of dated targets beside a distractor date
  when its class is dated, and for the distractor-only stratum otherwise. The *month-and-year
  stratum* is therefore the month-and-year statements with no distractor date.
- The allocation per stratum, as drawn (in brackets, the items dated 2023 or later): month and
  year 12 (4); month with no year 10 (3); part of a month 10 (3); quarter, half or year 10 (3);
  range 10 (3); relative 10 (9); exact day 10 (3); TBD or unknown 12 (4); vague 3 (1); undated
  5 (2); silent 10 (3); distractor only 6 (2); dated target beside a distractor date 6 (2);
  discontinuation 6 (2). Every stratum fills its quota: 120 items, 44 of them dated 2023 or
  later and 108 outside the month-and-year stratum. One train-period relative statement was left
  to draw under the caps, so that stratum takes nine of its ten items from 2023 on. The quotas
  are fixed in the guide's allocation table before the draw, and a stratum with fewer statements
  than its quota gives all it has. The guide also fixes where a shortfall goes, the share of
  each quota taken from statements dated 2023 or later (one third), and the caps per text
  template and per episode.

**Gold.** The adjudicated labels of the two annotators (section 10). While adjudicating, and
from the two submitted sheets and the adjudication sheet alone, ADJ lists the gold items whose
reading rests on a convention the prompt does not state (guide, D14):
`analysis/coling/out/audit/literal_convention_items.csv`, one column `item_id`, with the
header only when there is none. It is committed with the gold file, its sha256 written in
that commit's message beside the gold's, before any reader output on those items is opened,
and changes afterwards only by
a dated amendment. Every E2 result is also given without these items and without the items
the adjudication marked as a gap of the guide; the registered family is the one on every gold
item.

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
run (section 8). A model that is dropped under section 9 or section 12 after its E2 or E5
runs are complete is still scored there.

**Metrics.** See section 7.1. Results are reported by form, and weighted by event and by
template, as section 7.1 defines the two weights. In the literal task "by form" means by
stratum of the guide's allocation table, the fourteen rows the sample is drawn on.

**Test (a secondary family with its own error control, separate from H1 to H3).**

- For each primary model, one exact McNemar test compares the model (`literal-v1`) with the
  rule reader, pooled over the items outside the month-and-year stratum. A month-and-year
  statement that carries a distractor date is in the stratum of dated targets beside a
  distractor date, so it is in the test.
- A reading is correct when its statement type is the gold one and either the reading and the
  gold both abstain or the IoU of their intervals is at least 0.5.
- Holm's correction runs over the two tests at 0.05.
- Per-form results are descriptive.
- *Letter reading.* For each primary, the difference between its letter accuracy and the rule
  reader's (section 7.1), over all gold letter items pooled without weights, with its 90% and
  95% percentile intervals over episodes. It is read by the rule of section 13 and is not a
  third test of the family.

**Positive result.**

- Rules roughly equal the models on month-and-year text.
- The models lead by at least 0.15 IoU on the part-of-month, no-year and range strata (the
  relative stratum is reported beside them), and on the stratum of dated targets beside a
  distractor date together with the distractor-only items whose gold gives an interval.
- False commitment exceeds 5% for at least one model, over the gold-ABSTAIN items of the
  TBD-or-unknown and silent strata; the rate over every gold-ABSTAIN item of the sample is
  reported beside it.

These three marks are descriptions. None is a test, and none decides the first sentence of
section 13: on the at most 22 gold-ABSTAIN items of the two strata, two false commitments pass
the third (one, if fewer than 20 of the items are gold-ABSTAIN).

**Negative result.** Neither McNemar test holds. The paper gives the differences between the
models and the rule reader with their intervals, says that none was detected, and does not
write that literal reading is solved. Its weight moves to E3.

### E3. Predictive reading against outcomes (must)

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
    estimates, and the prompt says so. A form with no stated end (TBD, silent) has no shares,
    and its rows show them as not applicable; its median is that of the cell when the cell
    holds at least 100 statements, else that of the form. The median is that of the time to
    recovery capped at 365 days: a median above 365 is shown as 365, and as not applicable
    when the follow-up of the row's statements stops before day 365. The table names the first
    and the last statement date behind it. The entry's own form and revision bucket are
    named under the table.
  - For the dev runs of the H3 selection the table comes from the fit split alone; for test
    runs, from the whole train period (fit and dev).
  - The examples are drawn by the seeded rule, stratified by form, from fit statements outside
    the earlier samples (section 3): a ranked pool of 50, of which the first ten resolved
    statements in rank order are shown, the same ten in the dev and the test runs. A statement
    is resolved when its displayed presentation recovered or was discontinued, or when it is
    censored 365 days or more after its date. An example shown as "not recovered within 365 days" must
    have a lower bound at least 365 days after its date.
- **(c) Literal reading plus calibrator.** The model's literal reading (`literal-v1`, run on
  the E3 items) is passed through the fixed empirical slip calibrator (section 8).

**Primaries only.**

- 20 samples at temperature 1 of condition (a) on a 300-item subset. For each item, the sampled
  quantiles are the empirical quantiles (0.1, 0.5, 0.8, 0.9, 0.95) of the 20 sampled medians.
  They are compared with the verbalised quantiles of the temperature-0 answer by pinball loss
  and by coverage of the 80% interval. A sample that fails to parse is left out and counted,
  and the quantiles are those of the parsed medians; an item with no parsed sample takes the
  base-rate quantiles.
- 3 prompt paraphrases of (b) on a 200-item subset, to measure prompt variance.
- The secondary item lists (TBD, silent and stale at issue; section 3) under conditions (a),
  (b) and (c).
- For a primary whose probe beat the base rate (E4), the figures of these three analyses that
  are scored against outcomes are given again on the statements dated after its cutoff.

Subsets are drawn from the eligible list by the seeded rule, stratified by statement year.

**Baselines.** Section 8.

**Metrics.** Section 7.2.

**Confirmatory family.** Section 6.

**Descriptive decomposition.** For each model, on the scoreable events, with the loss taken as
the primary Brier (section 7.2):

- the text's content value: loss(base rate by listing age) − loss(rule reading + calibrator),
  with the same difference from the structured-only GBM beside it;
- the reading loss: loss(model reading + calibrator) − loss(rule reading + calibrator);
- the trust loss: loss(condition a) − loss(model reading + calibrator).

The rule reading is the reference reading (section 2.5), so "rule reading plus calibrator" is
both the reference of this decomposition and the "rules plus slip" baseline of section 8.
For a primary, the decomposition, the overconfidence criterion (section 13), H2 on the
month-and-year form, the H3 contrast per condition, the outcome variants, the delayed-entry
analysis, the company clusters and the metrics of section 7.2 use the item set that the E4
probe fixed for that primary. The contrasts between model-free predictors use every eligible
statement.

**Secondaries (no multiplicity claim).**

- Every metric for all eight models and all conditions.
- The H1 and H2 contrasts for the six secondary models, and the H3 contrast for each of their
  three conditions (they have no dev runs, so no `m-best`).
- For each primary: `Δ_GBM`, and the H3 contrast for each of the three conditions (section 6).
- Post-cutoff slices.
- By statement type. A next-delivery statement gives a period for a delivery, and its horizon
  events still ask whether supply was back (section 2.5). For each primary, on the item set
  its probe fixed, a secondary scorer repeats, on the recovery statements and on the next-delivery
  statements apart (the type of the frozen rule reading): the H1, H2 and H3 contrasts and
  `Δ_GBM`; the primary loss and the calibration in the large of the three conditions and of
  the base rate; and the overconfidence criterion (section 13). The eligible list holds 1,891
  recovery statements in 101 episodes and 702 next-delivery statements in 67. Each quantity
  comes with its 95% percentile interval by episode and the two scenarios of section 7.2.
  Each contrast also comes with the difference between the two types (next delivery minus
  recovery) and its 95% percentile interval over 10,000 draws of the episodes of the item set,
  both types taken from each draw; a draw with no scoreable statement of one type is left
  out. A type with fewer than 50 scoreable statements in an item set is reported by its
  counts alone. The verdict of each test is the registered one on both types together. Where
  a contrast has opposite signs in the two types, or the overconfidence criterion holds on
  the item set and not on its recovery statements, the sentence that states the result says
  so. The two types differ in certainty class and in form, so a difference is not read as an
  effect of the type alone. The descriptives of E1 give the hold rate and the slip
  distribution by statement type.
- The recovery definition A (FDA resolved).
- The outcome over all covered presentations, and over any covered presentation.
- The two scenarios for the undetermined horizon events (section 7.2).
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
  is one-sided at 0.05, not adjusted, with the resampling and the p-value of section 6, on
  the probe statements whose time to recovery is not right-censored before the cap. With
  fewer than two episodes left the switch is undecided, and the model's three tests are not
  evaluable. The figures of a probe over 1 to 4 targets are withheld; its verdict is given.
- *Rule.* A model that beats the base rate is excluded from outcome claims on events dated before
  its cutoff.
- *For a primary model,* its three confirmatory tests are then evaluated on its post-cutoff slice
  instead of on the full test set. This switch is decided by the probe alone, before any H test
  is computed, and the family keeps six tests.
- *A switched primary with a small slice.* If that slice holds fewer than 50 scoreable
  statements, the model's three tests are reported as not evaluable. They stay in the family of
  six and count as not rejected. Nothing that uses the primary's item set is then computed
  for it: the overconfidence criterion (section 13) has no reading, although its first part
  uses no scoreable set, and the paper says so with the reason. The same holds when the
  switch is undecided or the model has no slice.
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

**Negative result.** Heavy memorisation, which confines the outcome claims to the post-cutoff
slices. That is reportable.

### E5. Minimal pairs from attested forms (must, reduced)

**Items.**

- About 800 items from about 100 real seeds. The seeds are stratified by form and drawn in the
  order of section 3: after the samples of section 10, the in-context examples and the dev
  prompt items, and excluding them. The seeds are train-period statements, except those of
  the relative form, which are dated 2023-01-01 or later (section 3); their pairs wait for F1.
- Names are fictitious. The gold of an unedited seed is the frozen rule reading of its
  statement; the gold of an edit follows from it by construction, and the rule reader is run
  on every item as a cross-check. No edit has the whole text of a statement of the labelling
  samples, the in-context pool, the dev prompt items or the guide's Appendix A.

**Factors, varied one at a time from the seed.**

- Certainty marker, attested only: estimated, expected, anticipated, TBD, "no estimated release
  date", "as it is released".
- Surface form: the same period in another writing that a train-period notice uses for the
  time of a delivery or a recovery.
- Granularity: early, mid or late, month ranges, "timeframe", quarters.
- Stale against fresh.
- Distractor date: depletion, "available until", expiry.
- Silent (no date given).

**Readers.** Seven models (all but gemini-3.8-flash), with `literal-v1`.

**Target.** The literal output should not change when the meaning does not, and should change
correctly when it does. A reading of an edited item is an *error* when it is not correct by the
E2 rule, or, for the certainty-marker factor, when its certainty class is wrong, or, for the
stale factor, when its stale flag is wrong. A reading of an unedited seed item is held to the
criterion of the factor it is compared with: it is an error when it is not correct by the E2
rule; in the contrast of the certainty-marker factor, also when its certainty class is wrong;
in the contrast of the stale factor, also when its stale flag is wrong.

**Test.**

- A logistic GEE of error on factor and model with their interaction, clustered by seed
  (independence working correlation, robust variance). The model has a cell for every factor
  and reader, so a reader's contrasts and their robust variances are those of that reader's
  rows alone. Each unedited seed item enters three times for each reader, once under each of
  the three criteria above, in the cluster of its seed; the contrast of a factor is against
  the seed rows under that factor's criterion.
- For each primary and each of the six factors, one test of "no effect of the factor on the
  error rate": the contrast between the items edited on that factor and the unedited seed
  items, which are among the items every reader gets. Holm's correction runs over the 12 tests
  at 0.05, as a secondary family of its own.
- *Fallback.* The robust variance cannot be computed when a cell of factor by a primary has an
  error rate of 0 or 1, when the fit of a primary does not converge, or when a contrast of a
  primary has no positive variance. All twelve tests then come from a cluster bootstrap over
  seeds (10,000 draws, seed 20261001) of the difference `d` between the two error rates
  (edited minus unedited). Its p-value is two-sided on the centred draws,
  `(1 + #{|d* − d| >= |d|}) / (B + 1)`, with `d*` the same difference in a draw of seeds; a
  draw with no item on one side is left out. The cells of the other five models never decide
  the procedure of the twelve; such a model has no Wald test where its own cell is flat, and
  its bootstrap contrast is given as a description. A contrast whose edited items, or whose
  unedited items, lie on fewer than two seeds is not evaluable; it stays in the family of
  twelve with p = 1.
- *Size of the fallback.* Under no effect of any factor, on the item file's own layout of
  seeds and factors and with synthetic errors (a run that is not in the committed output),
  the centred p-value gave a Holm familywise error of 0.2% to 5.8%, where the percentile
  p-value of the draft's kind gave 3.1% to 10.1%. The centred p-value is conservative at low
  error rates: with no error on the unedited items it needs about nine erring seeds, as the
  exact sign test does. The percentile p-value is reported beside it and enters no rule.
- 100 items are audited by hand (section 10).

The two authors' predictive readings of 100 pairs, in the draft, are cut for October.

**Positive result.** A test of a standing factor holds for a named primary, with the higher
error rate on the edited items. Whether it counts for the first sentence of section 13 is
decided by the standing part of the registered pattern there, which says which factors are
letter and which are standing. A letter-factor test that holds is reported in the same way.
Error rates by level stand beside each test, so TBD is reported on its own items.

**Negative result.** No test of a standing factor holds for a primary with the higher error
rate on the edited items. The paper gives the twelve contrasts with their intervals. If no test
of a standing factor holds in either direction, it says that no effect of an edit on the
standing was detected, and does not read that as invariance; a test that holds with the lower
error rate on the edited items is reported as that family's result (section 13).
The pairs become a robustness check.

### E6. Estimative terms at the FAA Command Center (should; gated on 4 October)

E6 stayed in the October study until its linker gate (owner decision, 1 October). It was first
in the cut order (section 12), to be cut if the gate was not passed on 4 October. No link was
checked by that day, and E6 was cut on 5 October (owner decision). The text below describes
E6 as it was built; under Plan B (section 12) it returns with its own amendment.

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
checked links correct. A1 and A2 check the links on sheets drawn with seed 20261001; a link
checked by both is correct only when both say so, and "unclear" is not correct. The rule is on
the share of all checked links, with no further minimum per term. The owner fixed this rule on
1 October, before any verdict was given.

**What "extended" means for a route** (owner decision, 1 October, before the gate sheets went
out). A route is extended when an advisory of the same TMI ID and name moves its end, or when
an advisory of the same name carries it on at its stated end under another TMI ID. The stricter
reading, the same TMI ID only, is reported as a sensitivity analysis. The wider reading was
drafted after the development months had been linked under the stricter one, where 2 of the 24
statements with the highest term were extended against 16 under the wider reading; this is
disclosed in the paper.

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

**Status.** Secondary and descriptive; nothing in E6 enters the confirmatory family.

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
  reference-reading check whose rule reading the annotators confirmed.
- The error classes are fixed at F1, before any test call: in the scorer of E7 if it exists
  by then, and otherwise in the text of F1.
- **Positive result.** Named error classes carry most of the cost.
- **Negative result.** Reading errors are cheap next to the trust loss, which is in line with
  the claim of section 1.

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

- *Equivalence.* It is declared when the registered test rejects, each at 0.05 one-sided, a
  difference of +0.02 Brier and a difference of −0.02 (the rule is under "Intervals", below).
  This is part of the H2 reading, but not a separate test in the family.
- *Caveat.* The stated period that defines the horizon events is the rule reading itself
  (section 2.5), which favours the rules: a model reading that is right where the rule is wrong
  is scored against the rule's horizon. The accuracy of the rule reading on the 100-statement
  check (the share without a confirmed error, section 10) is reported beside H2, and H2 is
  also reported on the month-and-year form alone, where the rule reading is least in doubt.

**H3: value of the text** (two-sided). `Δ = loss(base rate by listing age) − loss(m-best) ≠ 0`.

- *Comparator.* The base-rate predictor of section 8, refitted on fit and dev. It uses the
  Initial Posting Date and nothing of the statement text. It is fixed here, at registration,
  and is not selected again in F1. The draft's comparator was the structured-only GBM
  ("Changes from the 29 September draft", item 36).
- *Why this one.* Of the study's two predictors that read no text, the base rate has the lower
  primary loss on the scoreable dev statements, which is the rule that selects `m-best`: 0.195
  against 0.240 for the structured-only GBM on the 644 scoreable dev statements, a difference of
  0.045 (95% interval 0.025 to 0.070). Under the two scenarios of section 7.2, over the 1,334
  dated dev statements, it is 0.204 against 0.249 with every undetermined horizon event set to
  no, and 0.263 against 0.286 with every one set to yes (from the power code on the freeze-run
  tables).
  It also had the lower loss in every check made inside the fit split (item 36).
- *What the comparator is given.* Like every predictor, it is read at the two horizons, and
  the stated end comes from the rule reading of the text (section 2.5). H3 therefore measures
  what a reading of the notice adds once the length of the stated period is known. It does not
  measure the value of the stated date itself.
- *Failed answers.* Under conditions (a) and (b) an answer that fails to parse is replaced by
  the base-rate output (section 4), so it adds zero to `Δ`. The number of such answers is
  reported with H3, beside the sensitivity analysis on the events that both sides parsed.
- `m-best` is the one of `m`'s three conditions (a, b, c) with the lowest primary loss on the
  scoreable dev statements. Dev losses are compared at six decimals, as the selection file
  records them; a tie goes to the earlier of (a), (b), (c).
- The selection is recorded in F1, before any test call, with the dev loss of all three
  conditions and the dev outcome mix. The dev runs read the 644 scoreable dev statements
  only, so the two scenarios of section 7.2 equal the loss there; the 690 dated dev statements
  that are not read are counted beside it. The dev split is dominated by
  "no" answers (section 3), which favours the condition that gives the lowest probabilities.
  The H3 contrast is also reported with each of the three conditions in place of `m-best`, as
  secondaries.
- *The structured-only GBM.* `Δ_GBM = loss(structured-only GBM) − loss(m-best)`, the H3 of the
  draft, is a registered secondary outside the family. It is computed on the same statements
  and the same bootstrap draws as `Δ`, and is reported beside H3, with its 95% interval, in
  every table that shows H3.
- *Reading.*
  - H3 holds in favour of the text for `m` when its Holm-adjusted p is below 0.05 and `Δ > 0`.
    The models are shown structured fields that the base rate does not use (section 2.3), so
    the paper then writes that the text carries value beyond the structured fields only if
    the 95% interval of `Δ_GBM` also lies above zero (an interval that is withheld does not).
    This second condition is not a test of
    the family: it can only withhold a claim. When it fails, the paper says that `m-best` beat
    the base rate by listing age and did not beat the structured-only GBM, and makes no claim
    about the structured fields.
  - H3 holds in favour of the base rate when its Holm-adjusted p is below 0.05 and `Δ < 0`.
    This needs no second condition.
  - Otherwise H3 is null for `m`. A null is reported with its 95% interval and the minimum
    detectable `Δ` below, with the power that the registered test has at it ("Power"), and
    is not read as equivalence.
- *Other registered secondaries* (no multiplicity claim), each computed in the same way: the
  text-trained GBM, and rules plus slip, each against the base rate and against the
  structured-only GBM; and the structured-only GBM against the base rate.

**Resampling.** Shortage episodes are the resampling unit. For a contrast, `S_g` is the sum of
the paired loss differences (comparator minus tested) over the scoreable statements of episode
`g`, `n_g` their number, `G` the number of episodes and `N = Σ n_g`. Two sets of resamples are
drawn with seed 20261001, anew for each number of episodes `G`, so that contrasts over the
same episodes share them:

- *bootstrap draws:* `B` = 10,000 draws of `G` episodes with replacement, the same draw for
  both predictors;
- *sign draws:* 10,000 vectors of one sign per episode, plus or minus with equal chance; every
  one of the `2^G` vectors when there are at most 13 episodes.

**Test statistic.** The studentised contrast: `Δ = Σ S_g / N`,
`se² = G / (G − 1) × Σ (S_g − Δ n_g)² / N²` and `t = Δ / se`.

- A bootstrap draw that takes episode `g` `w_g` times gives `N* = Σ w_g n_g`,
  `Δ* = Σ w_g S_g / N*`, `se*² = G / (G − 1) × Σ w_g (S_g − Δ* n_g)² / N*²` and
  `t* = (Δ* − Δ) / se*`.
- A sign draw `s` gives `Δ° = Σ s_g S_g / N`, `se°² = G / (G − 1) × Σ (s_g S_g − Δ° n_g)² / N²`
  and `t° = Δ° / se°`.
- A statistic whose standard error is zero, observed or drawn, counts as plus or minus
  infinity, by the sign of its numerator, and as zero when the numerator is zero too. Zero
  here is anything up to 1e-12 times the largest absolute `S_g` (at least 1e-12).

**p-values.** Each one-sided p-value is the larger of two: that of the bootstrap-t, which
corrects for skewed differences, and that of the studentised sign-flip test, which is exact
when the episode sums are symmetric about zero. A test rejects only when both reject.

- `p_up = max((1 + #{t* >= t}) / (B + 1), (1 + #{t° >= t}) / (B + 1))`.
- `p_low = max((1 + #{t* <= t}) / (B + 1), (1 + #{t° <= t}) / (B + 1))`.
- When every sign vector is used, the sign-flip term is the share of the vectors itself.
- A sign-flip statistic that falls short of `t` by less than 1e-9 times the largest finite
  `|t°|` counts as reaching it, on either side.
- One-sided (H1): `p_up`. Two-sided (H2, H3): `min(1, 2 × min(p_up, p_low))`.
- A value `Δ0` other than zero is tested in the same way on the sums `S_g − Δ0 n_g`.

**Why this test.** It was chosen on a simulation run before registration, with no model called
and no test-period outcome read (`analysis/coling/size_check.py`, `out/size_check.json`; hashes
in section 17). Eleven procedures were tried at the episode sizes of the eligible list (115
episodes, the ten largest holding 39% of the statements), of its thinning to the registered
1,903 scoreable statements, and of the scoreable dev statements (74 episodes). The paired
differences were built from the dev losses of the three proxy pairs of the power estimate: as
whole dev episodes, and from a random-effects model with the dev distribution, also at half
and at twice the dev correlation within an episode, with heavy-tailed episode effects, with
added extremes, and with differences that are zero outside a random 15% of the episodes. A
tenth way of building them, whole dev episodes of any size, is a stress case and is left out
of the ranges below: with it the registered test rejects in 0.8% to 0.9% two-sided and in
1.5% one-sided, and the percentile p-values in 1.4% and 3.0%. At the per-test level of Holm's
first step, 0.05/6 = 0.83%, and at the eligible sizes:

- the percentile p-values of the draft reject a true null in 0.2% to 1.6% of data sets
  two-sided on the H2 and H3 proxies (2.5% with the zeros), and in 0.5% to 2.5% one-sided on
  the H1 proxy (2.7% with the zeros, 3.1% with heavy-tailed episode effects). Holm's
  familywise error is 5.5% to 9.2%, and 2.8% to 4.9% if the two models' losses were the same;
- the registered test rejects in 0.1% to 1.0% two-sided on the H2 and H3 proxies, zeros
  included, and in 0.5% to 1.5% one-sided on the H1 proxy (1.6% with the zeros, 2.2% with
  heavy-tailed episode effects). Holm's familywise error is 3.9% to 6.0%, and 1.9% to 3.1%
  if the two models' losses were the same.

Holm's familywise error is simulated with whole dev episodes and with the random-effects
model, the two models' losses being independent or half shared. At the dev sizes the upper
ends of these ranges are 2.0% (3.0% with the zeros) and 3.1%, with Holm's familywise error at
5.9% to 10.1%, for the percentile p-values, and 1.1%, 1.8% and 3.6% to 5.8% for the
registered test. No procedure tried holds
0.83% for the one-sided test when the differences are skewed against it as those of the H1
proxy are (skewness −1.9: a hedged forecast gains a little on most statements and loses much
on a few); the registered test comes nearest, and the paper reports H1 with these rates beside
it. Neither part does as well alone: the bootstrap-t rejects in up to 3.5% when most
differences are zero, and the sign-flip test in up to 2.5% under that skew (2.8% with
heavy-tailed episode effects).

**Intervals.** Every confirmatory contrast, and `Δ_GBM`, carries the interval of the values
`Δ0` that the registered test does not reject, at level `1 − a`. So do the same contrasts of
the six secondary models (H1, H2, and H3 for each condition), which are outside the family and
are reported with the percentile interval beside it. The lower end is searched
with `p_up` and the upper end with `p_low`, each against `a/2`: a bisection between `Δ` and
the value 50 standard errors away, in 60 halvings, whose result is a value not rejected next
to one that is. It is the last value not rejected whenever the p-value falls steadily with
the distance from `Δ`; where the p-value rises again (below), the search ends on one of the
changes of verdict. An end is unbounded when the value 50 standard errors away is not
rejected; the test may still reject values further away, and the interval does not show
them. When
the standard error is zero, an end is `Δ` itself if a value one unit away (or `|Δ|` away, if
that is more) is rejected, and unbounded otherwise. The level is 95%. H2 also carries its 90%
interval.

*Equivalence* is declared when `p_low` at `Δ0 = 0.02` and `p_up` at `Δ0 = −0.02` are both
below 0.05. That is the rule. As a rule of thumb it says that the 90% interval lies strictly
inside ±0.02, but the two can part, in two ways.

- The sign-flip part of the p-value need not fall steadily as `Δ0` moves away from `Δ`. In
  searches over synthetic data this happened only when a few episodes held most of the
  statements between them (the smallest cases found: one episode with 55% beside another
  with 32%, two with 40% each, three with 30% each), and never at episode sizes like those
  of the eligible list.
- An end is called unbounded on the value 50 standard errors away alone. When fewer than
  about three episodes (four for a 95% end) hold nearly all of the difference between the
  two losses, the bootstrap draws that take none of them give statistics that are finite
  and beyond 50. The interval then has no end on that side, at any episode sizes, although
  the test rejects values further away, and the rule declares equivalence when the margin
  is among them.

The paper reports the interval and reads the rule. The ends of the 95% interval, which the
reading of `Δ_GBM` uses, behave in the same way.

Two properties of these intervals follow from the test and not from the data. When the losses
of the two sides differ in very few episodes, the bootstrap draws that take none of those
episodes cannot reject, and the interval is unbounded on one side: about three differing
episodes are needed for an end at 90% and four at 95%, and more when their sums are of very
unlike sizes. With five or fewer episodes in all, every 95% interval is unbounded on both
sides.

In the simulation, at the eligible sizes,
the 95% interval covers the true value in 94.1% to 99.1% of data sets (the percentile interval
of the draft: 91.1% to 98.7%), and the one-sided error at 0.05 that governs the equivalence
reading is 3.5% to 6.1% on the H2 proxy (percentile: 4.0% to 8.4%). At the dev sizes these are
94.6% to 97.4% (90.3% to 96.2%) and 3.6% to 6.6% (4.5% to 9.7%). The losses of single
predictors and every other secondary keep 95% percentile intervals from the bootstrap draws
(a percentile of `B` draws is taken by linear interpolation between the two order statistics
around position `(B − 1) q`, the smallest draw being at position 0), as descriptions; where
such a contrast also carries a p-value,
it is that of the registered test, and the two can disagree. One secondary reads a verdict
from such intervals: the overconfidence criterion (section 13); there an end on zero does
not exclude zero, and with a single episode there is no interval and no part is met. The
two scenarios of section 7.2 are reported beside every confirmatory estimate.

**Sensitivity.** Reported beside every confirmatory p-value, and never used in Holm's rule:

- the percentile p-values of the draft, from the bootstrap distribution of `Δ*`: one-sided
  `(1 + #{Δ* <= 0}) / (B + 1)`; two-sided `min(1, 2 × min((1 + #{Δ* <= 0}) / (B + 1),
  (1 + #{Δ* >= 0}) / (B + 1)))`; with the 95% percentile interval. `Δ*` is the mean of the
  paired differences over the drawn episodes; a draw whose differences sum to zero counts on
  both sides, and a sum within 1e-12 times the largest absolute episode sum (at least 1e-12)
  of zero is a zero;
- the two parts of the registered p-value, each on its own (two-sided, the sign-flip part
  compares `|t°|` with `|t|`);
- the cluster sign-flip test on the episode sums of the paired differences, on the same sign
  draws: one-sided for H1, and two-sided on the absolute sum for H2 and H3.

For H2, where the two sides have the same loss wherever the model's reading is the rule's, the
paper also reports the number of statements and of episodes on which the two losses differ,
and how many of those episodes have a positive and a negative sum. A statement differs, and
an episode sum has a sign, when it is further from zero than 1e-12 times the largest absolute
episode sum (at least 1e-12); an episode whose differing statements cancel is counted apart.
When the losses differ in
few episodes and mostly in one direction, the registered test does not hold its level either.
In a further run that is not in the committed output (two generators of a second simulation,
at the eligible sizes) it rejected a true null at 0.83% in 2.4% of data sets, and in 13% when
nearly all the differences had one sign; the procedures that held their level there had no
power. The paper says so beside the H2 result.

**Power.**

- The minimum detectable `Δ` for each hypothesis, at 80% power under the Holm worst case of
  0.05/6, at the registered 1,903 scoreable statements in 106 episodes: 0.066 for H1, 0.016
  for H2 and 0.028 for H3 (0.076, 0.020 and 0.031 from episodes alone). The dev outcome mix
  behind them is 486 no/no, 82 no/yes and 76 yes/yes, on 644 scoreable dev statements in 74
  episodes.
- These figures use normal critical values. The simulation above gives the power of the
  registered test at them, on the eligible list thinned to the registered 1,903 scoreable
  statements (109 episodes there), for a true difference above and below zero. With
  differences drawn from the random-effects model it is 61% (H1), 69% and 73% (H2), and 66%
  and 73% (H3), where the percentile p-values have 75%, 80% and 82%, and 78% and 84%. With
  whole dev episodes, under which the estimates of H1 and H2 vary more than the power code
  assumes, it is 44% (H1), 43% and 49% (H2), and 70% and 71% (H3), where the percentile
  p-values have 54%, 44% and 55%, and 77% and 85%. The registered test therefore detects
  with 80% power only a larger difference than the figures above. How much larger was
  estimated in a run that is not in the committed output: about 1.3 times the H1 figure and
  1.1 to 1.2 times those of H2 and H3 under the random-effects model; under whole dev
  episodes 80% is not reached at 1.3 times for H1 and H2.
- Each hypothesis has a language model on one side, and no paid call precedes registration. The
  estimate therefore uses one pair of model-free predictors per hypothesis as a proxy: the
  paired loss variance of the pair on the scoreable dev statements, with its inflation from
  clustering, scaled to the registered number of scoreable test statements and to the
  size-weighted number of statements per episode of the eligible list, scaled by the
  scoreable share. The number of episodes enters only a second figure, "from episodes alone",
  printed beside it. Where a registered number is a lower bound, the bound is used.
- The pairs, as the power code holds them, each with the comparator first and with its contrast
  on the scoreable dev statements: for H1, the stated date at face value against rules plus slip
  (dev `Δ` 0.605); for H2, rules plus slip against the base-rate predictor (0.018); for H3, the
  base-rate predictor against the text-trained GBM (−0.021). The pairs of H1 and H2 were
  fixed in the power code before it read a dev outcome: face value against rules plus slip
  (H1); rules plus slip against the base-rate predictor (H2). The pair of H3 changed with its
  comparator, after the dev losses had been seen ("Changes from the 29 September draft",
  item 36): the base-rate predictor against the text-trained GBM. Rules plus slip could also
  stand for `m-best`; that is the pair of H2, so the value of H2 is the value of H3 under that
  stand-in. The text-trained GBM is taken because it gives the larger minimum detectable `Δ`.
- The values are indicative, and the dev outcome mix is stated beside them. Low power does not
  stop the study. It is written into the paper.

**Confirmatory runs.** These must all finish before any evaluation:

- E3 conditions (a), (b) and (c) for both primaries on every eligible event;
- the E4 probe for both primaries;
- the test predictions of every model-free predictor of section 8 on the same events, after the
  refit on fit and dev.

If a primary's confirmatory runs cannot be completed on its registered route, its three tests
are reported as not evaluable and stay in the family. No other model takes its place without an
amendment made before any evaluation. The evaluator takes this as a declaration on its command
line, recorded in the result file, and refuses when both primaries are declared. A secondary
scorer takes the same declaration, with the same reason, on its own command line: it refuses
one that the evaluator's result file does not record, and one that the file records and its
command line does not give. A contrast over fewer than two episodes is not evaluable.

**Evaluator.** The registered evaluator (`evaluate.py`; **TBD-at-F1**: its hash) accepts a run
stored in several parts and refuses:

- a run that is partial;
- a run whose stored model id or serving provider differs from the registered route (the
  harness stores both with every call and stops at a mismatch);
- a run whose item set differs from its registered item list (the eligible list or its probe
  subset; the scoreable dev list for the dev runs);
- a run that showed another track record than the one of its phase;
- a plan of runs that names a file in a sealed folder;
- a start without the sha256 of the sealed file, of the eligible list, of the model-free test
  predictions and of each primary's selection file;
- item sets that differ by 1 to 4 statements (the eligible list and a post-cutoff slice, or
  the slices of the two primaries): the same figures on both would give those few back. On
  the registered list this cannot arise: the slices hold 1,524 and 591 of its 2,593
  statements, and 1,121 and 411 of its 1,903 scoreable ones. The refusal counts statements,
  which are known from their dates before the sealed file is read.

It computes the six tests and Holm's rule; the secondaries of this section; the E4 probe rule;
and, of section 5, the E3 decomposition, the overconfidence criterion, the post-cutoff slices,
definition A, the outcome over all and over any covered presentation, the delayed-entry
analysis, the resampling by company and the metrics of section 7.2 for the two primaries and
for the model-free predictors. The other registered analyses that need a sealed file are
computed by secondary scorers (standing rules): the descriptives of E1; every contrast and
metric of the six secondary models; the TBD, silent and stale-at-issue lists; the sampled
quantiles and the paraphrases; the 2×2 of E4; the analysis by statement type (section 5, E3);
the fit that leaves out the dominant company
and the full-follow-up refit; the sensitivity analyses of the recovery rule (section 2.5:
definition BL, leaving the list, and the Date Discontinued cell); selective prediction; the
mean of `P(E_end)` minus the Turnbull share recovered by the stated end, beside the
overconfidence criterion (section 13); and E7.
E2 and E5 read no sealed file; the scorer of each is named, with its hash, in F1 or in a
dated amendment pushed before it is first run on model readings. Two figures come from
elsewhere: the accuracy of the rule reading beside H2, from the reference-reading check
(section 10), and the minimum detectable differences beside a null, from the power code at
the gate. E1 to E4 are never cut (section 12), so the scorers of E1's descriptives, of E2 and
of the 2×2 are built before any other. Another secondary analysis that is not computed by
the freeze of numbers (section 12) is named in the paper as not run.

## 7. Metrics

### 7.1 Literal (E2, E5, condition c)

- **Statement-type accuracy.**
- **Interval IoU**, in days.
- **Endpoint error** of the start and end, in days.
- **Abstention** precision, recall and F1. Abstention is correct when the gold reading gives no
  date.
- **False-commitment rate:** the share of gold-ABSTAIN items (abstain reasons `tbd`, `no_date`,
  `vague` and `no_statement`) where the reader outputs a date.
- **Stale-flag** accuracy and F1.
- **Distractor uptake:** among the gold items that carry a distractor date, the share where the
  reader returns an interval with IoU of at least 0.5 with a distractor's interval and below
  0.5 with the gold interval (or the gold abstains). A distractor's interval is its quoted
  words read by the conventions of section 2.5. The answer schema has no distractor field.
- **Certainty-class** accuracy and Cohen's kappa against gold, over the four classes.
- **Letter accuracy:** among the gold items that give an interval and carry no distractor date
  (the *letter items*), the share of readings correct by the E2 rule: the statement type is the
  gold one and the IoU is at least 0.5.

On the letter items, statement-type accuracy, interval IoU, endpoint error and letter accuracy
score the letter; over all items the first three also move with errors of standing. Abstention,
the false-commitment rate, the stale flag, distractor uptake and the certainty class score the
standing (section 1).

For E2, each is reported per stratum of the guide's allocation table; pooled over the sample
without weights; and pooled with each stratum weighted by its statements in the frame
("weighted by event") or by its distinct masked templates in the frame ("weighted by
template"). Inside a stratum every scored item counts the same. The frame is taken without
the statements whose whole text is a phrase the guide quotes (685 statements of the frame, 486
of them silent and 158 TBD; 688 when statements outside the frame are counted too) and
without the statements of the guide's Appendix A; no sample holds one. These weights undo the
allocation across strata and nothing else. Inside a stratum the sample is not proportional to
the frame: at most two items share a masked
template over the pilot, the check sets and the literal sample together, and one third of each
quota is dated 2023 or later. The weighted figures are therefore descriptions of the sample at
the strata's frame sizes, not estimates of a rate over all statements of the frame.

### 7.2 Against outcomes (E3, E4, and E7 if it runs)

- **Primary Brier.** For event `i`, the primary loss is `(BS_i(E_end) + BS_i(E_end90)) / 2`, where
  `BS = (p − y)^2`.
  - The primary analysis uses scoreable events (complete case). Whether an event is scoreable
    depends on its outcome as well as on the captures: an event still seen not recovered after
    both horizons is scoreable, and one whose recovery bracket contains a horizon is not. On
    the train period the scoreable events hold fewer recoveries within 90 days of the stated
    end than the list, and a forecaster who states low probabilities is favoured on such a
    set. On the dev split the Turnbull share recovered within 90 days of the stated end is
    0.446 over the 1,334 dated statements and 0.245 over the 644 scoreable ones (0.122 and
    0.118 by the stated end); always answering no scores 0.182 on the scoreable ones, and the
    base rate by listing age 0.195 (`result_rules_check.py`, section 17).
  - *Two scenarios (all no, all yes):* over every statement of the item set, every
    undetermined horizon event is set to 0, and then to 1. Both results are reported. They are
    two settings and not limits: a loss is greatest when each undetermined event is set
    against the predictor's own probability, and a loss or a contrast can lie outside both.
    Where the change list, the code or a result file says "bounds" of the horizon events,
    these two scenarios are meant.
  - *Reading.* The verdict of a test is that of the registered test on the scoreable events,
    whatever the two scenarios show. When a scenario has the other sign than the estimate, the
    sentence that states the result says so.
- **Brier decomposition** into reliability, resolution and uncertainty (Murphy), with 10
  equal-count bins, for each horizon event. Statements that share a probability count with
  the frequency of the event among all of them, so that the figures do not depend on the
  order of the statements; a forecast of one value has no resolution.
- **Calibration in the large:** the mean of `P(E_end)` minus the observed frequency of `E_end`
  on the scoreable events, and the same for `E_end90`, with 95% intervals by episode bootstrap.
  Over every event of an item set it is also given with every undetermined event counted as
  yes, and then as no. For this quantity, unlike a loss, the two settings are limits: the
  first is its least value and the second its greatest. Beside it stand the same quantities
  for the base rate by listing age on the same events (section 13).
- **Decision loss.** The pinball loss at τ 0.5, 0.8 and 0.95 on the time to recovery.
  - Pinball at the critical fractile τ = c_u / (c_u + c_o) is the expected cost of buffering
    stock until recovery. The three τ are generic cost ratios of 1:1, 4:1 and 19:1.
  - An interval-censored target is scored with the midpoint of its bracket. The loss bounds (the
    minimum and maximum over the bracket) are reported too.
  - A right-censored target beyond the cap is scored at the cap.
  - A target that is right-censored before the cap (follow-up ends before recovery and before
    day 365) has no midpoint. It is left out of the pinball loss, and the number left out is
    reported. The loss bounds include it, with the target at its lower bound and at the cap.
    The draft gave no rule for this case.
- **Coverage** of the 80% interval `[q0.1, q0.9]`, counted on events whose bracket lies wholly
  inside or wholly outside the interval.
- **Probe and 2×2 metrics** (E4): as defined in E4.
- **Selective prediction:** loss against abstention rate, for condition (c) and the rule reader
  only. The predictive answer schema has no abstain option.

## 8. Baselines and conditions

**Freezing.** The code of every model-free component is hashed at registration. Every component
is fitted on the fit split for the dev runs and refitted on fit and dev together for the test
runs; none is selected or tuned on dev. The test predictions of the refitted components are
hashed in F1, before any test call (section 17).

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
  dated statements in the fitting set; otherwise the estimate of the form, when the form holds
  at least 100; otherwise the estimate over all dated forms. Statements that are stale at
  issue are neither counted nor fitted. In the fit split (the dev runs) the three cells of the
  month-and-year form meet the minimum, with 247, 240 and 459 dated statements for the first,
  the second and the third or later statement; no other form holds 100 (the largest, part of a
  month, holds 85), so every other cell uses the estimate over all dated forms (1,163
  statements). In fit and dev together (the test runs) the same three cells meet it, with 309,
  365 and 1,371; part of a month holds 181, so its cells use the estimate of the form; every
  other cell uses the estimate over all dated forms (2,497 statements).
- Given a literal reading with period end `ŝ`: `P(E_end) = F_slip(t_end − ŝ)` and
  `P(E_end90) = F_slip(t_end + 90 − ŝ)`. The quantiles are `ŝ − s` plus the slip quantiles,
  kept within 0 to 365 days.
- When the reading is ABSTAIN, the calibrator falls back to the no-date time-to-recovery
  distribution by listing age.

**Structured-only quantile GBM (a registered secondary of H3).**

- It was the comparator of H3 in the draft. On the train period it lost to the base rate by
  listing age, which uses one of its five features ("Changes from the 29 September draft",
  item 36). It is kept as it was, untuned, and its contrast with `m-best` is reported beside
  H3 (section 6).
- Features: reason for shortage, therapeutic category, time since initial posting, company and
  calendar month. No free text. Status is not a feature: it is constant on at-risk statements.
- It gives the 19 quantiles at 0.05 to 0.95. The CDF is read at each horizon by straight
  lines through (0, 0) and the 19 quantiles, and is never above 0.95 below the cap of 365
  days; at or beyond the cap it continues with the conditional tail of the pooled Turnbull
  estimate.
- Censoring in fitting: an interval-censored fit event is given the midpoint of its bracket. A
  right-censored fit event becomes 10 copies of weight 1/10, placed at the (k − 0.5)/10
  quantiles (k = 1 to 10) of the conditional tail of the pooled Turnbull estimate beyond its
  censoring time, capped at 365 days.
- The settings of the boosting are fixed in the predictor code hashed in section 17 and are
  not tuned on dev. The fit is identical across runs and thread counts on the registered
  environment; pinball boosting is discontinuous at tied targets, so a fit may not reproduce
  bit for bit on another platform, and F1 records the environment with the hash of the
  predictions.

**Text-trained quantile GBM.** TF-IDF on the availability and related text, plus the structured
features. It reads the text without a language model. Its contrasts with the base rate and with
the structured-only GBM (the same learner without the text) are registered secondaries of H3
(section 6).

**Other predictors.**

- **The stated date at face value** (the issuer as forecaster): `P(E_end) = P(E_end90) = 1`, with
  every quantile at `t_end − s`.
- **Base-rate remaining duration** by listing age (the comparator of H3, section 6): a Turnbull curve of time to recovery for
  each bin of the time since initial posting (under 90 days, 90 to 364, 365 to 729, 730 to
  1,094, 1,095 to 1,824, 1,825 or more, and unknown), fitted on dated, TBD and silent
  statements. A bin with fewer than 100 fitting statements uses the pooled curve. The
  fallback of the calibrator for an ABSTAIN reading is the same construction fitted on TBD and
  silent statements only. The base rate uses the Initial Posting Date and nothing of the
  statement text, and nothing in it is tuned.
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
The cap is on spend at list prices, as the harness records it. OpenRouter's fee on buying
credits (5.5% on its standard plan on 1 October) is outside the price of a call and outside the
cap. The rules, which the harness (`read.py`, frozen at F1) enforces:

- *One ledger.* Every paid run uses one output root, and declares its cap in the study ledger
  there before its first call.
- *Caps.* A cap belongs to a run: one model, one template and one condition under one run name
  (a run may be one part of an item list). A run is refused when the caps and recorded spend of
  its model's runs would pass the model's cap in the table below (or the cap a logged amendment has put in
  its place), or those of all runs would
  pass $200. Caps of runs in flight count, not only recorded spend.
- *Before every paid call,* the call is refused if its projected cost would take the run past
  its cap.
- *Registration first.* A paid call is refused unless the registration tag is an ancestor of the
  checkout; a call on a test-period or late-period item also needs the F1 tag (section 17).
- *Completeness.* Whether an item list was read in full is checked on the runs of that line
  alone, named to the harness, because trial, dev and secondary runs share the output root and
  may share a model and condition with a confirmatory run.
- *The run sheet* lists every run with its model, template, item list and cap; the caps of a
  model's runs sum to that model's cap. It is given under "Run sheet" below, at the registered
  counts.

Every call is logged with its tokens and its price.

**Price of a call.** Input tokens × the input price per 1M, plus output tokens (including
reasoning or thinking) × the output price per 1M, at the registered prices of section 4.

**Scope.**

- `gemini-3.8-flash` reads E2 and the E3 conditions on the eligible statements, and nothing
  else beyond its cost trial: no probe, no E5 and no E6.
- The TBD, silent and stale-at-issue secondaries are read by the two primaries only.
- The Late split is not read for outcomes.
- E6 was cut on 5 October (section 12) and is read by no model.

**Calls per model.** `N_E` is the number of eligible statements, `N_S` the number of statements
in the three secondary lists together, and `N_D` the number of scoreable dev statements. At the
freeze they are 2,593, 942 (376 TBD, 550 silent and 16 stale at issue) and 644.

| Item set | Calls | Read by |
|---|---|---|
| E2: 120 items, two templates | 240 | all eight |
| E3: conditions a, b, c on the eligible statements | 3 × `N_E` | all eight |
| E4 probe | 300 | seven (not gemini-3.8-flash) |
| E5: about 800 items | 800 | seven (not gemini-3.8-flash) |
| Cost trial: 20 dev items per template used | 100 (gemini-3.8-flash: 80) | all eight |
| E3 secondaries: conditions a, b, c on the secondary lists | 3 × `N_S` | primaries |
| Dev runs for the H3 selection | 3 × `N_D` | primaries |
| E4 2×2: three further cells on 300 items | 900 | primaries |
| E3 paraphrases: 3 on 200 items | 600 | primaries |
| E3 samples: 20 on 300 items | 6,000 | primaries |

Repair calls (at most one per failed answer) are not in these counts and count against the caps.


| Model | Calls | Cost per call | Estimate | Upper estimate | Cap |
|---|---|---|---|---|---|
| gemini-3.8-flash | 320 + 3 `N_E` = 8,099 | $0.00759 (thinking billed) | $61.45 | $156.88 | $110 |
| grok-4.20 | 1,440 + 3 `N_E` = 9,219 | $0.00168 | $15.51 | $20.93 | $30 |
| deepseek-v3 | 8,940 + 3 (`N_E` + `N_S` + `N_D`) = 21,477 | $0.00041 | $8.82 | $12.21 | $12 |
| llama-3.3-70b | 8,940 + 3 (`N_E` + `N_S` + `N_D`) = 21,477 | $0.00013 | $2.82 | $3.95 | $5 |
| qwen-2.5-7b | 1,440 + 3 `N_E` = 9,219 | $0.00013 | $1.24 | $1.67 | $3 |
| gemma-3-27b | 1,440 + 3 `N_E` = 9,219 | $0.00011 | $0.99 | $1.34 | $3 |
| gpt-oss-20b | 1,440 + 3 `N_E` = 9,219 | $0.00021 (reasoning billed) | $1.98 | $4.23 | $3 |
| gpt-4o-mini | 1,440 + 3 `N_E` = 9,219 | $0.00023 | $2.08 | $2.94 | $3 |
| **All** | 97,148 | | $94.90 | $204.16 | caps $169; reserve $31 |

The calls and both estimates are those of the harness's run sheet at these counts
(`python -m analysis.coling.read --run-sheet`), at the prices of section 4; the cost per call is
the estimate divided by the calls, and every figure is rounded once. A call is
priced from the length of its prompt, rendered on the harness's fixed test item at four
characters to a token (condition (b) with the track record of fit and dev), and from a typical
answer of 70 tokens for a predictive template and 90 for a literal one; for gemini-3.8-flash and
gpt-oss-20b the output also counts the median hidden reasoning of logged calls of the same
model. The upper estimate is the figure the harness checks before a paid call: the prompt length
times 1.25 plus 16 tokens, an answer of twice the typical length, and the 90th percentile of
hidden reasoning.
The median understates the mean of a reasoning model: at the draft's cost of about $0.011 a
call, the 8,099 calls of gemini-3.8-flash come to $89.09. The costs per call of the 29 September
draft (about $0.011, $0.0025, $0.0004 and $0.00015 for the first four rows, and $0.0001 to
$0.00025 for the four small models) are withdrawn. All of these are replaced by the cost trial.

**Check of the caps at the registered counts.** With `N_E` 2,593, `N_S` 942 and `N_D` 644 the
formulas give 8,099 calls for gemini-3.8-flash, 9,219 for grok-4.20 and for each of the four
small models, and 21,477 for each primary: 97,148 calls and an estimate of $94.90 in all,
against caps of $169. The estimate of every model is under its cap. The upper estimate passes
the cap for three models: gemini-3.8-flash ($156.88 against $110), gpt-oss-20b ($4.23 against
$3) and deepseek-v3 ($12.21 against $12). The upper estimates sum to $204.16, above the study
cap of $200. E6, which is cut, would have added 1,200 calls to every model but gemini-3.8-flash:
8,400 calls and $3.37 in all (105,548 calls, $98.27), of which $1.90 for grok-4.20, which would
then stand at $17.41 of its $30; every estimate would stay under its cap, and the upper estimate
of gpt-4o-mini ($3.32 against $3) would pass its cap as well. The harness refuses a call that
would take a run past its cap, so no cap is passed: a model whose spend follows its upper
estimate stops before its runs are complete, and the rules below apply to the projection of the
cost trial.

**Run sheet.** The runs at the registered counts, without E6, as the harness prints them. A line
read by one model is one run; a line over several item lists or cells (the three secondary
lists, the three cells of the 2×2, the three paraphrases) is one run for each, and a run may be
read in parts.

| Run | Template | Item list | Items | Calls per model | Read by |
|---|---|---|---|---|---|
| e2-literal | `literal-v1` | the 120 literal items | 120 | 120 | all eight |
| e2-literal-free | `literal-free-v1` | the 120 literal items | 120 | 120 | all eight |
| e3-a | `predictive-v1` | the eligible list | 2,593 | 2,593 | all eight |
| e3-b | `predictive-track-v1` | the eligible list | 2,593 | 2,593 | all eight |
| e3-c | `literal-v1` | the eligible list | 2,593 | 2,593 | all eight |
| e4-probe | `probe-v1` | the probe subset | 300 | 300 | seven (not gemini-3.8-flash) |
| e5 | `literal-v1` | the minimal pairs | 800 | 800 | seven (not gemini-3.8-flash) |
| trial-literal | `literal-v1` | the first 20 dev prompt items | 20 | 20 | all eight |
| trial-literal-free | `literal-free-v1` | the first 20 dev prompt items | 20 | 20 | all eight |
| trial-a | `predictive-v1` | the first 20 dev prompt items | 20 | 20 | all eight |
| trial-b | `predictive-track-v1` | the first 20 dev prompt items | 20 | 20 | all eight |
| trial-probe | `probe-v1` | the first 20 dev prompt items | 20 | 20 | seven (not gemini-3.8-flash) |
| e3-secondary-a | `predictive-v1` | the three secondary lists | 942 | 942 | primaries |
| e3-secondary-b | `predictive-track-v1` | the three secondary lists | 942 | 942 | primaries |
| e3-secondary-c | `literal-v1` | the three secondary lists | 942 | 942 | primaries |
| dev-a | `predictive-v1` | the scoreable dev statements | 644 | 644 | primaries |
| dev-b | `predictive-track-v1` | the scoreable dev statements | 644 | 644 | primaries |
| dev-c | `literal-v1` | the scoreable dev statements | 644 | 644 | primaries |
| e4-2x2 | `predictive-track-v1` | the 2×2 subset | 300 | 900 | primaries |
| e3-paraphrases | three paraphrases of `predictive-track-v1`, fixed at F1 | the paraphrase subset | 200 | 600 | primaries |
| e3-samples | `predictive-v1` | the 20-sample subset | 300 | 6,000 | primaries |

The cap of each run, in dollars. A model's cap is split over its runs in proportion to their
upper estimates, each share rounded down to $0.0001; the remainder, under one cent, goes to the
model's largest run, which is e3-b for every model, so that the caps of a model's runs sum to
its cap. The cap of a line over several lists or cells is split among them in proportion to
their calls.

| Run | gemini-3.8-flash | grok-4.20 | deepseek-v3 | llama-3.3-70b | qwen-2.5-7b | gemma-3-27b | gpt-oss-20b | gpt-4o-mini |
|---|---|---|---|---|---|---|---|---|
| e2-literal | 1.6264 | 0.3728 | 0.0707 | 0.0296 | 0.0372 | 0.0372 | 0.0390 | 0.0384 |
| e2-literal-free | 1.6030 | 0.2930 | 0.0567 | 0.0239 | 0.0293 | 0.0293 | 0.0380 | 0.0316 |
| e3-a | 33.8762 | 4.2884 | 0.8415 | 0.3579 | 0.4288 | 0.4288 | 0.7921 | 0.4770 |
| e3-b | 36.6666 | 13.7950 | 2.5105 | 1.0302 | 1.3799 | 1.3799 | 0.9055 | 1.2887 |
| e3-c | 35.1457 | 8.0564 | 1.5281 | 0.6397 | 0.8056 | 0.8056 | 0.8428 | 0.8303 |
| e4-probe |  | 0.4300 | 0.0857 | 0.0367 | 0.0430 | 0.0430 | 0.0908 | 0.0495 |
| e5 |  | 2.4856 | 0.4714 | 0.1973 | 0.2485 | 0.2485 | 0.2600 | 0.2561 |
| trial-literal | 0.2710 | 0.0621 | 0.0117 | 0.0049 | 0.0062 | 0.0062 | 0.0065 | 0.0064 |
| trial-literal-free | 0.2671 | 0.0488 | 0.0094 | 0.0039 | 0.0048 | 0.0048 | 0.0063 | 0.0052 |
| trial-a | 0.2612 | 0.0330 | 0.0064 | 0.0027 | 0.0033 | 0.0033 | 0.0061 | 0.0036 |
| trial-b | 0.2828 | 0.1063 | 0.0193 | 0.0079 | 0.0106 | 0.0106 | 0.0069 | 0.0099 |
| trial-probe |  | 0.0286 | 0.0057 | 0.0024 | 0.0028 | 0.0028 | 0.0060 | 0.0033 |
| e3-secondary-a |  |  | 0.3057 | 0.1300 |  |  |  |  |
| e3-secondary-b |  |  | 0.9116 | 0.3738 |  |  |  |  |
| e3-secondary-c |  |  | 0.5551 | 0.2324 |  |  |  |  |
| dev-a |  |  | 0.2090 | 0.0888 |  |  |  |  |
| dev-b |  |  | 0.6232 | 0.2556 |  |  |  |  |
| dev-c |  |  | 0.3795 | 0.1588 |  |  |  |  |
| e4-2x2 |  |  | 0.8709 | 0.3572 |  |  |  |  |
| e3-paraphrases |  |  | 0.5806 | 0.2381 |  |  |  |  |
| e3-samples |  |  | 1.9473 | 0.8282 |  |  |  |  |
| **Sum, the model's cap** | 110.0000 | 30.0000 | 12.0000 | 5.0000 | 3.0000 | 3.0000 | 3.0000 | 3.0000 |

**Cost trial.** After registration and before F1, each model runs 20 dev items per template it
uses. The trial's cost is scaled to the registered call counts and recorded in F1.

**If a projection exceeds a cap or the total**, the following apply in order until the
projection fits:

1. a cap is raised within the reserve, recorded in F1;
2. gemini-3.8-flash is dropped;
3. the cut order of section 12.

**Resuming a run.** A run stopped by its cap or by a provider error is resumed from its cache,
under the same name, and each resumption is recorded in the study ledger. A cap may be raised
within the reserve, or lowered again; every change is logged as an amendment with its reason,
and holds for the model's later runs until another amendment replaces it. An amendment that a
later one replaced is not applied a second time. A run that cannot finish is reported as incomplete.

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
  settles the open points of the pilot and does the availability-string check.
- The adjudicator may develop prompts and read model outputs. On the items of a task still to
  be adjudicated, the adjudicator looks only at aggregates (calls made and remaining,
  parse-failure and repair counts for the whole run, spend) until that task's gold is hashed.
  This limit is the guide's addition.
- If the adjudicator cannot do a task in time, A1 and A2 settle each item together by naming
  the deciding convention. An item they cannot settle that way is left out of the gold, and
  the number of such items is reported.
- Who A1 and A2 are is recorded by the owner outside the repository.

**Blinding.** While they label a statement, A1 and A2 know neither its outcome, nor any later
version of the notice, nor any reader's output on it. In the literal task they see only the
display row as defined in section 2.3; in the reference-reading check, that row and the rule
reading. In the outcome audit they see the capture rows of the audited thread, which for the
train half stop at the train horizon; the train-half sample leaves out every thread that
carries a statement they label and, for the thread of the row they are shown, every statement
that thread carried at any date, with all its presentations.

**Tasks.**

1. **Availability-string check** (the adjudicator, before the freeze run): done on 1 October
   (section 2.2).
2. **Pilot and check set** (the pilot before registration, on 3 to 5 October; the check set
   from 6 October, its gate recorded in amendment F1).
   - 20 train-period items are labelled by A1 and A2 independently under the guide's draft of
     1 October. A meeting of A1, A2 and the adjudicator was to settle every disagreement. The
     pilot left one disagreement and no convention in dispute, so no meeting was held: the
     adjudicator settled the open points from the two sheets (guide, section 4), and the
     guide was revised to v1.
   - A check set of 20 fresh train-period items from the dated forms is then labelled
     independently under v1.
   - *Gate.* Krippendorff's alpha (interval metric) on the month offset of the start, and on the
     month offset of the end, over the check set: both at least 0.6. The share of items with
     identical intervals is reported beside it and is not part of the gate. If fewer than 10
     check items have an interval from both annotators, or the offsets vary too little for
     alpha to be defined, the pilot items are pooled with the check items.
   - One further revision is allowed, with the 20 reserve items that are drawn with the check
     set. A second failure is a hold trigger (section 12).
   - *At registration.* The check sheets went to A1 and A2 on 6 October and were not back when
     the registration was due. By the owner's decision of that day the registration was made
     on time without them. The gate is computed as written here as soon as both sheets are
     in, and its result is recorded in amendment F1. It must pass before the literal task is
     handed out and before any confirmatory call; the cost trials and the dev runs do not
     wait for it. Nothing else in this plan depends on the check set.
   - The pilot may change the guide and the prompt text. It does not change `rules.py`; a
     difference that remains is disclosed.
   - Pilot, check and reserve items stay out of the gold and out of every other sample.
3. **Literal task (E2 gold; 6 to 8 October).** A1 and A2 each label the 120 E2 statements,
   independently.
   - Agreement is reported before adjudication, overall and by form: Krippendorff's alpha on
     the start and end month offsets (day offsets as a secondary), and Cohen's kappa on
     abstention, certainty class and statement type. Intervals resample items: 2,000 draws, seed
     20261001.
   - Disagreements are adjudicated. The gold file is hashed before any model output on those
     items is opened.
4. **Reference-reading check (E3).** 100 eligible test statements are drawn at random from the
   eligible list by the seeded rule. A1 and A2 check the rule reading against the text (guide,
   section 12.2): that it took the target statement, that the statement gives a period, the
   last day of that period, and that the period is not stale; a wrong first day is noted and
   is no error, since E3 uses the last day only. They are blind to outcomes (45 statements
   each, and 10 checked by both).
   - Reported: the share without a confirmed error, with a Wilson 95% interval; the confirmed
     errors by form, by code and by statement year; the agreement on the 10 shared
     statements; and the share whose rule reading is confirmed, whose statements E7 uses
     (`analysis/coling/out/audit_reference/reference_confirmed.csv`).
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
     before the evaluator runs, and only after A1 and A2 have submitted their sheets of the
     literal task, the reference-reading check and the minimal-pair audit. Their sheets exist
     only under the sealed folder.
   - Each auditor also gets planted errors. Their key is scored by code after both sheets are
     in; no auditor opens it.
   - Pass, for each half: at most 2 confirmed errors among its 50 items, that is, at least 95%
     of the audited brackets agree with the auditor's reading of the captures, for B and
     separately for A.
   - A failure fixes the rule, never single items. In the train half the rule is also fixed
     when the same kind of error is confirmed twice with the same cause. For the train half
     that happens before the freeze run: the outcomes are derived again, and the affected items
     and 20 fresh ones are audited again; each of these two sets passes with confirmed errors
     up to 5% of its items, rounded down (1 in 20, none below 20). For the test half the outcomes are derived and sealed
     again, and the new hash is logged as an amendment before the evaluator runs.
6. **Minimal-pair audit.** 100 E5 items: 45 to each annotator and 10 to both, with planted
   errors scored as in the outcome audit. An item has an error when a gold label does not
   follow from the edited text, when the edit changes more than its factor, or when the
   inserted form is not attested in a real notice. Pass: at least 95 of the 100 items are free
   of confirmed errors. Otherwise the generator is fixed and a fresh 100 are audited, with the
   fix logged.
7. **E6 link checks**, had E6 stayed in the study (it was cut on 5 October, section 12): the
   hand check of at least
   150 links that is the linker gate (section 5, E6), by A1 and A2. Its sheets and its
   procedure come with the linker code and E6's amendment, not with the guide.

The draft's E5 predictive readings are cut.

**Estimated load.** **TBD-at-F1**: minutes per person at the rate measured on the check
set, which was not back at registration (task 2 above). The guide's hours table gives the
planning rates written before the pilot: 400 minutes for
each annotator (175 before registration and 225 after) and 190 for the adjudicator, with a
range of 250 to 550 minutes per annotator. The sitting times on the pilot sheets (120 and 300
minutes) and on the train-half audit sheets (300 minutes each) include reading the guide, so
they give no rate. The draft's figure (10 to 12 hours per author, plus reference labels) is
withdrawn. A1 and A2 started on Saturday 3 October and returned the pilot and the train-half
audit on 5 October; the figure must fit the hours they can give.

## 11. Leakage controls

- **Temporal split.** By statement date. Test outcomes are sealed, with their hash recorded at
  registration.
- **Fitting.** Every fitted component and the track-record table come from the train period
  only (the fit split for dev runs; fit and dev for test runs), and the in-context examples
  from the fit split. Train outcomes stop at the train horizon (section 3). No test item
  appears in any prompt's context.
- **Prompt development.** The text changes of 1 October are made before registration, with no
  model call: the two fields added to the entry block and the probe, and the wording of the
  track-record table. Two sentences of the literal prompts were settled from the pilot on
  5 October and entered before registration: how "until X" and "through X" are read
  (`literal-v1`), and the certainty class of a statement that gives no date and has no unknown
  marker (both literal templates). The same day one sentence was added to the track-record
  prompt: a median of 365 means 365 days or more. After registration, development uses dev items only, with at most 3
  variants per prompt, all disclosed. Prompts are selected by parse rate and format compliance,
  and never by an outcome loss. The one outcome-based choice after registration is the selection of
  `m-best` on dev, recorded in F1. The H3 comparator was fixed before registration, after
  train-period losses of the model-free predictors had been seen ("Changes from the
  29 September draft", item 36). From F1 on, a changed prompt takes a new template id.
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
| **Thu 1 Oct** | Done when this revision was written: decisions on scope and rules; capture manifest; availability-rule fix and the availability-string check; harness changes (fields shown, provider pin, study ledger, paid-call guards); form classifier; dataset builder; samplers, sheet generators and agreement code, with draft sheets for the train-half outcome audit; model cutoffs and routes collected at source; FAA collector, parser and linker; FAA collection started; plan and guide revised. Still to do that day: model-free predictors, power code, counts-only code, an independent check of each new module, and OpenReview profiles started for every author. |
| Fri 2 Oct | Pilot, meeting, guide v1, check set, alpha gate. Train-half outcome audit. Freeze run of the corpus builder (the one sealed write). Counts-only code run. Every gate value filled in. Power check. Independent check of every filled number against the code. |
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
confirmed at source. No scoreable count was printed. On 1 October the builder printed the
fourth threshold as worded, at the same cutoff, and it was met on the gate set (section 16).

*The registered gate record* is in two parts.

- From the freeze run of the builder, run with the cutoff confirmed in section 4 (2023-12-31):
  the four counts on the builder's gate set, as distinct statements with the statement-level
  bracket under B. Since 1 October the builder prints the fourth as worded, on observable events
  dated after the cutoff, and keeps the weaker count beside it. The gate set holds 4,328
  presentation-level events. The four counts: 3,134 distinct statements (600 needed); 1,422 of
  them observable under B (250 needed; 2,011 events); 123 shortage episodes (100 needed); and
  834 observable statements dated after 2023-12-31 (150 needed; 1,205 events). The weaker count
  beside the fourth is 1,947 statements dated after 2023-12-31 with a later capture of their
  thread, of 1,948. Under A, with no threshold, 405 statements are observable (590 events), 214
  of them dated after 2023-12-31 (334 events). All four thresholds are met on the gate set.
- From the counts-only code: the same four counts on the E3-eligible statements (section 3),
  which have a stated date by the frozen rule reading, with the primary outcome (the displayed
  presentation, definition B); and the scoreable count. The first and the third are first-sight
  counts and are met: 2,593 eligible statements (600 needed) in 115 episodes (100 needed). The
  second and the fourth come from the counts-only code and are met: 1,275 statements have an
  observable outcome (250 needed), 714 of them dated after 2023-12-31 (150 needed). 1,903
  statements are scoreable (no threshold).

The gate passes only if the thresholds hold in both parts. They do: Gate 1 passed on the
freeze run of 5 October.

**Hold triggers.** Any one of these moves the paper to ARR January 2027, which loses COLING 2027
(October is the last cycle it takes):

- Gate 1 fails on the freeze run;
- the check-set alpha stays below 0.6 after the one allowed revision;
- the registration is not pushed by 3 October, 23:59 AoE (4 October under the one relaxation);
- numbers are not frozen by 6 October, 23:59 AoE (7 October under the one relaxation);
- the UV camera-ready needs more than 1.5 days before 12 October.

**The schedule from 5 October (owner decision, 5 October).** The third trigger above fired:
A1 and A2 started on Saturday 3 October and returned the pilot sheets and the train-half
outcome audit on Monday 5 October, after the deadline and its one relaxation. Nothing was
registered, and no language model had been called. On 5 October the owner first decided to hold
the paper for the ARR cycle of January 2027, and the same evening decided to submit to the
October cycle after all, on a later schedule; the paper was by then registered with ARR for
that cycle. The triggers above are replaced by those below, once, and nothing in the design
changed with the dates. What was done by 5 October stands: the corpus code, the samples, the
pilot (both sheets valid; one disagreement in 20 notices) and the train-half outcome audit
(passed: no confirmed error in 50 items under B, one under A).

| Day | Work |
|---|---|
| **Mon 5 Oct** | Pilot points settled and guide v1; pilot sentences in the prompts; check sheets to A1 and A2; the freeze run of the corpus builder (the one sealed write) and the counts-only code; every gate value filled in. |
| **Tue 6 Oct** | Check-set gate. Independent check of every filled number against the code. **Registration pushed and tagged, by 23:59 AoE.** Then cost trials and dev runs. Literal task starts. |
| Wed 7 Oct | Selection of `m-best`. Refit on fit and dev. **F1 pushed.** Confirmatory runs: E3 conditions a, b, c and the probe, both primaries. Then E2, E5, the 2×2 and the secondaries, in cost order. |
| Thu 8 Oct | Runs finish. Literal task, reference-reading check and minimal-pair audit done; agreement computed; gold hashed. Test-half outcome audit, after the last confirmatory run. |
| **Fri 9 Oct** | Registered evaluator. **Gate 2: submit or hold. All numbers frozen by 23:59 AoE.** |
| 10 to 11 Oct | Write the 8 pages. Limitations, ethics, datasheet, Responsible NLP checklist. Overlap check against the UV text. Independent check of every number and claim. Anonymised supplement. |
| Mon 12 Oct | ARR submission (23:59 AoE). |

*As it fell on 6 October.* The check sheets went out that day and were not back when the
registration was due. The registration was pushed and tagged on time without the check-set
result; the gate is recorded in amendment F1, and the literal task starts when it has passed
(section 10, task 2; change-list item 43).

*Hold triggers from 5 October.* Any one of these moves the paper to ARR January 2027:

- Gate 1 fails on the freeze run;
- the check-set alpha stays below 0.6 after the one allowed revision;
- the registration is not pushed by Tuesday 6 October, 23:59 AoE;
- numbers are not frozen by Friday 9 October, 23:59 AoE.

There is no relaxation of these dates. The secondaries that are not finished by the freeze of
numbers are left out and named as not run. The cut order below applies as written.

**Gate 2 (Friday 9 October; 6 October in the schedule of 1 October).** Submit if:

- every confirmatory run is complete, or its primary has been declared not evaluable
  (section 6, "Confirmatory runs");
- the registered evaluator has run;
- the E2 agreement is computed;
- no hold trigger has fired.

Gate 2 never looks at the sign or significance of any result. A registered negative result is
submitted.

**Cut order.** The first two cuts of the draft's order were taken on 1 October: E8 and E9
(owner decision). What remains, in order, when time runs short:

1. E6. It is also cut if its linker gate is not passed on 4 October. That is what happened:
   no link was checked by that day, and E6 was cut from the October study on 5 October
   (owner decision). Under Plan B it returns;
2. E7;
3. fewer models, 8 down to 6. The two dropped are the secondary models whose runs are least
   complete at the time of the cut; ties go gemma-3-27b first, then gpt-4o-mini;
4. E5 down to 474 of its 800 items: the unedited seed item and every edit of the first 50
   seeds of the seed list in its draw order (the 50 lowest `draw_rank` of
   `sample_pair_seeds.csv`), the same for every reader, fixed before any E5 call. The cut
   item file holds the registered rows of those seeds unchanged.

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

- Models read the letter of a notice but not its pragmatics (E2, E5). The paper states this
  sentence for a primary model only when the registered pattern below holds for that model.
- The zero-shot predictive readings are overconfident relative to outcomes (E3). The registered
  criterion, a secondary with no multiplicity claim, has two parts. Both are for condition (a)
  and `E_end`, over every statement of the primary's item set (section 5, E3), each with a 95%
  percentile interval by episode.
  - *Against outcomes.* The mean of `P(E_end)` minus the largest frequency of `E_end` that the
    captures allow (every undetermined `E_end` counted as yes) is positive, with an interval
    that excludes zero. This is the least value that calibration in the large can take on the
    item set (section 7.2). It uses no scoreable set and no assumption about the undetermined
    events. A primary without an item set has no reading (section 5, E4). Where the figures
    over every statement are withheld (section 2.5), the criterion has no reading either: the
    paper gives the part against the base rate and writes none of the five sentences.
  - *Against a predictor that reads no text.* The mean of `P(E_end)` minus the mean `P(E_end)`
    of the base rate by listing age on the same statements is positive, with an interval that
    excludes zero. No outcome enters this part: the observed frequency is the same on both
    sides.
  - *Reading,* for each primary by name, in this order. (1) When the greatest value (every
    undetermined `E_end` counted as no) is negative with an interval that excludes zero, the
    paper writes that the readings are underconfident relative to outcomes, and nothing else
    of this list. (2) When both parts hold, it writes "overconfident relative to outcomes".
    (3) When only the second holds, it writes that the model states higher probabilities than
    the base rate, gives the least and the greatest value of its calibration in the large, and
    says that the captures do not decide whether it is overconfident. (4) When only the first
    holds, it writes that the model's probabilities exceed every frequency the captures allow,
    that they were not shown to exceed the base rate's, and that the excess is not put down to
    the reading. (5) Otherwise it writes that overconfidence was not detected, gives both
    values, and does not write that the readings are calibrated.
  - *Why two parts.* On the 644 scoreable dev statements the base rate, which reads no text,
    stands at +0.135 on `E_end` (mean `P(E_end)` 0.253 against 76 of 644; 95% interval 0.083
    to 0.177). The selection of the scoreable statements does not make it: over the 1,334 dated
    dev statements the base rate stands 0.142 above the Turnbull share recovered by the stated
    end (0.264 against 0.122). On the fit split, where it was fitted, it already stands 0.051
    above (0.272 against 0.221); the rest goes with the fall of the list's hold rate from fit
    to dev. The selection acts on `E_end90` (section 7.2). The second part removes an excess
    that a predictor with no text shares; the first ties the claim to outcomes without a
    scoreable set. Over the 1,334 dated dev statements the least value is −0.144 for the base
    rate and +0.591 for the stated date at face value (`result_rules_check.py`, section 17).
  - *Reported beside it,* for condition (a) and for the base rate on the same statements:
    both parts for `E_end90`; both parts on the answers that parsed (withheld, their counts
    apart, when 1 to 4 answers failed on the item set or 1 to 4 parsed, or when the answers
    that parsed and the scoreable statements differ by 1 to 4: beside the figures over every
    statement they would give the horizon events of those statements);
    calibration in the large
    on the scoreable statements with its interval, and the difference of the two predictors
    there; the mean of `P(E_end)` minus the Turnbull share recovered by the stated end
    (secondary scorer); and the coverage of the 80% interval. The claim is conditional on
    survival to first sight (section 2.5).
- The models use the list's track record when it is given (H1 holds).
- The free text carries value beyond the structured fields: H3 holds in favour of the text
  against the base rate by listing age, and the 95% interval of `Δ_GBM` lies above zero
  (section 6). If only the first holds, the paper says which predictor `m-best` did not beat
  and makes no claim about the structured fields.
- On H2, an LLM reading beats the rules (a reading effect), or equivalence holds (reading is not
  the bottleneck). Both are informative. If H2 holds with `Δ < 0`, the paper writes that the
  model's literal reading loses to the rule reading through the same calibrator; if H2 is null
  and equivalence is not declared, it gives the 90% and 95% intervals and reads neither.

**The registered pattern.** It decides the sentence of the first bullet above and nothing else.
It reads E2 and E5 for the two primary models only. No outcome and none of H1 to H3 enters it.

- *Terms.* Letter, standing and pragmatics are defined in section 1. Of the two things that
  pragmatics names, only the standing enters the pattern. The predictive reading has its
  criterion in the second bullet above; wherever the paper states the sentence for a model, the
  same paragraph gives the outcome of that criterion for the model, whichever way it came out.
  In E5, surface form and granularity are the *letter factors*: the edit rewrites the period or
  changes the period itself. Certainty marker, stale, distractor date and silent are the
  *standing factors*: the edit leaves the words of the period as they are, or takes them away.
  TBD is a level of the certainty marker: 73 of that factor's 94 items take the date away (TBD, "no
  estimated release date", "as it is released") and 21 add or change a hedge word and keep the
  date. In E2, the *letter items* are the gold items whose gold gives an interval and carries
  no distractor date. By the allocation these are the 72 items of the seven dated strata, 60
  of them of forms other than month and year, and any dated depletion or discontinuation
  statement of the other strata; the adjudicated gold fixes the set.
- *The letter part.* (a) Under `literal-v1`, over all gold letter items pooled without weights
  (the item set of every gold item), the model's letter accuracy (section 7.1) is not more
  than 0.10 below the rule reader's: the lower end of the 90% percentile interval of the
  difference, model minus rule reader, lies above −0.10 (10,000 draws of shortage episodes,
  seed 20261001). Condition (a) sets no upper limit and is read on the interval alone. This
  is a one-sided reading
  at a nominal 0.05, the level of H2's equivalence: in a simulation on the clusters of the 72
  items (a run that is not in the committed output) a model 0.10 below the rule reader met it
  in 4% to 7% of data sets. (b) Neither of the model's E5 tests on a letter factor holds with
  the higher error rate on the edited items. Condition (b) can only withhold; the reading of
  the letter rests on (a).
- *The standing part.* For at least one standing factor, all three hold. (a) The model's E5
  test of the factor holds, under Holm over the twelve tests, with the higher error rate on the
  edited items. (b) The model's error rate on the items of the factor is at least 0.10 above
  its error rate on the unedited seed items, and at least 0.10 above its error rate on the
  items of the two letter factors taken together, every rate under the criterion of the factor
  (section 5, E5, "Target"). (c) The factor's own error occurs on at least 0.10 of the items of
  the factor on which it can occur. The own error is a period given where the gold gives none
  (certainty marker and silent: the false-commitment rate of section 7.1), the distractor's
  period taken (distractor date: distractor uptake, section 7.1), or a period given without
  the stale flag on an item whose gold is stale (stale). None of the three can occur on an
  unedited seed item, which is
  dated, not stale and carries no distractor date. A wrong statement type, a wrong interval or
  a wrong certainty class does not make a factor count by itself; each is reported.
  Conditions (b) and (c) can only withhold.
- *The sentence.* The pattern holds for a model when both parts hold. When it holds for both
  primaries, the paper states the sentence for the two primary models. When it holds for one,
  the paper states it for that model by name and says in the same place which part did not
  hold for the other. When it holds for neither, the paper does not state the sentence and
  reports each part for each primary. A part that does not hold is not read as its opposite,
  and the paper says which condition withheld it. A test of the E5 family that holds is
  reported as that family's result, with its size, also when a floor or the other part
  withholds the sentence; the paper then does not write that no effect was detected on the
  factors of that test's kind, letter or standing (section 5, E5, "Negative result"). A primary
  whose E2 or E5 run is declared not run has no pattern, and the paper says so. If E5 is cut
  (section 12, cut 4), the pattern is read on those items with the same floors; if E5 is
  not scored by the freeze of numbers, the sentence is not stated.
- *Error control.* The standing part reads rejections of the E5 family (Holm at 0.05 over its
  twelve tests) and adds no test to it. The letter part adds one one-sided reading for each
  primary, outside the Holm rule of E2's two tests; the paper reports it as a reading of this
  rule and not as a test of that family. The sentence needs a rejection of the E5 family, so
  where no standing factor has an effect it is written no more often than that family errs.
- *Support, not the rule.* The false-commitment rate, distractor uptake and the stale-flag
  scores of E2 are reported for every model with their counts and 95% intervals (for the two
  rates the exact binomial interval beside the percentile one), beside the rule reader's and
  each annotator's, and stale-value uptake on the 16 stale-at-issue statements of E3 beside
  them. The letter accuracy of the model, of the rule reader and of each annotator against the
  other (on the gold's letter items, by the E2 rule against the other's label) stands beside
  the sentence, with the two weighted differences. None of these decides
  anything, and neither do the three marks of E2's positive result. For each standing factor
  that counts, the paper gives the rate of its own error in the sentence that names it, and
  the share of the factor's errors that are of another kind. The secondary models are
  described by the same quantities (gemini-3.8-flash by those of E2 alone). Their E5 contrasts
  are outside the family of twelve, so no pattern is computed for them; the paper states the
  sentence for no secondary model and uses no plural that includes one.

- *Small points of the reading.* The E2 run of the pattern is the primary's `literal-v1` run,
  and the pattern is read from one E2 and one E5 result of the same plan of the runs. The
  lower end of the interval of the letter part must lie above −0.10: an end of exactly −0.10
  does not meet (a), and without a gold letter item (a) is not met. A difference or a share
  of exactly 0.10 meets a floor of the standing part; a floor whose rate has no item is not
  met. The items on which a factor's own error can occur are: for the certainty marker and
  for silent, the items whose gold gives no period; for the distractor date, the items whose
  gold carries a distractor date; for stale, the items whose gold is stale. A factor with no
  such item does not meet (c). A test of E5 holds by Holm's rule on the p-value of the
  procedure in force (under the fallback, the centred bootstrap p-value); its direction is
  the sign of the difference of the two error rates; a test that is not evaluable does not
  hold. When the standing part does not hold: if no test of a standing factor holds with the
  higher error rate on the edited items, it is withheld by (a); otherwise the paper names the
  floor or the condition (c) that each factor with such a test misses.
  When the pattern holds for one primary and the other has no pattern, the paper states the
  sentence for the first by name and says that the other has none. When neither primary has
  a pattern, the sentence is not stated.

**Negative, publishable because registered.**

- The models do not use the track record even when shown it (H1 fails).
- A model's reading of the notice loses to the base rate by listing age (H3 holds in favour
  of the base rate), or no difference is detected (H3 null). A null is reported with its 95%
  interval and the minimum detectable `Δ` of section 6, with the power that the registered
  test has at it, and is not read as "the text adds nothing".
- No difference between a primary and the rule reader is detected in the literal task (E2).
  This is a non-detection and is not read as "literal reading is solved".
- No test of a standing factor holds on the minimal pairs (E5). This is a non-detection and is
  not read as invariance.
- Memorisation confines the outcome claims to post-cutoff slices (E4).

The issuers' own optimism or calibration (E1) is context, never a result for or against the
claim.

**Expected, not evidence.**

- From Chicoine and Griffin (2025): a face-value reader will be overconfident on `E_end`, and
  condition (b) should reduce the primary Brier.
- H2 is expected to be small, because month-and-year forms dominate.
- H3 is open. On the train period, rules plus slip (a reading with no language model) was
  behind the base rate on the scoreable dev statements and ahead of it in the check on 2020
  ("Changes from the 29 September draft", item 36).
- `Δ_GBM` is expected to be positive for any reading passed through the calibrator: rules plus
  slip had the lower loss than the structured-only GBM in every train-period check.

**Not claimed.**

- A new method.
- Issuer optimism as a new finding.
- "First" (the paper writes "to our knowledge").
- That models "understand" anything, or that a standing error is a failure of pragmatic
  inference in the sense of implicature: "pragmatics" is the operational term of section 1.
- The term "commitment" (the label layer is "certainty class").
- That the base rate is the best predictor that could be built from the structured fields: it
  is the better of the two registered ones.

## 14. Outputs and release

**Where outputs go.**

- Derived tables: `analysis/coling/out/` (tracked).
- Reading runs: parsed readings, spend logs, invocation logs and run manifests in
  `analysis/coling/out/read/<run>/`, with the study ledger beside them (tracked); raw responses
  in `results/coling/read/<run>/` and the one call cache in `results/coling/read/cache/`
  (ignored by git).
- Annotation: the sample lists, the blank sheets and the manifest of the literal task, the
  pilot and the check sets in `analysis/coling/out/audit/`, where the sampler writes them; the
  train-half outcome-audit sheets and traces in `analysis/coling/out/audit_outcomes/`; the
  minimal pairs and the blank sheets of their audit in `analysis/coling/out/e5/`; the blank
  sheets, the manifest, the submitted sheets and the result of the reference-reading check in
  `analysis/coling/out/audit_reference/`; sheets in
  progress, the planted-error keys and the gold of the minimal pairs under
  `external_data/annotation/` (ignored by git). An annotator may fill a sheet as an Excel
  workbook in which every cell is text; `sheet_xlsx.py` writes it from the blank sheet and
  turns the filled workbook back into the sheet's own layout before it is validated.
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
- the anonymised copies of the registered plan and guide, with the script that makes them
  and the hash files (below).

**Anonymity and the evidence of registration** (owner decision, 1 October). The repository
that holds the registration stays public under the owner's account. ARR has no anonymity
period, and the submission does not link to the repository, so the registration commit itself
is not cited in the anonymous submission. The registration is evidenced by anonymised copies
of the registered `PLAN.md` and `AUDIT_GUIDE.md` in the supplement. A script that is
committed by F1 (`analysis/coling/anonymise.py`; it is not in the registration commit) makes
each copy from the registered file: it replaces every string of a list committed with it by a
fixed token and changes nothing else. The sha256 of the two
registered files, of the two copies, of the script and of the list are recorded in amendment
F1, so whoever holds the registration commit and F1 can rebuild the copies byte for byte;
each later amendment records the same for the files as amended. The supplement carries the
copies, the script, those hashes, the tokens with the number of places each replaces, and the
push time. The replaced strings and the commit id are released with the identified record on
acceptance, and the paper says so. Before acceptance a reviewer can check that the copies
match the hashes beside them, and no more: when the text was fixed is shown by the push
record of the tagged commit, which a reviewer cannot see.

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

- From `analysis/commitment/endpoints.py`: the model ladder (endpoints, model ids and billing
  rules; the prices and their date are those of the harness's own table, section 4), and the
  served-model echo check.
- From `analysis/real_content_pilot/transport.py`: the guarded transport, which handles
  retries, the spend cap and the spend log.
- From `collie.llm`: the disk cache, the cache key and the client types.

**One stray file pair.** `analysis/coling/dev_text_size.py` and
`analysis/coling/out/dev_text_size.json` are a development script of the earlier design and its
output. The script imports the commitment study's arms and simulator. Neither is part of this
study, nothing in the study calls them, and they are left out of the release; they stay in
the study folder at registration and are moved out by a later commit.

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

**From 29 September to registration (1 to 6 October).**

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
  with the availability rule as changed that day and no string rejected. The counts of rows,
  events, statements, episodes and of the gate set are unchanged. Changed or new:
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
  this for a counted set of eligible test statements (the set counted in the list above). This
  is the value of one horizon outcome for a subset of test statements, deduced without reading
  an outcome field. It is the only test-period outcome value known to have been stated. No
  tabulation of that set by year, form or company was made, and none is made before the
  evaluator runs. The rule that followed is in "Changes", item 11.
- **The form classifier, the dataset builder and the outcome-audit sampler were run on 1
  October** on the events of every period and on the open train outcomes. They wrote counts of
  statements by form, split, year, revision bucket and analysis set, a draft of the eligible
  list with its subsets, and, for the train period only, counts of outcomes and draft sheets
  for the train-half outcome audit. The classifier reads no outcome, the dataset builder
  refuses an outcome table that holds a test-period row, and the train half of the audit
  reads train-period outcomes only. None of these runs printed or wrote a test-period outcome.
- **Availability strings of all periods were read** as bare strings, to design the rule fix of
  1 October ("Changes", item 9). No outcome was involved. The effect of the fix on the test
  period is reported only as the count of events whose at-risk flag changes. In the rebuild of
  1 October, 55 presentation-level events in 33 statements became at risk under B (30 events
  dated before 2023 and 25 from 2023), and none left the at-risk set. The author check of the
  same day rejected no string (section 2.2), so it changes none of these. The registered count,
  from the freeze run's events table compared with the events table of 29 September as it stands
  in the repository's history (commit `cab9b62`): 55 presentation-level events in 33 statements
  are at risk under B in the freeze run's table and were not in that of 29 September, 30 events
  in 21 statements dated before 2023 and 25 events in 12 statements from 2023; none left the
  at-risk set. The two tables hold the same 22,727 events and differ only in the availability
  class of these 55, which moved from available to other.
- **FAA advisories of 2026 (from 1 October).** The advisories are collected from 1 October.
  The parser, the statement builder and the linker are developed on the 2024 pilot sample and
  on the development months (April and May 2026); the code refuses any later month until E6's
  amendment is registered. Two contacts with later months are disclosed. The first version of
  the parser, run on 1 October, opened the list pages of three June days to count the
  advisories they list; it read their numbers only and parsed no advisory. The collector's
  log, which a review of 1 October read, gives the number of advisories listed on each day.
  Since that review a locked month yields a count of files and nothing else.
- **An archive of results and downloaded data** made on 29 September lies untracked in another
  checkout of the repository. It may hold a copy of the sealed folder as built that day. It has
  not been opened. On the owner's decision it was moved, unopened, under the sealed folder on
  1 October, where the rule of the sealed files applies to it.

- **Thread counts in a code review.** On 1 October a review of the track-record builder
  counted, by thread and from first-sight fields, the test-period statements on the threads of
  the ten in-context examples (13, of which 4 eligible) and on the threads of train statements
  censored at their first capture in 2023 (none). No outcome field of a test-period statement
  was read, and no code or table depends on the counts.
- **The freeze run (5 October).** The counts-only code read the sealed test file once and
  printed counts only (section 3): 1,903 scoreable and 690 undetermined statements of the
  eligible list, in 106 scoreable episodes; the scoreable count of each of the six post-cutoff
  slices; and 1,275 statements with an observable outcome, 714 of them dated after 2023-12-31
  (section 12). No count needed a mask. The scoreable counts and the episode sizes of the
  eligible list entered the power estimate and the size simulation (section 6).
- **Counts for the result rules (5 and 6 October).** For item 41 of the change list the
  eligible list was counted by the rule reading's statement type, with form and certainty
  class, from first-sight fields: 1,891 recovery statements in 101 episodes and 702
  next-delivery statements in 67. The 120 literal items were counted by first-sight form,
  distractor flag and episode, for a simulation (72 letter items by the rule reading, in 59
  clusters), and those 72 by the rule reading's statement type and stale flag (51 recovery
  and 21 next delivery; 2 stale at issue). The names of the three files in
  `analysis/coling/out/audit/keys/` were listed once, and none was opened. No outcome field of
  a test-period statement was read.

To our knowledge, no test-period outcome has been derived, printed or tabulated outside the
sealed folder, apart from the counts of events with an observable outcome, the counts that the
counts-only code printed at the freeze run (above), and the one deduction recorded above.

## 17. Registration record

Hashes are the first 16 hex characters of sha256.

**Identity.**

- A file cannot hold its own hash, nor the id of the commit that holds it. The registration is
  identified by a commit and a tag: the commit on the study branch that holds this file with
  no marker and no owner tag left, together with the guide and the code listed below; and the
  annotated tag `coling-registration` on that commit. The tag `gate-1` that already exists in
  the repository belongs to the UV study and is not used.
- The commit id and the push time (UTC) are therefore not written here. They are recorded in
  amendment F1, with the sha256 of `PLAN.md` and of `AUDIT_GUIDE.md` at that commit and of
  their anonymised copies (section 14). The supplement gives the push time and not the
  commit id.
- F1 is identified in the same way, by its commit and the tag `coling-f1`. The harness checks
  both tags by these names (section 9).
- Before the push, an independent check runs the study's test files, reruns the corpus builder
  once and compares both sealed hashes with the freeze run's (`freeze.py --verify-rerun`),
  confirms every filled number against the code, and runs the checker of this file
  (`plan_check.py`), which fails while a marker or an owner tag is left or a hash recorded
  here differs from the file on disk.

**Environment.** Python 3.12.11; the lock file `uv.lock`, hash `3308eeb43cb51580` on 1 October,
re-read at registration. Nothing is installed for this study. The bytes of the gzip tables
depend on the pandas version, so the environment is part of the record.

**Captures.**

- The capture manifest `analysis/coling/out/capture_manifest.csv` (110 files): hash
  `8104e4f23dd0c7b5` on 1 October, re-read at the freeze run
  (`python -m analysis.coling.manifest --check --pin 8104e4f23dd0c7b5`).

**Code (hashed at registration).**

- `corpus.py` (events, clusters, outcomes, with the frozen list of rejected availability
  strings): `a44cd27ccddad604`.
- `rules.py` (the rule reader): `6a810bcb1ae277b9`.
- `forms.py` (the form classifier): `b99502d348ea82be`; `manifest.py` (the capture manifest):
  `b08607c9b6623edf`.
- The dataset builder (`dataset.py`), the samplers and sheet generators (`audit_sample.py`,
  `audit_outcomes.py`), the agreement code (`audit_agreement.py`), the counts-only code
  (`sealed_counts.py`) and the freeze script that runs them in order and writes the record
  (`freeze.py`): `dataset.py` `2fe95d355d3d5c77`; `audit_sample.py` `67ddfa330cf441d4`;
  `audit_outcomes.py` `0cb4d4d93eddb8ea`; `audit_agreement.py` `0a040e036d2b7697`;
  `sealed_counts.py` `22d592e0b65b339b`; `freeze.py` `0850418be7315cb0`.
- The calibrator (`predictors.py`): `452254cac0cb7817`; both GBMs (`gbm.py`):
  `1e5eb3791e90b587`; the power code (`power.py`): `6948ee5f2f27e111`. If the text-trained GBM
  is not ready, its code hash moves to F1 by an edit of this line before the push.
- The track-record builder (`track_record.py`): `53873bade0dd0e4b`. Its two record files and
  their manifest are hashed in F1, before any call that shows them.

**Tables.**

- Sealed: `external_data/sealed/outcomes_test.csv.gz` and
  `external_data/sealed/outcomes_train_uncensored.csv.gz`, as printed by the freeze run of
  5 October: `67df1acccd9a7174` and `6f4d96d7e18d878a`. The one checking rerun, the same day,
  gave both hashes and both open tables again.
- Open: `analysis/coling/out/events.csv.gz` and `analysis/coling/out/outcomes_train.csv.gz`,
  each as the gzip file and as its decompressed content. `events.csv.gz`: gzip file
  `d8d970a91691e702`, decompressed content `41f723e3debea466`. `outcomes_train.csv.gz`: gzip
  file `8772acd6b63afa36`, decompressed content `d114076e052819d6`.
- The E3 eligible list and the three secondary item lists. The eligible list
  `analysis/coling/out/eligible_e3.csv` (2,593 statements): file `8c12fc3e940f250e`, ids
  `a65983839e361c6e`. The secondary lists, by their ids: TBD (376 statements)
  `49466e77d6649d73`; silent (550) `e2e69a03c89c1d2c`; stale at issue (16) `be48aa1e4b00e9f9`.
- The sample lists of section 3 that are drawn before registration, each as its file under
  `analysis/coling/out/`. Step 1: the pilot `audit/samples/sample_pilot.csv` (20 rows)
  `edd0c9c477b83f79`; the check set `audit/samples/sample_check.csv` (20) `eb80b0fc1ceb2485`;
  the reserve check set `audit/samples/sample_reserve.csv` (20) `6be05e4f1a000cbd`; the
  literal-task sample `audit/samples/sample_literal.csv` (120) `05fcaf84b77406d7`. Step 2: the
  train-half outcome-audit sample `audit_outcomes/outcome_train_sample.csv` (56 rows: 50 items
  and 6 planted) `53a1c2449c26a233`. Step 3: the in-context pool
  `audit/samples_later/sample_incontext_pool.csv` (50) `ba42ebab7b3d1bb6`; the dev prompt items
  `audit/samples_later/sample_dev_prompt.csv` (60) `b404466c9a22a1b6`; the minimal-pair seeds
  `audit/samples_later/sample_pair_seeds.csv` (100) `17caf511bf2bf3e1`. Step 4, drawn by the
  dataset builder from the eligible list and given by their ids: the probe sample (300)
  `efbeb16e16ce86ff`; the 20-sample subset (300) `682f734bea32ce6c`; the paraphrase subset (200)
  `80ba3cf00b14b4d7`; the 2×2 subset (300) `7ed79fa3c0db7e72`; the reference-reading check (100)
  `d8227bd74cef2485`.

**Minimal pairs (E5).** The generator, `minimal_pairs.py`: `71a89fab1e618a67`. The item file
it wrote, `analysis/coling/out/e5/e5_pairs.jsonl` (800 items: the 100 unedited seeds and 700
edits of them): file `5acc3a0af1fd13af`, ids `10c21484b8c9b9cc` (the generator's digest: the
ids in file order; the harness and the scorer give `ef7120124b1b671e` for the same ids,
sorted). The generator's rule reading
agrees with the gold on all 800. The sample of the minimal-pair audit (100 items and 10
planted) is drawn from this file by the seeded rule. The freeze script does not run the
generator, so these hashes are not in the freeze record; the generator's own manifest
(`e5_manifest.json`) carries them. A fix that the minimal-pair audit requires
(`AUDIT_GUIDE.md` section 7.4) is a dated amendment with new hashes.

**Reference-reading check (task E).** Its script, `audit_reference.py`: `938cb1b61e5533e4`. It
draws nothing: it takes the 100 statements that the dataset builder marked on the eligible
list (ids `d8227bd74cef2485`, above) and splits them by the seeded rule. It reads no outcome
and no key. The freeze script does not run it, so its hash is not in the freeze record.

**Size simulation (section 6, "Why this test").** `size_check.py`: `b9b01f14e73a980b`. Its output,
`analysis/coling/out/size_check.json`: `1ce93baffa45a549`, made on the frozen statement table, the
eligible list and `power.json`, with seed 20261001. The file records its runtime and the
number of worker processes, so a rerun gives the same figures under another hash. The
simulation reads no sealed file. In the code and in its output the word "registered" still
names the percentile p-values of the draft, which were the registered ones when the code was
written; the test of section 6 is the procedure it calls `max_t`.

**Result-rule checks (sections 5, 7.2 and 13; change-list item 41).** `result_rules_check.py`:
`23fca5c56da1f17f`. Its output, `analysis/coling/out/result_rules_check.json`: `515d9c94bf64f7a3`, made with seed
20261001 on the frozen statement table, the eligible list, `dev_losses.json`, the list and the
strata of the literal sample, and the minimal pairs with their counts; the output holds the
hash of each. It reads the outcome cells of train-period rows, first-sight fields of the
other periods, and no sealed file.

**Annotation.**

- `AUDIT_GUIDE.md` v1: `ce58129993b31d33`. The check set was labelled under the v1 text of
  5 October as it stood before its corrections of the same day (`449c8e049be6cab1`, named in the
  check sheets). The guide's changelog lists what changed after that text: corrections, and
  the account of the script of task E once it was written. None of it touches a convention
  of the literal task.
- The pilot, on 20 items, both sheets valid: alpha 1.0 on the start and on the end month
  offsets; identical intervals on all 13 items where both annotators gave one; one item to
  adjudication (a statement type). Submitted sheets: `efea7ec22465b953` (A1) and
  `66da9e436ff06bc3` (A2).
- The train-half outcome audit, on 50 real and 6 planted items, both sheets valid: all six
  planted errors caught; definition B, no confirmed error; definition A, one confirmed error
  (code O1, a thread lost when a product's NDC was renumbered; adjudicated on 5 October). It
  passes for both definitions, and no rule fix is required. Submitted sheets:
  `8f5a9b9a4dab71ae` (A1) and `55da2448f7053a0b` (A2); the adjudication sheet
  `63ebd2182ab482a3`.
- The sample lists, the sample manifest and the minimal-pair items, with their manifest and
  counts, are in the registration commit. The submitted sheets and the adjudication sheet
  named in this section are fixed by their hashes and are not in it.
- The check-set result, which is the gate (both alphas, the share of identical intervals),
  with the hashes of the two submitted sheets. **TBD-at-F1**: the check sheets were not back at
  registration (section 10, task 2).
- The availability-string check (section 2.2): done on 1 October 2026; 910 strings read, none
  rejected; the list as read has hash `da0bde1baac48473`, re-read at the freeze run.

**Counts.** Every gate value above, with the Gate 1 record (section 12).

**Models.** `MODELS.md` (cutoffs, release dates, routes, endpoints and prices, each with its
source and retrieval date): its hash is `3c64439b5610ee40`, and the table of section 4 is the one it
gives. The facts were read at their sources on 1 October and read again, twice and
independently, on 5 October, because registration had moved: every registered value held.

**Prompts.** The SHA-256 pins of the five templates (`literal-v1`, `literal-free-v1`,
`predictive-v1`, `predictive-track-v1`, `probe-v1`) as they stand at registration, after the
text changes of 1 October and the two pilot sentences. Two pins have not moved since 1 October:
`predictive-v1` `c0732a5b2d109c60a94e56cd0820a4aa5851786bd01fd31acd3b12c9d47534ed`; `probe-v1`
`02e8d4338c3532a22615a43c47c54423250bf13474ef3f556925f5c878e8d08e`. Three moved with the edit of
5 October (the two pilot sentences, and one sentence on the median in the track-record prompt),
and the harness prints them as: `literal-v1`
`855244013a7614501ebdd6fbb45c8998f102a877e1299a6d86f81e1359934b27`; `literal-free-v1`
`ab87cd7525a49965763f78f55d6f8c47f4ca1476f49216a525635f97d6ef2555`; `predictive-track-v1`
`d0384c1f860d734bd26fa197de0a99e1bcdf520392941b399ef9d0f7b3213483`. The freeze record holds
all five, each matching its pin, with no sentence pending. No call has been made under any of
these ids, so the pins of 29 September are replaced under the same ids.

**E6.** Not part of this record. If E6 passes its gate, its own amendment records the hashes
of `faa_fetch.py`, `faa.py` and `faa_links.py`, the manifest of the collected advisories, the
gate result and what section 5 lists.

**At F1:**

- the final template ids and pins (until F1 an edit moves the pin under the same id; from F1
  on a changed prompt takes a new id), the three paraphrase templates, and the parsers;
- the hashes of `read.py`, of the evaluator (`evaluate.py`), and of every secondary scorer and
  of the scorer of E2 and E5 (`literal_scores.py`) that exists by then (a scorer hashed later
  takes a dated amendment: standing rules; section 6, "Evaluator");
- the dev prompt variants tried;
- the cost-trial projection, and any cap raised within the reserve;
- the H3 selection for each primary, with the dev losses of all three conditions, and the
  sha256 of its selection file (written by `evaluate.py dev`);
- the sha256 of the model-free test predictions after the refit on fit and dev, as
  `evaluate.py baselines` prints it, with the environment;
- the provider pin as sent, the provider that served the cost-trial calls, and the reasoning
  setting each model served;
- the check-set result and the estimated load (section 10), which were not available at
  registration;
- the registration's commit id, tag, push time and file hashes ("Identity"), with the sha256 of the
  anonymised copies of the plan and the guide, of the script that makes them and of its list
  of strings (section 14).

## Changes from the 29 September draft (1 October 2026)

The draft of 29 September is this file at commit `69b1588`. Between it and this
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
   yes/yes) and leaves 799 for fit. These counts use the bracket over all covered
   presentations, which was the primary unit when the boundary was set; on the displayed
   presentation (item 5) they differ a little, and the registered counts are those of section
   3. *Why:* train outcomes stop at 2022-10-06 and no capture exists for the 308 days before
   2022-10-04, so a late boundary scores almost only statements that had not recovered; the H3
   selection and the power check would rest on that.
4. **Reference reading and eligibility.** Draft: the stated period came from the rule output
   for forms where it matched author labels on 95% of audited train items, and from author
   labels for every other test event. Now: the frozen rule reading for every form; the authors
   check 100 eligible statements and the accuracy is reported; no author labels on the other
   forms in October. With the labels gone, the H2 secondary on author-labelled events becomes
   H2 on the month-and-year form alone, and E7 takes the rule reading as its reference.
   *Seen:* test-period event counts (the eligible count, and its split by the rule reading:
   418 of 2,585 eligible statements have another granularity than a month, or a distractor
   date beside the target). No test-period outcome. *Why:* the eligible list and the stated
   end printed in every predictive prompt must exist at registration, and the labels would
   have come after it; the labelling load did not fit the annotators' hours.
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
   results descriptive; the draft's descriptive mixed model is dropped. In the positive
   result, "vague" forms (on which the gold abstains, so no IoU exists) are replaced by
   part-of-month forms. *Seen:* event counts by form in all periods (texts only). *Why:*
   annotator hours; under the quotas of the guide's first draft only one form reached 15
   items, so the per-form family had no power.
8. **Budget scope.** gemini-3.8-flash reads E2 and the E3 conditions only (no probe, no E5, no
   E6); the TBD, silent and stale secondaries are read by the two primaries only; the Late
   split is not read for outcomes, where the draft kept it for descriptive post-cutoff slices
   of the newest models; the table is rebuilt from itemised counts; the cost trial runs 20 dev
   items per template, not per task type; the order of the budget fallbacks changes with the
   scope. *Seen:* test-period event counts (2,585 eligible statements against the 1,000 the
   draft assumed). *Why:* the draft's scope passed the gemini-3.8-flash cap at the real counts.
9. **Availability rule and capture set.** Negated, future and estimated uses of "available",
   and a mention directly followed by a time, no longer class a row as available; strings the
   author rejects go in a frozen list (none was rejected, item 26); the capture set is frozen
   at the 110 files, with a manifest the builder checks, and a capture whose content repeats
   the one before it is not used. *Seen:* the availability strings of all periods, as bare text;
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
    track-record table has the same cells and carries Turnbull shares. The table is described
    as the track record of the whole list, where the draft said "the issuer's"; an example
    shown as not recovered needs 365 days of follow-up. *Seen:* train outcomes
    (cell sizes and Turnbull fits), and the test-period count of statements per revision
    bucket. *Why:* most form-by-revision cells are too small, and the draft's "1, 2, 3 or more"
    did not match an index that starts at 0.
13. **Small rules.** The date shift is plus 4 years. The 20 samples use condition (a) and are
    scored as empirical quantiles of the sampled medians. The probe sample comes from the
    eligible list, stratified by year; its items carry no stated period, and the probe asks
    for the two probabilities at 90 and 180 days as well as the quantiles. The H2 margin of
    0.02 is confirmed. Parsing is strict: the draft's sentence that sorted quantiles and
    clipped probabilities is deleted; an empty response is not repaired; an answer with
    `P(E_end90)` below `P(E_end)` is kept and counted. *Seen:* nothing from the data. *Why:*
    the draft left these open, or contradicted the harness.
14. **E5.** The authors' predictive readings are cut. The registered test is a GEE clustered by
    seed, with 12 tests under Holm; the draft's mixed model with Firth's correction is dropped.
    *Seen:* nothing from the data. *Why:* no library in the environment fits the mixed model,
    and the readings had no procedure or hours.
15. **What is hashed when.** Code of the form classifier, calibrator and GBMs at registration;
    fitted artefacts at F1. *Seen:* nothing from the data. *Why:* every component is refitted
    after the H3 selection, so no fitted artefact is final at registration.
16. **deepseek-v3.** It stays a primary with a cutoff bounded by its release month, since its
    maker documents none, and is served by the endpoint `deepinfra/fp4` (owner decision,
    1 October). *Seen:* nothing from the data. *Why:* the draft assumed a documented cutoff.
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
23. **New definitions.** The power proxies (the H3 proxy changed again with item 36); the criterion for "overconfident"; distractor
    uptake; selective prediction limited to condition (c) and the rules; the E5 error and the
    contrast of each E5 test; the evaluator's three refusals in terms of what the harness
    stores; bounds beside every confirmatory estimate; the pinball loss of a target that is
    right-censored before the cap. *Seen:* nothing from the data beyond the items above. *Why:*
    the draft named these without defining them, or gave no rule.
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
    of available; the strings classed limited are added as an optional part. The check was
    done on 1 October on the whole list, and nothing was rejected (section 2.2). *Seen:* the
    availability strings, as bare text. *Why:* the rule change needs a check in both
    directions; the strings classed limited (647) bear mainly on a sensitivity analysis.
27. **Sealing rule.** Now explicit: before registration the sealed files are read once, by the
    counts-only code at the freeze, which prints the numbers of scoreable and undetermined
    statements, of scoreable episodes, of scoreable statements in each post-cutoff slice and
    the two observable counts of the Gate 1 record, masks any count that would give a number
    below 5, and prints no outcome value; the files are written by the freeze run and its one
    checking rerun only. The draft allowed counts of events with an observable outcome and had
    Gate 1 print a scoreable count, without saying what code reads the sealed file. *Seen:*
    nothing from the data. *Why:* several builds share one sealed folder.
28. **Other standing rules.** Draft: every collector sends at most one request per second and
    caches. Now: the pause each collector keeps is stated, with two exceptions disclosed (the
    openFDA page requests; the model pages read through a page reader). New: nothing is
    tabulated from the later rows of a thread in the open events table; no API key is in a
    build environment before registration; no personal name is written to any file; the
    seeded draw is defined. *Seen:* nothing from the data. *Why:* the draft's request rule did
    not describe two of the collectors, and the others were unwritten practice.
29. **Outcome audit.** Draft: 100 outcomes stratified by era, passing at 95% agreement. Now:
    presentation-level brackets under B and under A, with the statement-level bracket beside
    them; in each half 20 items for each annotator and 10 for both, with planted errors scored
    by code; a half passes with at most 2 confirmed errors, for B and for A separately; the
    train-half sample leaves out every thread that carries a labelled statement, and its
    traces stop at the train horizon. *Seen:* train outcomes (the train-half sheets are built
    from them, and draft sheets were made on 1 October). No test-period outcome. *Why:* the
    draft did not say what unit is audited, by whom, or how a 95% rule applies to 50 items.
30. **Minimal-pair audit.** Draft: at least 95% of labels match the text. Now: an item also
    fails when its edit changes more than its factor or its inserted form is not attested; 45
    items for each annotator and 10 for both; pass at 95 of 100. *Seen:* nothing from the
    data. *Why:* the plan and the guide have to state one rule.
31. **Prompt text before registration.** Draft: prompts are developed on dev items and frozen
    at F1. Now: the text changes of 1 October (the two added fields, the wording of the
    track-record table), the two sentences settled from the pilot and one sentence on the
    median in the track-record prompt are entered before
    registration, with no model call, and the five templates are pinned again under the same
    ids; from F1 on a changed prompt takes a new id. *Seen:* nothing from the data, and no
    model output. *Why:* the annotation sheets show the entry block that the models see, and
    the guide quotes the prompt's conventions, so both must be fixed before the pilot gate.
32. **Paid-call controls.** Draft: a run starts only if recorded spend plus its cap fits in
    $200, and routing "is pinned". Now the harness keeps one ledger for all runs, with a cap
    per model as well as the study cap, and counts the caps of runs in flight; refuses a paid
    call unless the registration tag is an ancestor of the checkout, and a test-period or
    late-period item unless the F1 tag is too; and names one provider endpoint per OpenRouter
    model, storing who served each call. *Seen:* nothing from the data. *Why:* two runs
    started together each saw the other's spend as zero, and only process kept a paid call
    from coming before registration.
33. **E6.** The data are described as three kinds of statement, each taken at its first
    issuance. In the linker gate a term needs 30 checked links, or all of its links when it
    has fewer; A1 and A2 do the checks, and a link checked by both counts only when both
    accept it. Seven models read E6, and nothing in it enters the confirmatory family. The
    amendment also fixes the prompts, the item sets and who gives the author readings.
    *Seen:* the 2024 pilot sample and the advisories of the development months (April and May
    2026) as far as they were collected on 1 October; no later month was parsed or linked.
    *Why:* the collector, parser and linker were written on 1 October, and the draft did not
    say what a term with fewer than 30 links needs or how a doubly checked link counts.
34. **Model facts and prices.** The table of section 4 is filled from `MODELS.md`. Against the
    draft: qwen-2.5-7b was released in September 2024, not October; each OpenRouter model is
    pinned to one endpoint at a stated precision where the endpoint states one; and the prices
    of deepseek-v3, gemma-3-27b and gpt-oss-20b change to those of the pinned endpoints.
    deepseek-v3 has no cutoff documented by its maker and is bounded by its release month. The
    $200 cap is stated as a cap on list-price spend. *Seen:* the makers' model cards and
    pages and OpenRouter's public endpoint listing, read on 1 October; no model was called.
    *Why:* the draft's prices were per model id, and a pinned endpoint has its own price.
35. **Literal-task samples.** Four rules settled by the owner on 1 October, before any sheet
    was handed out. (a) The row "vague or undated" of the guide's sample table is split into a
    vague row and an undated row, with a vague shortfall going to the undated row. (b) The row
    "distractor date" is split into "distractor only" and "dated target beside a distractor
    date". (c) A statement that shares a wording with a phrase quoted in the guide may be
    drawn; a statement whose whole text is, word for word and punctuation aside, a quoted phrase of
    three or more words, or
    whose two text fields are each such a phrase, is excluded from every sample of statements
    that are read. (d) The minimal-pair seeds of the relative form are taken from
    statements dated 2023-01-01 or later, text only, and calls on them wait for F1. *Seen:*
    the counts of statements by form and period, the texts of a first draw of the four sample
    lists, and the guide; no outcome field. *Why:* the first draw had no vague item in the
    pilot, 10 of its 12 distractor items had no target beside the distractor, 4 literal items
    were word for word a phrase quoted in the guide, and five of the six train statements of
    the relative form were in a labelling sample or in the guide's appendix A, with the sixth
    barred by the cap per episode.

36. **H3 comparator.** Draft: `Δ = loss(structured-only GBM) − loss(m-best)`, with that GBM
    called the content-free control. Now: the comparator is the base rate by listing age,
    fixed at registration; the draft's contrast is a registered secondary reported beside H3;
    the paper writes "value beyond the structured fields" only when `m-best` beats both
    (section 6). With it change the content value of the decomposition (E3), the H3 pair of
    the power estimate (now the base rate against the text-trained GBM), and the H3 line of
    the six secondary models, which is reported per condition because they have no dev runs.
    No predictor code changed. *Seen:* train outcomes, on the build of 1 October; no model
    output (no model had been called) and no test-period outcome. The figures below are
    those of that build, whose statement table still rested on the events table of
    29 September; the freeze run of 5 October rests on the events table after the
    availability-rule fix, where 33 more statements are at risk under B, and gives the
    registered figures of sections 3 and 6 (644 scoreable dev statements in 74 episodes;
    0.195 against 0.240). In detail:
    - *Dev.* The primary loss on the 643 scoreable dev statements (73 episodes; 485 no/no, 82
      no/yes, 76 yes/yes): base rate 0.197, rules plus slip 0.214, text-trained GBM 0.215,
      structured-only GBM 0.243, face value 0.818; a constant 0 scores 0.182. Every pairwise
      contrast with its interval, and the bounds of section 7.2.
    - *The two predictors that read no text.* The structured-only GBM is worse than the base
      rate by 0.046 on dev (95% interval 0.025 to 0.071), and under both bounds over the 1,332
      dated dev statements (0.254 against 0.206; 0.287 against 0.262). On the 259 scoreable
      dev statements whose two horizons fall on or before 2021-11-30 the difference is 0.013
      (−0.007 to 0.038). Four checks were made inside the fit split, each fitted on the
      statements before a date and scored on the scoreable dated statements after it. The GBM
      is worse by 0.029 (0.020 to 0.040; fitted before 2020, the 569 statements of 2020),
      0.037 (0.025 to 0.051; the 240 of January to June 2020), 0.041 (0.024 to 0.059; fitted
      before April 2020, the 340 of April to September) and 0.022 (0.007 to 0.039; fitted
      before July 2020, the 329 of July to December). The four checks overlap. In each of
      them the GBM gives the lower probabilities, so its loss does not come from a subset
      that favours low probabilities.
    - *The text-reading predictors against the base rate* (the base rate's loss minus
      theirs; dev, then the four checks in the same order). Rules plus slip: −0.017 (−0.030
      to −0.003), +0.020 (0.000 to 0.040), +0.022 (−0.003 to 0.048), +0.025 (0.002 to 0.047),
      −0.007 (−0.034 to 0.021). Under both bounds on dev, rules plus slip has the lower loss
      (0.196 against 0.206; 0.255 against 0.262). Text-trained GBM: −0.018, −0.033, −0.038,
      −0.027, −0.014.
    - *The same against the structured-only GBM.* Rules plus slip: +0.029 (0.004 to 0.061; p
      0.017), +0.050, +0.059, +0.067, +0.015 (−0.022 to 0.053). Text-trained GBM: +0.028,
      −0.004, −0.001, +0.015, +0.007.
    - *Other predictors that read no text*, tried for this change and not registered. One
      curve for all listing ages scores within 0.002 of the base rate in every comparison.
      On dev and three of the checks: the GBM on listing age alone is worse than the base
      rate by 0.005 to 0.017; on listing age and month, by 0.006 to 0.040; without the
      company, by 0.022 to 0.041. A logistic model on all structured fields and the horizon
      is worse on three and within 0.003 on one. A logistic model on listing age and horizon
      length, fitted on scoreable statements only, beats the base rate on dev (0.171 against
      0.197) and loses to it on 2020 (0.282 against 0.236).
    - *Selection of the scoreable statements.* The Turnbull share recovered by the stated end
      plus 90 days is 0.447 over all dated dev statements against 0.246 among the scoreable
      ones (0.545 against 0.440 on the fit split).
    - *Power.* The minimum detectable `Δ` of H3 is 0.017 under the draft's pair and 0.029
      under the new one. With rules plus slip standing for the model it is 0.036 under the
      draft's comparator and 0.015 under the new one.
    - *The refit.* The GBM fitted for the dev runs had 7 right-censored targets of 1,421; the
      refit for the test runs will have 642 of 3,033.

    *Why:* H3 asks whether a reading of the notice forecasts better than a predictor that
    reads none of it. The structured-only GBM lost to a table that uses one of its five
    features, so a positive `Δ` against it would have shown that the comparator is weak. A
    failed answer under conditions (a) and (b) is replaced by the base-rate output (section
    4): against the draft's comparator, a model whose answers all failed would have been
    credited with the base rate's margin over the GBM. The comparator is fixed and not left
    to a dev rule because the rule's result was known, and because a rule run on the
    scoreable dev statements rewards low probabilities. The GBM was not tuned or replaced: a
    new structured model would have been one more choice made after dev outcomes were seen.
    The change makes H3 harder to hold in favour of the text on dev; on 2020 it does not
    decide the sign. The draft's contrast is reported beside H3 so that both can be read.

37. **Dates.** Draft and revision of 1 October: registration by 3 October (4 October under one
    relaxation), numbers frozen by 6 October (7 October). Now: registration by Tuesday
    6 October and numbers frozen by Friday 9 October, with no relaxation; E6 is cut. *Seen:*
    the pilot and the train-half outcome audit, returned on 5 October; no model output and no
    test-period outcome. *Why:* A1 and A2 started on 3 October and returned on 5 October. The
    owner first decided to hold for January and then, the same day, to keep the October cycle;
    nothing in the design, the samples or the tests changed with the dates.
38. **Registered test.** Draft and revision of 1 October: p-values from the percentile
    bootstrap distribution of `Δ`, percentile intervals, and a sign-flip test on the episode
    sums as the sensitivity analysis. Now: the registered p-value is the larger of the
    bootstrap-t and the studentised sign-flip p-values; the intervals of the confirmatory
    contrasts and of `Δ_GBM` are those of that test, and H2's equivalence is read from it;
    the draft's p-values, its interval and its sign-flip test are sensitivity analyses
    outside Holm's rule; the power paragraph says what the test costs; the E4 probe rule uses
    the same test (sections 5 and 6). *Seen:* train outcomes and the
    dev losses of the model-free predictors, from which the simulation builds its paired
    differences; the episode sizes of the eligible list and the registered number of
    scoreable test statements (test-period event counts); no model output (no model had been
    called) and no test-period outcome value. On the model-free proxy pair of H3 (scoreable
    dev statements, freeze-run tables) the draft's p-value is 0.023 (`out/dev_losses.json`)
    and the registered one 0.100 (the evaluator's `contrast` on the same differences), so
    the change does not favour a finding. *Why:* a
    simulation at the study's episode sizes, run before registration (section 6, "Why this
    test"), showed that the draft's p-values reject a true null more often than their level
    (Holm's familywise error 5.5% to 9.2%, against 5%), that the 90% percentile interval
    declares equivalence too often when the differences are sparse, and that the sign-flip
    test on sums does not guard against skew. The test was chosen for its size. It costs
    power, and section 6 says how much.
39. **What the evaluator does, said exactly.** A review of the evaluator against this plan
    found points on which the plan was silent, or said more than the code does. The plan now
    states them: who reads the sealed outcomes after registration, and which analyses the
    evaluator computes and which fall to secondary scorers (standing rules; sections 5, E1,
    and 6, "Evaluator"); ties in the selection of `m-best`, and what the selection records;
    the test of the E4 probe and the case in which it cannot be made; how a primary is
    declared not evaluable; three further refusals of the evaluator; draws that sum to zero
    and the sign patterns of the sensitivity analyses; a literal interval given for a
    depletion or discontinuation statement (section 4); failure and refusal rates reported
    separately; the item set of the decomposition; what F1 hashes (selection files, the
    model-free test predictions, the secondary scorers); where E7's error classes are
    fixed. The standing rule on sealing is wider than the draft's: scripts other than the
    evaluator read the sealed files, each only after the evaluator has run, and one may be
    hashed after F1, by an amendment pushed before its first read.
    *Seen:* as item 38. *Why:* the registered text and the code that will run must agree
    before either is frozen, and the evaluator does not compute every registered secondary.
    No hypothesis, sample or metric changes.
40. **The tests of E5, and what E2 reports.** A review of the scorer of E2 and E5 against this
    plan found that two things in the test of E5 could not stand as worded. (a) An unedited
    seed item was an error by the E2 rule alone, while an item edited on the certainty marker
    or made stale was also an error by its certainty class or its stale flag; a reader that
    errs on the certainty class as often on the seed as on the edit would have shown an
    effect of the factor. Now the seed item is held to the criterion of the factor it is
    compared with. (b) The fallback of the GEE had no p-value. Now it is the centred bootstrap
    p-value on the difference of the two error rates, and only a primary's own cells can
    call it. For E2 the plan now says that "by form" is by stratum of the guide's table, what
    the two weights do and do not correct, which items the two bars of its positive result
    are read on, and where the list of convention items is kept and when it is fixed.
    *Seen:* nothing from the data: synthetic readings on the registered item file's layout
    of seeds and factors, and the plan and the scorer's code; no model output (no model had
    been called) and no test-period outcome. *Why:* a test must compare like with like, and
    a p-value that enters Holm's rule must be defined before it is computed.
41. **Result rules, after a review of the paper draft.** A review of the draft paper against
    this plan (5 October) found five places where the plan did not fix what the paper may
    write. All five are fixed here, before any model call. Points (a) and (b) were the owner's
    to decide, and the owner decided them on 6 October: the registered pattern, with a margin
    of 0.10 in its letter part, and the criterion in two parts. Later that evening the build of
    the scorers completed both, and the owner reads these points after the registration: the
    bullet "Small points of the reading", with the cases of a primary without a pattern;
    "Condition (a) sets no upper limit and is read on the interval alone" in place of "A model
    better than the rule reader meets (a)"; and the criterion without a reading where its part
    against outcomes is withheld (item 42).
    (a) *The first sentence of section 13.* Draft and revision of 1 October: the sentence held
    when a rate was "measurably above the rules or above the human ceiling", with no number.
    Now: the registered pattern of section 13, read on E2 and E5 for the two primaries.
    Letter, standing and pragmatics are defined in section 1; the six E5 factors are grouped;
    the three marks of E2 are descriptions; a null of E2 or of E5 is a non-detection; E3 is no
    longer titled the headline.
    (b) *The overconfidence criterion.* Before: calibration in the large on `E_end` on the
    scoreable statements, positive with an interval that excludes zero. Now: two parts over
    every statement of the item set, against outcomes and against the base rate (section 13).
    (c) *Scenarios.* The two settings of the undetermined events are called scenarios, and
    section 7.2 says what the complete case does.
    (d) *Anonymised copies.* A script and a fixed list of replaced strings, with the hashes of
    the copies recorded in F1; the commit id is not in the supplement (sections 14 and 17).
    (e) *By statement type.* A registered secondary of E3, and E1's descriptives by type
    (section 5).
    *Seen:* the paper draft and its review; train outcomes and the dev losses of the
    model-free predictors; first-sight counts (section 16); simulations on synthetic readings
    (runs that are not in the committed output). No model output (no model had been called)
    and no test-period outcome. On dev (`result_rules_check.py`, section 17): the base rate
    meets the earlier criterion of (b) on the scoreable statements (+0.135), and over the
    1,334 dated statements the stated date at face value meets its new first part (+0.591)
    and the base rate does not (−0.144). Rules plus slip and the two GBMs behave as the base
    rate does on both counts (a run that is not in the committed output). The base rate minus
    rules plus slip is
    −0.018 on the scoreable statements, and +0.009 and +0.007 under the scenarios; by type it is
    −0.013 on the 457 recovery statements
    and −0.032 on the 187 next-delivery statements. The Turnbull share recovered by the stated
    end is 0.252 for recovery and 0.118 for next-delivery statements on fit, and 0.133 and
    0.109 on dev. Item 36 gives the selection of the scoreable statements on the earlier build
    (0.447 against 0.246); on the freeze-run tables it is 0.446 against 0.245. In the
    simulations of (a), on the item file's layout of seeds and factors and under the centred
    fallback of E5: with no effect of any edit the pattern held for a primary in no data set;
    with every edit adding 0.10 errors, in 1% to 4% of data sets, where a standing test alone
    held in 39% to 59%; with stale alone adding 0.15 of its own error, in 40% to 71%.
    *Why:* the earlier wording of (a) had no number, and one model of eight could meet the 5%
    mark on 22 items by two false commitments; the earlier criterion of (b) did not separate a
    reader from a table; the two settings of (c) are not limits of a loss; an anonymised copy
    cannot have the hash of the registered file, so the earlier text of (d) gave a reviewer
    nothing to check; a next-delivery statement is scored against recovery, which asks for
    more than the notice states. No hypothesis, sample, prompt or split changes, and none of
    the six tests.

42. **Withholding, and points the scorers had to decide (6 October).** A check of the
    evaluator's criterion and a review of the secondary scorer found points on which the plan
    was silent. Now stated: (a) a figure is withheld, its counts apart, where it would give
    back the outcomes of 1 to 4 statements: the contrast on the statements both sides parsed,
    and its counts where 1 to 4 answers failed (section 4); the two parts of the overconfidence
    criterion on the answers that parsed, and the criterion without a reading where its part
    against outcomes is withheld (section 13); the figures over every statement of a set in
    which 1 to 4 statements are not scoreable, or only 1 to 4 are, with the mean probabilities
    and the calibration in the large on its scoreable statements, and a contrast under a
    sensitivity analysis that gives 1 to 4 statements another horizon event (section 2.5); a
    further cell in the tables of E1, and the figures of a probe over 1 to 4 targets (section
    5, E1 and E4); and, with these, a count that would say how many of 1 to 4 statements are
    scoreable, the check across sets made on pairs, how a withheld interval of `Δ_GBM` is read,
    and the evaluator's refusal of item sets that differ by 1 to 4 statements (standing rules;
    section 6); (b) a primary without an item set has no reading of the criterion, an interval
    end on zero does not exclude zero, and a single episode gives no interval (sections 5, E4,
    6 and 13); (c) what the Date Discontinued cell does in its
    sensitivity analysis, and where the two scenarios are reported (section 2.5); (d) a sample
    that fails to parse in the sampled quantiles (section 5, E3), statements that share a
    probability in the Brier decomposition (section 7.2), how a percentile of the draws is
    taken and the declaration that a secondary scorer takes (section 6), and what the evaluator
    does with a link into a sealed folder and with the hash of a sealed file (standing rules);
    (e) small completions from a
    last read of this plan against itself, the guide and the frozen files: the general rule
    of withholding in the standing rules, the draws behind the intervals of the slip
    distribution, the primaries' subsets after a cutoff, the freeze run in
    section 16, the two outcomes of H2 that section 13 did not word, which items a cut of E5
    keeps, and what task E checks. The six confirmatory contrasts are never withheld. *Seen:*
    the code and its tests on synthetic readings, this plan, and one run of the train-period
    descriptives on the open train table (for its run time); no model output (no model had
    been called) and no test-period outcome. *Why:* the code that will run had to decide
    these before it is frozen, and a figure on a few statements beside the same figure on all
    of them gives their outcomes back. No hypothesis, sample or test changes.

43. **The check-set gate at registration.** Draft and revisions: the check set is labelled and
    its gate passed before registration. Now: the registration was made on time without the
    check-set result; the gate is recorded in amendment F1 and must pass before the literal
    task is handed out and before any confirmatory call (section 10, task 2). *Seen:* the
    pilot (alpha 1.0 on both offsets; one statement type to adjudication); nothing of the
    check set, no model output and no test-period outcome. *Why:* the check sheets went out on
    6 October and were not back when the registration was due. The owner decided on 6 October
    to register on time and not to move the later dates.

**Status of these changes.** The owner confirmed on 1 October the scope (item 1), the deadlines
and their one relaxation (item 2), the availability rule, the capture freeze and the result of
the availability check (items 9 and 26), the roles (item 24), the public repository with
an anonymised copy of the plan and guide in the supplement (item 17), deepseek-v3 and its
endpoint (item 16), the E6 gate rule and the reading of a route extension (item 33), and the
four sample rules of item 35. The other items, item 36
included, were provisional rules of 1 October; the owner confirmed them as written on
3 October. Item 37 is the owner's decision of 5 October. Items 38 and 39 follow the simulation
and the review of the evaluator of 5 October. The owner decided both that evening. Three
tests were put to the owner: the one of section 6; the same with H1 two-sided; and the draft's
percentile p-values with their size disclosed. The owner chose the one of section 6, and
confirmed the sealing rule of item 39 as written. Item 40 follows the review of the scorer of
E2 and E5 of 5 October and is read by the owner after the registration. Item 41 follows a
review of the paper draft of 5 October; the owner decided its points (a) and (b) on 6 October
(above), and reads the others, and what was added to (a) and (b) after that decision, after
the registration. Item 42
follows the check of the evaluator and the review of the secondary scorer of 6 October and is
read by the owner after the registration. Item 43 is the owner's decision of 6 October. The
registration was tagged at its deadline on that decision, before the owner had read items 40
and 42 and the later points of item 41; a change that follows from the owner's reading is a
dated amendment.

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
- "By X" runs from the Date of Update to the end of X. The conventions for a year alone, a
  half, the parts of a quarter and of a year, relative times and vague times are written out;
  a half with no year is not read.
- A statement event is keyed by the listing as well as by generic, company, text and date.
- The upper bound of a bracket is the first capture that shows recovery or discontinuation,
  and observable brackets include brackets to discontinuation.
- The literal answer carries the quoted words it rests on. Masking in the 2×2 replaces names
  and NDC digits and rescales strengths; the draft said it removes them.
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
