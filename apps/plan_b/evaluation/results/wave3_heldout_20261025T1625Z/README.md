# Wave 3 held-out evaluation: run `wave3_heldout_20261025T1625Z`

This is the frozen comparison run once on the locked held-out cases, under the full protocol
(`PEEAI_plan/08_evaluation.md`):

- **campus**: C01–C08; P0 once per case, P1–P3 at seeds 101/202/303; **80 of 80 episodes
  recorded**;
- **pantry**: T01–T04, the same design; **40 of 40 episodes recorded**.

Both ran from a clean detached worktree of commit `49e62b5` (the case-lock commit; the freeze
commit is `3de5962`). The two suites are separate: separate results directories, denominators
and conclusions.

## Results (counts from `campus/report/` and `pantry/report/`)

Each cell gives episodes meeting the case's outcome class over recorded episodes. Failures stay
in the denominators: a capped episode is scored as it stands. There is no composite score and no
significance test.

Counts are episodes. The statistical unit is the case (8 campus, 4 pantry). The three seeds are
repeated trials within a case, not independent units, and every miss repeats in all trials of its
case. By case (all trials met): campus P0 6/8, P1 8/8, P2 6/8, P3 7/8; pantry P0 4/4, P1 2/4,
P2 3/4, P3 2/4. These are descriptive counts from one run on these cases. They do not show that
one policy is better than another, and they do not generalize beyond these cases. In particular,
P2 shows no consistent advantage over P1 or P0 here.

| Suite | Policy | Met / recorded | By class | Statuses | Provider-reported USD |
| --- | --- | --- | --- | --- | --- |
| campus | P0 rules | 6/8 | goal completion 5/7 (C01–C07); appropriate infeasibility 1/1 (C08) | 8 completed | 0 |
| campus | P1 tool use | 24/24 | goal completion 21/21; appropriate infeasibility 3/3 | 24 completed | 3.006960 |
| campus | P2 selective | 18/24 | goal completion 15/21; appropriate infeasibility 3/3 | 21 completed, 3 capped | 1.004722 |
| campus | P3 verify-all | 21/24 | goal completion 18/21; appropriate infeasibility 3/3 | 24 completed | 0.570856 |
| pantry | P0 rules | 4/4 | original target 2/2 (T01–T02); supported partial 2/2 (T03–T04) | 4 completed | 0 |
| pantry | P1 tool use | 6/12 | original target 6/6; supported partial 0/6 | 6 completed, 6 capped | 2.555110 |
| pantry | P2 selective | 9/12 | original target 6/6; supported partial 3/6 | 6 completed, 6 capped | 0.953090 |
| pantry | P3 verify-all | 6/12 | original target 3/6; supported partial 3/6 | 6 completed, 6 capped | 0.986032 |

Some details behind these counts:

- **Integrity measures.** Executed violations are 0 for every policy in both suites. Unnecessary
  committed changes on the negative controls C02–C04 are 0 for every policy. The pantry has 0
  conservation failures and 0 duplicate or unauthorized credits.
- **Who decided** (`decided_by`, `metrics.json`). On C08, P0's infeasibility report was decided
  by the policy, P1's (3) by the model, and P2's and P3's (3 each) by the server's shared
  narration. For pantry partial fulfillment, P0's two reports were decided by the policy, and
  P2's and P3's (T04 only, 3 each) by the server. P1 met no partial-fulfillment episode; its
  three T03 deficit reports (class not met) were decided by the model.
- **Failures.** Every non-success episode and its earliest broken stage is in
  [`FAILURES.md`](FAILURES.md). Campus misses are C06 (P0, P2 ×3, P3 ×3) and C07 (P0, P2 ×3).
  Pantry misses are T02 (P3 ×3), T03 (P1, P2, P3 ×3 each) and T04 (P1 ×3).
- **Provider errors.** None in the reported run: all 482 model calls returned a completion.

## Integrity of the run

- **Freeze.** `uv run plan-b eval verify-freeze --require-heldout` passed in the worktree before
  the run: freeze.json covers 76 files, files_sha256 `7d41fada…`; heldout.json covers 28 files.
  Each invocation recorded `freeze.ok` and `heldout_lock.ok` true, `git_head` `49e62b5`, and
  `app_tree_clean` true (`*/invocations.jsonl`). The results directories were outside the
  worktree. `plan.json` binds measured_files_sha256, heldout_files_sha256, both manifest digests
  and the model (openrouter, `anthropic/claude-sonnet-5.5`, `https://openrouter.ai/api/v1`,
  per-run cap 0.50 USD). Copies of both manifests are in `manifests/`.
- **Timing.** The freeze was at 2026-10-25T14:51:31Z and the case lock (`locked_at`) at
  16:16:24Z. The first held-out model call was at **16:22:46.69Z**, in voided attempt 1. Attempt
  2's first call was at 16:25:49.97Z.
- **Model.** Every completion was requested and returned as `anthropic/claude-sonnet-5.5`.
  Seeds were passed to `run_case` but not sent to the provider (the model refuses one), so the
  three trials are separate, non-reproducible runs within each case: repeated trials, not
  independent statistical units. No model response was cached or reused (482 distinct provider
  generation ids, each billed once), and each episode ran in a fresh process with a fresh
  database. The OpenRouter upstream route was neither pinned nor recorded per call. The requested
  and returned model and every recorded setting are identical on all 482 calls, but which
  upstream endpoint served each call is not in the run's data.
- **Order.** The run order was shuffled within each case over all four policies from order seed
  20261025 (`plan.json`; `policy_subset` false). With `--jobs 1` the episodes ran one at a time
  in that order.
- **Recomputation.** `plan-b eval report` run on this copy's `campus/` and `pantry/` reproduces
  `report/` byte for byte (checked after copying).

## Attempt 1 was voided (provider rate limit), and why

The first attempt started at 16:22:45Z: campus with `--jobs 8`, then pantry with `--jobs 8` from
16:23:13Z.

1. **What happened.** From 16:22:57Z OpenRouter answered HTTP 429, "new accounts are limited to
   20 requests per minute for this model". After 16:23:11Z no call succeeded: 692 of its 732
   calls were 429s. The frozen policies treat a provider error as a visible wait that uses one of
   the episode's 8 model calls, so the LLM episodes were capped by the provider within seconds.
2. **Stopping.** Pantry had already recorded all 40 episodes (36 capped). Campus was stopped by
   exact PID after recording 59 of 80.
3. **The decision.** Before any attempt-2 result existed, attempt 1 was declared void as a
   provider-side failure, and a fresh, complete run of the whole protocol was started. It used
   the same frozen plan and order and `--jobs 1`. Attempt 1's directories were moved to
   `attempt1_rate_limited/` first, and attempt 2 started fresh on the same `--out` paths ("80
   planned, 0 already finished"). One clean episode makes 9–11 model calls per minute, so two
   concurrent episodes would exceed 20 per minute. The suites ran back to back.
4. **This departs from the frozen status rules.** Under `docs/EVALUATION.md`, a provider error
   is a visible wait and a capped episode is scored as it stands; only harness stops are
   `aborted` and rerun. Under those rules, attempt 1's 429-capped episodes would have been scored
   as capped outcomes. The cause was the operator's `--jobs 8` against the account's 20 requests
   per minute, and every LLM episode of every policy was affected alike. The decision was
   recorded at 16:25:34Z, before attempt 2's first call. No rule for a provider-wide rate-limit
   failure was written down before the run; a later run should fix one in advance.
5. **What is reported.** Attempt 2 is the reported result whatever its outcomes. Nothing from
   attempt 1 is mixed into it.
6. **What is kept.** Attempt 1 is kept unedited in `attempt1_rate_limited/{campus,pantry}/`:
   plans, invocations, every public and evaluator record, and the reports generated from it
   while all its traces were present. The per-policy 429 counts are in `FAILURES.md`.

Its traces are listed in `attempt1_rate_limited/*/trace_index.json` (sha256 and size of every
trace). Only one 429-capped trace per LLM policy and suite is included; that keeps the directory
under 40 MB. A report regenerated from this copy of attempt 1 would therefore not match its
stored report.

The index hashes the compressed files, and each record holds its uncompressed trace's sha256. The
post-run audit checked all 99 full attempt-1 traces, kept outside the repository by the evaluator,
against both. Every compressed file matches its index entry, and every uncompressed trace matches
its record.

## Spend

`spend_extract.json` holds the ledger entries this step added, copied unedited, with a summary.

| | Entries | USD |
| --- | --- | --- |
| Ledger before this step | 178 | 3.756130 |
| Attempt 1 (voided): 40 ok, 692 HTTP 429 (not billed), 1 abandoned reservation charged at its bound | 733 | 0.565272 |
| Attempt 2 (reported): 482 ok | 482 | 9.076770 (campus 4.582538, pantry 4.494232) |
| **This step** | 1215 | **9.642042** |
| Ledger after | 1393 | 13.398172 |

The cumulative cap was set to `PLAN_B_MODEL_MAX_TOTAL_COST_USD=23.75` (the starting ledger plus
this step's 20 USD budget, rounded down; the Wave 3 limit is 40). It is not part of the frozen
model binding. No reservation was left open.

## Disclosures the results carry

These were recorded before the runs, at the case lock (`scenarios/private/eval/README.md`, "Case
audit before the lock"):

- **P0.** P0's frozen parser reads none of the held-out messages. Its campus outcomes come from
  typed status checks and its deadline watch, and C06 and C07 are outside its reach by
  construction. Its three `correct` extraction labels (C02) are abstentions on messages
  annotated `no_change`.
- **C06.** Among the frozen policies only P1 can reach C06, whose one early signal is a person's
  self-report. P0's parser does not read it. P2 and P3 read it correctly, but their attention
  rule treats only equipment notices as material, so the reading forms no planner hypothesis and
  never puts the plan in question (see `FAILURES.md`). P0's, P2's and P3's C01–C07 goal
  completion is therefore capped at 6 of 7 cases by this case.
- **Case design.** T04 repeats the development partial-handoff mechanism, and the pantry fixture
  keeps the development offsets. The campus recoveries are mostly the swap.
- **Metric caveats.**
  - P2/P3 extraction labels ignore effective_time.
  - C04's server-chosen duplicate reading is labelled incorrect.
  - `infeasibility_reported` accepts any blocking-constraint name, so use the class verdict.
  - C06/C07 churn is 3 against 2.
  - T02's refused attempts appear under invalid attempts by code.
  - One pantry extraction label is `incorrect` besides C04's: T03 `hp_v7s__P3__s303`, a
    one-off reading of one forwarded receipt notice.
- **Caps.** The episode caps are the frozen values from development: 8 model calls (the
  protocol's proposed starting cap) and 48 tool calls (the protocol proposed 16). Neither was
  tuned on held-out cases. The model-call cap was reached in 21 of the 120 episodes. It ended 15
  of the 26 failures (`FAILURES.md`), and 6 capped episodes (T02, P1 and P2) met their class.

Added by the post-run audit (audit_eval), from the frozen code and the traces:

- **Prompts differ by policy.** P1 uses one generic prompt (`tool_use.v3`) for both suites. Only
  P2 and P3 have pantry-specific guidance (`choose_action_pantry.v1`: "A partial plan is honest
  but never counts as meeting the target"; "Prefer the candidate that leaves the least of the
  original target unfulfilled on time"). Both were frozen at `3de5962`. So the pantry
  partial-class difference (P1 0/6, P2 3/6, P3 3/6) cannot be attributed to the controller alone.
- **A frozen-code defect affected T03 (P2 and P3).** A pool checked as `unavailable` stays a
  ranked, requestable handoff option for the planner and the menu, and the shared attention rule
  withholds the shortfall report while that handoff still looks possible. This is the earliest
  broken stage of all six T03 P2/P3 failures (`FAILURES.md`, "Findings in frozen code"). The
  results stand as measured; the defect is a result of this evaluation.
- **No 429 backoff.** A provider error uses one of the 8 model calls with no wall-clock wait
  (the cause of attempt 1's void). It affected no reported episode.
- **These held-out cases are now spent.** This README, `FAILURES.md` and the reports describe the
  case designs by id, and the case files are committed at `49e62b5`. Any later policy or prompt
  revision needs a freshly authored and locked held-out set.

## Layout

| Path | Content | Side |
| --- | --- | --- |
| `campus/`, `pantry/`: `plan.json`, `invocations.jsonl`, `episodes/<key>/record.json`, `episodes/<key>/trace.json.gz` (all 120) | the reported run's public records and sanitized traces | public |
| `campus/report/`, `pantry/report/` | `evaluation_results.md`, `metrics.json`, `figure.svg` from `plan-b eval report` | evaluator output |
| `campus/runner_private/`, `pantry/runner_private/` | evaluator records (`<key>.runner.json`: predicates, expected outcome, actors' log) and `cases.json` | evaluator only |
| `attempt1_rate_limited/` | the voided attempt, as described above | same split |
| `FAILURES.md`, `failure_digests/` | failure analysis and the per-episode digests it was read from | evaluator output |
| `manifests/` | copies of `freeze.json` (public) and `heldout.json` as run. `heldout.json` maps each case ref to its evaluator id and outcome class, so it is evaluator side, like the committed original in `plan_b/evaluation/manifests/` | public / evaluator |
| `spend_extract.json` | ledger entries and spend summary | public |
| `logs/*_console.txt` | the runner's console lines (status and public outcome summary per episode) | public |

**Erratum (report formatter).** The "Policy identifiers" line of each
`report/evaluation_results.md` lists the ids alphabetically, not in P0–P3 order. The pairing is:
P0 = `rules/1.0.0` (pantry: `pantry-rules/1.1.0`), P1 = `tool-use/1.1.0`, P2 = `live/1.1.0`, P3 =
`verify-all/1.1.0` (as in every record and `metrics.json`). The report is kept exactly as the
report tool regenerates it; the formatter (`plan_b/evaluation/report.py`, not frozen) is to be
fixed after release.

The `.lock` files, the episode `work/` databases and the runner's case copy were not copied. No
episode timed out or crashed, so there is no `runner_private/failed/`.

## Location

These results are in `apps/plan_b/evaluation/results/` rather than
`apps/plan_b/plan_b/evaluation/results/`. Everything under `apps/plan_b/plan_b/` except the
manifest's `EXCLUDED` paths is a measured file of the freeze, and `evaluation/results/` is not
excluded. A results file there makes `verify-freeze` fail with "measured file added": this was
checked in the worktree with a probe file, which was then removed.

## Commands (from `apps/plan_b` of the worktree, `unset VIRTUAL_ENV`)

The environment was set as follows; the key file is read by the provider only:

```bash
uv sync --all-groups --locked
export PLAN_B_MODEL_PROVIDER=openrouter PLAN_B_MODEL_BASE_URL=https://openrouter.ai/api/v1 \
       PLAN_B_MODEL_KEY_FILE=<repo>/.local/keys/openrouter.key PLAN_B_MODEL_MAX_TOTAL_COST_USD=23.75
uv run plan-b eval verify-freeze --require-heldout
```

Attempt 1 (voided):

```bash
uv run plan-b eval run --suite campus --jobs 8 --out <scratch>/results/campus
uv run plan-b eval run --suite pantry --jobs 8 --out <scratch>/results/pantry
```

Attempt 2 (reported), then the reports:

```bash
uv run plan-b eval run --suite campus --jobs 1 --out <scratch>/results/campus
uv run plan-b eval run --suite pantry --jobs 1 --out <scratch>/results/pantry
uv run plan-b eval report --results <scratch>/results/campus
uv run plan-b eval report --results <scratch>/results/pantry
```

The campus run finished at 16:48:27Z with "80 planned, 0 already finished, 80 run: {'completed':
77, 'capped': 3}". The pantry run finished at 17:11:28Z with "40 planned, 0 already finished, 40
run: {'completed': 22, 'capped': 18}".
