# Literal-reading sheets: how to fill and return them

For annotators A1 and A2. The rules are in `analysis/coling/plan/AUDIT_GUIDE.md`; this page only
says what to do with the files. Read sections 1 to 3 of the guide and the opening of section 9
before you start.

## Your files

| Task | Your sheet | When |
|---|---|---|
| Pilot | `pilot_A1.csv` or `pilot_A2.csv` | first, under the draft guide |
| Check set | `check_A1.csv` or `check_A2.csv` | after the pilot meeting, under guide v1 |
| Reserve check set | `reserve_A1.csv` or `reserve_A2.csv` | only if the check set has to be repeated |
| Literal task | `literal_A1.csv` or `literal_A2.csv` | after registration |

Take only the sheet with your own label, and only when the sheet builder tells you it is ready.
A sheet can be in this folder before it is ready: the check sheets are written again after the
pilot meeting, so that they name the guide you label them under.

Do not open anything else here until the sheet builder says the task is closed: not the other
annotator's sheet, not `keys/`, `samples/`, `submitted/`, and not the `*_agreement.json`,
`*_labels.csv`, `*_disagreements.csv` or `*_adjudication.csv` files (guide, section 2).

## Steps

1. **Copy** your sheet to `external_data/annotation/<task>/` and work on the copy. Leave the file
   in this folder as it is: the validator compares your copy with it.
2. **Open** the copy in a spreadsheet or a text editor. In a spreadsheet, import it as UTF-8,
   comma-separated, with **every column as text**, so that dates and `2021-03` are not converted.
   Keep the lines that begin with `#`. A cell that begins with an apostrophe (`'-10 mg`) is
   written that way on purpose; leave it.
3. **Write the time** you start after `# sitting_start:` and the time you stop after
   `# sitting_end:`, as `HH:MM`. If you stop and come back, add another pair of these two lines
   under the first.
4. **Label every row.** Read only the row in front of you (guide, section 3.3), and label by
   hand, alone, with at most a calendar (section 2). The shown columns are the entry; do not
   change them. Fill the columns from `statement_type` on:

   | Column | What to enter | Guide |
   |---|---|---|
   | `statement_type` | `recovery`, `next_delivery`, `depletion`, `discontinuation` or `none` | 3.6 |
   | `start`, `end` | `YYYY-MM-DD`; `YYYY-MM` means the first day of the month in `start` and the last day in `end`; both empty when you abstain | 3.7 |
   | `abstain` | `1` when `start` and `end` are empty, else `0` | 3.7 |
   | `abstain_reason` | `tbd`, `no_date`, `vague` or `no_statement`; only when `abstain` is `1` | 3.7 |
   | `certainty` | `asserted`, `estimated`, `undetermined` or `no_statement` | 3.8 |
   | `quote` | the shortest exact words your reading rests on; needed only when the entry has more than one time expression | 3.4 |
   | `distractor_roles` | a list separated by semicolons: `expiry`, `depletion`, `discontinuation`, `onset`, `past`, `other` | 3.10 |
   | `distractor_quotes` | the words of each distractor, in the same order, separated by semicolons; if a quote holds a semicolon, separate the quotes with a vertical bar instead | 3.10 |
   | `hard` | `1` when you had to stretch a convention, else `0` or empty | 3.4 |
   | `note` | free text; required when `hard` is `1` | 3.4 |

   You do not enter `stale` or any offset; they are computed later.
5. **Save** as CSV UTF-8 (comma-separated), under the same name.
6. **Check** your copy. From the repository root:

   ```
   PYTHONPATH=. python -m analysis.coling.audit_sample validate external_data/annotation/<task>/<your sheet>
   ```

   Each line that starts with `error:` names a row and what is wrong with it (guide, section
   3.12), or says that the file was saved in another format. Fix it and run the check again
   until there is none. A line that starts with `warning:` asks you to look once more (a quote
   that is not word for word in the entry, a date more than 60 months from the Date of update);
   change the row only if it is a typing error.
7. **Return** the checked copy to the sheet builder, and say so. Do not send it to the other
   annotator, and do not talk about items until both sheets are in (guide, section 2, rule 4).

Questions about the guide go to the adjudicator, in writing. The answer goes to both annotators.

## For the adjudicator

After both literal sheets are in, the sheet builder gives you `literal_adjudication.csv`. Copy it
to `external_data/annotation/literal/` and work on the copy. For each row, fill the columns from
`statement_type` to `note` with the decided label, `adj_decision` with `slip` or `gap`, and
`adj_note` (guide, section 5). A `gap` row that cannot be settled is left without a label. Return
the copy to the sheet builder.

## For the sheet builder

Every file in this folder except this page is written by a command, from the repository root
with `PYTHONPATH=.`. Until the freeze run has rewritten `analysis/coling/out/events.csv.gz`, add
`--captures external_data/fda_wayback_csv` to the first three.

```
# sample lists (samples/), the pilot and check sheets, their item files and keys, manifest.json
python -m analysis.coling.audit_sample draw --sheets pilot check
# a sheet under a revised guide, or the reserve and literal sheets, from the lists on disk
python -m analysis.coling.audit_sample sheets --task check
# after the train-half outcome sample is final: in-context pool, dev prompt items, pair seeds
python -m analysis.coling.audit_sample draw-later --outcome-sample <outcome_train_sample.csv>
# both sheets returned: statistics, disagreements, and for check and reserve the gate
python -m analysis.coling.audit_agreement agree --task pilot --a1 <A1 copy> --a2 <A2 copy>
# literal task, after adjudication: the gold file and its hash
python -m analysis.coling.audit_agreement gold --adjudication <filled copy of literal_adjudication.csv>
```

- A draw repeated on the same inputs writes the same bytes. When the guide or the events table
  has changed so that a list on disk would hold other statements, `draw` stops and writes
  nothing. Name the sample under `--fixed` to keep its list, or under `--replace` to take the
  new one (with `--sheets` for it too, when its sheets are in this folder). Keep a list once a
  sheet of it has been handed out, and keep all four once the train-half outcome sample has
  been drawn, since that sample leaves them out.
- `draw` and `draw-later` stop when a row of the guide's Appendix A names no event, or when the
  fixed test item of the prompt harness is on no statement: correct the appendix.
- Both also leave out every statement whose whole text is a phrase the guide quotes in section
  3 or 7, or whose two text fields are each one (guide, Appendix A.4). `draw` prints how many
  frame statements that removes, by stratum and period, and the manifest keeps the table
  (`phrase_rule`). A paragraph of those sections with an odd number of quotation marks stops
  the draw: close the quotation. `draw` also prints how many items of each sample contain a
  quoted phrase among other words (`items_containing_a_guide_phrase` in the manifest).
- `draw-later` leaves out, besides, the statements that read like an item of the first draw:
  the same whole text on any drug, and the item's notice on another presentation (guide,
  section 10). It prints how many frame statements each of the two rules leaves out. Like
  `draw`, it stops and writes nothing when a list on disk would change; `--replace` takes
  the new lists.
- `sheets` draws nothing and reads no exclusion: under a guide revised after the draw it
  writes the same items with the new guide line.
- The lists of `draw-later` are in `samples_later/`, with `draw_rank` and `period`. A pair
  seed whose `period` is `test` (the relative form) is sent to no model before amendment F1
  of the plan is tagged.
- A sheet in this folder that holds labels was filled in place. The commands do not write over
  it; move it to `external_data/annotation/<task>/` first.
- `agree` checks each returned sheet against the blank here, so do not write a sheet again
  between handing it out and running `agree` on it. `agree` does not run again on the literal
  task while `literal_adjudication.csv` here holds a decision.
- After the pilot meeting, write the check sheets again (`sheets --task check`) before they are
  handed out; likewise the reserve sheets after a second revision. The gate prints a warning
  when a sheet names the same guide as the set labelled before it.
- `manifest.json` records the sha256 of every list, blank sheet, submitted sheet, agreement
  output and of the gold.
