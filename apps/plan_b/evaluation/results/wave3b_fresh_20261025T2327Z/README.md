# Fresh held-out check of policy version 1.2: run `wave3b_fresh_20261025T2327Z`

This is the one run of the frozen policy version 1.2 on the fresh held-out set, under the full
protocol (`PEEAI_plan/08_evaluation.md`):

- **campus**: C09, C10, C11 and C12. P0 once per case, P1, P2 and P3 at seeds 101, 202 and 303.
  **40 of 40 episodes recorded.**
- **pantry**: T05 and T06, the same design. **20 of 20 episodes recorded.**

The run of record for version 1.1 is still `wave3_heldout_20261025T1625Z` on the twelve spent
cases (C01 to C08, T01 to T04). Nothing here edits, replaces or relabels it. This run is a small
new check on six other cases, and the only held-out result for version 1.2. The two suites are separate, with separate results directories,
denominators and conclusions.

## Results (counts from `campus/report/` and `pantry/report/`)

Each cell gives the episodes that met their case's outcome class over the recorded episodes.
There is no composite score and no significance test.

| Suite | Policy | Met / recorded | By class | Statuses | Provider-reported USD |
| --- | --- | --- | --- | --- | --- |
| campus | P0 rules | 3/4 | goal completion 2/3 (C09, C10 met, C11 missed), appropriate infeasibility 1/1 (C12) | 4 completed | 0 |
| campus | P1 tool use | 12/12 | goal completion 9/9, appropriate infeasibility 3/3 | 12 completed | 1.168300 |
| campus | P2 selective | 12/12 | goal completion 9/9, appropriate infeasibility 3/3 | 12 completed | 0.342400 |
| campus | P3 verify-all | 12/12 | goal completion 9/9, appropriate infeasibility 3/3 | 12 completed | 0.210624 |
| pantry | P0 rules | 2/2 | original target 1/1 (T05), supported partial 1/1 (T06) | 2 completed | 0 |
| pantry | P1 tool use | 6/6 | original target 3/3, supported partial 3/3 | 6 completed | 1.149662 |
| pantry | P2 selective | 6/6 | original target 3/3, supported partial 3/3 | 6 completed | 0.419166 |
| pantry | P3 verify-all | 6/6 | original target 3/3, supported partial 3/3 | 6 completed | 0.317998 |

The USD column sums the per-episode provider-reported costs in `episodes/*/record.json`. The suite
totals match `spend_extract.json`: campus 1.721324 and pantry 1.886826.

Counts are episodes. The statistical unit is the case (4 campus, 2 pantry). The three seeds are
repeated trials within a case, not independent units. By case (all trials met): campus P0 3/4,
P1 4/4, P2 4/4, P3 4/4, and pantry 2/2 for every policy. These are descriptive counts from one
run on six cases. They do not show that one policy is better than another, they do not show
that version 1.2 is better than version 1.1 (the cases differ), and they do not generalize
beyond these cases.

Some details behind these counts:

- **The one miss** is C11 under P0 (`ev_w2n__P0__once`). P0's frozen parser does not read the
  facilitator's self-report, so the swap is never prepared. See [`FAILURES.md`](FAILURES.md).
- **Integrity measures.** Executed violations are 0 for every policy in both suites. Invalid
  attempts (tool calls the server refused, none executed) are 0 on campus. On the pantry they
  are P0 1 (T05, a `hold_resource` refused with `REVISION_CONFLICT`), P1 2 and P2 3 (T06, a
  `hold_resource` on the loft rack refused with `RESOURCE_UNAVAILABLE`, which the case's loft
  desk is designed to decline), and P3 0. Unnecessary committed changes on the negative control
  C10 are 0 in all 10 of its episodes. The pantry has 0 conservation failures.
- **Who decided** (`decided_by`, `metrics.json`). On C12, P0's infeasibility report was decided
  by the policy, P1's (3) by the model, and P2's and P3's (3 each) by the server's shared
  narration. On T06 (supported partial), the same split: P0 policy 1, P1 model 3, P2 server 3,
  P3 server 3.
- **Model-call cap.** No episode reached the cap of 8 model calls or 48 tool calls. Every
  episode has status `completed`. The most model calls in one episode was 7 (C09 P1 seed 101,
  and T06 under P1 and P2).
- **Provider errors.** None. All 194 model calls returned HTTP 200 with a completion
  (`spend_extract.json`), 0 retries and 0 rate-limit waits in every record.
- **Recovery delay on C09.** As disclosed at the lock, the recovery delay metric of C09 counts
  only plan changes at or after the van message (17:16). Read it together with the goal
  outcome, which every C09 episode met.

## Integrity of the run

- **Worktree.** Both suites ran from a clean detached worktree of commit `5955243` (the freeze
  and lock commit of version 1.2. The 1.2 code is commit `1ea8ea1`). Each invocation recorded
  `git_head` `5955243`, `app_tree_clean` true, `freeze.ok` true and `heldout_lock.ok` true
  (`*/invocations.jsonl`). The results directories were outside the worktree.
- **Freeze.** `uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout
  heldout2.json --require-heldout` passed (rc 0) in the worktree before the run. The freeze
  covers 76 files, files_sha256 `c3ad3118...488a`. The lock `heldout2.json` covers 15 files
  with case scope C09 to C12, T05 and T06 (lock files_sha256 `392ba3fa...9c64`). Copies of both
  manifests are in `manifests/`. `plan.json` binds the measured files, the held-out files, both
  manifest digests and the model.
- **Timing.** The freeze was written at 2026-10-25T23:23:47Z and the case lock at 23:23:54Z.
  The first model call of this run started at **23:27:31.78Z**. Before it, the last paid call
  in the ledger was the development smoke of 22:38:39Z, on development cases. So the lock came
  before every version 1.2 call on these cases.
- **Model.** Every completion was requested and returned as `anthropic/claude-sonnet-5.5` via
  OpenRouter, per-run cap 0.50 USD (frozen). Seeds were passed to `run_case` but not sent to the
  provider, so the trials within a case are separate, non-reproducible runs. No model response
  was cached (`model_response_cache` false). Each episode ran in a fresh process with a fresh
  database. The upstream route behind OpenRouter was not pinned or recorded.
- **Order and concurrency.** The run order was shuffled within each case over all four
  policies from order seed 20261025 (`plan.json`, `policy_subset` false). With `--jobs 1` the
  episodes ran one at a time, campus from 23:27:31Z to 23:35:38Z, then pantry from 23:35:38Z
  to 23:44:59Z. Nothing else called the model during those windows.
- **Cumulative cap.** `PLAN_B_MODEL_MAX_TOTAL_COST_USD=40` (the Wave 3 limit). It is not part of
  the frozen model binding. No call was refused.

## Disclosures the results carry

Recorded before the run, at the lock (`plan_b/scenarios/private/eval/README_set2.md`) and in
the pre-freeze audit (`docs/RUNTIME_CONTRACT.md` section 21, `docs/EVALUATION.md`):

- **Small set.** Four campus cases and two pantry cases are a small check.
- **Isolation is good but not perfect.** The policy author (`fix2`) never opened the fresh
  cases. The case author (`cases2`) saw no version 1.2 code, diff or output, but did read the
  policy author's prose brief, which lists the defects 1.2 was to fix. The pre-freeze auditor
  (`audit2`) read the fresh cases and therefore changed no policy behavior. No compared policy
  was run on these cases before the lock.
- **Near copies of spent wording.** The fixture texts and the pantry numbers follow the spent
  templates closely. No string, id or world is shared with a spent or development case.
- **Conditions repeat the spent ones.** C09 is the C01 condition, C10 is C03, C11 is C06, C12 is
  C08, T05 is T01 and T06 is T03. Version 1.2 was changed after reading the v1.1 failures on
  C06 and T03. A good result on C11 and T06 is therefore consistent with the fixes carrying over to
  new instances of the same conditions. Version 1.1 was not run on these cases, so this is not a
  measured effect. It is not evidence about conditions the fixes never saw.
- **Known limits of 1.2, frozen as they are.** A person's delay hypothesis outlives a later
  check-in (A1), the declined-menu key holds no time (A2), P1's declined key uses the view after
  its turn (A3), a stale re-issue reads as a model choice (A4), and a long `Retry-After` is cut
  to 20 s (A5). C11 has A1's structure. Every C11 episode of P1, P2 and P3 met its goal, so A1
  did not change an outcome in this run.
- **P0's version.** P0 keeps its ids (`rules/1.0.0`, `pantry-rules/1.1.0`) and runs on planner
  `plan_b.planner/1.2.0`, which the freeze records.
- **Report labels (formatter).** The column headers of `report/evaluation_results.md` are fixed
  text from Wave 3: "Goal completion C01–C07", "Appropriate infeasibility C08", "Unnecessary
  changes C02–C04", "Target met T01–T02" and "Supported partial fulfillment T03–T04". In this run
  they cover C09 to C11, C12, C10, T05 and T06. The rows, the case ids and `metrics.json` are
  correct. The report is kept exactly as `plan-b eval report` writes it.
- **Interpretation labels.** P2 and P3 record 3 `not_recorded` pantry labels each, on messages
  they never read as a structured claim. P1 records no structured reading. These do not change
  any outcome.

## Layout

| Path | Content | Side |
| --- | --- | --- |
| `campus/`, `pantry/`: `plan.json`, `invocations.jsonl`, `episodes/<key>/record.json`, `episodes/<key>/trace.json.gz` (all 60) | public records and sanitized traces | public |
| `campus/report/`, `pantry/report/` | `evaluation_results.md`, `metrics.json`, `figure.svg` from `plan-b eval report` | evaluator output |
| `campus/runner_private/`, `pantry/runner_private/` | evaluator records (`<key>.runner.json`) and `cases.json` | evaluator only |
| `FAILURES.md`, `failure_digests/` | failure analysis and the per-episode digests it was read from (`digest.py` is the Wave 3 script, copied unchanged) | evaluator output |
| `manifests/` | copies of `freeze_v1_2.json` and `heldout2.json` as run | public / evaluator |
| `spend_extract.json` | the ledger entries of this run, copied unedited, with a summary (see Spend) | public |
| `logs/*_console.txt` | the runner's console lines | public |

The `.lock` files, the episode `work/` databases and the runner's case copy
(`runner_private/cases/`) were not copied. No episode timed out or crashed.

## Spend

| | Entries | USD |
| --- | --- | --- |
| Ledger before this step | 1420 | 13.881234 |
| campus (40 episodes, 87 calls, all ok) | 87 | 1.721324 |
| pantry (20 episodes, 107 calls, all ok) | 107 | 1.886826 |
| **This run** | 194 | **3.608150** |
| Ledger after this run (1420 + 194 entries) | 1614 | 17.489384 |

`spend_extract.json` was written after the diagnostic rerun on the spent cases had finished, so its
`ledger_entries_after` (2144) and `ledger_total_after` (26.43397) include that rerun. Its `calls`
(194) and `total_this_extract` (3.608150 USD) are this run's alone.

## Commands (from `apps/plan_b` of the worktree, `unset VIRTUAL_ENV`)

```bash
git worktree add --detach <scratch>/eval2 5955243
uv sync --all-groups --locked
export PLAN_B_MODEL_PROVIDER=openrouter PLAN_B_MODEL_BASE_URL=https://openrouter.ai/api/v1 \
       PLAN_B_MODEL_KEY_FILE=<repo>/.local/keys/openrouter.key PLAN_B_MODEL_MAX_TOTAL_COST_USD=40
uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout heldout2.json --require-heldout
uv run plan-b eval run --suite campus --freeze freeze_v1_2.json --heldout heldout2.json --out <scratch>/results/wave3b_fresh_20261025T2327Z/campus --jobs 1
uv run plan-b eval run --suite pantry --freeze freeze_v1_2.json --heldout heldout2.json --out <scratch>/results/wave3b_fresh_20261025T2327Z/pantry --jobs 1
uv run plan-b eval report --results <scratch>/results/wave3b_fresh_20261025T2327Z/campus
uv run plan-b eval report --results <scratch>/results/wave3b_fresh_20261025T2327Z/pantry
```

The campus run finished at 23:35:38Z with "40 planned, 0 already finished, 40 run:
{'completed': 40}". The pantry run finished at 23:44:59Z with "20 planned, 0 already finished,
20 run: {'completed': 20}".
