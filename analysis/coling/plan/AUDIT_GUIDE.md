# Author audit guide

**Version v1 draft, 1 October 2026.** The pilot is labelled under this draft. The pilot meeting
(section 4) turns it into v1, which is frozen by hash at registration (`PLAN.md`, section 17).
After that, changes are made only through the adjudication log (section 5) and are listed in the
changelog at the end.

This guide covers the human labels of the COLING 2027 study "Estimated Recovery: TBD". Two
annotators (called A1 and A2 in every file; never by name) and one adjudicator (ADJ) do the work.
There is no crowd study. The tasks are:

- **A.** a literal reading of 120 FDA shortage notices, by both annotators;
- **B.** an audit of 100 derived recovery brackets, half before registration and half after the
  confirmatory runs;
- **C.** an audit of 100 minimal pairs;
- **D and E.** two short checks: the availability strings behind the outcome rule (done on
  1 October), and 100 reference readings (section 12).

The worked examples (sections 3.3, 3.11, 6.6, 12.2 and the seed of 7.3) are real rows from the
archived FDA CSV captures in `external_data/fda_wayback_csv/`, all from the train period
(statement dated before 2023-01-01). The short phrases quoted inside the definitions and
conventions show a form. Where a phrase of several words is taken from one train-period
statement, appendix A.2 names the statement; the others are bare date forms, wordings that many
statements share, or made up for the purpose, as are the edited entries of section 7.3. No
statement dated 2023 or later is quoted anywhere.

This draft follows the decisions of 1 October, recorded in the working note `DECISIONS.md`. A
decision that the owner changes is edited here before v1 is hashed. `PLAN.md` and this guide must
agree at registration: a difference found before then is settled in both before either is
hashed. Appendix B lists the differences known on 1 October.

## 0. At a glance

| Task | Items | Who | When | Pass rule |
|---|---|---|---|---|
| D. Availability strings (12.1) | the whole list: every string classed available or limited, now or before the 1 October rule change | ADJ | done on 1 October, before the corpus is frozen | none; no string was rejected, so the frozen list is empty |
| Pilot | 20 | A1 and A2, independently | Fri 2 Oct | none |
| Check set | 20, with 20 in reserve | A1 and A2, independently | Fri 2 Oct | alpha of at least 0.6 on the start and on the end month offsets |
| B. Outcome audit, train half | 50, plus 6 planted | 20 each, 10 shared, 3 planted each | Fri 2 Oct, before registration | at most 2 confirmed errors in the 50, for definition B and for definition A |
| A. Literal reading | 120 | A1 and A2, independently | Sat 3 to Mon 5 Oct | reported, no pass rule |
| E. Reference readings (12.2) | 100 | 45 each, 10 shared | after both task A sheets are in | reported, no pass rule |
| C. Minimal-pair audit | 100, plus 10 planted | 45 each, 10 shared, 5 planted each | after both task A sheets are in | at least 95 of the 100 free of confirmed errors |
| B. Outcome audit, test half | 50, plus 4 planted | 20 each, 10 shared, 2 planted each | after every confirmatory run, before the evaluator | at most 2 confirmed errors in the 50, for B and for A |
| Adjudication | disagreements and reported errors | ADJ (section 5) | after each task | |

**Hours.** Minutes per person, from 2 October on, at the planning rates in the third column.
The range uses the low and high rates in brackets. The pilot measures the literal rate, and the
train-half audit measures the audit rate; both are written into v1.

| Step | Items per person | Rate (low to high) | A1 | A2 | ADJ | Range, per annotator |
|---|---|---|---|---|---|---|
| Read this guide | | | 40 | 40 | 40 | 30 to 45 |
| Pilot | 20 | 45 s (30 to 60) | 15 | 15 | | 10 to 20 |
| Pilot meeting | | | 40 | 40 | 40 | 30 to 45 |
| Check set | 20 | 45 s (30 to 60) | 15 | 15 | | 10 to 20 |
| B. Outcome audit, train half | 33 | 2 min (1 to 3) | 65 | 65 | | 35 to 100 |
| Adjudication, train half | | | | | 20 | |
| **Before registration** | | | **175** | **175** | **100** | 115 to 230 |
| A. Literal reading | 120 | 45 s (30 to 60) | 90 | 90 | | 60 to 120 |
| Adjudication, task A | | | | | 60 | |
| E. Reference readings | 55 | 30 s (20 to 45) | 30 | 30 | | 20 to 40 |
| C. Minimal pairs | 60 | 40 s (20 to 60) | 40 | 40 | | 20 to 60 |
| B. Outcome audit, test half | 32 | 2 min (1 to 3) | 65 | 65 | | 35 to 100 |
| Adjudication, tasks E, C and the test half | | | | | 30 | |
| **After registration** | | | **225** | **225** | **90** | 135 to 320 |
| **Total** | | | **400** (6 h 40) | **400** (6 h 40) | **190** (3 h 10) | 250 to 550 (4 h 10 to 9 h 10) |

Not in the table:

- Task D, which ADJ did on 1 October (section 12.1); its time was not measured.
- A check set that fails once adds about 35 minutes for each annotator (20 reserve items and a
  second, shorter meeting).
- If E6 is still in the study on 4 October, the hand check of at least 150 links that is its
  gate (`PLAN.md` section 10, task 7) is done by A1 and A2. At 30 seconds a link that is
  about 75 minutes of checking between them, and more with the links that both check. The
  sheets and the procedure come with the linker code and E6's amendment; this guide does not
  cover them.
- The sheet builder's work is engineering time.

**If the hours do not fit.** Sizes are fixed at the pilot meeting and written into v1 before it
is hashed; nothing is resized after registration. The reductions that touch no registered test,
with the minutes each saves per annotator at the planning rates (each one also changes the
matching line of `PLAN.md` section 10, before registration):

1. task C from 100 to 60 pairs (27 each, 6 shared, 3 planted each; pass at 57 of 60): 16 minutes;
2. the test-half outcome audit without shared items (25 each, 2 planted each): 10 minutes, at the
   cost of the double-audit agreement for that half;
3. task E done by one annotator on all 100: 30 minutes for the other, at the cost of its
   agreement figure.

The large blocks (120 literal items, 50 outcomes per half) are fixed in `PLAN.md` and are changed
only there, by the owner. `PLAN.md` section 10 requires that the total fit the hours A1 and A2
can give; the owner confirms that at the pilot meeting, with the measured rates.

**Who reads what.** A1 and A2 read sections 1 to 3 and the opening of section 9 (how to edit a
sheet and its header lines) before the pilot, section 6 before the train-half audit, and
sections 7 and 12.2 before those tasks. Sections 8, 10 and 11, the rest of section 9 and the
appendices are for ADJ and the sheet builder.

## 1. Roles and order of work

- **A1 and A2** do all labelling and both outcome audits. They do not write, tune or run the
  model prompts, and they do not read model outputs on the items they label until the gold file
  of that task is hashed (section 2, rule 1).
- **ADJ**, the adjudicator, does not label. ADJ settles disagreements (section 5), chairs the
  pilot meeting, answers questions about this guide in writing, and did the availability-string
  check (12.1). ADJ may develop prompts and read model outputs, within the limit of section 2,
  rule 1.
- **Sheet builder.** Whoever runs the scripts that draw the samples, write the blank sheets,
  check a returned sheet and score the pair. For the literal task (and its pilot and check
  sets) the samples, the sheets and the validator are in `audit_sample.py`, and the statistics
  of section 8.1, the gate, the adjudication sheet and the gold are in `audit_agreement.py`,
  called the agreement script below. For task B everything is in `audit_outcomes.py`. Nobody
  opens the planted-error keys: the scoring script reads them (sections 6.2 and 7.1).

Who A1, A2 and ADJ are is recorded by the owner outside the repository. No file carries a name.

**Order in which the samples are drawn.** Every draw uses seed 20261001 and the seeded rule of
`PLAN.md`: the ids are put in the order of a hash of the seed, the name of the draw and the id,
and the first ones are taken, so a draw does not depend on the order of its input.

1. Pilot, check set, reserve check set and the literal sample, in that order. They are drawn from
   the events table and the form classifier only; no outcome field is read.
2. The train-half outcome sample, which excludes the statements and presentation threads of
   step 1 and of appendix A (section 6.2).
3. In-context examples, dev prompt items and minimal-pair seeds, which exclude everything drawn
   in steps 1 and 2, and every statement that reads like an item of step 1. (They are not part
   of this guide; the rule is stated here because the blinding rules depend on it. Section 10
   gives their lists and says what reads like an item, and section 7.1 gives the one case in
   which a seed is not a train-period statement.)
4. The task E sample, from the registered list of E3-eligible statements, leaving out the
   statements of step 1 (section 12.2).
5. The test-half outcome sample, drawn in sealed mode after every confirmatory run has finished.

**Order of work.**

1. ADJ checks the availability strings (12.1), before the corpus is frozen. Done on 1 October.
2. Pilot under this draft, meeting, revision to v1, check set under v1, gate (section 4).
3. Outcome audit, train half, then its adjudication. When it passes, the corpus is frozen.
4. Registration, with the hash of v1 and of every sample list drawn so far.
5. Task A, then its agreement statistics, then adjudication, then the gold file is hashed and
   committed.
6. Tasks C and E, after both task A sheets are submitted. ADJ finishes the task A adjudication
   before opening a task E sheet.
7. Outcome audit, test half: only after every confirmatory run has finished and after A1 and
   A2 have submitted their sheets of tasks A, C and E (its traces show test-period outcomes),
   and before the registered evaluator runs.

## 2. Blinding rules

These rules hold until the gold of the task in question is hashed and committed.

1. **No reader output on your items.** A1 and A2 do not read any output of a language model or
   of the rule reader on an item of the pilot, the check sets, the literal sample or the minimal
   pairs. That covers `analysis/coling/out/read/`, `results/coling/`, every `readings.jsonl` and
   `responses.jsonl`, and anyone's notes about how a reader handled an item. It also covers
   every file that holds a rule reading or the form class of an item:
   `rule_readings_train_golden.csv.gz`, `statements.csv.gz` and `eligible_e3.csv` in
   `analysis/coling/out/`, and the `keys/` folder beside the task A sheets, which gives the
   stratum and form of each item to the agreement script. (Task E shows rule readings by
   design. That is why it comes after the task A sheets are submitted, and why its sample
   leaves out the items of task A.)

   ADJ may read model outputs in general: dev items are never sample items (section 1), and
   prompt development needs their outputs. On the items of a task that ADJ has still to
   adjudicate, ADJ looks only at these aggregates until that task's gold is hashed:
   - the number of calls made and remaining;
   - parse-failure and repair counts for the whole run;
   - spend.

   Not allowed for anyone before the gold is hashed: a reader's output on a single sample item,
   and any figure that compares a reader with the labels, for the whole sample or by form.

   If someone has to open an output on a sample item (for example to debug a run that fails on
   it), the item ids go into the changelog, those items are reported separately, and that person
   takes no part in adjudicating them.
2. **No later captures (task A and task E).** Look only at the row shown in the sheet. Do not
   open the capture files, the corpus tables, the FDA website, the Wayback Machine or any other
   source about the drug. Do not search the web for the drug or the company.
3. **No outcomes (tasks A, C and E).** Do not open `external_data/sealed/`, the outcome tables in
   `analysis/coling/out/` (`outcomes_train.csv.gz`, and `statements.csv.gz`, which carries
   train-period outcomes), or any outcome audit sheet other than your own train-half sheet, and
   do not discuss what happened to any drug. Your train-half sheet shows no presentation whose
   statement you will label: its sample leaves out every presentation thread that carries a
   statement of the literal sample, the pilot or the check sets, and every presentation that
   shares such a statement. Where a trace has to mention a row of such a thread, it gives the
   row's names only (section 6.3). Its traces stop before 2023.
4. **No other annotator.** Label alone. Do not look at the other annotator's sheet or discuss
   items until both sheets are submitted. Questions about this guide go to ADJ, whose written
   answer goes to both annotators and into the changelog as a clarification.
5. **No assistants.** Label by hand. Do not paste items into a language model, a date parser or
   any tool that interprets the text. A calendar is allowed.
6. **Test outcomes stay sealed.** The test-half outcome audit sheets and their keys are written
   only under `external_data/sealed/audit/`. Nobody computes or writes down whether a stated
   estimate held, and the audit results are reported only as counts of agreements and of codes
   (section 8.2).
7. **Guide examples are excluded.** The statements listed in appendix A (the worked examples, the
   sources of quoted phrases and the prompt harness's fixed test item) are excluded from every
   sample. A statement of any drug whose whole text is a phrase quoted in section 3 or 7 is
   excluded from every sample of statements that are read (appendix A.4).

A breach is recorded in the changelog with the items affected. Those items are reported
separately.

## 3. Task A: literal reading

### 3.1 What is being labelled

The **literal reading** of a notice: what the notice itself says about timing, read with the
fixed conventions below. It is not a forecast. Do not use anything you know about the drug, the
company or the FDA's habits, and do not correct text that looks wrong.

The statement type, the interval or abstention, the certainty and the quote, with the stale flag
derived from the interval, are exactly the fields that the models return under the literal
prompt of `read.py` (`literal-v1`), so the gold can be scored against them field by field. Two
sentences of that prompt wait for the pilot (D1 and D3 in appendix B; `PILOT_SENTENCES` in
`read.py`), and the template cannot be run until they are settled and pinned. The abstention
reason, the distractors and the `hard` flag are extra gold fields.

### 3.2 Sample

- **Unit.** One distinct statement: a `statement_group_id` of `corpus.py`, which is one listing,
  linked generic, company, normalised statement text and statement date. The date belongs to the
  item, because the reading is anchored on it. No two items share generic, company and
  normalised text.
- **Display row.** When a statement covers several presentations, the row shown is the one the
  dataset builder fixes for that statement: one presentation at risk under definition B (section
  6.1), drawn by the seeded rule of `PLAN.md` section 2.3. A statement with no presentation at
  risk under B shows the member with the smallest `event_id`.
- **Frame.** Statements on the shortage listing whose row is Current when first seen, from all
  periods. Rows of the To Be Discontinued listing are not in the frame.
- **Strata.** The classes of the frozen form classifier (`forms.py`; `PLAN.md` section 2.6),
  grouped as in the table. The stratum is a sampling frame, not a label, and annotators do not
  see it.

  | Stratum | Classifier classes | Pilot | Check set | Reserve | Literal sample |
  |---|---|---|---|---|---|
  | month and year | `month_year` | 1 | 4 | 4 | 12 |
  | month with no year | `month_no_year` | 2 | 3 | 3 | 10 |
  | part of a month | `part_of_month` | 2 | 3 | 3 | 10 |
  | quarter, half or year | `quarter`, `half_year`, `year` | 2 | 3 | 3 | 10 |
  | range | `range` | 2 | 3 | 3 | 10 |
  | relative | `relative` | 1 | 1 | 1 | 10 |
  | exact day | `exact_day` | 2 | 3 | 3 | 10 |
  | TBD or unknown | `tbd` | 2 | | | 12 |
  | vague | `vague` | 1 | | | 3 |
  | undated | `no_date` | 1 | | | 5 |
  | silent | `silent` | 1 | | | 10 |
  | distractor only | `distractor`; `tbd`, `vague`, `no_date`, `silent` with a distractor date | 1 | | | 6 |
  | dated target beside a distractor date | `month_year`, `month_no_year`, `part_of_month`, `quarter`, `half_year`, `year`, `range`, `relative`, `exact_day` with a distractor date | 1 | | | 6 |
  | discontinuation | `discontinuation` | 1 | | | 6 |
  | **Total** | | **20** | **20** | **20** | **120** |

  A row owns the classes its cell names plainly. The part of a cell that ends in *with a
  distractor date* names classes the row takes only when the statement also carries a
  distractor date (the classifier's `distractor_dates` is above zero). So a statement that
  carries one leaves the row of its form:
  - for the *distractor only* row when its class has no dated target (`tbd`, `vague`,
    `no_date`, `silent`): the entry then holds a distractor date and no date to read;
  - for the row *dated target beside a distractor date* when its class is one of the nine
    dated classes of the first seven rows.

  A `distractor` statement is in the distractor-only row whatever it carries, and a
  `discontinuation` statement stays in its own row. The check sets come from the seven dated
  strata only (the first seven rows), since the gate is computed on intervals. In the files
  a stratum is called by the first class its row owns (`quarter`, `vague`, `no_date`,
  `distractor`); the row that owns none is `dated_distractor`.
- **Shortfall.** A stratum that cannot fill a quota gives all it has. What the vague stratum
  lacks goes to the undated stratum first. After that, in the literal sample the shortfall goes
  to the TBD, distractor-only and silent strata in turn; in the pilot and the check sets it
  goes to the month-and-year stratum.
- **Periods.** The pilot and both check sets come from the train period only. In the literal
  sample each stratum takes one third of its quota (rounded) from statements dated 2023-01-01 or
  later, more where the train period cannot fill the rest, and more from the train period where
  the later one cannot fill its third. A literal reading involves no outcome, so test-period
  text may be labelled.
- **Caps.** At most 2 items per masked template (months and numbers masked) and 3 per shortage
  episode, over the pilot, the check sets and the literal sample together.
- **Exclusions.** The statements of appendix A, and every statement whose whole text is a
  phrase this guide quotes: its statement text is, word for word and punctuation aside, a
  phrase of three or more words quoted in section 3 or in section 7, the worked-example
  tables included, whatever the drug or the company (appendix A.4). A statement that has both
  text fields is excluded when each of the two is such a phrase. A statement that only shares
  a wording with a quoted phrase, or contains one, can be drawn; the cap on masked templates
  limits how many. Nothing else is excluded: the literal sample is drawn before the
  in-context examples, the dev prompt items and the minimal-pair seeds, which exclude it
  (section 1).
- **Order.** Each annotator gets the items in a different seeded order.

`forms.py` writes the number of statements per class and period to
`analysis/coling/out/form_counts.json`, and the sampler (`audit_sample.py`, which reads the
table above from this file) prints what each stratum has left, and how much of that the caps
allow, before it draws each sample. Three strata are thin in the train period (vague, relative
and discontinuation: ten statements or fewer each in the 1 October build).

- The vague class has eight statements in the frame, six of the train period and two later.
  Appendix A excludes two of them (worked examples 13 and 14) and the rule on quoted phrases a
  third, so three train-period statements and two later ones can be drawn. The pilot takes one
  and the literal sample three; no quota fell short in the draw of 1 October.
- The pilot and the check sets take their relative items first, so the literal sample finds
  too few train-period relative statements for its share and takes most of its relative items
  from 2023 on (one train-period item and nine later ones in the draw of 1 October).

The pooled test of `PLAN.md` E2 runs over the items outside the month-and-year stratum: 108
when every quota is filled, as in the draw of 1 October. A month-and-year statement that
carries a distractor date is in the row of dated targets beside a distractor date, so it is in
the test. Per-form results are descriptive.

### 3.3 What you see

Exactly the entry block that the models see (`ENTRY_BLOCK` in `read.py`), with dates in ISO form.
An empty field reads `(blank)`:

```
Entry
- Drug: Cefoxitin for Injection, USP
- Company: Fresenius Kabi USA, LLC
- Presentation: 1 g per vial; SDV; (NDC 63323-341-25)
- Therapeutic category: Anti-Infective
- Initial posting date: 2019-05-03
- Type of update: Revised
- Date of update: 2020-08-13
- Availability information: "Backordered. Next release October 2020."
- Related information: "Check wholesalers for inventory"
- Reason for shortage: "Manufacturing delays"
```

The sheet shows the same fields, one per column.

Read the statement from the Availability information and the Related information only. The Date
of update is the anchor. The Reason for shortage, the Therapeutic category and the Initial posting
date are context: they never hold the statement, and the Initial posting date is never a
distractor.

You do not see the Status, the capture date, other rows of the same drug or any later version of
the notice.

### 3.4 What you record

| Column | Values | Notes |
|---|---|---|
| `statement_type` | `recovery`, `next_delivery`, `depletion`, `discontinuation`, `none` | section 3.6 |
| `start`, `end` | `YYYY-MM-DD`, or `YYYY-MM` as shorthand for the first day (in `start`) or the last day (in `end`) of that month | blank when abstaining; section 3.7 |
| `abstain` | 1 or 0 | 1 exactly when `start` and `end` are blank |
| `abstain_reason` | `tbd`, `no_date`, `vague`, `no_statement` | only when `abstain` is 1; section 3.7 |
| `certainty` | `asserted`, `estimated`, `undetermined`, `no_statement` | section 3.8 |
| `quote` | the shortest exact words the reading rests on | required only when the entry has more than one time expression |
| `distractor_roles` | semicolon list of `expiry`, `depletion`, `discontinuation`, `onset`, `past`, `other` | section 3.10 |
| `distractor_quotes` | the words of each distractor, same order, separated by semicolons; use `\|` between them when a quote itself holds a semicolon | one quote for each role |
| `hard` | 1 or 0 | 1 when a convention had to be stretched; say why in `note` |
| `note` | free text | required when `hard` is 1 |

You type nothing else. The agreement script computes `stale` (section 3.9) and the month and day
offsets of `start` and `end` from the anchor (section 8.1); the validator runs the consistency
checks of section 3.12.

### 3.5 Decision order

1. Find every forward-looking statement about supply in the Availability and Related
   information.
2. Choose the target statement (section 3.6) and record its type.
3. Read its time with the conventions (section 3.7): an interval, or abstain with a reason.
4. Record the certainty (section 3.8).
5. Record every distractor date (section 3.10).
6. Set `hard` if you had to stretch a convention.

### 3.6 Statement type and the target statement

The types, with the definitions of the literal prompt and the cue words of `rules.py`:

- **`recovery`**: when supply is expected to return to normal, or the shortage to end. Cues:
  recovery, Estimated Recovery, resupply or re-supply, restock, back in stock, off backorder,
  relaunch, launch, resume, return; availability at a time ("Estimated availability Dec-2020",
  "Anticipated availability - April 2021", "Available by 4/5/19", "available for order");
  shortage duration; meet or support demand; and shortage states that end at a time ("backorder
  until X", "on allocation through X", "not available until X", "delays ... until X", "will
  remain on backorder for N"). A bare unknown marker with no cue ("TBD") is a recovery statement,
  and so is a text that is only a date and at most four words with no cue ("Stocked Out, December
  2021").
- **`next_delivery`**: when the next shipment, release or delivery is expected. Cues: next
  delivery, release, shipment, batch, lot, supply or replenishment; release, ship, deliver,
  replenish; additional or new lots, units, quantities or stocks; arrive; scheduled for
  manufacturing; "product will be made available as it is released".
- **`depletion`**: when current stock is expected to run out, or until when product remains
  available. Cues: deplete, exhaust, run out, "to last until", "N months of inventory",
  and "available", "stock", "supply duration", "distribution will continue" or "continue to be
  sold" until or through a time. A shortage word before the "until" makes it a `recovery`
  statement instead ("limited supply until X", "not available until X").
- **`discontinuation`**: when the product will be, or has been, discontinued. Cues: discontinue,
  cease, stop sale or shipping, final date, final order or batch, last order, shipment, batch or
  distribution ("The anticipated final date of availability to patients is approximately April
  2019"), no longer available or supplied, delist, phase out, withdraw, market exit.
- **`none`**: the entry makes no forward-looking statement about timing ("On backorder", "Check
  wholesalers for inventory").

Expiry dating, lot numbers, NDCs, strengths, phone numbers and past events are never statements
about timing. A misspelled cue word counts as the word intended ("availabilty", "Backorderd").

**Choosing the target** when the entry makes more than one statement. Rule 1 is the prompt's
order. The prompt says nothing about two statements of one type, so rules 2 to 4 are the
ranking of `rules.py` (appendix B, D22, lists the corners where `rules.py` leaves rule 1):

1. Take the first type present in the order `recovery`, `next_delivery`, `discontinuation`,
   `depletion`. A type is present when the entry makes a statement of it, dated or not: "Next
   Delivery: May 2021; Estimated Recovery: TBD" is a `recovery` statement that abstains, and
   "Discontinuation of the manufacture of the drug. Current supply expected to deplete by May/June
   2020 timeframe." is an undated `discontinuation` statement, with the depletion date as a
   distractor.
2. Between two `recovery` statements, the kind of cue decides first, in this order:
   - an explicit "recovery" cue ("Estimated Recovery", "recovery in");
   - resupply, restock, back in stock, relaunch, off backorder;
   - resume, return, launch, "estimated availability", "available for order", shortage
     duration, meet or support demand;
   - a shortage state that ends at a time ("backorder until X", "on allocation through X");
   - a bare "available", "in stock" or "supply", or no cue at all.

   With the same kind of cue, a dated statement beats one with an unknown marker. A vague
   recovery statement (C14) comes after all of these. So in "On backorder. Limited inventory
   available in November 2021." with the Related information "Recovery unknown at this time",
   the target is the explicit recovery statement, which abstains (`tbd`).
3. Within each of the other types, a dated statement beats one with an unknown marker, which
   beats a vague or undated one. Between two dated `next_delivery` statements, a "next ..." cue
   ("next delivery", "next release", "next shipment") beats the others.
4. Remaining ties go to the first mentioned, Availability information before Related information.
   Set `hard` if the tie felt arbitrary.
5. "Next Delivery and Estimated Recovery: X" is a `recovery` statement.
6. A list of times for one type ("Next Delivery: May 2020, July 2020, August 2020 and November
   2020", "Month and Month") is read as separate statements; the first listed is the target. A
   month without a year in such a list takes the year of the next month that has one.

### 3.7 Time conventions

The conventions marked **[P]** are the literal prompt's own words. Those marked **[R]** come
from the frozen conventions of `rules.py` and fill gaps the prompt leaves open. Those marked **[G]**
are this guide's own; the pilot checks them. The pilot meeting decides which [R] and [G]
conventions are written into the prompt (appendix B, D3 and D14), and v1 updates the marks.
Appendix B records the check of these conventions against `rules.py`.

- **C1. Anchor.** Read every time relative to the Date of update shown. [P]
- **C2. Month.** "April 2020", "Apr-20", "April of 2020", "4/2020" (numeric month and year): the
  whole month. [P, R]
- **C3. Part of a month.** Early, beginning of, start of: days 1 to 10. Mid, middle of: 11 to 20.
  Late, end of, end-, or "end" after the month's name ("March end"): 21 to the last day. First
  half of a month: 1 to 15; second half: 16 to the last day. [P, R]
- **C4. Weeks.** "Week of <date>": that date and the 6 days after it. "First week of", "1st week
  of", "week 1 of" a month: days 1 to 7; second 8 to 14; third 15 to 21; fourth 22 to 28; fifth
  29 to the last day. "Last week of": the last 7 days. "The week of <part of a month>", where no
  date is given, is read as that part of the month, with `hard` set. [R, G; "fifth week of"
  and "5th week of" are a known mismatch, D18]
- **C5. Quarter.** "Q2 2020", "2Q20", "Q2-2020", "second quarter of 2020", "1st quarter 2020": the
  whole quarter. Early, mid or late in a quarter: its first, second or third month; the end of a
  quarter is its third month. [P, R]
- **C6. Half.** First half of a year, "1H", "H1": January to June. Second half, "2H", "H2": July to
  December. [P, R]
- **C7. Year.** A year alone, "in 2020", "sometime in 2023": the whole year. Early or beginning of
  a year: January to April; mid: May to August; late or end of: September to December. [P, R]
- **C8. Missing year.** A month, quarter or half written without a year: its first occurrence
  that ends on or after the Date of update. A day without a year likewise: its first occurrence on
  or after the Date of update. A part of a month takes the year of its month. Two-digit years mean
  20NN ("Mar 21", "April/May 21", "1Q20", "Nov-22", "4/5/19"). In a month followed by a bare
  two-digit number with no comma and no ordinal ("Mar 21", "June 15"), the number is a year
  when 20NN lies from the year before the Date of update to three years after it, and a day
  otherwise: dated 2020-08-13, "Mar 21" is March 2021 and "June 15" is 15 June 2021. [P, R, G]
- **C9. Ranges.** "May-June 2020", "April/May 2021", "Feb/Mar 2021", "January – February 2021
  timeframe", "4Q 2021 to 1Q 2022", "end of May/early June 2020": from the start of the first
  part to the end of the last. A year written once applies to every part. When the first part's
  month is later in the year than the last part's, the first part belongs to the year before
  ("Dec-Jan 2021" is December 2020 to January 2021). "From X to Y" is a range like any other,
  also when X is already past: "Shortage duration from July 2019 to March 2020", dated
  2019-08-01, is 2019-07-01 to 2020-03-31 (C16). [P, R]
- **C10. "By", "before", "no later than", "at the latest".** From the Date of update to the end
  of the time named: "by the end of April 2021" dated 2021-04-12 is 2021-04-12 to 2021-04-30. If
  that time ends before the Date of update, read the time itself (the entry is then stale). [P, R]
- **C11. "Until", "through", "thru", "till" and "not ... until".** The period named, and nothing
  more: "Estimated shortage until March 2020" is March 2020; "on allocation through February 2021"
  is February 2021; "no plans to manufacture until sometime in 2023" is 2023. "After X", "not
  sooner than X" and "no earlier than X" are also the period X. [R, G; open point D3]
- **C12. Relative times.** Counted from the Date of update, with a week of 7 days and a month of
  30 days. "Within N", "up to N" or "over the next N": the Date of update to N later. "N to M"
  ("3-18 months", "4-6 weeks"): N later to M later. A single N ("in 6 weeks", "for 3 months"): N
  later, as both start and end. "Next month", "next quarter", "next year": the calendar unit after
  the one holding the Date of update; "this month", "end of the month" and "end of the year"
  follow C3 and C7 for the unit holding it. [P, R]
- **C13. Exact date.** That day, as both start and end: "7/1/2020", "Available by 4/5/19" (with
  C10), "June 1st, 2022". Numeric dates are month first. [P, R]
- **C14. Vague times.** A time with no number and no calendar name ("few months", "a couple of
  months", "several weeks", "soon", "shortly", "the near future", "coming weeks", "an extended
  period", "long-term"): abstain, reason `vague`. [P]
- **C15. Words that do not change the interval.** Approximately, about, around, on or near,
  sometime, timeframe, target, ETA and every certainty marker: "approximately April 2019" is April
  2019; "the June timeframe" is June. [R]
- **C16. No clipping, no correction.** Keep an interval that starts or ends before the Date of
  update. Never correct a date that looks like a typing error ("Next release November 2019" dated
  2021-09-23 is November 2019); say so in `note`. [G]
- **C17. Seasons.** Spring, summer, fall, autumn and winter are not read as calendar names: "winter
  2021" is the year 2021, and a season with no year abstains as `vague`. Set `hard`. [R, G; open
  point D13]

**Abstain** (blank `start` and `end`) when the target statement gives no date or period:

| `abstain_reason` | When |
|---|---|
| `tbd` | an unknown marker governs the target: TBD, to be determined, unknown, not known, no estimated (release) date, (release) date not available at this time, unable to provide, cannot be estimated |
| `no_date` | the target is stated with no time at all ("Product will be made available as it is released", "Additional lots are scheduled for release") |
| `vague` | C14 |
| `no_statement` | `statement_type` is `none` |

### 3.8 Certainty

How the entry presents the timing of the target statement:

- **`undetermined`**: an unknown marker (the `tbd` list above) governs the target, or the target
  gives no time at all (`no_date`). An unknown marker wins over every other marker: "Estimated
  recovery TBD" is `undetermined`.
- **`estimated`**: a hedge governs the target, or the target's time is vague (C14; a vague time
  is a hedged one). The closed list of hedges: estimated, estimate or est., expected or
  expecting, anticipated or anticipate, projected or projecting, predicted, target, tentative,
  approximately, ETA, on or near, around, about, likely, should.
- **`asserted`**: a statement with none of these ("Next release October 2020", "Recovery May
  2020", "will", "scheduled", "planned").
- **`no_statement`**: exactly when `statement_type` is `none`.

A marker governs the target when it is the nearest marker before the target's time in the same
clause, or, failing that, when it follows the time within about 25 characters. Clauses end at a
full stop followed by a capital letter, at a semicolon, and at the boundary between the two text
fields. So in "Next Delivery: May 2021; Estimated Recovery: July 2021" the recovery is
`estimated`, and in "Backordered. Next Delivery: May 2020, ... Expecting May and July delivery to
be depleted immediately." the target is `asserted`.

So the certainty of an abstaining target follows from its reason: `tbd` and `no_date` give
`undetermined`, `vague` gives `estimated`, `no_statement` gives `no_statement`. "Will remain on
backorder for few months" is `estimated`; "Product will be made available as it is released" is
`undetermined`. This is how `rules.py` maps its readings to the prompt's classes. It is open point
D1 (appendix B): the pilot confirms the mapping or changes it.

### 3.9 Stale

`stale` is true when the interval ends before the Date of update: the entry repeats an estimate
that had already passed when it was updated. It is false when the item abstains. The agreement
script computes it from `end` and the anchor, as the prompt defines it; you do not type it.

### 3.10 Distractor dates

A distractor is any time expression in the entry, other than the target, that a careless reader
could return as the delivery or recovery time. Record each with its role:

| Role | Examples |
|---|---|
| `expiry` | "5 month expiry (1/2022 expiry) dating available by request", "(expiry 6/30/2021)" |
| `depletion` | "Remaining inventory estimated to last until April 2020", "available until", "Distribution will continue in the US until January 30, 2023" (when the target is not itself a depletion) |
| `discontinuation` | "To be discontinued in 2021" (when the target is not a discontinuation) |
| `onset` | "Projecting backorder in May", "backorder expected in X", "shortage anticipated from X" |
| `past` | "Backordered material arrived in end of September", "as of X", "effective X", "since X" |
| `other` | any other time expression that is not a delivery or recovery statement ("will provide an update in X") |

Other delivery or recovery statements (the later items of a list, a next delivery beside the
target recovery) are not distractors.

### 3.11 Worked examples

All from train-period captures; A is the Date of update. "Offsets" are the month offsets of start
and end (section 8.1). The Text column quotes the Availability information and, after a
semicolon, the Related information; a Related information that says nothing about timing
("Check wholesalers for inventory", "Manufacturing capacity constraint") is left out of the
table in examples 2, 4, 5, 14, 15, 17 and 20. Your sheet always shows both fields.

| # | Entry (drug, company, A) | Text (Availability; Related) | Type | Interval | Certainty | Stale | Offsets | Why |
|---|---|---|---|---|---|---|---|---|
| 1 | Bupivacaine and epinephrine, Hospira, 2019-10-07 | "Next Delivery and Estimated Recovery: June 2021"; "Shortage per Manufacturer: Manufacturing Delay" | recovery | 2021-06-01 to 2021-06-30 | estimated | no | 20, 20 | 3.6 rule 5; C2 |
| 2 | Cefoxitin, Fresenius Kabi, 2020-08-13 | "Backordered. Next release October 2020." | next_delivery | 2020-10-01 to 2020-10-31 | asserted | no | 2, 2 | C2 |
| 3 | Hydromorphone, Teva, 2020-08-20 | "Backorder - Product availabilty ETA Late August" | recovery | 2020-08-21 to 2020-08-31 | estimated | no | 0, 0 | availability cue, misspelt; C3; C8 (August 2020 ends after A) |
| 4 | Lidocaine with epinephrine, Fresenius Kabi, 2021-05-19 | "Backordered. Next release early Q3." | next_delivery | 2021-07-01 to 2021-07-31 | asserted | no | 2, 2 | C5; C8 |
| 5 | Loxapine, Lannett, 2021-02-02 | "Unavailable. Additional lots are scheduled for release in the March/April timeframe. Product will be made available as it is released (allocating inventory)." | next_delivery | 2021-03-01 to 2021-04-30 | asserted | no | 1, 2 | C9; C15 ("timeframe"); "scheduled" is not a hedge |
| 6 | Nefazodone, Teva, 2021-11-17 | "Estimated availability in 4Q 2021 to 1Q 2022" | recovery | 2021-10-01 to 2022-03-31 | estimated | no | -1, 4 | C9; C16 (no clipping) |
| 7 | Alogliptin, Perrigo, 2019-10-09 | "On backorder – expected release the week of 10/28" | next_delivery | 2019-10-28 to 2019-11-03 | estimated | no | 0, 1 | C4; C8 |
| 8 | Azacitidine, Dr. Reddy's, 2021-01-12 | "Low inventory"; "Partial shipments on allocation through February 2021" | recovery | 2021-02-01 to 2021-02-28 | asserted | no | 1, 1 | shortage state ending; C11 |
| 9 | Triamcinolone, Novartis, 2022-09-30 | "Availability through wholesalers: not available. Estimated duration of supply shortage: 3-18 months." | recovery | 2022-12-29 to 2024-03-23 | estimated | no | 3, 18 | C12 (30-day months) |
| 10 | Hydroxyzine pamoate, Impax, 2019-12-13 | "Expected to be on allocation until sometime in 1Q20." | recovery | 2020-01-01 to 2020-03-31 | estimated | no | 1, 3 | C5; C8; C11; C15 |
| 11 | Guanfacine, Mylan, 2020-03-20 | "Unavailable. Estimated recovery TBD." | recovery | abstain (`tbd`) | undetermined | no | | TBD wins over "Estimated" |
| 12 | Cefotaxime, Hikma, 2019-09-09 | "Currently unavailable"; "On backorder. Shortage duration is unknown at this time." | recovery | abstain (`tbd`) | undetermined | no | | timing in Related information counts |
| 13 | Levetiracetam, Solco, 2019-04-02 | "Long-term backorder for all skus. No estimated release date at this time." | recovery | abstain (`vague`) | estimated | no | | "Long-term backorder" is a vague recovery statement and outranks the TBD release statement (3.6 rule 1) |
| 14 | Levetiracetam, Lupin, 2019-04-02 | "Will remain on backorder for few months" | recovery | abstain (`vague`) | estimated | no | | C14; 3.8 |
| 15 | Lidocaine, Fresenius Kabi, 2021-08-25 | "5 month expiry (1/2022 expiry) dating available by request. Next release date not available at this time." | next_delivery | abstain (`tbd`) | undetermined | no | | distractor `expiry` "(1/2022 expiry)" |
| 16 | Cefoxitin, WG Critical Care, 2019-05-03 | "On backorder"; "Please check wholesalers for available inventory." | none | abstain (`no_statement`) | no_statement | no | | silent |
| 17 | Cisatracurium, Meitheal, 2020-04-08 | "Backordered. Next Delivery: May 2020, July 2020, August 2020 and November 2020. Expecting May and July delivery to be depleted immediately." | next_delivery | 2020-05-01 to 2020-05-31 | asserted | no | 1, 1 | 3.6 rule 6; the hedge is in another clause |
| 18 | Tacrolimus, Mylan, 2020-06-02 | "Unavailable, recovery in May 2020" | recovery | 2020-05-01 to 2020-05-31 | asserted | **yes** | -1, -1 | stale at issue |
| 19 | Furosemide, Baxter, 2020-06-02 | "Backordered.  Next delivery anticipated in late-May 2020" | next_delivery | 2020-05-21 to 2020-05-31 | estimated | **yes** | -1, -1 | C3; stale |
| 20 | Heparin and sodium chloride 0.9%, Fresenius Kabi, 2021-09-23 | "Backordered. Next release November 2019." | next_delivery | 2019-11-01 to 2019-11-30 | asserted | **yes** | -22, -22 | C16: read the letter; note the likely typo |

**Hard cases** (set `hard`, and give the reason in `note`):

| # | Entry | Text | Reading | Point |
|---|---|---|---|---|
| H1 | Alogliptin, Perrigo, 2019-12-10 | "On backorder – expected release the week of late December/early January" | next_delivery, 2019-12-21 to 2020-01-10, estimated | C4 last clause; C9 across the year |
| H2 | Indigo carmine, American Regent, 2022-08-24 | "Out of Stock, no plans to manufacture until sometime in 2023" | recovery, 2023-01-01 to 2023-12-31, asserted | read as a shortage state that ends at a time ("Out of Stock ... until"), C11 with C7 (D6) |
| H3 | Alfentanil, Hospira, 2020-03-25 (Related information only) | "Discontinuation of the manufacture of the drug. Current supply expected to deplete by May/June 2020 timeframe." | discontinuation, abstain (`no_date`), undetermined; distractor `depletion` "Current supply expected to deplete by May/June 2020 timeframe" | the type order (3.6 rule 1): an undated discontinuation outranks a dated depletion (D2). This row is on the To Be Discontinued listing, so it is outside the sampling frame; it is kept because it shows the rule plainly |

### 3.12 Consistency checks run on every sheet

Before submitting, run the validator on your sheet
(`python -m analysis.coling.audit_sample validate <sheet>`; section 9). It rejects a row, and
you fix it, when:

- `abstain` is 1 and a date is given, or 0 and a date is missing;
- `start` is after `end`, or a date does not exist;
- `statement_type` is `none` but `certainty` is not `no_statement`, or the other way round;
- `statement_type` is `none` and an interval is given;
- `certainty` is `undetermined` but an interval is given;
- `abstain_reason` is missing when abstaining, or given when not;
- `abstain_reason` and `certainty` disagree (`tbd` or `no_date` need `undetermined`, `vague` needs
  `estimated`, `no_statement` needs `no_statement`);
- the numbers of distractor roles and of distractor quotes differ;
- `hard` is 1 and `note` is empty;
- a coded column holds a value outside its list.

It rejects the sheet as a whole when an item is missing, added or listed twice, when a shown
cell was changed (import every column as text), and when the header lines give no start and
end time for each sitting. It warns, without rejecting, when a quote is not found word for word
in the entry and when a date lies more than 60 months from the Date of update: check those rows
for typing errors.

The sheet is filled in a copy (section 9). The validator compares the copy with the blank
sheet, which stays where the sheet builder wrote it. When it finds no blank, because the sheet
was filled in place or the blank was moved, it warns that the list of items and the shown cells
were not checked. Such a sheet cannot be submitted: the agreement script refuses a sheet that
is the blank's own file, and one whose blank is missing or changed.

## 4. Pilot, revision and check set

1. **Pilot (this draft).** 20 train-period items, allocated as in section 3.2. A1 and A2 label
   them independently under this draft and write the start and end time of the sitting in the
   sheet header (`# sitting_start:` and `# sitting_end:`, section 9).
2. **Agreement.** The agreement script (`audit_agreement.py agree --task pilot`) computes the
   statistics of section 8.1 on the pilot, lists every disagreement, and gives the mean seconds
   per item.
3. **Meeting (A1, A2 and ADJ; about 40 minutes).** For each disagreement, each annotator names
   the convention they applied. Three outcomes are possible:
   - a slip against a clear convention, which needs no change;
   - an unclear convention, which is reworded;
   - a missing convention, which is added.

   The meeting then settles the open points:
   - D1: the certainty of an abstaining target that has no unknown marker (section 3.8);
   - D3: "until X" and "through X" (C11);
   - D13: seasons (C17). No pilot item carries a season word, since no train-period statement
     does; the meeting settles the point on the two forms that C17 names;
   - D14: what is done about the conventions marked [R] or [G] that the prompt does not state;
   - the hours: the measured seconds per item against section 0, and any reduction from its list;
   - whether the `YYYY-MM` shorthand and the sheet format worked.

   Every change is written into this file as v1 and logged in the changelog. For D1 and D3 the
   meeting also fixes the sentence that goes into the literal prompt.
4. **Check set (v1).** 20 fresh train-period items from the seven dated strata (section 3.2),
   labelled independently under v1.
5. **Gate.** Krippendorff's alpha (section 8.1) is computed twice over the check set, on the
   start month offsets and on the end month offsets. Both must be at least 0.6. The share of
   check items with identical intervals is reported beside the two alphas; it is not part of the
   gate.
   - If fewer than 10 check items have an interval from both annotators, or the offsets do not
     vary enough for alpha to be defined, the pilot items are pooled with the check items. A
     gate that is still undefined after pooling counts as not passed.
   - If either alpha is below 0.6, the guide is revised once more and the 20 reserve items are
     labelled under the revision. A guide revised after a failed gate is v1.1: its version line
     reads `v1.1`, and the reserve sheets are written again so that they name it.
   - The reserve gate is computed like the check gate, on the reserve items. In the two cases
     of the first point it pools with the pilot items, as the check set does, and not with the
     check items. If it fails too, the hold trigger of `PLAN.md` section 12 fires.
   - The agreement script prints the gate (`agree --task check`, or `--task reserve`) and
     exits with status 0 when it passes.
6. **Freeze.** v1 (or v1.1) is committed and its hash goes into the registration record. Pilot,
   check and reserve items stay out of the gold and out of every other sample, whether or not the
   reserve was used. Their labels are reported in an appendix as pilot data. They get no
   consensus label.

`rules.py` is frozen (sha256 prefix `6a810bcb1ae277b9`) and does not follow the pilot. If the
meeting changes a convention, the guide and the literal prompt change, and the remaining
difference from `rules.py` is recorded in appendix B as a known mismatch.

## 5. Disagreement adjudication

1. **Freeze first.** Both annotators submit their sheets. The sheet builder records the sha256 of
   each file, and the agreement script computes and saves the agreement statistics. Only then is
   anything adjudicated. Reported agreement is always the pre-adjudication agreement.
2. **What goes to adjudication (task A).** Every item where A1 and A2 differ in any recorded
   field: `statement_type`, `abstain`, `abstain_reason`, `start`, `end`, `certainty` or the
   distractor roles. Differences in `quote`, `hard` and `note` alone do not; the gold then
   takes `hard` as 1 if either annotator set it.
3. **Procedure.** For each item, ADJ reads both labels and the reasons in `note`, then decides by
   the conventions of this guide. Each decision records one of:
   - `slip`: one annotator misapplied a convention that decides the case;
   - `gap`: no convention decides it. ADJ decides, words a new convention, applies it to every
     item it touches (not only the disputed one), and adds it to the changelog as a dated
     clarification.
4. **If ADJ cannot do a task in time**, A1 and A2 settle each item together by naming the
   deciding convention. An item they cannot settle that way is marked `gap` and left out of the
   gold; the number of such items is reported.
5. **Items marked `gap`** are reported, and every E2 result is also given without them.
6. **Gold.** The adjudicated labels form the gold file, which is hashed and committed before
   anyone opens a reader's output on these items. Gold is never changed after that, except
   through a dated amendment that is reported.
7. **Audit tasks (B, C and E).** Every real item that an auditor marks `error` or `cannot_tell`
   goes to ADJ, which covers every shared item on which the two auditors differ. ADJ confirms or
   rejects each error with the trace in hand, or leaves it unresolved when the captures do not
   decide. The pass rules use confirmed errors; the counts as reported by the auditors are given
   as well. Planted items never reach ADJ: the scoring script checks them against the key once
   both sheets of the task (and half) are returned, and leaves them out of the list it gives
   ADJ.

## 6. Task B: outcome audit

### 6.1 What is being checked

Whether the recovery bracket that `corpus.py` derived for one presentation's statement event is
what its own written rule gives when applied by hand to the raw capture rows. The reference is
the module docstring of `corpus.py` as frozen at registration (the file's hash is printed in the
sheet header). In short:

- **Thread.** One presentation's rows across captures, linked on the exact key (listing,
  generic, company, presentation) and then on the NDCs in the presentation text.
- **Event.** A statement event of that thread, first seen at capture `c0`. A new event starts
  when the statement text changes, when the thread goes from Resolved back to Current, or when
  it reappears after missing at least one capture with a different Date of update. A later row
  with the same text is a re-confirmation, not a new event. The statement date is the Date of
  update of the row at `c0`, or the capture date when the Date of update is missing or more than
  one day later than the capture.
- **Definition A (the FDA calls it resolved).** Recovered at a capture when the thread's row has
  Status Resolved, or when the row is absent while its generic is on the shortage listing with no
  Current row (the generic is Resolved).
- **Definition B (supply is back; the primary outcome).** Recovered when the row's Availability
  information says the product is available now, or when A holds. A future, estimated or negated
  use of the word does not count ("available by 4/5/19", "no release date available at this
  time"), and neither would a string on the rejected list of section 12.1, which is empty.
- **Definition BL (a sensitivity analysis for B).** As B, with limited supply counted as
  available. It is not audited separately; a doubtful class between limited and available is
  recorded as flag N5.
- **Not recovered.** The row is listed with Status Current and, for B, is not available. A
  capture where the row is absent while its generic is Current or not on the list says nothing.
- **Competing event.** Discontinuation: the presentation (same NDC, or the same generic, company
  and presentation text) appears in the To Be Discontinued listing and was not there at `c0`. It
  wins ties. A Date discontinued cell on a shortage row is not used.
- **Bracket.** `lower` is the last capture at which the thread was seen not recovered (at least
  `c0`); `upper` is the first capture showing the event. The width is `upper` minus `lower` in
  days.
- **Horizon** (`followed_to` in the sheet). The last capture an event's outcome may use. For a
  test event it is the archive's last capture. For a train event it is the last capture before
  2023-01-01, which is the capture of 2022-10-06 in the frozen capture set. Some train events
  (a Date of update before 2023) were first captured in 2023, nearly all of them at its first
  capture, 2023-01-13; such an event has its own first capture as its horizon and no follow-up
  at all.
- **Censoring.** With no event by the horizon, the outcome is right-censored at `lower`, with one
  of these reasons:

  | Reason | Meaning |
  |---|---|
  | `end_of_train` | train event; the row is still listed and not recovered at the horizon capture, so `lower` is that capture. The follow-up stops there by rule: this is not an error and says nothing about what happened later |
  | `end_of_archive` | test event; the same at the archive's last capture |
  | `no_followup` | test event first seen at the archive's last capture |
  | `absent_generic_current` | the row is absent at the horizon capture and its generic is Current there; `lower` is the last capture where the row was seen not recovered |
  | `absent_generic_unlisted` | the same, with the generic not on the list at the horizon capture |

  For the two `absent` reasons the sheet also gives the exit date: the first capture after
  `lower` at which the row was missing. It is kept for a sensitivity analysis that counts
  leaving the list as recovery.

- **At risk.** Under A, when the row is on the shortage listing and Current at `c0`; under B,
  when it is also not available at `c0`. Otherwise the outcome is `not_at_risk`.

**The audit unit** is the bracket of one presentation thread, under B and under A. It is the
primary outcome of the study: when a statement covers several presentations, the analysis scores
the presentation shown to the reader. The statement-level bracket (the latest recovery among the
presentations the statement covers) is a secondary outcome. It is shown beside the thread's
bracket for information and is not audited: a unit test covers how it is combined.

If `PLAN.md` and `corpus.py` still differ at registration, the audit follows the frozen
`corpus.py`, and the difference is recorded in the registration.

### 6.2 Sample

- **Size.** 100 presentation-level statement events: 50 train-period and 50 test-period.
- **Frame.** The shortage-listing events of the half. Outcomes exist for these only.
- **Exclusions, by statement and thread.** Left out are: every presentation thread that carries
  a statement of the pilot, the check sets, the literal sample or appendix A; every
  presentation that shares such a statement; and every other event on those threads. Both
  annotators label every literal item, so a thread is left out for both. The sample lists
  name, for each statement, the thread of the row shown to the annotators. For that thread
  the builder goes one step further: every statement the thread carried at any date is left
  out as well, with all its presentations. So no statement in the pool covers a presentation
  that an annotator is shown, and the statement-level bracket beside an item never includes
  one. The builder refuses to draw either half without the sample lists, which hold
  statements of both periods. It also stops when a row of appendix A matches no event, and
  when a list names an id that is no event of the corpus as built (the lists then come from
  another build): in each case the exclusion would be incomplete. Only a draft, which is
  never handed out, is drawn without them. The rule on quoted phrases (appendix A.4) is not
  applied to this sample: the audit asks nothing about the wording of a statement.
  A trace shows the rows of the audited thread, so a statement an annotator will label does not
  appear in them. Where the audited thread is absent, the trace also lists a row of another
  thread with the same NDC (section 6.3); when that thread is an excluded one, the trace gives
  only the row's generic, company and presentation, not its status or text. The audit is
  reported for the pool that remains, with its size.
- **Stratification.** Within each half, by definition-B outcome type (recovered, discontinued,
  censored, not at risk), by bracket width (31 days or less, 32 to 90, more than 90) where the
  bracket is closed, and by whether the event was re-confirmed. Every stratum that is not empty
  gets 2 items, or the one event its pool has; the other items follow the pool in proportion,
  so rare strata are oversampled.
  A stratum that cannot fill its quota passes the shortfall to the largest ones. The error rate
  is reported raw and reweighted to the pool.
- **Caps.** At most one item per thread and per statement, and at most 2 per generic.
- **Assignment.** Within each half, 20 items to A1, 20 to A2, and 10 audited by both, spread
  evenly over the strata. Both definitions are audited on every item.
- **Planted errors.** Each auditor also gets planted items, 3 in the train half and 2 in the
  test half, made from events outside the sample. The bracket shown for a planted item is wrong
  in one known way: `upper` moved one capture later, `lower` moved one capture earlier, recovery
  and discontinuation swapped, or the rows of another presentation of the same generic and
  company linked after `c0`. Planted items look like real ones and are excluded from the pass
  statistic. Which items are planted is written only to the key file, which is kept apart from
  the sheets (section 10). Nobody opens it; the scoring script reads it once both sheets are
  returned.
- **Sealing.** The test-half sample is drawn by code that stratifies on sealed fields and prints
  only total counts: no stratum table and no outcome value. Its sheets, traces and key are
  written only under `external_data/sealed/audit/`, and only after every confirmatory run has
  finished.

The builder prints the stratum table of the train half (events, excluded, pool, quota, drawn)
when it writes the sheets, so the pool is known before the audit starts.

### 6.3 What you see

One row per event in your sheet, and the event's capture rows in the traces file:

1. **Header cells.** Audit id; generic, company and presentation; the statement text; the
   statement date; `c0`; `followed_to` (the horizon); and, for each definition, the derived
   outcome type, `lower`, `upper`, the width in days, the censoring reason and the exit date.
   Beside them, for information: the number of presentations the statement covers and the
   statement-level type, `lower` and `upper` under B and A.
2. **Class strip.** One letter per capture from `c0` to the end of the window:

   | Letter | Row at that capture | Under B | Under A |
   |---|---|---|---|
   | `U` | Current, unavailable (backordered, out of stock, not available) | not recovered | not recovered |
   | `L` | Current, limited (limited supply, allocation, intermittent) | not recovered | not recovered |
   | `O` | Current, other text (for example the estimate itself is written in the field) | not recovered | not recovered |
   | `B` | Current, blank | not recovered | not recovered |
   | `A` | Current, available now | **recovered** | not recovered |
   | `R` | Status Resolved | **recovered** | **recovered** |
   | `r` | row absent; generic listed and Resolved | **recovered** | **recovered** |
   | `.` | row absent; generic Current or not on the list (the trace says which) | says nothing | says nothing |
   | `D` | the presentation is in the To Be Discontinued listing (and was not at `c0`) | **discontinued** | **discontinued** |

   A `|` stands before a capture that follows a gap of more than 90 days.
3. **Trace.** One row per capture: the capture date and timestamp; whether the row is before
   `c0`, at `c0` or after it; present or absent; how the row was linked (same key, or NDC); the
   generic, company and presentation strings of that row; Status, Type of update, Date of
   update, Availability information, Related information, Resolved note, Change date and Date
   discontinued; whether the statement text is the event's; the generic's status at that
   capture; whether the presentation is in the To Be Discontinued listing, with its date there;
   the class letter; and the days since the capture before. Where the thread is absent after
   `c0`, a row of another thread that carries the same NDC is listed too (`present` reads
   `other_thread`). If that other thread is one of those left out of the sample (section
   6.2), `present` reads `other_thread_withheld` and only its generic, company and
   presentation are given: say so in `note` if you cannot judge the link without the rest, and
   use `cannot_tell` only if the outcome depends on it. Two captures can fall on the same day
   (two on 2020-10-30); they are separate rows. The cells are the FDA's text as captured,
   except that an e-mail address reads `[email]`.

The traces are in one CSV file for both auditors. The builder also writes your items as a text
file, `outcome_<A1|A2>_<half>_items.txt`: one block per item in the order of your sheet, with
the header cells and then the trace, one line per capture (`<` marks a capture before `c0`,
`*` marks `c0`). Read the items there if you prefer; the verdicts go into the CSV sheet.

**The window.**

- It opens with up to two captures before `c0`, and the thread's last earlier row, so that the
  start of the event can be checked.
- When a shown outcome is censored, it runs to the horizon.
- Otherwise it runs to one capture past the later `upper` of the two definitions, and on through
  the captures within 90 days after the `upper` of B, so that a relapse can be seen.

**Train-half windows never pass the horizon.** No trace of a train-half item shows a capture
after 2022-10-06, except the single first row of an event first captured in 2023. How a thread
stood from 2023 on is test-period outcome information.

### 6.4 How to check an item (about 2 minutes)

1. **Link.** Do the trace rows belong to one presentation (the same NDC, or a recognisable
   re-formatting of the same product)? Is the thread absent anywhere while the same NDC appears
   under another string?
2. **Event start.** Does the event start at `c0` by the rule of section 6.1 (a new text, a
   return from Resolved to Current, or a return after an absence with a new Date of update), and
   not at an earlier capture? The rows before `c0` show this. Is the statement date the Date of
   update of the row at `c0`?
3. **At risk.** Under A, is the row Current at `c0`? Under B, is its letter at `c0` also not
   `A`?
4. **Classes at the transitions.** At `lower` and `upper`, and at any capture where the letter
   changes, read the raw Availability information and Status, and confirm the letter.
5. **Bounds.** Under B and then under A: is `lower` the last capture seen not recovered before
   the event, and `upper` the first capture showing recovery or discontinuation? Skip `.`
   captures: they say nothing.
6. **Competing event.** Is there a `D` at or before the derived `upper`? Then the outcome is
   discontinued at the first `D`.
7. **Censoring.** If censored:
   - is there really no recovery and no discontinuation up to the horizon?
   - is the reason the one the table of section 6.1 gives for the row's state at the horizon
     capture?
   - for the two `absent` reasons, is `lower` the last capture seen not recovered, and is the
     exit date the first capture after it where the row is missing?

   `end_of_train` is correct whenever the row is still listed and not recovered at the horizon
   capture. Do not mark it as an error because the follow-up is short.

Record `ok`, `error` (with codes) or `cannot_tell` for each definition. Do not record, and do not
work out, whether the statement's estimate held.

### 6.5 What counts as an error

An item is an **error** under a definition when your reading of the captures by the written rule
gives a different outcome type, `lower` or `upper` from the derived one. Give the codes for B in
`codes_B` and for A in `codes_A`, and what you read instead in the `true_` cells or in `note`.

| Code | Error |
|---|---|
| O1 | linkage: another presentation's rows are linked, or a re-formatted presentation is missed |
| O2 | event start: wrong `c0` or wrong statement date |
| O3 | at risk: marked at risk when not, or the other way round |
| O4 | class: an availability string or status read into the wrong class, moving a bound |
| O5 | `lower` is not the last capture seen not recovered |
| O6 | `upper` is not the first capture showing the event |
| O7 | competing event missed, or wrongly assigned |
| O8 | censoring: closed when it should be censored, censored when an event is visible, or the wrong reason |
| O9 | other; explain in `note` |

These are **flags, not errors**, entered in the column `note_codes`. They never count against the
pass rule. They are numbered N1 to N6 (in v0 they were F1 to F5), so that they cannot be confused
with amendment F1 of `PLAN.md`.

| Flag | Meaning |
|---|---|
| N1 | a tighter bound is visible: the Date of update on the first recovered row is earlier than `upper` (write it, as `YYYY-MM-DD`, in `dou_first_recovered`) |
| N2 | relapse: the thread goes back to `U` or `L` at a capture in the window that is within 90 days after `upper` |
| N3 | conflicting fields, for example Status Resolved while the Resolved note says Unavailable |
| N4 | the bracket spans an archive gap of more than 90 days |
| N5 | a class looks debatable but does not move a bound of B or A (it may move BL) |
| N6 | the derived value follows the written rule, but the text says something the rule cannot record, for example a notice that says the product is discontinued while it is not in the To Be Discontinued listing |

`cannot_tell` is for an item whose trace does not let you decide (a link you cannot judge, a
field that is cut). Say why in `note`. It goes to ADJ (section 5).

### 6.6 Worked examples (train period)

1. **Alogliptin 6.25 mg, 30 tablets, Perrigo.** The event "On backorder – expected release the
   week of 01/27/2020" (dated 2019-12-10) is first seen in the capture of 2019-12-29.
   - Class strip: `U | U A A A A A A A A R R`. The captures are 2019-12-29 and 2020-04-02 (the
     same text), then 2020-06-12 "Available" (Date of update 2020-05-12), and 2020-10-11 Resolved
     (Change date 10/05/2020).
   - Definition B: recovered, (2020-04-02, 2020-06-12], 71 days. Flag N1: 2020-05-12.
   - Definition A: recovered, (2020-09-30, 2020-10-11], 11 days.
   - A derived B bracket of (2019-12-29, 2020-04-02] would be O5 and O6: the second `U` capture
     was skipped.
2. **Loxapine 5 mg, Lannett.** The event "... scheduled for release in the March/April
   timeframe ..." (dated 2021-02-02) is first seen on 2021-03-18.
   - Class strip: `U U A A A A A A A | R R`. On 2021-04-12 the text changes to April/May, which
     starts a new event. The first event's outcome still follows the thread.
   - 2021-05-12 shows "Available" (Date of update 2021-05-06).
   - Definition B: recovered, (2021-04-12, 2021-05-12], 30 days. Flag N1: 2021-05-06. Ending
     the first event's outcome at the revision would be O6.
   - Definition A: recovered, (2021-11-30, 2022-10-04], 308 days: Status Resolved is first seen
     after the 2021 to 2022 archive gap. Flag N4.
   - The statement covers two presentations. The 25 mg one recovered later, so the
     statement-level B bracket shown beside is (2021-05-21, 2021-08-02]. That is not an error of
     this item.
3. **Ranitidine 150 mg, 60 capsules, Novitium.** The event "Product is currently unavailable.
   Estimated shortage duration is until Q1 2020" (dated 2020-01-07) is first seen on 2020-04-02.
   - Class strip: `U D D D D D`. On 2020-06-12 the presentation is in the To Be Discontinued
     listing (date there 04/03/2020).
   - Both definitions: discontinued, (2020-04-02, 2020-06-12], 71 days.
   - "Recovered" or "censored" would be O7.
4. **Fentanyl 2,500 mcg per 50 mL, Fresenius Kabi.** The event "Backordered. Next release
   December 2021." (dated 2021-10-08) is first seen on 2021-10-20 and re-confirmed on 2021-11-30
   (Reverified 2021-11-23).
   - Class strip: `U U | A A`. The next capture, 2022-10-04, shows "Available" (Date of update
     2022-09-14); 2022-10-06 is the horizon.
   - Definition B: recovered, (2021-11-30, 2022-10-04], 308 days. This is correct. Flag N4 (the
     archive gap) and flag N1 (2022-09-14). The bracket is not observable at 31 days.
   - Definition A: censored at 2022-10-06, `end_of_train`. The row is still Current there. This
     is correct.
   - The statement also covers the 1,000 mcg per 20 mL vial, which was still backordered on
     2022-10-06, so the statement-level B outcome shown beside is censored. That is not an error
     of this item.
5. **Leuprolide 7.5 mg kit, Abbvie.** The event "Available.  Next expected release mid-November"
   (dated 2020-10-07) is first seen on 2020-10-11.
   - The row is available at `c0` (letter `A`), so the event is `not_at_risk` under B.
   - Under A it is at risk, since the Status is Current. The row stays Current to 2022-10-06:
     censored at 2022-10-06, `end_of_train`.
   - A B outcome of "recovered at 2020-10-17" would be O3.
6. **Hydromorphone 10 mg/mL, Teva.** The event "Backorder - Product availabilty ETA Late August"
   (dated 2020-08-20) is first seen on 2020-08-24.
   - 2020-09-15 shows "Available" (Date of update 2020-09-04).
   - Definition B: recovered, (2020-08-24, 2020-09-15], 22 days. It is observable at 31 days.
     Flag N1: 2020-09-04.
   - Definition A: censored at 2022-10-06, `end_of_train`.
   - At 2021-05-12 the row is linked by NDC, because the generic name was re-formatted (it
     lost its ", USP"). Check the NDC; this is not O1.
   - In August 2021 the thread goes back to `U`. That is long after `upper`, so it is not a
     relapse flag (N2 covers 90 days), and it does not change this event's bracket.
7. **Sulfasalazine delayed-release 500 mg, bottle of 100, Pfizer.** The event "Next delivery and
   Estimated recovery: July 2020" (dated 2020-06-05) is first seen on 2020-06-12 and re-confirmed
   on 2020-07-08 (Date of update 07/01/2020, the same text).
   - Class strip: `O O O . . .` and so on to the horizon. The estimate is written in the
     Availability field, so the class is other, which is not recovered. From 2020-08-15 the row
     is absent while the generic is still Current.
   - Both definitions: censored at 2020-07-15, `absent_generic_current`.
   - "Recovered at 2020-08-15" would be O8: leaving the list while the generic is Current says
     nothing.
8. **Dexrazoxane 500 mg vial, Pfizer.** The event "Next Delivery: December 2019; Estimated
   Recovery: January 2020" (dated 2019-10-07) is first seen on 2019-10-20.
   - Class strip: `O O | r r`. On 2019-12-29 the text is revised (a new event; the first event's
     outcome still follows the thread). On 2020-04-02 the row is absent and the generic is
     listed as Resolved.
   - Both definitions: recovered, (2019-12-29, 2020-04-02], 95 days. Flag N4.
   - "Censored, `absent_generic_current`" would be O8: the generic is Resolved, not Current.

### 6.7 Pass rule and what happens on failure

- **Count.** A half passes when at most 2 of its 50 real items carry a confirmed error, counted
  for definition B and separately for definition A. That is the 95% rule of `PLAN.md` section 10
  applied to each half. The rate over all 100 items is reported as well.
- **Adjudication.** Every item marked `error` or `cannot_tell` under a definition goes to ADJ,
  one row per item and definition. ADJ decides `confirmed`, `rejected` or `unresolved`, and
  gives the cause of a confirmed error in a few words. An unresolved row does not count against
  the rule and is reported beside it.
- **Planted items** are excluded. An auditor who misses 2 or more of their planted items in a
  half re-checks their own real items of that half once before results are reported. Both passes
  are reported.
- **Train half.** It is audited before registration. If it fails, or the same code is confirmed
  twice with the same cause, the rule in `corpus.py` is fixed, never single items. The outcomes
  are then re-derived, the affected items and 20 fresh ones are re-audited, and the corpus is
  frozen and sealed only after that.
- **Re-audit commands.** Both write a set of their own (another `--out` and `--keys` than the
  first round), and each set is validated, scored and adjudicated like the first:
  - the fresh items:
    `audit_outcomes sheets --half train --round 2 --own <n> --shared <n> --planted <n>
    --exclude analysis/coling/out/audit/samples <the first round's outcome_train_sample.csv>`,
    with sizes that give 20 real items. The first round's items and their threads stay out
    of the draw;
  - the affected items:
    `audit_outcomes sheets --half train --items <the first round's key> --changed`, run once
    the first round is scored. It draws nothing: the items are those of the first round whose
    bracket, derived again, differs from the one the key records, and each goes to the
    auditor who had it. Planted items are added only with `--planted`.
- **Pass rule of a re-audit (provisional, for the owner to confirm).** The scorer allows
  confirmed errors up to 5% of the real items of the set, rounded down, for B and separately
  for A. That is 1 error among 20 fresh items, and none in an affected set of fewer than 20
  items. `PLAN.md` gives no rule for these two sets; this one is what the scorer applies, and
  it is confirmed or changed by the owner before a re-audit is scored.
- **Test half.** A failure after registration is handled the same way, logged as a dated
  amendment with the new sealed hash, before the evaluator runs.
- **Flags** (N1 to N6) are counted and reported. A flag does not change the rule after
  registration. Before registration, ADJ may ask for a rule change when the same flag has the
  same cause in several train-half items; the change is then treated like a failure above.

## 7. Task C: minimal-pair audit

The audit checks the literal gold of the minimal pairs. The authors' predictive readings of
minimal pairs are not collected in October.

### 7.1 Sample and what you see

- **Sample.** 100 E5 items, stratified by factor: certainty marker, surface form, granularity,
  stale against fresh, distractor date, and silent. At most 2 per seed.
- **Seeds.** The pairs are made from the seed statements of `sample_pair_seeds.csv` (section
  10): statements of the seven dated strata, from the train period. One form is the
  exception: the seeds of the relative form are statements dated 2023-01-01 or later, because
  the labelling samples leave almost none of the train period (in the draw of 1 October, five
  of its six statements are in a labelling sample or in appendix A). Only the text of such a
  seed is used, and no outcome of it is read. The list marks these seeds (`period` reads
  `test`), and no model is called on a pair made from one of them until amendment F1 of
  `PLAN.md` is tagged, as for every test-period item.
- **Assignment.** 45 to A1, 45 to A2, and 10 audited by both. Each auditor also gets 5 planted
  items, where the generator's gold was corrupted in one field by a seeded rule. The key is
  kept apart from the sheets (section 10); nobody opens it, and the scoring script reads it
  (section 5).
- **What you see.** The seed entry and its gold; the edited entry (fictitious names); the factor
  and level; the gold of the edited entry in the fields of section 3.4; and `attested_text`, a real
  notice that uses the inserted form.

### 7.2 What you check

1. **Label.** For each gold field (`statement_type`, interval or abstain, `certainty`, `stale`,
   distractors): does the edited entry entail it under sections 3.6 to 3.10? Mark each field 1 or
   0, and give the correct value when 0.
2. **Minimal.** Does the edit change only the named factor? Its gold may differ from the seed's
   only as that factor implies.
3. **Attested.** Does the inserted marker or form appear in `attested_text`, with only months and
   numbers changed?
4. **Natural** (secondary; not part of the pass rule). Would the edited entry look unremarkable on
   the FDA list?

An item is an **error** when any label field is 0, or minimal is 0, or attested is 0.

### 7.3 Worked examples

The seed is Cefoxitin, Fresenius Kabi, dated 2020-08-13, "Backordered. Next release October
2020.". Its gold is `next_delivery`, 2020-10-01 to 2020-10-31, `asserted`, not stale.

| Factor, level | Edited entry | Generator gold | Verdict |
|---|---|---|---|
| certainty, estimated | "Backordered. Next release expected October 2020." | next_delivery, 2020-10-01 to 2020-10-31, estimated, not stale | ok ("Next release expected <MON> <YYYY>" is attested) |
| certainty, TBD | "Backordered. Next release date not available at this time." | next_delivery, abstain, undetermined, not stale | ok |
| granularity, mid | "Backordered. Next release mid-October 2020." | next_delivery, 2020-10-01 to 2020-10-31, asserted | **error**: the interval must be 2020-10-11 to 2020-10-20 (C3) |
| stale | the same text; Type of update Reverified, dated 2020-11-16 | next_delivery, 2020-10-01 to 2020-10-31, asserted, stale | ok |
| distractor, expiry | "4 months dating available by request (expiry 12/31/2020). Backordered. Next release October 2020." | unchanged, plus distractor `expiry` | ok |
| surface form, no year | "Backordered. Next release October." | next_delivery, 2020-10-01 to 2020-10-31, asserted | ok (C8) |
| silent | "Backordered." | none, abstain, no_statement | ok |
| certainty, TBD | "Unavailable. Estimated recovery TBD." | recovery, abstain, undetermined | **error**: not minimal, because the type and the status wording changed too |
| certainty, "as it is released" | "Backordered. Product will be made available as it is released." | next_delivery, abstain (`no_date`), undetermined | ok (3.8; D1) |

### 7.4 Pass rule

This is the 95% rule of `PLAN.md` section 10, with the two further checks of 7.2 (minimal and
attested) counted as errors too. It passes when at least 95 of the 100 real items are free of
confirmed errors. Otherwise the generator is fixed, the failing template or factor is
dropped or corrected, and a fresh 100 are audited, with the fix logged. Planted items are excluded
from the 100.

## 8. Statistics to report

All intervals are 95% percentile bootstrap intervals over items: 2,000 draws, with seed 20261001.
Every table gives n. (Agreement statistics resample items. The episode-level resampling of
`PLAN.md` applies to the analyses against outcomes.)

### 8.1 Task A (both annotators, before adjudication)

- **Month offsets.** For a date `d` and anchor `a`, the offset is
  `12 × (year(d) − year(a)) + (month(d) − month(a))`, computed for `start` and for `end`.
- **Krippendorff's alpha** (interval metric, two coders) on the start offset and, separately, on
  the end offset. It is computed over the items where both annotators gave an interval. This is
  the study's headline agreement figure and, on the check set, the pilot gate.
- **Identical intervals.** The share of items on which the two sheets give the same `start` and
  the same `end`. Two abstentions count as identical; an interval against an abstention does
  not. It is reported beside alpha everywhere, and beside the gate.
- **Secondary.** Alpha on day offsets (`start − a` and `end − a`, in days).
- **Cohen's kappa** over all items, on:
  - `abstain` (yes or no);
  - `certainty` (4 classes);
  - `statement_type` (5 classes);
  - `stale` (derived from the intervals, reported for completeness);
  - any distractor (yes or no).

  Each kappa is shown with the raw agreement and both annotators' marginal shares, since kappa
  moves with prevalence.
- **By stratum and by period.** n, raw agreement and the kappas for every cell, and alpha when a
  stratum has at least 10 pairs of intervals. Below that no alpha is given. The kappas of a
  cell with few items stay in the output and are read with the raw agreement and n beside
  them; a kappa is undefined, and written as null, when both annotators gave one and the
  same value on every item of the cell.
- **Adjudication.** Counts of `slip` and `gap` decisions, by field.
- **Time.** The mean seconds per item, from the start and end times of each sitting, written in
  the sheet's header.
- **Pilot and check sets.** The same statistics, labelled by guide version, in an appendix.

`PLAN.md` section 10 registers the alpha on the start and end month offsets, with day offsets as
a secondary, and the kappas on abstention, certainty class and statement type. The kappas on
`stale` and on distractors are reported in addition.

### 8.2 Task B

- Agreement rate for each definition (B, A): (real items without a confirmed error) / (real
  items), with a Wilson 95% interval. It is given raw and reweighted to the pool, by half (train,
  test) and over both, with the size of the pool and of the excluded part.
- Counts by error code, per definition, and by flag. The test half is reported only as total
  counts of each code and flag. There is no breakdown by outcome type, width or stated period
  until the registered evaluator has run.
- Rows left unresolved by ADJ.
- Double-audited items: raw agreement on `ok` against `error`. Cohen's kappa is given only when
  both verdicts occur; with a rule that passes, the shared items are usually all `ok`.
- Planted items: the number each auditor caught, per half, and whether the re-check of section
  6.7 was needed.

### 8.3 Task C

- The share of the 100 real items free of confirmed errors, with a Wilson 95% interval, overall
  and by factor.
- Counts of the failures of each check: each label field, minimal, attested; and natural,
  separately.
- Double-audited items: raw agreement, and kappa when both verdicts occur. Planted items: the
  share caught. An auditor who misses 2 or more of their 5 re-checks their own real items once;
  both passes are reported.

### 8.4 Tasks D and E

- **D.** The date of the check, the number of strings read in each class (available, limited,
  moved out of available by the 1 October rule change), the number rejected, and the number of
  moved-out strings that the checker would have kept. Section 12.1 gives them.
- **E.** The share of the 100 reference readings without a confirmed error, with a Wilson 95%
  interval; the errors by form class and by code K1 to K4; the number with `start_differs`; raw
  agreement on the 10 shared items.

## 9. Sheet layout

One CSV file (UTF-8, comma-separated, every cell quoted, a header row) per annotator per task.

- **Editing.** Fill a copy of the sheet, kept under `external_data/annotation/<task>/`
  (section 10), and leave the blank where the sheet builder wrote it: the checks compare the
  two. Spreadsheet software may be used. Import every column as text, so that dates and the
  `YYYY-MM` shorthand are not converted, and save back as CSV.
- **Header lines.** The rows above the header row begin with `#` and read `# key: value`. They
  give the task or half, the seed, the guide version and hash, the values each coded column
  takes (task A), and, for task B, the `corpus.py` hash and the horizon. Keep them. The scripts
  read these rows by position, so a `#` inside an entry is harmless.
- **Times.** Two header lines are yours to fill, with the time as `HH:MM`. The two builders
  name them differently:
  - task A sheets (pilot, check, reserve, literal): `# sitting_start:` and `# sitting_end:`.
    For a further sitting, add another pair of these lines under the first. The validator
    rejects a sheet without them.
  - task B sheets: `# session_start:` and `# session_end:`. For more than one sitting, give
    the times of each on the same line, separated by semicolons. The validator warns when
    they are missing.
- **Guarded cells.** A shown cell that begins with `=`, `+`, `-` or `@` is written with a leading
  apostrophe so that it is not taken for a formula. The apostrophe is not part of the entry.
- **Computed columns and checks** are not in the sheet. Run the validator on your file before
  you submit it; it lists the rows to fix. From the repository root, with `PYTHONPATH=.`:
  - task A: `python -m analysis.coling.audit_sample validate <sheet>`. It finds the blank by
    the header lines of the sheet (`--blank` names another) and warns when it finds none:
    the list of items and the shown cells are then unchecked;
  - task B: `python -m analysis.coling.audit_outcomes validate <sheet> --blank <blank sheet>`.

  The scripts of tasks C and E give theirs in their docstrings when they are written.
- **Submission checks.** For task A, `agree` validates both sheets against the blanks again
  and refuses a sheet that was filled in place (it is then the blank's own file) and one
  whose blank is missing or is not the file the manifest records. For task B, `score`
  validates both sheets against the blanks, reads the key only when both pass, and refuses a
  set whose blanks or key are not the files its manifest lists.

**Task A: `literal_<A1|A2>.csv`** (the pilot and check sheets, `pilot_`, `check_` and
`reserve_`, have the same layout; all are written by `audit_sample.py`)

| Column | Shown or entered | Content |
|---|---|---|
| `item_id` | shown | random id; reveals neither stratum nor sample |
| `drug`, `company`, `presentation` | shown | as in the entry block |
| `therapeutic_category`, `initial_posting_date` | shown | context only (section 3.3) |
| `type_of_update` | shown | New, Revised or Reverified |
| `date_of_update` | shown | the anchor, ISO |
| `availability_information`, `related_information`, `reason_for_shortage` | shown | verbatim |
| `statement_type`, `start`, `end`, `abstain`, `abstain_reason`, `certainty`, `quote`, `distractor_roles`, `distractor_quotes`, `hard`, `note` | entered | section 3.4 |

The agreement script adds `stale`, `start_offset_m`, `end_offset_m`, `start_offset_d`,
`end_offset_d` and `check` (sections 3.9, 3.12 and 8.1) in its own output
(`<task>_labels.csv`, beside `<task>_agreement.json`). It lists the disagreements in
`<task>_disagreements.csv` for the pilot and the check sets, and in `literal_adjudication.csv`
for the literal task; ADJ fills that sheet with the decided label, `adj_decision` (`slip` or
`gap`) and `adj_note`. The gold file `literal_gold.csv` has `item_id`, the entered columns
(dates written in full), `adj_decision` (`agree`, `slip`, `gap`) and `adj_note`. On an item
the annotators agreed on, the gold takes the shorter of the two quotes, `hard` if either set
it, both notes, and A1's distractor quotes.

**Task B: `outcome_<A1|A2>_<train|test>.csv`** (one row per item, written by
`audit_outcomes.py`; the capture rows of section 6.3 are in the companion file
`outcome_<half>_traces.csv`, and the same items with their traces are in
`outcome_<A1|A2>_<half>_items.txt` as text)

| Column | Shown or entered | Content |
|---|---|---|
| `audit_id` | shown | random id; planted items look the same |
| `generic`, `company`, `presentation`, `statement_text`, `statement_date`, `c0`, `followed_to` | shown | section 6.3; `followed_to` is the horizon |
| `class_strip` | shown | section 6.3 |
| `derived_B_type`, `derived_B_lower`, `derived_B_upper`, `derived_B_width`, `derived_B_censor`, `derived_B_exit` | shown | definition B; `_exit` is the exit date of section 6.1 |
| `derived_A_type`, `derived_A_lower`, `derived_A_upper`, `derived_A_width`, `derived_A_censor`, `derived_A_exit` | shown | definition A |
| `group_n_presentations`, `group_B_type`, `group_B_lower`, `group_B_upper`, `group_A_type`, `group_A_lower`, `group_A_upper` | shown | the statement-level outcome, for information; not audited |
| `verdict_B`, `verdict_A` | entered | `ok`, `error`, `cannot_tell` |
| `codes_B`, `codes_A` | entered | semicolon lists, O1 to O9, one list per definition; only with `error` |
| `true_B_type`, `true_B_lower`, `true_B_upper`, `true_A_type`, `true_A_lower`, `true_A_upper` | entered | only when the verdict is `error`: what you read instead |
| `note_codes` | entered | the flags: semicolon list, N1 to N6 |
| `dou_first_recovered` | entered | `YYYY-MM-DD`, exactly when `note_codes` has N1 |
| `note` | entered | free text; required for `cannot_tell` and for O9 |

Traces file columns: `audit_id`, `capture_date`, `capture` (the 14-digit timestamp), `window`
(`before`, `c0` or `after`), `present` (`yes`, `no`, `other_thread` or `other_thread_withheld`),
`linked_by` (`key` or `ndc`), `generic`, `company`, `presentation`, `status`, `type_of_update`,
`date_of_update`, `availability_information`, `related_information`, `resolved_note`,
`change_date`, `date_discontinued`, `same_text` (1 when the row's statement text is the
event's), `generic_state` (`current`, `resolved` or `unlisted`), `discontinuation_listing`,
`discontinuation_date`, `class_letter`, `gap_before_days`.

The adjudication file `outcome_<half>_adjudication.csv` has one row per item and definition
that an auditor marked `error` or `cannot_tell`, with both auditors' entries. ADJ fills
`decision` (`confirmed`, `rejected` or `unresolved`), `confirmed_codes`, `cause` and `adj_note`;
a confirmed error needs its codes and its cause. The scorer
(`python -m analysis.coling.audit_outcomes score`) writes this file on its first run and reads
it, filled, on its second.

**Task C: `pairs_<A1|A2>.csv`**

| Column | Shown or entered | Content |
|---|---|---|
| `pair_id`, `seed_id`, `factor`, `level` | shown | |
| `seed_entry`, `seed_gold` | shown | the seed's entry block and gold |
| `edited_entry` | shown | the edited entry block (fictitious names) |
| `gold_statement_type`, `gold_start`, `gold_end`, `gold_abstain`, `gold_certainty`, `gold_stale`, `gold_distractor_roles` | shown | the generator's gold |
| `attested_text` | shown | a real notice using the inserted form |
| `ok_type`, `ok_interval`, `ok_certainty`, `ok_stale`, `ok_distractors`, `minimal`, `attested`, `natural` | entered | 1 or 0 |
| `correct_value`, `note` | entered | when a field is 0 |

The agreement script derives the verdict: `error` if any of the checks before `natural` is 0.

**Task D: `availability_strings.csv`**, written by `corpus.py`

| Column | Shown or entered | Content |
|---|---|---|
| `string` | shown | the normalised Availability information text, bare |
| `class_after_fix`, `class_before_fix` | shown | the class under the present rule and under the rule before 1 October |
| `n_rows` | shown | how many capture rows carry the string |

The list was read as written and nothing was entered in it (section 12.1). If the check is
ever repeated with marks, they go into a copy with three more columns: `ok` (`yes` or `no`: is
`class_after_fix` right?), `should_be` (`available`, `limited` or `other`, when `ok` is `no`)
and `note`.

**Task E: `reference_<A1|A2>.csv`**

| Column | Shown or entered | Content |
|---|---|---|
| `item_id` and the entry-block columns of task A | shown | |
| `rule_statement_type`, `rule_start`, `rule_end`, `rule_stale` | shown | the frozen rule reading; `rule_end` is the `stated_end` used in E3 |
| `verdict` | entered | `ok`, `error`, `cannot_tell` |
| `codes` | entered | K1 to K4 (section 12.2) |
| `true_end` | entered | when `error`: the right last day, or blank if the target gives no date |
| `start_differs` | entered | 1 or 0 |
| `note` | entered | |

## 10. Files, hashes and sealing

The folders below are the scripts' defaults on 1 October, as `PLAN.md` section 14 lists them.

- **Blank sheets.** The task A sheets (pilot, check, reserve, literal) go to
  `analysis/coling/out/audit/`, with the matching item file for the reading harness
  (`<task>_items.jsonl`); the task C and E blanks are to go there too, once their scripts are
  written. They contain only public notice text, rule readings (task E) and fictitious pairs
  (task C). The task D list is `analysis/coling/out/availability_strings.csv`, where
  `corpus.py` writes it. Train-half task B sheets and traces go to the folder the builder is
  given (`analysis/coling/out/audit_outcomes/` unless another is named); they hold
  train-period outcomes, which are open.
- **Test-half task B sheets, traces and key** go only to `external_data/sealed/audit/`. They are
  filled in there and stay there until the registered evaluator has run.
- **Work in progress.** Each annotator keeps their filled sheet under
  `external_data/annotation/<task>/` (git-ignored) until both have submitted.
- **Submission.** The agreement script copies each submitted task A sheet to
  `analysis/coling/out/audit/submitted/` and records its sha256 in
  `analysis/coling/out/audit/manifest.json`, with the hashes of the agreement output and later
  of the gold; for task B the scorer writes its files beside the sheets. The pair is committed
  together. The gold hash is recorded before any reader output on those items is opened.
- **Sample lists.** The list of ids of every sample and its sha256 go into the manifest and
  into the registration record. The lists of the pilot, the check set, the reserve and the
  literal sample are `analysis/coling/out/audit/samples/sample_<name>.csv`; each carries
  `event_id`, `statement_group_id` and `thread_id` and nothing else (no stratum and no form
  class), so that a later draw can exclude it. That folder is where the task B builder looks
  for them (`--exclude`). The train-half outcome sample is `outcome_train_sample.csv` beside
  its sheets, with the same three columns. The task E sample is the column `reference_check`
  of the eligible list (`analysis/coling/out/eligible_e3.csv`).
- **Later lists.** Once the train-half outcome sample is final, `audit_sample.py draw-later`
  writes three more lists to `analysis/coling/out/audit/samples_later/`. Each has the three
  id columns, `draw_rank` (the place of the statement in the seeded draw: whoever uses a list
  walks it in that order) and `period` (`train`, or `test` for a statement dated 2023-01-01
  or later). Each leaves out the first draw, the outcome sample, appendix A with its rule on
  quoted phrases (A.4), and the lists before it, by statement and by text (the same generic,
  company and normalised text at another date). Each also leaves out the statements that read
  like an item of the first draw, which A1 and A2 label:
  - a statement whose whole text is that of an item, word for word and punctuation aside,
    whatever the drug or the company (a text with no word is not compared);
  - a statement of the same generic and company, dated the same day as an item, for which
    the rule reader finds the same statement type and the same period: the item's notice on
    another presentation, as when two presentations differ by a typing error.

  A statement that only shares a wording with an item (another month or number) can be on a
  list. The three lists:
  - `sample_incontext_pool.csv`: the in-context pool, 50 fit-split statements at risk under
    B, with a dated form and not stale at issue, taken in turn over the dated forms; one per
    masked template and one per episode;
  - `sample_dev_prompt.csv`: 60 dev prompt items, dev-split statements at risk under B, taken
    in turn over the strata of section 3.2, under the two caps of that section;
  - `sample_pair_seeds.csv`: 100 pair seeds for the minimal-pair generator, statements of the
    seven dated strata that are not stale at issue, one per masked template and at most 3 per
    episode: 22 of month and year and 13 of each other stratum, a shortfall going to month
    and year. They are train-period statements, except those of the relative stratum
    (section 7.1), which carry `test` in `period`.
- **Lists that are fixed.** A draw repeated on the same inputs writes the same bytes. When the
  guide or the events table has changed so that a list on disk would hold other statements,
  `draw` stops and writes nothing until the sample is named under one of two flags:
  `--fixed <sample>` keeps the list on disk and draws the others around it; `--replace
  <sample>` takes the new list (with `--sheets <sample>` when its sheets are on disk). From
  the moment a sheet of a list is handed out, or a later draw has left the list out, the
  list is kept with `--fixed`. The outcome-audit builder has the matching rule: it does not
  write over a final set without `--replace`. So has `draw-later`: when one of its three
  lists on disk would hold other statements, or another order, it stops and writes nothing
  until `--replace` is given.
- **Sheets and a revised guide.** A sheet names, in its header, the guide it was written
  under (version and hash). The task A sheets of a set that is labelled under a revised guide
  are written again from the list on disk (`sheets --task check` after the pilot meeting):
  the items stay, the guide line changes. The train-half task B sheets are not written again:
  the set drawn under the draft is validated and scored as it stands after the guide becomes
  v1, since no check compares its guide line with the guide on disk, and section 6 is not
  among the parts the pilot meeting revises.
- **Item keys of task A.** `analysis/coling/out/audit/keys/<task>_key.csv` links each
  `item_id` to its statement, stratum, form and period, for the agreement script. The form is
  a rule reading, so A1 and A2 do not open this folder (section 2, rule 1).
- **Planted-error keys** are written under `external_data/annotation/keys/` (git-ignored; the
  task B builder writes there unless `--keys` names another folder), and for the test half
  under the sealed folder. Nobody opens them; the scoring script reads them after both sheets
  are returned. The train-half and task C keys are committed with the scores; the test-half
  key leaves the sealed folder only after the registered evaluator has run.

## 11. ARR Responsible NLP checklist statement

Draft for section D of the form (human annotators; check the item wording on the current form).
The bracketed parts are for the authors to confirm.

> All human labels in this paper were produced by the authors: two annotators, and a third author
> who adjudicated. No crowdworkers or other participants were recruited, and no one was paid for
> annotation beyond their normal [salary or studentship]. The annotators labelled public notices
> from the US FDA drug-shortage list, a US federal government work that contains no personal
> information; the list's company contact column was removed before annotation and release. A
> few notices name a company e-mail address or telephone number in their text. E-mail addresses
> are masked in the outcome-audit files; the literal-task sheets show each notice as the models
> read it, and company telephone numbers remain as the FDA published them [confirm what the
> released files mask]. The full guideline, including the time conventions, blinding rules,
> pilot and adjudication procedure, is released with the data (Appendix [X]). Because the
> annotators are authors
> labelling public, non-personal text, and no data about people were collected, we did not seek
> ethics-board review [confirm that this matches institutional policy]. Both annotators are
> fluent readers of English with a background in [NLP research]. Because they knew the study's
> hypotheses, they labelled blind to model outputs, to later versions of each notice and to
> realised outcomes, and the literal labels were frozen before any model output on those items
> was inspected; agreement is reported before adjudication.

The checklist's item on assistance in writing and coding is answered on 10 October, as `PLAN.md`
section 12 schedules. Its answer has to cover how this guideline was drafted.

## 12. Two short checks

### 12.1 Task D: availability strings (ADJ; done on 1 October, before the corpus is frozen)

Definition B rests on the class of the Availability information. Every distinct string that the
rule reads as available or limited, or read as available before the rule change of 1 October,
is read once, bare.

1. **The list.** `corpus.py` writes `analysis/coling/out/availability_strings.csv` (its
   docstring gives the command). Each row is one normalised string with its class under the
   present rule, its class under the rule before 1 October, and the number of capture rows
   that carry it. No drug, company, date or capture is shown, so the check reveals no
   statement's outcome.
2. **What is asked of each string.** Does it say that the product can be had now?
   - Classed `available`: it must say so. If the word is future, estimated, negated or about
     something else, the string is rejected.
   - Classed `other` after being `available` before the rule change: it must not say so. If
     it does, the rule moved it out wrongly.
   - Classed `limited`: it must report limited supply. These strings matter for the BL
     sensitivity analysis, and for B only when one in fact reports full supply.
3. **What a rejection does.** A rejected string that the rule classes available or limited
   goes into the frozen list in `corpus.py` (`REJECTED_AVAILABLE`) and is then classed other.
   The list can only move a string to other. A string that belongs in another supply class,
   which includes one that the rule moved out and the checker would keep, is reported to the
   owner of `corpus.py`, who changes the rule before the freeze or records the difference.
4. **Result (1 October).** ADJ read the whole list as `corpus.py` wrote it that day (sha256
   prefix `da0bde1baac48473`): 910 strings, of which 233 are classed available, 647 limited,
   and 30 were moved out of available by the rule change. ADJ found the classes in order: no
   string is rejected, and none of the 30 is moved back. `REJECTED_AVAILABLE` is therefore
   empty and the rule stands as it is. The list was read as a whole; no mark per string was
   kept.
5. **If the list changes.** The freeze build writes the list again. If its hash is not the
   one above, ADJ reads the strings that are new or whose class changed before the corpus is
   frozen, and step 4 is updated.

**Limits.** The list holds the strings classed available or limited, now or before the rule
change. A string classed unavailable is not on it, even when it also contains "available" or
"in stock": 105 distinct strings in the 1 October build, most of them negations of the kind
"not available", a few reporting supply and a backorder together. A row with such a string
counts as not recovered under B.

### 12.2 Task E: reference readings (A1 and A2, after both task A sheets are in)

E3 takes the end of each statement's stated period (`stated_end`), and the list of eligible
statements, from the frozen rule reading. This check measures how often that reading is right.
It changes no item: the eligible list and every `stated_end` are registered before it.

- **Sample.** 100 statements drawn at random, with seed 20261001, from the registered list of
  E3-eligible statements (`PLAN.md` section 3); the dataset builder marks them in the column
  `reference_check` of the eligible list. Eligible statements are dated 2023 to 2025, so the
  pilot and the check sets, which are train-period, cannot be among them. No statement of the
  literal sample may be on a task E sheet, so that no rule reading of an item you labelled is
  shown before the task A gold is hashed (section 2, rule 1). The draw leaves such statements
  out: `dataset.py` reads the four lists of the first draw (and leaves out the same text at
  another date), and its counts file marks the subset as final only when all four lists were
  read and every id on them is a statement of the build. The eligible list is therefore built
  again after the first draw. If the registered subset is not final, a statement that is in
  both samples is left off the task E sheets, the check then has fewer than 100 items, and
  the number left off is reported.
- **Assignment.** 45 to A1, 45 to A2, 10 checked by both.
- **When.** After both task A sheets are submitted, since the sheet shows rule readings. The
  sheets are returned and hashed before A1 or A2 see any E3 output and before the registered
  evaluator runs. ADJ adjudicates task A before opening a task E sheet.
- **What you see.** The entry block of section 3.3, and the rule reading: type, start, end and
  the stale flag. No outcome is shown. Blinding rules 2 and 3 apply.
- **What you check**, with sections 3.6 and 3.7:
  1. Is the rule's statement the target statement?
  2. Does the target give a date or a period?
  3. Is `rule_end` the last day of that period?
  4. Does the period end on or after the Date of update (not stale)?
- **Verdict.** `ok` when all four hold; `cannot_tell` when the text does not let you decide
  (say why in `note`). Otherwise `error`, with a code:

  | Code | Error |
  |---|---|
  | K1 | wrong target: the period read belongs to another statement of the entry |
  | K2 | right target, wrong last day |
  | K3 | the target gives no date or period; the reading should abstain |
  | K4 | the period ends before the Date of update, so the statement is stale and should not be eligible |

  Give `true_end` when you mark an error. Set `start_differs` to 1 when the last day is right
  but the first day is not; this is not an error, because E3 does not use the start.
- **Example.** Bupivacaine and epinephrine, Hospira, 2019-10-07, "Next Delivery and Estimated
  Recovery: June 2021", with the rule reading recovery, 2021-06-01 to 2021-06-30, not stale:
  `ok`.
- **Limits.** The check covers statements the rule read as dated. A dated statement that the
  rule failed to read is not in the eligible list and so not in this sample; task A measures
  that on its own items. Most eligible statements are plain month-and-year (about five in six
  in the build of 29 September; `PLAN.md`, "Changes", item 4), so the sample says little about
  any single other form.

## Appendix A. Statements excluded from every sample

A row below names a generic, a company and a statement date. It excludes every statement of
that generic and company dated that day, and every statement of that generic and company with
the same normalised text at another date. The samplers read the rows from this file
(`audit_sample.guide_exclusions` and `audit_outcomes.guide_examples`): the three cells of
every row of a three-column table under this heading, with the dates found in the third cell.
The lists of rows are kept in three-column tables: the first reader skips a table of another
width, and the second takes the first three cells of any row with three cells or more, so no
other table of this appendix has a date in its third column. Section A.4 adds a rule that
needs no row.

### A.1 Worked examples

| Generic | Company | Statement date |
|---|---|---|
| Bupivacaine Hydrochloride and Epinephrine Injection, USP | Hospira, Inc. | 2019-10-07 |
| Cefoxitin for Injection, USP | Fresenius Kabi USA, LLC | 2020-08-13 |
| Hydromorphone Hydrochloride Injection, USP | Teva Pharmaceuticals | 2020-08-20 |
| Lidocaine Hydrochloride (Xylocaine) Injection with Epinephrine | Fresenius Kabi USA, LLC | 2021-05-19 |
| Lidocaine Hydrochloride (Xylocaine) Injection | Fresenius Kabi USA, LLC | 2021-08-25 |
| Loxapine Capsules | Lannett Company, Inc. | 2021-02-02 |
| Nefazodone Hydrochloride Tablets | Teva Pharmaceuticals | 2021-11-17 |
| Alogliptin Tablets | Perrigo Company PLC | 2019-10-09 and 2019-12-10 |
| Azacitidine for Injection | Dr. Reddy's Laboratories, Inc. | 2021-01-12 |
| Triamcinolone Acetonide Injectable Suspension | Novartis | 2022-09-30 |
| Hydroxyzine Pamoate Oral Capsules | Impax Laboratories | 2019-12-13 |
| Guanfacine Hydrochloride Tablets | Mylan Pharmaceuticals Inc. | 2020-03-20 |
| Cefotaxime Sodium Injection | Hikma Pharmaceuticals USA, Inc. (formerly West-Ward) | 2019-09-09 |
| Levetiracetam Immediate-Release Oral Tablets, USP | Solco Healthcare US, LLC | 2019-04-02 |
| Levetiracetam Immediate-Release Oral Tablets, USP | Lupin | 2019-04-02 |
| Cefoxitin for Injection, USP | WG Critical Care | 2019-05-03 |
| Cisatracurium Besylate Injection | Meitheal Pharmaceuticals, Inc. | 2020-04-08 |
| Tacrolimus Capsules | Mylan Pharmaceuticals Inc. | 2020-06-02 |
| Furosemide Injection, USP | Baxter Healthcare | 2020-06-02 |
| Heparin Sodium and Sodium Chloride 0.9% Injection | Fresenius Kabi USA, LLC | 2021-09-23 |
| Indigotindisulfonate Sodium Injection | American Regent | 2022-08-24 |
| Alfentanil Injection | Hospira, Inc. | 2020-03-25 |
| Ranitidine Tablets/Capsules | Novitium Pharma LLC | 2020-01-07 |
| Fentanyl Citrate (Sublimaze) Injection | Fresenius Kabi USA, LLC | 2021-10-08 |
| Leuprolide Acetate Injection | Abbvie | 2020-10-07 |
| Sulfasalazine Tablets | Pfizer Pharmaceuticals | 2020-06-05 |
| Dexrazoxane Injection | Pfizer Pharmaceuticals | 2019-10-07 |

The outcome examples of section 6.6 are these events, so that a test can pin their derived values
to `analysis/coling/out/outcomes_train.csv.gz`:

| Example | `event_id` |
|---|---|
| 1 Alogliptin | `E67ea1febd54f` |
| 2 Loxapine | `Eafaaeed0571f` |
| 3 Ranitidine | `E48ae38b90804` |
| 4 Fentanyl | `E9330db7817b8` |
| 5 Leuprolide | `E90906000950a` |
| 6 Hydromorphone | `E2b715e04fcab` |
| 7 Sulfasalazine | `E376aca9fd75f` |
| 8 Dexrazoxane | `E8bcddf5be163` |

### A.2 Sources of phrases quoted in sections 3 and 7

Train-period statements on the shortage listing from which a phrase of several words is quoted;
the phrase follows the date. Bare date forms ("Mar 21", "Nov-22", "1st quarter 2020", "the June
timeframe") and phrases that several statements share ("Product will be made available as it
is released", "Next Delivery: May 2021; Estimated Recovery: July 2021", "available for order")
have no row here. A statement whose whole text is such a phrase is excluded by A.4; the cap on
masked templates limits the statements that only contain one. Four quoted phrases come from the To
Be Discontinued listing, which is outside the sampling frame, and need no entry (the final date
of availability in section 3.6, and three of the distractor examples of section 3.10).

| Generic | Company | Statement date, and the phrase |
|---|---|---|
| Leucovorin Calcium Lyophilized Powder for Injection | Sagent Pharmaceuticals | 2020-03-31: "Estimated availability Dec-2020" |
| Tacrolimus Capsules | Glenmark Pharmaceuticals | 2021-01-13: "Anticipated availability - April 2021" |
| Olmesartan Medoxomil Tablets | Aurobindo Pharma | 2019-03-12: "Available by 4/5/19" |
| Ketorolac Tromethamine Injection | Baxter Healthcare | 2021-08-25: "Stocked Out, December 2021" |
| Hydrocortisone Tablets, USP | Pfizer Pharmaceuticals | 2021-03-12: "Next Delivery: May 2021; Estimated Recovery: TBD" |
| Misoprostol Tablets | Pfizer Pharmaceuticals | 2021-05-07: the same |
| Methyldopa Tablets | Accord Healthcare Inc. | 2019-06-07: "Estimated shortage until March 2020" |
| Leuprolide Acetate Injection | Abbvie | 2021-04-12: "by the end of April 2021" |
| Propofol Injectable Emulsion | Hikma Pharmaceuticals USA, Inc. (formerly West-Ward) | 2020-12-15: "January – February 2021 timeframe" |
| Valproate Sodium Injection, USP | Hikma Pharmaceuticals USA, Inc. (formerly West-Ward) | 2020-12-30: the same |
| Disulfiram Tablets | Alvogen, Inc. | 2020-04-01: "end of May/early June 2020" |
| Tacrolimus Capsules | Sandoz | 2020-11-13: "Feb/Mar 2021" |
| Midazolam Injection, USP | Gland Pharma Limited | 2021-03-30: "April/May 2021" |
| Bupivacaine Hydrochloride Injection, USP | AuroMedics Pharma LLC (mfd. by Aurobindo Pharma Ltd.) | 2021-04-01: "April/May 21" |
| Echothiophate Iodide (Phospholine Iodide) Ophthalmic Solution | Fera Pharmaceuticals | 2022-06-01: "June 1st, 2022" |
| Hydroxyzine Pamoate Oral Capsules | Pfizer Pharmaceuticals | 2020-06-05: "7/1/2020" |
| Ondansetron Hydrochloride Injection | Fresenius Kabi USA, LLC | 2020-11-16, 2020-12-30, 2021-03-15, 2021-04-30, 2021-05-19: "(expiry 6/30/2021)" |
| Fluvoxamine ER Capsules | Teva Pharmaceuticals | 2021-04-29: "Projecting backorder in May" |
| Piperacillin and Tazobactam (Zosyn) Injection | Wockhardt | 2019-10-09: "Backordered material arrived in end of September" |
| Tacrolimus Capsules | Accord Healthcare Inc. | 2019-08-01, 2019-12-12: "Shortage duration from July 2019 to March 2020" (the second date has the same wording with another end) |
| Kit for the Preparation of Technetium Tc 99m Sulfur Colloid Injection | Sun Pharmaceutical Industries Inc. | 2021-10-08: "Limited inventory available in November 2021", "Recovery unknown at this time" |
| Paclitaxel Injection (protein-bound particles) | Bristol Myers Squibb Co. | 2021-10-06: "will provide an update in" |
| Doxycycline Hyclate Injection | Fresenius Kabi USA, LLC | 2020-10-08: "Next release expected October 2020" (section 7.3) |
| Hydralazine Hydrochloride Injection, USP | Fresenius Kabi USA, LLC | 2020-10-08: the same |

### A.3 The fixed test item of the prompt harness

The item that `read.py` renders to pin its templates is built on this statement ("Expected
recovery April 2020").

| Generic | Company | Statement date |
|---|---|---|
| Anagrelide Hydrochloride Capsules | Teva Pharmaceuticals | 2020-03-17 |

### A.4 Statements whose whole text is a quoted phrase

A statement is also excluded, with no row above, when its whole text is a phrase that this
guide quotes, whatever the drug, the company and the date (owner's decision of 1 October).

- **Phrase.** The words between two double quotation marks in section 3 or in section 7, the
  worked-example tables included, when they are three words or more; a word is a part between
  spaces that holds a letter or a digit.
- **Whole text.** The statement text that `corpus.py` builds from the two fields (the Related
  information, after an Availability information that is more than a bare label), normalised
  as there (lower case, single spaces) and compared with the phrase word for word. Punctuation
  is not compared: a colon, a hyphen or a full stop inside the text does not tell a statement
  from a phrase, so "Estimated recovery: TBD" is the phrase "Estimated recovery TBD" of
  section 3.8. The statement is excluded when its words are those of the phrase, in the same
  order. A statement that has both fields is excluded when each field is a quoted phrase:
  this guide quotes the two fields of an entry apart, and in some worked examples it leaves
  the Related information out of the table and quotes it once in the text above. A statement
  that contains a quoted phrase among other words, has its wording with another month or
  number, or has one field that is not quoted, is not excluded.
- **Where it applies.** To the samples of statements that are read: the pilot, the check set,
  the reserve, the literal sample, the in-context pool, the dev prompt items and the pair
  seeds. `audit_sample.py` reads the phrases from this file at every draw
  (`guide_phrases`), so a phrase quoted in a later revision is covered by the draws that
  follow it and does not change a list that is kept. The rule is not applied to the outcome
  audit, whose unit is the bracket of a presentation (section 6.2), and the draws of
  `dataset.py` do not apply it (appendix B).
- **What it removes (1 October build).** Sections 3 and 7 quote 114 phrases of three words or
  more. 729 statements of the task A frame are wholly quoted; 44 of these are excluded by the
  rows of A.1 to A.3 already, and the rule removes the other 685, of which 27 have two
  quoted fields. The strata not listed hold no such statement.

  | Stratum | Period | Frame | Excluded by A.1 to A.3 | Wholly quoted | Removed by this rule |
  |---|---|---|---|---|---|
  | month and year | train | 2,101 | 45 | 36 | 27 |
  | part of a month | train | 203 | 18 | 3 | 0 |
  | quarter, half or year | train | 109 | 6 | 4 | 1 |
  | range | train | 101 | 9 | 3 | 0 |
  | relative | train | 6 | 1 | 1 | 0 |
  | TBD or unknown | train | 243 | 14 | 30 | 24 |
  | TBD or unknown | 2023 on | 582 | 0 | 134 | 134 |
  | vague | train | 6 | 2 | 2 | 1 |
  | undated | train | 97 | 0 | 6 | 6 |
  | undated | 2023 on | 115 | 0 | 6 | 6 |
  | silent | train | 1,386 | 35 | 174 | 159 |
  | silent | 2023 on | 2,385 | 3 | 329 | 327 |
  | distractor only | train | 63 | 7 | 1 | 0 |

  The largest number is in the silent stratum: 486 of its 3,771 frame statements (13%), of
  which 474 have the one text "Check wholesalers for inventory". The largest share is in the
  TBD stratum: 158 of its 825 frame statements (19%), of which 126 have the one text
  "Estimated recovery: TBD", all of them dated 2023 or later. In the vague stratum the rule
  removes one statement of eight.
- **What it leaves in.** A statement that contains a quoted phrase among other words stays in
  the frame. In the draw of 1 October such statements are 7 of the 20 pilot items, 8 of the
  20 check items, 7 of the 20 reserve items and 30 of the 120 literal items; the sampler
  prints these numbers and writes them to the manifest.
- **What the silent and TBD items then stand for.** No silent item of a sample has the bare
  wholesaler sentence as its whole text, and no TBD item the bare "Estimated recovery: TBD".
  The cap on masked templates would have let in two items of each wording at most, over the
  four samples together. Results on these two strata are therefore results on the statements
  with other wordings.

## Appendix B. Decision points and alignment with the code (1 October)

This guide follows the literal prompt of `read.py` wherever the prompt speaks, and `rules.py`
where the prompt is silent. The rows below record where the documents differed and how each
point stands. Points marked **open for the pilot** are settled at the pilot meeting (section 4).
`rules.py` is frozen, so a point settled differently from it becomes a known mismatch, listed
here and disclosed in the paper.

**Check against the rule reader.** On 1 October `rules.read` with `as_literal_v1` (the frozen
file, sha256 prefix `6a810bcb1ae277b9`) was run on the 20 worked examples and 3 hard cases of
section 3.11 and on the 9 rows of section 7.3. It gives the reading of this guide in type,
interval or abstention, certainty and stale for all 32; for the "granularity, mid" row of 7.3
that is the corrected interval, not the generator's. The readings are the same when the Related
information that the table of 3.11 leaves out is added. The one difference in distractors is
example 17 (D17). About 250 further probes of the cue lists of section 3.6 and of the
conventions of section 3.7 also agree, except those listed under D13, D18 and D22. The target
ranking of section 3.6 was compared with the rule reader's choice on every statement of the
sampling frame, texts only (D22). The outcome examples of section 6.6 were checked against the
builder, run in memory on the captures, and against the capture rows, clipped at the horizon.
A second check the same day repeated the 32 readings, probes of every cue list and convention,
the ranking comparison and the eight outcome examples. It added the last form of D18 and the
two ties of D22, and it searched the events table for every quoted phrase of three words or
more: none occurs only in texts dated 2023 or later, after one cue of section 3.6 was reworded.

| # | Point | `read.py` prompt | `rules.py` | This guide | Status |
|---|---|---|---|---|---|
| D1 | Certainty of an abstaining target that has no unknown marker | "undetermined" is defined as "the entry says the timing is not known"; a sentence is reserved for this point (`PILOT_SENTENCES`, the last line of the certainty question) | `as_literal_v1`: `vague` gives estimated; `no_date` and `tbd` give undetermined | as `rules.py` (3.8) | **open for the pilot.** The meeting confirms or changes the mapping and fixes the prompt sentence |
| D2 | An undated discontinuation against a dated depletion | the order is recovery, next delivery, discontinuation, depletion | the same order; within a type, dated beats TBD beats undated | as both (3.6) | agreed |
| D3 | "Until X", "through X" | not covered; a sentence is reserved (`PILOT_SENTENCES`, after the convention on "by") | the period X | the period X (C11) | **open for the pilot.** As D1: the meeting confirms C11 and fixes the prompt sentence |
| D4 | "By X" | the Date of update to the end of X | the same, or X itself when X ends before the anchor | as both (C10) | agreed |
| D5 | "Final date of availability" | the depletion definition includes "until when product remains available" | discontinuation ("final date") | discontinuation (3.6) | agreed with `rules.py`; the prompt's wording overlaps |
| D6 | "No plans to manufacture until X" | not covered | recovery (a shortage state ending) | recovery, `hard` (H2) | agreed |
| D7 | Length of a relative month | 30 days | 30 days | 30 days (C12) | agreed |
| D8 | Certainty vocabulary | `asserted`, `estimated`, `undetermined`, `no_statement` | internally `firm`, `estimated`, `expected`, `anticipated`, `unknown`, mapped by `as_literal_v1` | the prompt's four classes | agreed |
| D9 | The type "availability until" | inside depletion | its own type internally, mapped to depletion | depletion | agreed |
| D10 | Fields shown to readers | `ENTRY_BLOCK` shows Therapeutic category and Initial posting date (added on 1 October) and no Status | | 3.3, the same block | closed (decision 6) |
| D11 | Outcome definitions and audit unit | | `corpus.py`: A, B and BL; one bracket per presentation thread, and a statement-level bracket | section 6: the audit follows the frozen `corpus.py`; the unit is the thread's bracket under B and A; the statement-level bracket is shown, not audited | closed (decision 5 makes the shown presentation's bracket the primary outcome) |
| D12 | Size of the literal task | | | 120 items double-labelled, a 20-item pilot, a 20-item check set with 20 in reserve | closed (decisions 7 and 10) |
| D13 | Seasons ("winter 2021", "in the summer") | not covered | with a year, the year (the season word is ignored); with no year, `none` | the year; with no year, `vague` (C17); `hard` | **open for the pilot.** No train-period statement contains a season word. If C17 stays, the yearless case is a known mismatch with `rules.py` |
| D14 | Conventions the prompt does not state (weeks, parts of a year, "over the next N", calendar units such as "next month", a month followed by a two-digit number, "from X to Y", no clipping, the choice between two statements of one type) | not covered; no sentence is reserved for them | covered (frozen conventions) | C4, C7, C8, C9, C12, C16 and rules 2 to 4 of 3.6, marked [R] or [G] | **open for the pilot.** The gold follows conventions the models are not given. Either a sentence for them is added to the prompt before it is pinned, or ADJ marks the gold items whose reading rests on them and E2 is also reported without those items |
| D15 | Reference reading for E3 | `stated_end` is supplied to the prompt | the frozen rule reading | task E checks 100 eligible statements (12.2); no further author labels in October | closed (decision 4) |
| D16 | Authors' predictive readings of minimal pairs | | | not collected (section 7) | closed (decision 15) |
| D17 | Distractor roles | the answer has no distractor field | seven roles, with `availability_until`; in example 17 "May and July delivery" is listed as `other` | six roles; "available until" is `depletion`; delivery mentions are not distractors | closed: the scorer maps `availability_until` to `depletion`; example 17 is a known mismatch |
| D18 | Forms the rule reader misses | covers "N to M" and a half without a year; says nothing on the others | "Estimated recovery 4-6 weeks" and "Next release 4 to 6 weeks" (no "in", no colon) read as `none`; "Will remain on backorder for 3 months" reads as `none`; "early to mid 2021" reads as May to August; a half with no year ("Estimated recovery: 1H") reads as `none`; a numeric day with no year and no word before it ("Next release 10/5") reads as `none`, though "on 10/5", "by 10/5" and "week of 10/5" are read; "cannot be estimated" is not taken as an unknown marker; "fifth week of May" and "5th week of May" read as the whole month, though "week 5 of May" is read | C12 and C9: 4 to 6 weeks later; 3 months later; January to August. C8: the first occurrence of the half that ends on or after the Date of update, and of the day on or after it. 3.7: an unknown marker, so abstain with `tbd`. C4: days 29 to the last | known mismatch, found by probes on 1 October (not corpus texts); disclosed, not patched |
| D19 | Sample of the alpha gate | | | the 20-item check set, with the share of identical intervals beside it (section 4) | closed (decision 10) |
| D20 | Who adjudicates, and who may read model outputs | | | ADJ adjudicates and does not label; A1 and A2 do not read reader outputs on their items before the gold is hashed (section 2, rule 1) | closed (decision 10). The limit on ADJ's looks at items still to be adjudicated is this guide's addition, for the owner to confirm |
| D21 | Exclusion unit of the train-half outcome sample | | | statement and presentation thread (section 6.2), as `audit_outcomes.py` implements it, not the whole shortage episode of v0 | closed in this draft, for the owner to confirm: the episode rule would leave about a quarter of the train events; this one leaves 5,011 of the 8,020 (62%) in the draw of 1 October, with all four sample lists read. Of the 3,009 left out, 1,826 are on a thread that carries a sampled or appendix A statement; the other 1,183 come from the further step for the thread of the shown row (6.2) |
| D22 | Choice of the target among several statements | the type order (recovery, next delivery, discontinuation, depletion); nothing on two statements of one type | `_score`: the type order, except that a dated discontinuation outranks a next delivery stated with no time and ties with one under an unknown marker, and a discontinuation under an unknown marker ties with a next delivery stated with no time (the first mentioned then wins); within recovery the kind of cue first, then dated over unknown marker, a vague statement last, except for two ties that go to the first mentioned: a shortage state under an unknown marker against a dated statement with a bare cue, and a bare cue under an unknown marker against a vague statement; a cue written after the date ("October 2021 supply") ranks with the resupply cues | rule 1 of 3.6 is the prompt's order, with no exception; rules 2 to 4 are the ranking of `rules.py`, without the two ties | known mismatch in these corners, disclosed. They decide no target in the sampling frame: on 1 October the ranking of 3.6, coded with the reader's own cue table, was compared with `_score` on every statement of the frame that makes two or more statements (texts only, with and without the bare availability label), and the two chose the same statement every time. v0 and the first draft of 1 October put "dated over unknown marker" before the kind of cue, which differed from `rules.py` on a handful of statements |

**Differences from `PLAN.md` and from the code, known on 1 October.** The plan was being amended
while this draft was written, and it has taken up most of the differences listed in earlier
drafts: the roles, the draft the pilot is labelled under, the gate with its pooling rule and its
reserve items, the timing of the reference-reading check and the statements its draw leaves out,
the E2 test over the items outside the month-and-year stratum, the display row of a statement
that is not at risk, the availability-string check and its result, the error rule of the
minimal-pair audit, the output folder of the literal task, the E6 link checks, the two
distractor rows of E2, the rule on quoted phrases and the seeds of the relative form. What
remains, compared with `PLAN.md` at sha256 prefix `f24a449d57dbaf03`, is below. This list is
emptied before v1 is hashed.

| Where | Says or does | This guide |
|---|---|---|
| `PLAN.md` 3, calendar overlap | a train-period statement first archived in 2023 is "first seen in the capture of 2023-01-13" | nearly all are (6.1); in the open events table, 7 of the 377 train events first captured in 2023 are first seen in a later capture of that year |
| `PLAN.md` 10, tasks 4 to 6 | gives no order between the test-half outcome audit and tasks C and E | the test-half audit starts only after A1 and A2 have submitted their sheets of tasks A, C and E (section 1) |
| `PLAN.md` 3, samples and their order, step 3 | the in-context examples, the dev prompt items and the seeds "exclude everything drawn in steps 1 and 2 and one another" | they also leave out every statement that reads like an item of step 1: the same whole text whatever the drug or the company, and the item's notice on another presentation (section 10) |
| `PLAN.md` 7.1 and 5, E2 | every literal metric is reported per form, "weighted by event and by template" | no sample holds a statement whose whole text is a quoted phrase (A.4), 486 silent statements among them; the plan does not say that the per-form figures and their event weights describe the frame without those statements |
| `PLAN.md` 10, blinding and task 5 | the train-half sample "leaves out every thread that carries a statement they label" | it does, and it also leaves out every statement that the thread of a shown row carried at any date, with all its presentations (6.2, D21); the pool is 5,011 events, where the plan's wording alone would give 6,194 |
| `PLAN.md` 10, task 5 | the affected items and 20 fresh ones are audited again; no pass rule for these two sets | 6.7: the scorer allows confirmed errors up to 5% of the real items of a set, rounded down (1 in 20, none below 20); provisional, for the owner to confirm |
| `dataset.py`, the subsets of the eligible list | leave out appendix A and the fixed test item, and `reference_check` the first draw as well; the rule on quoted phrases (A.4) is not applied | A.4 names the samples it covers. No eligible statement has a quoted phrase as its whole text in the 1 October build: the 469 such frame statements dated 2023 or later are TBD, undated or silent, and the eligible list holds dated forms only. The eligible list is built again after the first draw (12.2) |
| `audit_sample.py` and `audit_outcomes.py`, header lines | the task A sheets take the times as `sitting_start` and `sitting_end`, one pair of lines per sitting; the task B sheets as `session_start` and `session_end`, with semicolons | section 9 describes both; one form for all sheets would be easier on the annotators |

Two lines of `PLAN.md` section 10 wait on this guide and on the owner: the load figure, which
is filled from the hours table of section 0 at the rates the pilot and the train-half audit
measure, and the owner's confirmation of the limit on what ADJ looks at (D20).

## Changelog

- **v0, 29 September 2026.** First draft, before the pilot.
- **v1 draft, 1 October 2026.** Before the pilot. Literal task set at 120 items with a 20-item
  pilot, a 20-item check set and a reserve; the allocation table follows the classes of
  `forms.py`; the unit is the dated statement. Alpha gate moved to the check set, with the share
  of identical intervals. Roles: two annotators and an adjudicator who does not label; limits on
  who reads reader outputs. Section 6 rewritten for the frozen outcome rule: definitions A and B,
  the five censoring reasons, the horizon, train-half windows clipped at 2022-10-06, the thread
  as audit unit with the statement-level bracket shown, a finer class strip, pass counts per
  half, the treatment of `cannot_tell`, codes per definition, flags renumbered N1 to N6, and
  planted items scored by script; sample, window and sheet columns follow `audit_outcomes.py`.
  Two short checks added (section 12).
  Computed columns and validation moved from the sheets to the agreement script. Hours per
  person in section 0. Appendix A extended to quoted phrases and the prompt harness's test item.
  Appendix B: D10 to D12 closed; D1, D3 and D13 left for the pilot; D14 to D21 added.
  After a check of the draft against `rules.py`, `corpus.py`, `audit_outcomes.py` and
  `PLAN.md`, the same day: within `recovery` the kind of cue now decides before "dated over
  unknown marker", as in `rules.py` (3.6, D22); "Shortage duration from July 2019 to March
  2020" is a range and no longer an example of a past date (C9, 3.10); the rule for a month
  followed by a two-digit number (C8); the depletion cues; further known mismatches under D18;
  the task B sheet as the builder now writes it (`note_codes`, the exit date, the trace
  columns, the items file, `session_start` and `session_end`); the test-half key stays sealed
  until the evaluator has run; the task E draw leaves out the literal items; the list of
  differences from `PLAN.md` redone.
  After the owner's check of the availability strings and a second check of the draft against
  the code, the same day: task D recorded as done, with no string rejected (section 12.1, and
  the hours table without it); the folders, file names, header lines and validator commands of
  `audit_sample.py` and `audit_agreement.py`, which did not exist when the draft was written
  (sections 3.12, 4, 9 and 10); a row of an excluded thread is shown in a trace by its names
  only (6.2, 6.3); the test-half outcome audit follows the submission of tasks A, C and E
  (section 1); what happens when the task E subset overlaps the literal sample (12.2); the
  files that hold rule readings named in blinding rule 1; a train event first captured later
  in 2023 than 2023-01-13 (6.1); "March end" and the fifth week of a month (C3, C4, D18); two
  ties of the rule reader's ranking (D22); the thin strata (3.2).
- **v1 draft, 1 October 2026, after the owner's four decisions on the samples.** Made before
  any sheet was handed out; the four sample lists and the pilot and check sheets were drawn
  again under this text.
  - *Vague row (3.2).* The row "vague or undated" is split into a vague row (pilot 1, literal
    3) and an undated row (pilot 1, literal 5). What the vague stratum lacks goes to the
    undated stratum first.
  - *Distractor rows (3.2).* The row "distractor date" is split into "distractor only" (pilot
    1, literal 6) and "dated target beside a distractor date" (pilot 1, literal 6). The table
    now says which classes a row takes only with a distractor date, and the sampler reads
    that from it. In the literal sample the general shortfall goes to the TBD,
    distractor-only and silent strata. The E2 test still covers the 108 items outside the
    month-and-year row.
  - *Quoted phrases (2, 3.2, A.2, A.4).* A statement whose whole text is a phrase of three or
    more words quoted in section 3 or 7 is excluded from the samples of statements that are
    read, whatever the drug or the company, and so is a statement whose two text fields are
    each such a phrase; a statement that only shares or contains a wording can still be
    drawn. A.4 gives the rule and what it removes. It is not applied to the outcome audit
    (6.2).
  - *Pair seeds (1, 7.1, 10).* The seeds of the relative form are statements dated 2023-01-01
    or later, text only, marked in the list; no model is called on their pairs before
    amendment F1.
  - *Thin strata (3.2).* Vague is named with relative and discontinuation; the numbers of the
    draw are given.
- **v1 draft, 1 October 2026, corrections of the text to the tooling, the same day.**
  - 3.12 and 9: sheets are filled in a copy; `validate` warns when it finds no blank sheet;
    `agree` refuses a sheet filled in place; the submission checks of `agree` and `score`.
  - 4, step 5: the reserve gate pools with the pilot items, as the check gate does; a guide
    revised after a failed gate carries `v1.1` in its version line.
  - 6.2: the outcome-audit builder refuses either half without the sample lists, and stops on
    a row of appendix A that matches no event and on a listed id unknown to the build; a
    stratum whose pool has one event gets that one.
  - 6.7: the two re-audit commands, and the pass rule the scorer applies to a re-audit set
    (provisional, for the owner to confirm).
  - 8.1: a small stratum gets no alpha; its kappas stay in the output.
  - 10: the later lists (`samples_later/`, `draw_rank`, `period`, their three rules), the
    flags `--fixed` and `--replace`, and what a revised guide does to sheets already written.
  - 11: e-mail addresses are masked in the outcome-audit files and not in the literal-task
    sheets; company telephone numbers in the FDA text remain.
  - 12.2: `dataset.py` now leaves the first draw out of the task E subset; the eligible list
    is built again after the first draw.
  - Appendix A: both samplers that read the rows are named. Appendix B: the pool of the
    train-half outcome audit (D21); the list of differences from `PLAN.md` and the code,
    redone against the plan as it stood that evening.
- **v1 draft, 1 October 2026, after an independent check of the samples and sheets, the same
  day.** Made before any sheet was handed out. The pilot, check and reserve lists did not
  change. One literal item changed, and with it the pool of the train-half outcome audit
  (5,011 events); the 56 items of that audit stayed the same. The three later lists were
  drawn again, and every sheet was written again so that it names this text.
  - *Quoted phrases (3.2, A.4).* A statement and a quoted phrase are compared word for word,
    punctuation aside. That leaves out 129 more statements of the TBD stratum, 126 of them
    with the text "Estimated recovery: TBD"; one was a literal item. A.4 also gives the
    numbers of drawn items that contain a quoted phrase, and what the silent and TBD items of
    a sample stand for.
  - *Later lists (1, 10).* The in-context pool, the dev prompt items and the pair seeds also
    leave out the statements that read like an item A1 and A2 label: the same whole text
    whatever the drug or the company, and the same notice on another presentation. The first
    draw of these lists held 12 statements with the whole text of an item of another drug,
    and 6 that were an item's notice on another presentation; one of the 6, in the in-context
    pool, differed from a literal item by a typing error. `draw-later` no longer writes over
    a list on disk that would change, unless `--replace` is given.
  - *Outcome audit (6.2, D21).* The text now says all that the builder leaves out: for the
    thread of a shown row, every statement it carried at any date, with all its
    presentations. The builder did not change.
  - *Pilot (4).* D13 has no pilot item; the meeting settles it on the forms C17 names.
  - Appendix B: the list of differences from `PLAN.md`, redone against the plan of that
    night.
