# Outcome audit, train half: how to fill and return the sheets

For annotators A1 and A2. The rules are in `analysis/coling/plan/AUDIT_GUIDE.md`, section 6; this
page only says what to do with the files. Read section 6 of the guide and the opening of section
9 before you start.

## Your files

| File | What it is |
|---|---|
| `outcome_A1_train.csv` or `outcome_A2_train.csv` | your sheet: one row per item, 33 rows; your verdicts go here |
| `outcome_A1_train_items.txt` or `outcome_A2_train_items.txt` | the same items as text, each with its trace under it, in the order of your sheet; read the items here if you prefer |
| `outcome_train_traces.csv` | the capture rows of every item, as a table, for both auditors |

Take only the two files with your own label and the traces file, and only when the sheet builder
tells you they are ready. Do not open the other auditor's sheet or items file, and do not open
`outcome_train_adjudication.csv` or `outcome_train_score.json` when they appear (guide, section
2). The key of the planted items is not in this folder; nobody opens it.

## Steps

1. **Copy** your sheet to `external_data/annotation/outcome_train/` and work on the copy. Leave
   the file in this folder as it is: the validator and the scorer compare your copy with it.
2. **Open** the copy in a spreadsheet or a text editor. In a spreadsheet, import it as UTF-8,
   comma-separated, with **every column as text**, so that dates are not converted. Keep the
   lines that begin with `#`. A cell that begins with an apostrophe is written that way on
   purpose; leave it.
3. **Write the time** you start after `# session_start:` and the time you stop after
   `# session_end:`, as `HH:MM`. If you stop and come back, give the times of each sitting on
   the same two lines, separated by semicolons (`09:00; 13:00` and `10:05; 13:20`).
4. **Check every row** as section 6.4 of the guide says, with the item's trace beside it. The
   shown columns are the derived outcome; do not change them. Fill the columns from `verdict_B`
   on:

   | Column | What to enter | Guide |
   |---|---|---|
   | `verdict_B`, `verdict_A` | `ok`, `error` or `cannot_tell`, for definition B and for definition A | 6.4 |
   | `codes_B`, `codes_A` | the error codes `O1` to `O9`, separated by semicolons; only with `error` | 6.5 |
   | `true_B_type`, `true_B_lower`, `true_B_upper` and the same for A | only with `error`: what you read instead (`recovered`, `discontinued`, `censored` or `not_at_risk`; dates as `YYYY-MM-DD`) | 6.5 |
   | `note_codes` | the flags `N1` to `N6`, separated by semicolons; a flag is never an error | 6.5 |
   | `dou_first_recovered` | `YYYY-MM-DD`, exactly when `note_codes` has `N1` | 6.5 |
   | `note` | free text; required for `cannot_tell` and for `O9`, and for an `error` with no `true_` cell | 6.5 |

   Do not record, and do not work out, whether the statement's estimate held.
5. **Save** as CSV UTF-8 (comma-separated), under the same name.
6. **Check** your copy. From the repository root:

   ```
   PYTHONPATH=. python -m analysis.coling.audit_outcomes validate external_data/annotation/outcome_train/<your sheet> --blank analysis/coling/out/audit_outcomes/<your sheet>
   ```

   Each line that starts with `problem:` names an item and what is wrong with it, or says that
   the file was saved in another format. Fix it and run the check again until there is none. A
   line that starts with `warning:` asks you to look once more (a shown cell that changed, or
   session times that cannot be read).
7. **Return** the checked copy to the sheet builder, and say so. Do not send it to the other
   auditor, and do not talk about items until both sheets are in (guide, section 2, rule 4).

Questions about the guide go to the adjudicator, in writing. The answer goes to both annotators.

## For the adjudicator

When both sheets are in, the scorer writes `outcome_train_adjudication.csv` here: one row for
each item and definition that an auditor marked `error` or `cannot_tell`, with both auditors'
entries. Fill `decision` (`confirmed`, `rejected` or `unresolved`), and for a confirmed error
`confirmed_codes` and `cause`; `adj_note` is free (guide, sections 5 and 6.7). Planted items are
not on it. Tell the sheet builder when it is filled.

## For the sheet builder

Every file in this folder except this page is written by a command, from the repository root
with `PYTHONPATH=.`.

```
# the sample, both sheets, the items files, the traces and the manifest; the key goes to
# external_data/annotation/keys/
python -m analysis.coling.audit_outcomes sheets --half train
# both sheets returned: the planted items are scored and the adjudication sheet is written
# (exit status 3); run again once it is filled for the result (0 pass, 1 fail)
python -m analysis.coling.audit_outcomes score --half train --a1 <A1 copy> --a2 <A2 copy>
```

- `sheets` needs the four sample lists under `analysis/coling/out/audit/samples/`: the audit
  leaves out their threads. Run again on the same inputs it writes the same bytes.
- A final set in this folder is not written over by a set that differs, unless `--replace` is
  given. Do not replace a set once a sheet of it has been handed out: the returned sheets could
  no longer be scored.
- `score` checks both returned sheets against the blanks here, and the blanks and the key
  against `outcome_train_manifest.json`, before it reads the key.
- A re-audit after a rule fix is written to another folder (`--out` and `--keys`); the guide's
  section 6.7 gives the two commands.
