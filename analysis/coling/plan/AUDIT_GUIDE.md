# Author audit guide

**Version v0, 29 September 2026. Draft.** The pilot (section 4) turns this into v1, which is frozen
by hash at registration (`PLAN.md`, section 17). After that, changes are made only through the
adjudication log (section 5) and are listed in the changelog at the end.

This guide covers the human labels of the COLING 2027 study "Estimated Recovery: TBD". Two authors
(called A1 and A2 in every file; never by name) do three tasks: a literal reading of about 150
FDA shortage notices, an audit of 100 derived recovery brackets, and an audit of 100 minimal
pairs. There is no crowd study. Every example below is a real row from the archived FDA CSV
captures in `external_data/fda_wayback_csv/`, and every example is from the train period
(statement dated before 2023-01-01).

## 0. At a glance

| Task | Items | Who | When (plan) | Minutes per author | Pass rule |
|---|---|---|---|---|---|
| Pilot and check set | 20 + 10 | A1 and A2, independently | Thu 1 and Fri 2 Oct | about 45, with the meeting | alpha of at least 0.6 on the check set |
| A. Literal reading | 150 | A1 and A2, independently | Sat 3 to Mon 5 Oct | about 75 | reported, no pass rule |
| B. Outcome audit, train half | 50 | 20 each, 10 shared | Fri 2 Oct, before registration | about 20 | at least 95% agree |
| B. Outcome audit, test half | 50 | 20 each, 10 shared | Mon 5 Oct, after every confirmatory run | about 20 | at least 95% agree |
| C. Minimal-pair audit | 100 | 45 each, 10 shared | after task A | about 20 | at least 95% of labels match |
| Adjudication | disagreements | adjudicator (section 5) | after each task | about 15 | |

Total: about 3 hours per author, plus 15 minutes to read this guide. If the pilot shows a mean
above 40 seconds per literal item, task A is cut to 120 items, taken first from the month-and-year
and silent strata, keeping at least 10 per stratum.

**Relation to `PLAN.md` (draft of 29 September).** `PLAN.md` section 10 describes a larger
version: a 30-item pilot, 300 E2 items labelled by one author with 60 double-labelled, and about
10 to 12 hours per author. This guide implements the author audit agreed on 29 September: 150
items double-labelled by both authors, a 20-item pilot plus a 10-item check set, and about 3
hours each. One of the two documents must be amended to match the other before registration.

## 1. Roles and order of work

- **A1 and A2** label and audit. Neither writes, tunes or runs the model prompts during the study,
  if that can be arranged; if one of them must, it is recorded, and that person is never the
  adjudicator.
- **Adjudicator.** A third author who has not written or tuned the prompts, if one can give
  about 30 minutes per task. Otherwise A1 and A2 adjudicate jointly (section 5).
- **Sheet builder.** Whoever runs the scripts that draw the samples and write the blank sheets
  (the sheet generator and the agreement script are still to be written; suggested names
  `audit_sheets.py` and `agreement.py`). This person may be an annotator, but must not open the
  planted-error keys (sections 6.2 and 7.1).

Order, which the blinding rules (section 2) depend on:

1. Pilot, meeting, revision to v1, check set (Thu 1 and Fri 2 October).
2. Outcome audit, train half (Fri 2 October, before registration). Its sample excludes every
   shortage episode that has an item in the literal sample, the pilot, the check set or the
   examples of this guide.
3. Task A, the literal reading (Sat 3 to Mon 5 October), then its agreement statistics, then
   adjudication, then the gold file is hashed and committed.
4. Task C, the minimal-pair audit (after the task A labels are submitted).
5. Outcome audit, test half (Mon 5 October), only after every confirmatory run has finished and
   before the registered evaluator runs.

## 2. Blinding rules

These rules hold for both annotators until the gold of the task in question is hashed and
committed.

1. **No model outputs.** Do not open `analysis/coling/out/read/`, `results/coling/`, any
   `readings.jsonl` or `responses.jsonl`, the rule reader's output on sample items, or anyone's
   notes about how a model or the rule reader handled a sample item. Runs may be going on while
   you label; checking that they are running uses counts and spend only.
2. **No later captures (task A).** For a literal item, look only at the row shown in the sheet.
   Do not open the capture files, the corpus tables, the FDA website, the Wayback Machine or any
   other source about the drug. Do not search the web for the drug or the company.
3. **No outcomes (task A and task C).** Do not open `external_data/sealed/`, the outcome tables in
   `analysis/coling/out/`, or any outcome audit sheet other than your own train-half sheet, and do
   not discuss what happened to any drug. The train-half outcome audit (step 2 above) excludes the
   episodes you will label.
4. **No other annotator.** Label alone. Do not look at the other annotator's sheet or discuss
   items until both sheets are submitted. Questions about this guide go to the adjudicator, whose
   written answer goes to both annotators and into the changelog as a clarification.
5. **No assistants.** Label by hand. Do not paste items into a language model, a date parser or
   any tool that interprets the text. A calendar is allowed.
6. **Test outcomes stay sealed.** The test-half outcome audit sheets are written only under
   `external_data/sealed/audit/`. Nobody computes or writes down whether a stated estimate held,
   and the audit results are reported only as counts of agreements and error codes (section 8).
7. **Guide examples are excluded.** The statements used as examples in this guide (appendix A) are
   excluded from every sample.

A breach is recorded in the changelog with the items affected. Those items are reported
separately.

## 3. Task A: literal reading

### 3.1 What is being labelled

The **literal reading** of a notice: what the notice itself says about timing, read with the
fixed conventions below. It is not a forecast. Do not use anything you know about the drug, the
company or the FDA's habits, and do not correct text that looks wrong.

The fields are exactly those that the models return under the frozen `literal-v1` prompt of
`read.py`, so the gold can be scored against them field by field.

### 3.2 Sample

- **Unit.** A distinct statement: generic × company × normalised statement text, as built by
  `corpus.py`. When several presentation threads share it, one display row is drawn at random
  among them.
- **Size.** 150 items, plus the 20 pilot items and the 10 check items, which are drawn first and
  kept out of the 150.
- **Strata.** The form classes of `PLAN.md` section 2.6, assigned by the frozen form classifier.
  This is a sampling frame, not a label, and annotators do not see it.

  | Form | Items | Form | Items |
  |---|---|---|---|
  | month and year | 20 | exact day | 13 |
  | month with no year | 13 | TBD or unknown | 14 |
  | part of a month | 13 | silent (no timing) | 12 |
  | quarter or half | 13 | distractor date present | 14 |
  | range | 13 | discontinuation | 12 |
  | relative | 13 | | |

  A stratum with fewer eligible statements than its quota gives all it has, and the shortfall
  goes to the TBD and distractor strata in turn.
- **Periods.** Drawn from all periods, since a literal reading involves no outcome. About a third
  come from the test period where the form allows, so that E7 has gold readings on test events.
  The pilot and check items come from the train period only.
- **Caps.** At most 2 items per masked template (months and numbers masked) and 3 per shortage
  episode.
- **Exclusions.** Minimal-pair seeds, in-context examples, dev prompt-development items, and the
  examples of this guide.
- **Order.** Each annotator gets the items in a different random order (seeded).

In the 61 of the 110 captures that were on disk when this was checked, every stratum had at least
55 distinct statement events in each period on a rough regex count, so the quotas are feasible.

### 3.3 What you see

Exactly the entry block that the models see (`ENTRY_BLOCK` in `read.py`), with the date in ISO
form:

```
Entry
- Drug: Cefoxitin for Injection, USP
- Company: Fresenius Kabi USA, LLC
- Presentation: ...
- Type of update: Revised
- Date of update: 2020-08-13
- Availability information: Backordered. Next release October 2020.
- Related information: Check wholesalers for inventory
- Reason for shortage: Manufacturing delays
```

You do not see the Status, the capture date, other rows of the same drug or any later version of
the notice.

### 3.4 What you record

| Column | Values | Notes |
|---|---|---|
| `statement_type` | `recovery`, `next_delivery`, `depletion`, `discontinuation`, `none` | section 3.6 |
| `start`, `end` | `YYYY-MM-DD`, or `YYYY-MM` as shorthand for the first or last day of that month | blank when abstaining; section 3.7 |
| `abstain` | 1 or 0 | 1 exactly when `start` and `end` are blank |
| `abstain_reason` | `tbd`, `no_date`, `vague`, `no_statement` | only when `abstain` is 1; section 3.7 |
| `certainty` | `asserted`, `estimated`, `undetermined`, `no_statement` | section 3.8 |
| `quote` | the shortest exact words the reading rests on | required only when the entry has more than one time expression |
| `distractor_roles` | semicolon list of `expiry`, `depletion`, `discontinuation`, `onset`, `past`, `other` | section 3.10 |
| `distractor_quotes` | the words of each distractor, same order | |
| `hard` | 1 or 0 | 1 when a convention had to be stretched; say why in `note` |
| `note` | free text | |

Computed by the sheet, not typed: `stale` (section 3.9), the month offsets and the day offsets of
`start` and `end` from the anchor (section 8.1), and the consistency checks of section 3.12.

### 3.5 Decision order

1. Find every forward-looking statement about supply in the Availability and Related
   information.
2. Choose the target statement (section 3.6) and record its type.
3. Read its time with the conventions (section 3.7): an interval, or abstain with a reason.
4. Record the certainty (section 3.8).
5. Record every distractor date (section 3.10).
6. Set `hard` if you had to stretch a convention.

### 3.6 Statement type and the target statement

The types, with the definitions of the `literal-v1` prompt and the cue words of `rules.py`:

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
  available. Cues: deplete, exhaust, run out, "expected to last until", "N months of inventory",
  and "available", "supply", "distribution will continue" or "continue to be sold" until a time.
- **`discontinuation`**: when the product will be, or has been, discontinued. Cues: discontinue,
  cease, stop sale or shipping, final date, final order or batch, last order, shipment, batch or
  distribution ("The anticipated final date of availability to patients is approximately April
  2019"), no longer available or supplied, delist, phase out, withdraw, market exit.
- **`none`**: the entry makes no forward-looking statement about timing ("On backorder", "Check
  wholesalers for inventory").

Expiry dating, lot numbers, NDCs, strengths, phone numbers and past events are never statements
about timing. A misspelled cue word counts as the word intended ("availabilty", "Backorderd").

**Choosing the target** when the entry makes more than one statement. This follows the prompt's
order, and `rules.py` implements the same ranking:

1. Take the first type present in the order `recovery`, `next_delivery`, `discontinuation`,
   `depletion`. A type is present when the entry makes a statement of it, dated or not: "Next
   Delivery: May 2021; Estimated Recovery: TBD" is a `recovery` statement that abstains, and
   "Discontinuation of the manufacture of the drug. Current supply expected to deplete by May/June
   2020 timeframe." is an undated `discontinuation` statement, with the depletion date as a
   distractor.
2. Within one type, a dated statement beats one with an unknown marker, which beats a vague or
   undated one.
3. Then, within `recovery`: an explicit "recovery" cue beats resupply-type cues (resupply,
   restock, back in stock, relaunch, resume, return), which beat availability and shortage-duration
   cues, which beat "until" phrases and other cues. Within `next_delivery`, a "next ..." cue
   ("next delivery", "next release", "next shipment") beats the others.
4. Remaining ties go to the first mentioned, Availability information before Related information.
   Set `hard` if the tie felt arbitrary.
5. "Next Delivery and Estimated Recovery: X" is a `recovery` statement.
6. A list of times for one type ("Next Delivery: May 2020, July 2020, August 2020 and November
   2020", "Month and Month") is read as separate statements; the first listed is the target. A
   month without a year in such a list takes the year of the next month that has one.

### 3.7 Time conventions

The conventions marked **[P]** are the `literal-v1` prompt's own words. Those marked **[R]** come
from the frozen conventions of `rules.py` and fill gaps the prompt leaves open. Those marked **[G]**
are this guide's own; the pilot checks them. The examples and probes listed in appendix B were
run through `rules.read` on 29 September to confirm that the two agree.

- **C1. Anchor.** Read every time relative to the Date of update shown. [P]
- **C2. Month.** "April 2020", "Apr-20", "April of 2020", "4/2020" (numeric month and year): the
  whole month. [P, R]
- **C3. Part of a month.** Early, beginning of, start of: days 1 to 10. Mid, middle of: 11 to 20.
  Late, end of, end-, month end: 21 to the last day. First half of a month: 1 to 15; second half:
  16 to the last day. [P, R]
- **C4. Weeks.** "Week of <date>": that date and the 6 days after it. "First week of", "1st week
  of", "week 1 of" a month: days 1 to 7; second 8 to 14; third 15 to 21; fourth 22 to 28; fifth
  29 to the last day. "Last week of": the last 7 days. "The week of <part of a month>", where no
  date is given, is read as that part of the month, with `hard` set. [R, G]
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
  20NN ("Mar 21", "April/May 21", "1Q20", "Nov-22", "4/5/19"). [P, R, G]
- **C9. Ranges.** "May-June 2020", "April/May 2021", "Feb/Mar 2021", "January – February 2021
  timeframe", "4Q 2021 to 1Q 2022", "end of May/early June 2020": from the start of the first
  part to the end of the last. A year written once applies to every part. When the first part's
  month is later in the year than the last part's, the first part belongs to the year before
  ("Dec-Jan 2021" is December 2020 to January 2021). [P, R]
- **C10. "By", "before", "no later than", "at the latest".** From the Date of update to the end
  of the time named: "by the end of April 2021" dated 2021-04-12 is 2021-04-12 to 2021-04-30. If
  that time ends before the Date of update, read the time itself (the entry is then stale). [P, R]
- **C11. "Until", "through", "thru", "till" and "not ... until".** The period named, and nothing
  more: "Estimated shortage until March 2020" is March 2020; "on allocation through February 2021"
  is February 2021; "no plans to manufacture until sometime in 2023" is 2023. "After X", "not
  sooner than X" and "no earlier than X" are also the period X. [R, G]
- **C12. Relative times.** Counted from the Date of update, with a week of 7 days and a month of
  30 days. "Within N", "up to N" or "over the next N": the Date of update to N later. "N to M"
  ("3-18 months", "4-6 weeks"): N later to M later. A single N ("in 6 weeks", "for 3 months"): N
  later, as both start and end. "Next month", "next quarter", "next year": the calendar unit after
  the one holding the Date of update; "this month", "end of the month" and "end of the year"
  follow C3 and C7 for the unit holding it. [P, R]
- **C13. Exact date.** That day, as both start and end: "7/1/2020", "Available by 4/5/19" (with
  C10), "June 1st, 2022". Numeric dates are month first. [P]
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
  2021" is the year 2021, and a season with no year abstains as `vague`. Set `hard`. [R, G]

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
`undetermined`. This is how `rules.py` maps its readings to the prompt's classes (decision point
D1, appendix B).

### 3.9 Stale

`stale` is true when the interval ends before the Date of update: the entry repeats an estimate
that had already passed when it was updated. It is false when the item abstains. The sheet
computes it from `end` and the anchor, as the prompt defines it; you do not type it.

### 3.10 Distractor dates

A distractor is any time expression in the entry, other than the target, that a careless reader
could return as the delivery or recovery time. Record each with its role:

| Role | Examples |
|---|---|
| `expiry` | "5 month expiry (1/2022 expiry) dating available by request", "(expiry 6/30/2021)" |
| `depletion` | "Remaining inventory estimated to last until April 2020", "available until", "distribution will continue until January 30, 2023" (when the target is not itself a depletion) |
| `discontinuation` | "To be discontinued in 2021" (when the target is not a discontinuation) |
| `onset` | "Projecting backorder in May", "backorder expected in X", "shortage anticipated from X" |
| `past` | "Backordered material arrived in end of September", "Shortage duration from July 2019", "as of X", "effective X", "since X" |
| `other` | any other time expression that is not a delivery or recovery statement ("will provide an update in X") |

Other delivery or recovery statements (the later items of a list, a next delivery beside the
target recovery) are not distractors.

### 3.11 Worked examples

All from train-period captures; A is the Date of update. "Offsets" are the month offsets of start
and end (section 8.1).

| # | Entry (drug, company, A) | Text (Availability; Related) | Type | Interval | Certainty | Stale | Offsets | Why |
|---|---|---|---|---|---|---|---|---|
| 1 | Bupivacaine and epinephrine, Hospira, 2019-10-07 | "Next Delivery and Estimated Recovery: June 2021"; "Shortage per Manufacturer: Manufacturing Delay" | recovery | 2021-06-01 to 2021-06-30 | estimated | no | 20, 20 | 3.6 rule 5; C2 |
| 2 | Cefoxitin, Fresenius Kabi, 2020-08-13 | "Backordered. Next release October 2020." | next_delivery | 2020-10-01 to 2020-10-31 | asserted | no | 2, 2 | C2 |
| 3 | Hydromorphone, Teva, 2020-08-20 | "Backorder - Product availabilty ETA Late August" | recovery | 2020-08-21 to 2020-08-31 | estimated | no | 0, 0 | availability cue, misspelt; C3; C8 (August 2020 ends after A) |
| 4 | Lidocaine, Fresenius Kabi, 2021-05-19 | "Backordered. Next release early Q3." | next_delivery | 2021-07-01 to 2021-07-31 | asserted | no | 2, 2 | C5; C8 |
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
| H3 | Alfentanil, Hospira, 2020-03-25 (Related information only) | "Discontinuation of the manufacture of the drug. Current supply expected to deplete by May/June 2020 timeframe." | discontinuation, abstain (`no_date`), undetermined; distractor `depletion` "Current supply expected to deplete by May/June 2020 timeframe" | the type order (3.6 rule 1): an undated discontinuation outranks a dated depletion (D2) |

### 3.12 Consistency checks run on every sheet

The sheet (or the agreement script) rejects a row, and you fix it before submitting, when:

- `abstain` is 1 and a date is given, or 0 and a date is missing;
- `start` is after `end`, or a date does not exist;
- `statement_type` is `none` but `certainty` is not `no_statement`, or the other way round;
- `certainty` is `undetermined` but an interval is given;
- `abstain_reason` is missing when abstaining, or given when not;
- `abstain_reason` and `certainty` disagree (`tbd` or `no_date` need `undetermined`, `vague` needs
  `estimated`, `no_statement` needs `no_statement`);
- a distractor role has no quote.

## 4. Pilot, revision and check set

1. **Pilot (v0).** 20 train-period items, 2 from each form stratum except silent and
   discontinuation (1 each). A1 and A2 label them independently under v0, in about 15 minutes.
2. **Agreement.** The agreement script computes the statistics of section 8.1 on the pilot and
   lists every disagreement.
3. **Meeting (about 20 minutes).** For each disagreement, each annotator names the convention
   they applied. Three outcomes are possible:
   - a slip against a clear convention, which needs no change;
   - an unclear convention, which is reworded;
   - a missing convention, which is added.

   Every change is written into this file as v1 and logged in the changelog. The open decision
   points of appendix B are settled at this meeting.
4. **Check set (v1).** 10 fresh train-period items from the dated strata, labelled independently
   under v1, in about 7 minutes.
5. **Gate.** Krippendorff's alpha on the start and on the end month offsets (section 8.1) over the
   check set must both be at least 0.6 (if the check items do not vary enough for alpha to be
   defined, the pilot items are pooled with them). If either is below 0.6, revise once more
   (v1.1) and label another 10 fresh items. If it fails again, the hold trigger of `PLAN.md`
   section 12 fires.
6. **Freeze.** v1 is committed and its hash goes into the registration record before
   registration. Pilot and check items stay out of the gold and out of every other sample; their
   labels are reported in an appendix as pilot data.

If the gold conventions change at the pilot, the `literal-v1` prompt and the rule reader must be
brought into line before F1, or the difference is recorded as a known mismatch (appendix B).

## 5. Disagreement adjudication

1. **Freeze first.** Both annotators submit their sheets. The sheet builder records the sha256 of
   each file, and the agreement script computes and saves the agreement statistics. Only then is
   anything adjudicated. Reported agreement is always the pre-adjudication agreement.
2. **What goes to adjudication.** Every item where A1 and A2 differ in any recorded field:
   `statement_type`, `abstain`, `start`, `end`, `certainty` or the distractor roles. Differences in
   `quote` and `note` alone do not.
3. **Procedure.** For each item, the adjudicator reads both labels and the reasons in `note`, then
   decides by the conventions of this guide. Each decision records one of:
   - `slip`: one annotator misapplied a convention that decides the case;
   - `gap`: no convention decides it. The adjudicator decides, words a new convention, applies it
     to every item it touches (not only the disputed one), and adds it to the changelog as a
     dated clarification.
4. **Joint adjudication** (when there is no third author). A1 and A2 settle each item together by
   naming the deciding convention. Where none decides, the annotator who has had no role in
   prompt writing decides; the item is marked `gap`.
5. **Items marked `gap`** are reported, and every E2 result is also given without them.
6. **Gold.** The adjudicated labels form the gold file, which is hashed and committed before
   anyone opens a model output on these items. Gold is never changed after that, except through a
   dated amendment that is reported.
7. **Audit tasks (B and C).** Every item that an auditor marks as an error, and every shared item
   where the two auditors differ, goes to the adjudicator. The adjudicator confirms or rejects the
   error. The pass rules use confirmed errors; auditor-flagged counts are reported as well.

## 6. Task B: outcome audit

### 6.1 What is being checked

Whether the recovery bracket that `corpus.py` derived for a statement event is what its own
written rule gives when applied by hand to the raw capture rows. The reference is the builder's
docstring as frozen at registration (its hash is printed in the sheet header). As of 29 September
it defines:

- **Thread.** One presentation's rows across captures, linked on the exact key and then on NDC
  overlap.
- **Event.** A statement event, first seen at capture `c0`, with its statement date (the Date of
  update of that row).
- **Definition A (FDA resolved; `PLAN.md` calls it R2).** Recovered at a capture when the thread's
  row has Status Resolved, or when the row is absent while its generic is listed and Resolved.
- **Definition B (supply back; `PLAN.md`'s R1 at the level of one presentation).** Recovered when
  the row's Availability information is in the class `available` (not limited, allocation,
  backorder or unavailable), or when A holds.
- **Definition BL (a sensitivity analysis for B).** As B, with limited supply counted as
  available. It is not audited separately, but a class error between `L` and `A` is recorded
  (O4) because it moves BL.
- **Competing event.** Discontinuation: the presentation newly appears in the To Be Discontinued
  listing. It wins ties.
- **Bracket.** `lower` is the last capture at which the thread was seen not recovered (at least
  `c0`); `upper` is the first capture showing the event. With no event by the last capture, the
  outcome is right-censored at `lower`, with a censoring reason.
- **At risk.** Under A, when the row is Current at `c0`; under B, when it is also not available at
  `c0`. Otherwise the event is `not_at_risk`.

If `PLAN.md` and `corpus.py` still differ at registration (for example on how a disappearing row
is treated), the audit follows the frozen `corpus.py`, and the difference is recorded in the
registration.

### 6.2 Sample

- **Size.** 100 statement events: 50 train-period and 50 test-period.
- **Stratification.** Within each half, by definition-B outcome type (recovered, discontinued,
  censored, not at risk), by bracket width (31 days or less, 32 to 90, more than 90) and by
  whether the event was re-confirmed. Rare cells are oversampled; the error rate is reported raw
  and reweighted to the population.
- **Assignment.** Within each half, 20 items to A1, 20 to A2, and 10 audited by both. Both
  definitions are audited on every item: B is the main check, and A is quick.
- **Planted errors.** Each auditor also gets 5 planted items (3 train, 2 test), made by the sheet
  generator from events outside the sample. Each has one seeded perturbation: `upper` or `lower`
  moved by one capture, the outcome type changed, or a wrong presentation linked. The key is
  written to a separate file that only the adjudicator opens. Planted items are excluded from the
  pass statistic.
- **Exclusions.** The train half excludes every shortage episode that has an item in the literal
  sample, the pilot, the check set or the examples of this guide.
- **Sealing.** The test-half sample is drawn by code that may stratify on sealed fields but prints
  only counts. Its sheets are written only to `external_data/sealed/audit/`, and are opened only
  after every confirmatory run has finished.

### 6.3 What you see

One item block per event:

1. **Header.** Event id; generic, company and presentation; the statement text; the statement
   date; `c0`; and, for each definition, the derived outcome type, `lower`, `upper`, the width in
   days and the censoring reason.
2. **Class strip.** One letter per capture from `c0` to one capture past `upper` (or to the end
   of the archive): `A` available, `L` limited, `U` unavailable, `O` other, `B` blank, `R` resolved
   listing, `D` in the discontinuation listing, `.` absent. Gaps of more than 90 days between
   captures are marked `|`.
3. **Raw trace.** One row per capture in the same window: capture timestamp, present or absent,
   Status, Type of update, Date of update, Availability information, Related information,
   Resolved note, Change date and Date discontinued. Rows linked by NDC rather than by exact key
   are marked. The same NDC found under another presentation string in a capture where the thread
   is absent is listed as well.

### 6.4 How to check an item (about 30 seconds)

1. **Link.** Do the trace rows belong to one presentation (the same NDC, or a recognisable
   re-formatting of the same product)? Is the thread absent anywhere while the same NDC appears
   under another string?
2. **Event start.** Does the statement text appear at `c0`, and not in an earlier capture of the
   same thread with the same text (which would make `c0` a re-confirmation)?
3. **At risk.** Under A, is the row Current at `c0`? Under B, is its availability also not
   `available`?
4. **Classes at the transitions.** At `lower` and `upper`, and at any capture where the letter
   changes, read the raw Availability information and Status, and confirm the letter.
5. **Bounds.** Is `lower` the last capture seen not recovered, and `upper` the first capture
   showing recovery or discontinuation? A capture where the row is absent and the generic is
   Current or unlisted says nothing: skip it.
6. **Competing event.** Does the presentation enter the To Be Discontinued listing at or before
   the derived `upper`?
7. **Censoring.** If censored, is there really no recovery or discontinuation up to the last
   capture, and is the reason (end of archive, or the thread left the list) right?

Record `ok`, `error` (with codes) or `cannot_tell`. Do not record, and do not work out, whether
the statement's estimate held.

### 6.5 What counts as an error

An item is an **error** when the auditor's reading of the captures under the frozen rule gives a
different outcome type, `lower` or `upper` for definition B, or for definition A.

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

These are **flags, not errors**, and never count against the pass rule:

| Flag | Meaning |
|---|---|
| F1 | a tighter bound is visible: the Date of update on the first recovered row is earlier than `upper` (write it in `dou_first_recovered`) |
| F2 | relapse: the thread goes back to U or L within 90 days after `upper` |
| F3 | conflicting fields, for example Status Resolved while the Resolved note says Unavailable |
| F4 | the bracket spans an archive gap of more than 90 days |
| F5 | a class-table entry looks debatable but does not move a bound |

An `error` caused by the frozen rule itself, which the builder applied correctly, is still an
error for the pass rule. The remedy then is a change to the rule, never to the single item.

### 6.6 Worked examples (train period)

1. **Alogliptin 6.25 mg, Perrigo.** The event "On backorder – expected release the week of
   01/27/2020" (dated 2019-12-10) is first seen in the capture of 2019-12-29.
   - Class strip from 2019-12-29: `U U A A A A A A A A R ...`. The captures are 2019-12-29 and
     2020-04-02 (the same text), then 2020-06-12 "Available" (Date of update 2020-05-12), and
     2020-10-11 Resolved (Change date 10/05/2020).
   - Definition B: recovered, (2020-04-02, 2020-06-12], 71 days. Flag F1: 2020-05-12.
   - Definition A: recovered, (2020-09-30, 2020-10-11].
   - A derived B bracket of (2019-12-29, 2020-04-02] would be O5 and O6: the second U capture
     was skipped.
2. **Loxapine 5 mg, Lannett.** The event "... scheduled for release in the March/April
   timeframe ..." (dated 2021-02-02) is first seen on 2021-03-18.
   - On 2021-04-12 the text changes to April/May, which starts a new event. The first event's
     outcome still follows the thread.
   - 2021-05-12 shows "Available" (Date of update 2021-05-06).
   - Definition B: recovered, (2021-04-12, 2021-05-12], 30 days. Flag F1: 2021-05-06.
   - Ending the first event's outcome at the revision would be O6.
3. **Ranitidine 150 mg, 60 capsules, Novitium.** The event "Product is currently unavailable.
   Estimated shortage duration is until Q1 2020." (dated 2020-01-07) is first seen on 2020-04-02.
   - On 2020-06-12 the presentation is listed as To be Discontinued (Date discontinued
     04/03/2020).
   - Both definitions: discontinued, (2020-04-02, 2020-06-12].
   - "Recovered" or "censored" would be O7.
4. **Fentanyl 2,500 mcg per 50 mL, Fresenius Kabi.** The event "Backordered. Next release
   December 2021." (dated 2021-10-08) is first seen on 2021-10-20 and re-confirmed on 2021-11-30
   (Reverified 2021-11-23).
   - The next capture, 2022-10-04, shows "Available" (Date of update 2022-09-14).
   - Definition B: recovered, (2021-11-30, 2022-10-04], 308 days. This is correct.
   - Flag F4 (the 2021 to 2022 archive gap). The bracket is not observable at 31 days.
   - The thread had gone from Available back to Backordered several times before; those earlier
     events are separate.
5. **Leuprolide 7.5 mg kit, Abbvie.** The event "Available.  Next expected release mid-November"
   (dated 2020-10-07) is first seen on 2020-10-11.
   - The row is available at `c0`, so the event is `not_at_risk` under B.
   - Under A it is at risk, since the Status is Current.
   - A B outcome of "recovered at 2020-10-17" would be O3.
6. **Hydromorphone 10 mg/mL, Teva.** The event "Backorder - Product availabilty ETA Late August"
   (dated 2020-08-20) is first seen on 2020-08-24.
   - 2020-09-15 shows "Available" (Date of update 2020-09-04).
   - Definition B: recovered, (2020-08-24, 2020-09-15], 22 days. It is observable at 31 days.
     Flag F1: 2020-09-04.

### 6.7 Pass rule and what happens on failure

The rule is the one in `PLAN.md` section 10. It passes when at least 95% of the audited brackets
agree with the auditor's reading, counted on confirmed errors over the 100 real items, for
definition B and separately for definition A.

- **Train half.** It is audited before registration. If the rule fails, or the same error code
  has the same cause twice or more, the builder rule is fixed, never single items. The outcomes
  are then re-derived and re-sealed, the affected items and 20 fresh ones are re-audited, and the
  new hash is recorded.
- **Test half.** A failure after registration is handled the same way, logged as a dated
  amendment with the new sealed hash, before the evaluator runs.

## 7. Task C: minimal-pair audit

### 7.1 Sample and what you see

- **Sample.** 100 E5 items, stratified by factor: certainty marker, surface form, granularity,
  stale against fresh, distractor date, and silent. At most 2 per seed.
- **Assignment.** 45 to A1, 45 to A2, and 10 audited by both. Each auditor also gets 5 planted
  items, where the generator's gold was corrupted in one field by a seeded rule. The key is held
  by the adjudicator.
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

This is the rule in `PLAN.md` section 10. It passes when at least 95 of the 100 real items are
free of confirmed errors. Otherwise the generator is fixed, the failing template or factor is
dropped or corrected, and a fresh 100 are audited, with the fix logged. Planted items are excluded
from the 100.

## 8. Statistics to report

All intervals are 95% percentile bootstrap intervals over items: 2,000 draws, with seed 20261001.
Every table gives n.

### 8.1 Task A (both annotators, before adjudication)

- **Month offsets.** For a date `d` and anchor `a`, the offset is
  `12 × (year(d) − year(a)) + (month(d) − month(a))`, computed for `start` and for `end`.
- **Krippendorff's alpha** (interval metric, two coders) on the start offset and, separately, on
  the end offset. It is computed over the items where both annotators gave an interval. This is
  the study's headline agreement figure and the pilot gate.
- **Secondary.** Alpha on day offsets (`start − a` and `end − a`, in days), and the share of items
  with identical start and end.
- **Cohen's kappa** over all items, on:
  - `abstain` (yes or no);
  - `certainty` (4 classes);
  - `statement_type` (5 classes);
  - `stale` (derived from the intervals, reported for completeness);
  - any distractor (yes or no).

  Each kappa is shown with the raw agreement and both annotators' marginal shares, since kappa
  moves with prevalence.
- **By form stratum and by period.** n, raw agreement, the kappas, and alpha when a stratum has at
  least 10 items (or pairs of intervals). Below that, raw agreement only.
- **Adjudication.** Counts of `slip` and `gap` decisions, by field.
- **Time.** The mean seconds per item, from the session start and end times written in each
  sheet's header.
- **Pilot and check set.** The same statistics, labelled v0 and v1, in an appendix.

Relation to `PLAN.md`: section 10 there asks for alpha "on endpoint offsets in days from the
anchor month". This guide reports month offsets as primary and day offsets as secondary, so both
readings of that phrase are covered.

### 8.2 Task B

- Agreement rate for each definition (B, A): (real items without a confirmed error) / (real items),
  with a Wilson 95% interval. It is given raw and reweighted to the population, and by half
  (train, test).
- Counts by error code and by flag. The test half is reported only as total counts of each code
  and flag. There is no breakdown by outcome type, width or stated period until the registered
  evaluator has run.
- Double-audited items: raw agreement and Cohen's kappa on `ok` against `error`.
- Planted items: the share each auditor caught. If an auditor misses 2 or more of their 5, they
  re-check their own real items once before results are reported. Both passes are reported.

### 8.3 Task C

- The share of the 100 real items free of confirmed errors, with a Wilson 95% interval, overall
  and by factor.
- Counts of the failures of each check: each label field, minimal, attested; and natural,
  separately.
- Double-audited items: raw agreement and kappa on `ok` against `error`. Planted items: the share
  caught, with the same re-check rule as task B.

## 9. Spreadsheet layout

One CSV file (UTF-8, comma-separated, a header row) per annotator per task. Spreadsheet software
may be used, with drop-down validation on the coded columns, but the file is saved back as CSV.
The first lines of each file are `#` comments giving the task, the annotator (A1 or A2), the
guide version and hash, the session start and end times, and, for task B, the `corpus.py`
docstring hash.

**Task A: `literal_<A1|A2>.csv`**

| Column | Shown or entered | Content |
|---|---|---|
| `item_id` | shown | random id; reveals neither form nor period |
| `drug`, `company`, `presentation` | shown | as in the entry block |
| `type_of_update` | shown | New, Revised or Reverified |
| `date_of_update` | shown | the anchor, ISO |
| `availability_information`, `related_information`, `reason_for_shortage` | shown | verbatim |
| `statement_type`, `start`, `end`, `abstain`, `abstain_reason`, `certainty`, `quote`, `distractor_roles`, `distractor_quotes`, `hard`, `note` | entered | section 3.4 |
| `stale`, `start_offset_m`, `end_offset_m`, `start_offset_d`, `end_offset_d`, `check` | computed | sections 3.9, 3.12 and 8.1 |

The gold file `literal_gold.csv` has the same entered columns, plus `adj_decision` (`agree`,
`slip`, `gap`) and `adj_note`.

**Task B: `outcome_<A1|A2>_<train|test>.csv`** (one row per item; the item blocks of section 6.3
are in a companion file `outcome_<half>_traces.csv`, one row per item and capture)

| Column | Shown or entered | Content |
|---|---|---|
| `audit_id` | shown | random id; planted items look the same |
| `generic`, `company`, `presentation`, `statement_text`, `statement_date`, `c0` | shown | section 6.3 |
| `class_strip` | shown | section 6.3 |
| `derived_B_type`, `derived_B_lower`, `derived_B_upper`, `derived_B_width`, `derived_B_censor` | shown | definition B |
| `derived_A_type`, `derived_A_lower`, `derived_A_upper`, `derived_A_censor` | shown | definition A |
| `verdict_B`, `verdict_A` | entered | `ok`, `error`, `cannot_tell` |
| `codes` | entered | semicolon list, O1 to O9 |
| `true_B_type`, `true_B_lower`, `true_B_upper`, `true_A_type`, `true_A_lower`, `true_A_upper` | entered | only when a verdict is `error` |
| `flags` | entered | semicolon list, F1 to F5 |
| `dou_first_recovered` | entered | for F1 |
| `note` | entered | |

Traces file columns: `audit_id`, `capture`, `present`, `linked_by` (`key` or `ndc`), `status`,
`type_of_update`, `date_of_update`, `availability_information`, `related_information`,
`resolved_note`, `change_date`, `date_discontinued`, `class_letter`, `gap_before_days`.

**Task C: `pairs_<A1|A2>.csv`**

| Column | Shown or entered | Content |
|---|---|---|
| `pair_id`, `seed_id`, `factor`, `level` | shown | |
| `seed_entry`, `seed_gold` | shown | the seed's entry block and gold |
| `edited_entry` | shown | the edited entry block (fictitious names) |
| `gold_statement_type`, `gold_start`, `gold_end`, `gold_abstain`, `gold_certainty`, `gold_stale`, `gold_distractor_roles` | shown | the generator's gold |
| `attested_text` | shown | a real notice using the inserted form |
| `ok_type`, `ok_interval`, `ok_certainty`, `ok_stale`, `ok_distractors`, `minimal`, `attested`, `natural` | entered | 1 or 0 |
| `verdict` | computed | `error` if any of the checks before `natural` is 0 |
| `correct_value`, `note` | entered | when a field is 0 |

## 10. Files, hashes and sealing

- **Blank sheets.** Task A and task C blanks, the pilot and the check set go to
  `analysis/coling/out/annotation/`. They contain only public notice text and fictitious pairs.
  Train-half task B sheets go there too.
- **Test-half task B sheets** go only to `external_data/sealed/audit/`. They stay there until the
  registered evaluator has run.
- **Work in progress.** Each annotator keeps their filled sheet under
  `external_data/annotation/<task>/` (git-ignored) until both have submitted.
- **Submission.** The sheet builder records the sha256 of each submitted sheet in
  `analysis/coling/out/annotation/manifest.json`, then commits the pair together, with the
  agreement output and later the gold. The gold hash is recorded before any model output on those
  items is opened.
- **Planted-error keys** go to `external_data/annotation/keys/`, and only the adjudicator opens
  them.

## 11. ARR Responsible NLP checklist statement

Draft for section D of the form (human annotators; check the item wording on the current form).
The bracketed parts are for the authors to confirm.

> All human labels in this paper were produced by two of the authors. No crowdworkers or other
> participants were recruited, and no one was paid for annotation beyond their normal
> [salary or studentship]. The annotators labelled public notices from the US FDA drug-shortage
> list, a US federal government work that contains no personal information; the list's company
> contact column was removed before annotation and release. The full guideline, including the
> time conventions, blinding rules, pilot and adjudication procedure, is released with the data
> (Appendix [X]). Because the annotators are authors labelling public, non-personal text, and no
> data about people were collected, we did not seek ethics-board review [confirm that this matches
> institutional policy]. Both annotators are fluent readers of English with a background in
> [NLP research]. Because they knew the study's hypotheses, they labelled blind to model outputs,
> to later versions of each notice and to realised outcomes, and the literal labels were frozen
> before any model output on those items was inspected; agreement is reported before
> adjudication.

The checklist's AI-assistance item should also say that this guideline was first drafted with an
AI assistant and then revised and adopted by the authors.

## Appendix A. Statements used as examples (excluded from every sample)

These are identified by generic, company and statement date.

| Generic | Company | Statement date |
|---|---|---|
| Bupivacaine Hydrochloride and Epinephrine Injection, USP | Hospira, Inc. | 2019-10-07 |
| Cefoxitin for Injection, USP | Fresenius Kabi USA, LLC | 2020-08-13 |
| Hydromorphone Hydrochloride Injection, USP | Teva Pharmaceuticals | 2020-08-20 |
| Lidocaine Hydrochloride (Xylocaine) Injection | Fresenius Kabi USA, LLC | 2021-05-19 |
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

## Appendix B. Decision points and alignment with the code (as of 29 September, 06:30)

This guide follows the `literal-v1` prompt of `read.py` wherever the prompt speaks, and `rules.py`
where the prompt is silent. The rows below record where the three documents first differed and
how each point stands. Open points are settled at the pilot meeting. After that, the prompt or the
rule reader is brought into line before F1, or the mismatch is disclosed.

**Check against the rule reader.** `rules.read` with `as_literal_v1` (version of 06:17) was run
on the 20 worked examples, the 3 hard cases and 4 of the minimal pairs. It gives the reading of
this guide in type, interval, certainty and stale for all 27. The one difference is a distractor
role in example 17, where the rule reader lists "May and July delivery" as `other`; this guide
counts those words as delivery mentions, not distractors. Eighteen further probes of the
conventions of section 3.7 (end of the year, within and over the next N, "by" a time already past,
weeks, quarters, halves, 30-day months, a bare "TBD", a yearless quarter) also agree, except the
yearless season (D13).

| # | Point | `read.py` prompt | `rules.py` | This guide | Status |
|---|---|---|---|---|---|
| D1 | Certainty of an abstaining target that has no unknown marker | "undetermined" is defined as "the entry says the timing is not known" | `as_literal_v1`: `vague` gives estimated; `no_date` and `tbd` give undetermined | as `rules.py` (3.8) | open: the prompt should add one sentence saying so |
| D2 | An undated discontinuation against a dated depletion | the order is recovery, next delivery, discontinuation, depletion | the same order; within a type, dated beats TBD beats undated | as both (3.6) | agreed |
| D3 | "Until X", "through X" | not covered | the period X | the period X (C11) | open: the prompt should say so |
| D4 | "By X" | the Date of update to the end of X | the same, or X itself when X ends before the anchor | as both (C10) | agreed |
| D5 | "Final date of availability" | the depletion definition includes "until when product remains available" | discontinuation ("final date") | discontinuation (3.6) | agreed with `rules.py`; the prompt's wording overlaps |
| D6 | "No plans to manufacture until X" | not covered | recovery (a shortage state ending) | recovery, `hard` (H2) | agreed |
| D7 | Length of a relative month | 30 days | 30 days | 30 days (C12) | agreed |
| D8 | Certainty vocabulary | `asserted`, `estimated`, `undetermined`, `no_statement` | internally `firm`, `estimated`, `expected`, `anticipated`, `unknown`, mapped by `as_literal_v1` | the prompt's four classes | agreed |
| D9 | The type "availability until" | inside depletion | its own type internally, mapped to depletion | depletion | agreed |
| D10 | Fields shown to readers | `ENTRY_BLOCK`: no Status, Therapeutic Category or Initial Posting Date | | as `read.py` (3.3) | open: `PLAN.md` section 2.3 lists more fields |
| D11 | Outcome definitions | | | the audit follows the frozen `corpus.py` (A, B; BL as a sensitivity) | open: `PLAN.md` names them R2 and R1 and takes the maximum over the presentations an event covers, while `corpus.py` builds events per presentation thread |
| D12 | Size of the literal task | | | 150 items double-labelled, 20-item pilot and 10-item check set | open: `PLAN.md` section 10 says 300 single-labelled with 60 double-labelled and a 30-item pilot |
| D13 | Seasons ("winter 2021", "in the summer") | not covered | with a year, the year (the season word is ignored); with no year, `none` | the year; with no year, `vague` (C17); `hard` | open: none were found in the train-period text checked; decide at the pilot whether to add a season convention to both |

## Changelog

- **v0, 29 September 2026.** First draft, before the pilot.
