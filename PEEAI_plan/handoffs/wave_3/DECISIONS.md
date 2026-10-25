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
11. **The evidence directory is filled by the collector.** In this working tree it was run once
    to check it. The integrate step regenerates it from a clean checkout.
