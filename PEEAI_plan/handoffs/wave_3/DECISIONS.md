# Decisions taken in W3.4 (presentation and release)

Taken by the automated `story` worker under the 75-minute time box. No human has reviewed them.

1. **The script follows the deck.** `SHOWCASE.md` uses the submission deck's 12 timed slides and
   its spoken lines (`pres-note.md`) for slides 5, 9, 10, 11 and 12. That keeps the two from
   disagreeing. The board is optional. The deck alone tells the story.
2. **The failure shown is the deck's: C06, P2, `hk_q8n__P2__s101`** (planner input). It is the
   most informative miss that can be told without case contents: a correct reading that never
   reached the planner. C07/P2 (`hk_f6k__P2__s101`, cap before an approved fallback could be
   applied) is kept as the second failure, for questions.
3. **The tradeoff is stated plainly:** "P2 shows no consistent advantage." The figures behind
   it: P2 cost about a third of P1 on campus and met fewer cases. Per-case causes are given, so
   the tradeoff can be explained.
4. **The pantry cameo label is "deterministic pantry policy acting live in the sandbox".** The
   template's three labels assume a model. The cameo runs the implemented adapter, so it is not
   a "Planned domain extension". No model runs in it, so it is not "Live model + sandbox tools".
   The fallback is a **Recorded replay** of `pantry_dev01_trace.json`.
5. **No paid call.** The live UI press the task allowed was not used. The showcase does not rely
   on live mode, and a 429 during a concurrent run would cost a call for nothing.
6. **Forced failure without network or key.** Rehearsal 2 points the provider at a closed port
   on 127.0.0.1, with a placeholder key file. Its server runs the CLI with the spend ledger moved
   to a temporary file (`plan_b.agent.config.DEFAULT_LEDGER`, patched in the server process
   only), so the real ledger is never touched. The real provider class still runs end to end up
   to the connection.
7. **The rehearsal reuses the storyboard's story** unchanged (`storyboard.story`), with
   `load_case` wrapped to read each episode's receipts and final state before it is reset. The
   three rehearsals must give identical signatures, plus the known outcomes.
8. **What the release package contains:**
   - It includes the results directory: public records, traces, reports, `FAILURES.md` and the
     voided attempt's public parts.
   - It excludes every `runner_private/` and the held-out case files
     (`scenarios/private/eval/`). These are evaluator-only.
   - It includes `heldout.json`: file hashes, the ref-to-id-to-fixture mapping, each case's
     outcome class and the negative-control outcomes of C02 to C04. The results README and
     `FAILURES.md` already publish all of these.
   - It includes only the nine fallback traces the runbook opens, not all 31 Wave 2 traces.
9. **The package is verified from itself.** `plan_b` is imported from the package directory.
   The checks are freeze.json, the held-out public fixtures against `heldout.json`,
   `demo_prep.py`, `plan-b serve` with every `PLAN_B_*` variable removed (so no model
   configuration), the board and each replay byte for byte, and `verify-trace`.
10. **Stale policy ids were updated to the frozen ids.** This covers `apps/plan_b/README.md` and
    the `scripts/run_live_cases.py` docstring. `scripts/` is not in freeze.json (checked), so
    this changes no frozen file. Recorded Wave 2 traces keep their 1.0.0 ids, as both texts now
    say.
11. **The evidence directory is filled by the collector.** It was first run on the working tree
    to check it. The integrate step then regenerated it from a clean checkout of `3442874`.

## Wave 3b polish (October 25, 2026, no paid call, no result changed)

12. **The spoken script was cut to 921 words, about 395 s (later 932 words, about 399 s, item 22).** The slide budgets and checkpoints
    stay at the 420 s plan, so about 25 s are left for pointing and slide changes. The cuts
    removed repeated or developer wording. Every honesty line stays, and three were added to the
    spoken text: "twelve held-out cases" (slides 9 and 12), "These are descriptive counts only"
    (slide 9) and "No community has used it yet" (slide 12). The P3 sentence of slide 8 is no
    longer "skip if late", because P3 appears in the results. The `\note` blocks of
    `slides.tex` carry the same text.
13. **The poster leads with what the project is.** The band reads "An AI event coordinator that
    decides what to verify, what to prepare, and when to commit a change", and the 2-minute
    script states the held-out finding in its first 20 seconds. Case-level counts (B7) are given
    as one line, "P1 met all 8 campus cases", from the generated macro `campus:P1:cases`. A full
    case table would crowd column 3, and for P1 to P3 every miss repeated in all trials of its
    case, so the run bars carry the same proportions.
14. **The board text has no em dash, with three exceptions.** The label `Unavailable — service did not respond`
    stays, because `tests/e2e/walkthrough.py` (outside this step) matches it
    exactly. The `—` placeholder for an empty value and the `–` icon of "Not applicable" are
    symbols, not prose. Time ranges keep their en dash (`17:10–17:30`), which
    `walkthrough_wave2.py` matches.
15. **No static table of contents in the documentation.** Its headings are Word heading styles,
    so Word's navigation pane lists them, and a typed list would go stale if a section is added.
16. **`DRAFT.md` is now in `check_writing.py`.** It is an internal draft, but it lives beside the
    items and had the only remaining semicolons (E9).
17. **Test gaps closed in the tests, not in the frozen code.** `tests/test_release_failures.py`
    gained the provenance walk of functional check 11 (P0 on seven development cases, P1 to P3
    with the scripted provider on dev01 and pantry_dev01, a forged label and a quoted status),
    the consumed-kits-in-a-later-slot drill, and a check that `web/dist/index.html` is the build
    of `web/index.html` with nothing else in `web/dist` (D5). `tests/e2e/keyboard.py` now has 21
    checks. No frozen file changed. D10 (searching the bundle for every held-out case's private
    strings) and C13(c) (the closed-port race in `rehearsal.py`) stay open: D10 reads the
    held-out registry that the v1.2 workers are changing, and `rehearsal.py` is outside this step.

## Wave 3b results in the deliverables (October 25, 2026, no paid call)

18. **Three result layers, each always labeled.** (i) The v1.1 held-out run
    `wave3_heldout_20261025T1625Z` stays the evaluation of record, with every number and
    sentence about it unchanged. (ii) Version 1.2 on the fresh held-out set C09 to C12, T05 and
    T06 (`wave3b_fresh_20261025T2327Z`, 60 runs) is called "a new, small held-out check". (iii)
    Version 1.2 on the spent cases (`wave3b_rerun_spent_20261025T2345Z`) is called "post-hoc
    diagnostic rerun, on spent cases, not held-out" wherever it appears. Layer (iii) appears only
    beside its label, never in a held-out heading or figure.
19. **A second source in `make_results.py`, never a replacement.** `RUN_ID` still reads the v1.1
    run. `V12_RUNS` adds the fresh run and the rerun, and their numbers go to new files under
    prefixed keys: `slides/figures/results_numbers_v12.tex` (`\res{fresh:campus:P2:met}`,
    `\res{rerun:pantry:P3:met}`, and the totals `fresh:both:metk` and `fresh:both:metn`) and
    `documentation/results_v12.json`. No v1.1 key is shadowed. `cmp` against copies taken before
    the change shows `results_numbers.tex`, `fig_results.tex`, `fig_results_v.tex` and
    `results.json` byte-identical.
20. **No comparative claim beyond descriptive counts.** The fresh counts are not set against the
    v1.1 counts as an improvement, because the cases differ, and the rerun counts are not one
    either, because the fixes came from those cases. The wording is "consistent with the fixes",
    never "the fixes removed". P2 still shows no consistent advantage, and the items say so.
21. **The rerun's harness labels are quoted with their explanation, not edited.** Its
    `plan.json`, `metrics.json` and report text say "held-out" because a scratch case lock was
    the only way to run spent ids without a code change. Raw records and reports are never
    edited, so every item that cites the rerun carries its label instead.
22. **Version 1.2 gets its own slide, and the script stays under 400 s.** Slide 12, "Version 1.2:
    the fixes, then six fresh held-out cases", sits after the pantry slide, with a two-row table
    (the v1.1 record and the fresh 1.2 run) and the caption "not a before and after". The
    diagnostic rerun is only on a backup slide, so the main deck never sets it beside the record.
    To make room, the spoken voided-attempt and refusal sentences of slide 9 moved to the slide
    and its backup, and a few phrases elsewhere were cut. The script is 932 words, about 399 s
    against the 420 s plan, with the slide budgets and checkpoints set again (`REHEARSALS.md`).
23. **Final audit fixes stay small (audit3).** Four read-only auditors (a first-time judge,
    every number against the three result layers, the writing rules and templates, and the M3
    record) found no number mismatch and no honesty problem. The fixes: slide 9 says "version
    1.1" in its title, the slide 12 table row reads "Version 1.2: 6 different, fresh cases", the
    architecture card names the recorded decision's version 1.0, the cost backup labels its
    capped counts as version 1.1 and adds "21 runs, 15 of them among the 26 failed runs", and
    the void sentence says why it is a departure. Push-state sentences in the packet now carry
    a date, so they stay true after the integrate step pushes. The screenshot characters are
    recorded as limitation 28, not edited.
