Post-hoc diagnostic rerun after fixes, on spent cases. Not a held-out result.

# Diagnostic rerun of policy 1.2 on the spent Wave 3 cases: run `wave3b_rerun_spent_20261025T2345Z`

This directory holds a run of the frozen policy version 1.2 on the twelve Wave 3 cases that
are **spent**: C01 to C08 (campus) and T01 to T04 (pantry). The 1.2 fixes were made after
reading the v1.1 failures on exactly these cases. A better count here is therefore expected
and says nothing about cases the fixes never saw. This run is a check that the fixes do what
they were written to do on the cases that motivated them, and that they broke nothing else
there. It is never a held-out result, and no table built from it may call it one.

- The evaluation of record for version 1.1 is `wave3_heldout_20261025T1625Z`. It is not edited,
  replaced or relabeled by this run.
- The only held-out result for version 1.2 is the fresh set in `wave3b_fresh_20261025T2327Z`
  (C09 to C12, T05 and T06).

The design is the frozen protocol's: P0 once per case, P1, P2 and P3 at seeds 101, 202 and 303.

- **campus**: **80 of 80 episodes recorded.**
- **pantry**: **40 of 40 episodes recorded.**

The run is complete. Nothing was stopped early.

## Results (counts from `campus/report/` and `pantry/report/`)

Each cell gives the episodes that met their case's outcome class over the recorded episodes.

| Suite | Policy | Met / recorded | By class | Statuses | Provider-reported USD |
| --- | --- | --- | --- | --- | --- |
| campus | P0 rules | 6/8 | goal completion 5/7 (C06, C07 missed), appropriate infeasibility 1/1 (C08) | 8 completed | 0 |
| campus | P1 tool use | 24/24 | goal completion 21/21, appropriate infeasibility 3/3 | 23 completed, 1 capped | 3.003018 |
| campus | P2 selective | 21/24 | goal completion 18/21 (C07 missed 3 times), appropriate infeasibility 3/3 | 21 completed, 3 capped | 1.044174 |
| campus | P3 verify-all | 24/24 | goal completion 21/21, appropriate infeasibility 3/3 | 24 completed | 0.528386 |
| pantry | P0 rules | 4/4 | original target 2/2 (T01, T02), supported partial 2/2 (T03, T04) | 4 completed | 0 |
| pantry | P1 tool use | 10/12 | original target 6/6, supported partial 4/6 (T04 missed 2 times) | 4 completed, 8 capped | 2.660922 |
| pantry | P2 selective | 12/12 | original target 6/6, supported partial 6/6 | 8 completed, 4 capped | 0.975414 |
| pantry | P3 verify-all | 9/12 | original target 3/6 (T02 missed 3 times), supported partial 6/6 | 9 completed, 3 capped | 0.732672 |

The USD column sums the provider-reported costs in `episodes/*/record.json`. The suite totals
match `spend_extract.json`: campus 4.575578 and pantry 4.369008.

By case (all trials met): campus P0 6/8, P1 8/8, P2 7/8, P3 8/8. Pantry P0 4/4, P1 3/4, P2 4/4,
P3 3/4. These are descriptive counts from one run on cases the fixes were built from.

### Side by side with the v1.1 record (descriptive only)

The v1.1 column is copied from `wave3_heldout_20261025T1625Z/README.md`. The two runs share the
cases, seeds, caps and model, but not the code, and the v1.2 code was written after reading the
v1.1 column's failures. So the difference is consistent with the fixes doing what they were written to do on
the failures they were written from, though model runs also vary between trials. It is not a measured improvement, and no claim beyond these counts
is made.

| Suite | Policy | v1.1 record (held-out) | This rerun, 1.2 (post-hoc, not held-out) | Misses in this rerun |
| --- | --- | --- | --- | --- |
| campus | P0 | 6/8 | 6/8 | C06, C07 |
| campus | P1 | 24/24 | 24/24 | none |
| campus | P2 | 18/24 | 21/24 | C07 ×3 |
| campus | P3 | 21/24 | 24/24 | none |
| pantry | P0 | 4/4 | 4/4 | none |
| pantry | P1 | 6/12 | 10/12 | T04 ×2 |
| pantry | P2 | 9/12 | 12/12 | none |
| pantry | P3 | 6/12 | 9/12 | T02 ×3 |

Every miss in this rerun is in a case and policy pair that also missed in the v1.1 record. The
pairs that missed in v1.1 and met here are C06 under P2 and P3, T03 under P1, P2 and P3, and
T04 under P1 in one of three seeds. C07 under P0 and P2, C06 under P0 and T02 under P3 miss as
before (see [`FAILURES.md`](FAILURES.md)).

Some details behind these counts:

- **Integrity measures.** Executed violations are 0 for every policy in both suites.
  Unnecessary committed changes on the negative controls C02 to C04 are 0 for every policy. The
  pantry has 0 conservation failures. Invalid attempts (tool calls the server refused, none
  executed) are campus P0 0, P1 3, P2 0, P3 6 and pantry P0 4, P1 13, P2 4, P3 9, mostly stale
  revisions (`REVISION_CONFLICT`, `CANDIDATE_STALE`) and, on T03, the declined handoff hold
  (`RESOURCE_UNAVAILABLE`).
- **Who decided** (`decided_by`, `metrics.json`). C08: P0 policy 1, P1 model 3, P2 server 3,
  P3 server 3. Pantry partial fulfillment: T03 P0 policy 1, P1 model 3, P2 server 3, P3 server
  3, and T04 P0 policy 1, P1 model 1, P2 server 3, P3 server 3.
- **Model-call cap.** The cap of 8 was reached in 19 of the 120 episodes (campus 4, pantry 15).
  It ended 8 of the 10 misses. 11 capped episodes met their class.

## How this run was made, and why the harness calls it "held-out"

The harness has no separate mode for a diagnostic rerun of spent cases. Without a code change
(none was allowed), the run was made as follows:

- `heldout.json` (the v1.1 lock) no longer verifies, by design: the fresh set added 16 files
  (the 15 files under `scenarios/*/eval/set2/` and `README_set2.md`), and the lock was made against `freeze.json`, not
  `freeze_v1_2.json`. `heldout2.json` covers only the fresh cases, so the harness refuses C01 to
  T04 under it.
- So a **diagnostic lock** of the twelve spent cases was written outside the repository with
  `plan-b eval lock-heldout --manifest <scratch>/diag/diagnostic_lock_spent_v1_2.json --freeze
  freeze_v1_2.json --cases C01,...,T04` at 2026-10-25T23:28:29Z (27 files, files_sha256
  `988d088f...8ef5`). It was never committed to `plan_b/evaluation/manifests/`. A copy is in
  `manifests/` here. It was written after the 1.2 fixes and after the fresh run had started,
  and it carries no held-out meaning. It only lets the unchanged harness check that the case
  files, the frozen code and the protocol settings are the frozen ones.
- Because the run goes through that path, `plan.json` and `report/metrics.json` record
  `"heldout": true`, `plan.json` records the phase `frozen`, each `report/evaluation_results.md`
  says "held-out" in its opening paragraph and in its run manifest ("held-out lock
  files_sha256"), the lock copy's `artifact` is `plan_b.eval_heldout`, and
  `runner_private/cases.json` keeps each case's private-store flag `"heldout": true`. In this
  directory those words mean "evaluator cases from the private store, run under the frozen
  settings". They do not make this a held-out result.
- The report's column headers ("Goal completion C01–C07" and so on) are fixed text and happen
  to match these cases.

## Integrity of the run

- **Worktree.** Both suites ran from the same clean detached worktree of commit `5955243` as the
  fresh run. Each invocation recorded `git_head` `5955243`, `app_tree_clean` true, `freeze.ok`
  true (`freeze_v1_2.json`, 76 files, files_sha256 `c3ad3118...488a`) and `heldout_lock.ok` true
  for the diagnostic lock (`*/invocations.jsonl`). The results directories were outside the
  worktree. No code, case or fixture was changed.
- **Order.** It started after the fresh run had finished. Campus ran from 23:45:01Z to
  23:56:53Z, then pantry from 23:56:53Z to 00:09:15Z (2026-10-26). The order was shuffled within
  each case over all four policies from order seed 20261025 (`plan.json`).
- **Concurrency and rate limits.** Unlike the v1.1 record and the fresh run (`--jobs 1`), this
  run used `--jobs 2`. OpenRouter allows this account 20 requests per minute for the model, so
  two concurrent episodes sometimes got HTTP 429. Version 1.2's provider waits a 429 out inside
  the same call (3 s doubling to 20 s, at most 60 s in all) and sends the request again, so a 429
  uses none of the episode's 8 model calls. This was checked on the first affected episodes
  before the run went on (`hk_m2q__P3__s202`, `hk_m2q__P2__s202`: 2 retries and 9 s of waiting
  inside one call each, 3 and 4 model calls recorded, all ok). Over the whole run:
  - 61 HTTP 429 answers (campus 30, pantry 31), each its own ledger entry at 0 USD.
  - They fell on 28 model calls in 28 episodes (campus 13, pantry 15). The total wait was 171 s
    (campus) and 177 s (pantry). The longest wait inside one call was 21 s, well under the
    60 s bound.
  - No 429 reached a policy. Every recorded model call returned a completion (469 of 469), and
    no episode timed out, crashed or was aborted.
  - The waits add wall time only. The scenario clock moves only through the runner, the
    moderator control and tool durations (`docs/RUNTIME_CONTRACT.md`, "scenario clock"). Five
    of the 10 misses had a wait. `FAILURES.md` lists them and compares them with their seeds that
    had none.
- **Model.** Every completion was requested and returned as `anthropic/claude-sonnet-5.5` via
  OpenRouter, per-run cap 0.50 USD (frozen). Seeds were passed to `run_case` but not sent to the
  provider. No response was cached. Each episode ran in a fresh process with a fresh database.

## Layout

| Path | Content | Side |
| --- | --- | --- |
| `campus/`, `pantry/`: `plan.json`, `invocations.jsonl`, `episodes/<key>/record.json`, `episodes/<key>/trace.json.gz` (all 120) | public records and sanitized traces | public |
| `campus/report/`, `pantry/report/` | `evaluation_results.md`, `metrics.json`, `figure.svg` from `plan-b eval report` | evaluator output |
| `campus/runner_private/`, `pantry/runner_private/` | evaluator records (`<key>.runner.json`) and `cases.json` | evaluator only |
| `FAILURES.md`, `failure_digests/` | failure analysis and the per-episode digests (`digest.py` is the Wave 3 script, copied unchanged) | evaluator output |
| `manifests/` | `freeze_v1_2.json` and `diagnostic_lock_spent_v1_2.json` as run | public / evaluator |
| `spend_extract.json` | the ledger entries of this run (completions and 429 answers), copied unedited, with a summary | public |
| `logs/*_console.txt` | the runner's console lines | public |

The `.lock` files, the episode `work/` databases and the runner's case copy
(`runner_private/cases/`) were not copied.

## Spend

| | Entries | USD |
| --- | --- | --- |
| Ledger before this run (after the fresh run) | 1614 | 17.489384 |
| campus: 231 completions, 30 HTTP 429 (not billed) | 261 | 4.575578 |
| pantry: 238 completions, 31 HTTP 429 (not billed) | 269 | 4.369008 |
| **This run** | 530 | **8.944586** |
| Ledger after | 2144 | 26.433970 |

## Commands (from `apps/plan_b` of the worktree, `unset VIRTUAL_ENV`, the same environment as the fresh run)

```bash
uv run plan-b eval lock-heldout --manifest <scratch>/diag/diagnostic_lock_spent_v1_2.json --freeze freeze_v1_2.json --cases C01,C02,C03,C04,C05,C06,C07,C08,T01,T02,T03,T04
uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout <scratch>/diag/diagnostic_lock_spent_v1_2.json --require-heldout
uv run plan-b eval run --suite campus --freeze freeze_v1_2.json --heldout <scratch>/diag/diagnostic_lock_spent_v1_2.json --out <scratch>/results/wave3b_rerun_spent_20261025T2345Z/campus --jobs 2
uv run plan-b eval run --suite pantry --freeze freeze_v1_2.json --heldout <scratch>/diag/diagnostic_lock_spent_v1_2.json --out <scratch>/results/wave3b_rerun_spent_20261025T2345Z/pantry --jobs 2
uv run plan-b eval report --results <scratch>/results/wave3b_rerun_spent_20261025T2345Z/campus
uv run plan-b eval report --results <scratch>/results/wave3b_rerun_spent_20261025T2345Z/pantry
```

The campus run finished at 23:56:53Z with "80 planned, 0 already finished, 80 run:
{'completed': 76, 'capped': 4}". The pantry run finished at 00:09:15Z with "40 planned, 0
already finished, 40 run: {'completed': 25, 'capped': 15}".
