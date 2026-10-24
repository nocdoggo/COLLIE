# Verification record (M2)

This record says what ran, where, and with what result. Counts come from
`evidence/reports/checks.json`, `evidence/reports/m2_focused_tests.json`,
`evidence/reports/pantry_accounting.json`, the walkthrough reports in `evidence/screenshots/`,
and the live-run records `evidence/reports/live_*_run.json`. Nothing is reported as passing
unless it ran. Scenario times are given in each fixture's local time (America/New_York);
traces store UTC.

All of this is **development evidence** on fictional, synthetic fixtures. It is not held-out
evaluation, it supports no comparative claim, and it is not community validation.

## 1. How the evidence was produced

Two scripts produced it on 2026-10-24. The recorded live runs were made once from the working
tree, after every Wave 2 worker had finished. The rest of the evidence was then regenerated from
a fresh, clean checkout of the packet commit `fd04d48`, after the integrator's commits.
`environment.json` records `git_head = fd04d48…` and `app_tree_clean = true`. The collector made
no paid call: it copied the recorded live runs and verified each live trace again.

A clean checkout has no `.local/` directory, so the regeneration passed the non-secret endpoint
settings of `.local/keys/model_endpoint.env` as environment variables (`PLAN_B_MODEL_PROVIDER`,
`PLAN_B_MODEL_BASE_URL`, `PLAN_B_MODEL_KEY_FILE`). The Wave 2 walkthrough only selects the live
policy, so no model call was made. Without these settings its policy-switch flow correctly
reports that the live policy is not configured.

```bash
cd apps/plan_b
# 1. Recorded live runs (paid; each case once; never re-run or edited afterwards)
PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00 uv run python scripts/run_live_cases.py --out <live> dev01
PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00 uv run python scripts/run_live_cases.py --out <live> dev04
PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00 uv run python scripts/run_live_cases.py --out <live> dev02
PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00 uv run python scripts/run_live_cases.py --out <live> skills_dev01
PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00 uv run python scripts/run_live_cases.py --out <live> skills_dev02 pantry_dev01
PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00 uv run python scripts/run_live_cases.py --out <live> dev05 dev06
# 2. Every check, the deterministic cases, both walkthroughs and the scans (no paid call),
#    from a clean checkout of fd04d48 (git worktree, uv sync --all-groups --locked, npm ci)
uv run python scripts/collect_wave2_evidence.py --out <empty dir> \
    --live ../../PEEAI_plan/handoffs/wave_2/evidence \
    --gate ../../PEEAI_plan/handoffs/wave_2/evidence/reports/g_llm_gate.json
```

Every `run_live_cases.py` invocation exited 0. The collector printed `all checks passed` and
exited 0. Its temporary directory was removed.

### Environment

| | |
| --- | --- |
| Python | CPython 3.12.11 (app `.venv`) |
| uv / Node / npm | 0.9.18 / v22.19.0 / 11.15.0 |
| Browser | Playwright 1.64.1, headless Chromium |
| SQLite | 3.50.3 |
| Model | `anthropic/claude-sonnet-5.5` through OpenRouter, requested and returned on every call |
| Prompts | `interpret.v1`, `choose_action.v1` (sha256 in `reports/fixture_hashes.json` and on every live decision) |
| Episode caps | 48 tool calls, 8 model calls, phase `development` |
| Spend caps | 0.50 USD per episode; 8.00 USD cumulative over the ledger (this step's limit) |

`reports/fixture_hashes.json` holds the hashes of the three public fixtures, the nine private
cases, the 11 planning examples, the planning schema, the prompts, both lockfiles and migrations
0001–0004.

## 2. Commands and results

These are the collector's rows from `reports/checks.json`. `<work>` is its temporary directory
and `<evidence>` is `PEEAI_plan/handoffs/wave_2/evidence`.

| # | Check | Command (from `apps/plan_b`) | Exit | Result |
| --- | --- | --- | --- | --- |
| 1 | Lint | `uv run ruff check .` | 0 | All checks passed |
| 2 | Format | `uv run ruff format --check .` | 0 | 100 files already formatted |
| 3 | Types | `uv run mypy` | 0 | no issues in 65 source files |
| 4 | Web typecheck | `npm run typecheck` (web/) | 0 | `tsc --noEmit` clean |
| 5 | Web build | `npm run build` (web/) | 0 | JS 318.86 kB (94.90 kB gzip) |
| 6 | Python tests | `uv run pytest -o addopts= -q -p no:cacheprovider --junitxml=…` | 0 | **634 passed, 0 failed, 0 skipped** (1 warning: Starlette's httpx deprecation) |
| 7 | Web tests | `npm test` (web/) | 0 | **379 passed**, 0 failed |
| 8 | Web boundary lint | `npm run lint` (web/) | 0 | 25 read-only modules, 40 sources, dist bundle scanned |
| 9 | Development cases | `uv run plan-b run-case all --db <work>/runs.sqlite3 --out <work>/out` | 0 | 9/9 `matches_expectation=True`, `violations=0` (section 4) |
| 10 | Rejections | `uv run plan-b demo-rejections --db <work>/demo.sqlite3 --out <work>/out` | 0 | all 20 steps got their expected result; 7 rejected receipts, 2 attempts without receipt, `violations=0` (`reports/rejected_actions_steps.json`) |
| 11–20 | Trace integrity | `uv run plan-b verify-trace <work>/out/traces/<trace>.json` | 0 | dev01, dev02, dev04, dev05, dev06, pantry_dev01, pantry_dev02, skills_dev01, skills_dev02, rejected_actions: all `intact` |
| 21 | Wave 1 lines | dev01–dev06 lines compared with the Wave 1 evidence | 0 | identical (`reports/wave1_parity.json`) |
| 22 | Pantry accounting | computed from the pantry traces | 0 | section 5 |
| 23 | M2 focused tests | the M2 checks mapped to their tests in row 6's JUnit report | 0 | every mapped test passed (section 3) |
| 24 | Browser, Wave 1 | `uv run python tests/e2e/walkthrough.py --out <work>/shots1` | 0 | **41/41 checks passed** |
| 25 | Browser, Wave 2 | `uv run python tests/e2e/walkthrough_wave2.py --out <work>/shots2` | 0 | **30/30 checks passed** (pantry staff flow, community check-in and offer, policy switch) |
| 26–33 | Live trace integrity | `uv run plan-b verify-trace <evidence>/traces/live_<case>_trace.json` | 0 | all 8 recorded live traces `intact` |
| 34 | Credential scan | every text file written: an OpenRouter key prefix, a bearer token | 0 | none found (no key was read for this scan) |
| 35 | Identifier scan | every text file written: host name, user name, git email, local paths | 0 | none found |

pytest ran after the web build, so the bundle-privacy test scanned the real bundle. The JUnit
report is `reports/pytest_junit.xml`, with its host name replaced and its timestamp removed.

## 3. M2 checks → recorded outcomes

The checks are the "Mandatory M2 checks" of `PEEAI_plan/waves/02_adaptation.md`. Test paths are
relative to `apps/plan_b/tests/`. `reports/m2_focused_tests.json` lists every mapped test with
its outcome in the row-6 run.

| M2 check | Recorded outcome | Evidence |
| --- | --- | --- |
| **Live campus behavior**: one real model-driven end-to-end recovery with a useful tool call, a validated action and fresh-state agreement; a stale warning gets a distinct, justified response | **Pass** (one live trial each; see the dev01 and dev04 details below the table) | `reports/live_dev01_run.json`, `traces/live_dev01_trace.json`; `reports/live_dev04_run.json`, `traces/live_dev04_trace.json`; also live dev02, dev05, dev06, skills_dev01 and skills_dev02 (section 4); `reports/g_llm_gate.json` (G-LLM pass); 8 focused tests passed |
| **Bounded failure behavior**: malformed output, unknown entity, exhausted cap, timeout and stale revision stay visible and produce no invented success | **Pass on the focused tests; two failure paths also occurred live** (see below the table) | 35 focused tests passed (`test_agent_boundary.py`, `test_agent_provider.py`, `test_integration_policy.py`, `test_integration_api.py`); `reports/live_skills_dev02_run.json`, `reports/live_dev06_run.json` |
| **Community workflow**: participant input changes a role fact and affects planning; unauthorized goal or stock actions reject; the skills exchange loads through the event adapter | **Pass** (see below the table) | 40 focused tests passed (`test_community_skills_exchange.py`, `test_resource_offer.py`, `test_integration_api.py`, `test_stock_conservation.py::test_agent_cannot_call_staff_only_tools`); `traces/skills_dev01_trace.json`; `traces/live_skills_dev01_trace.json`; walkthrough_wave2 community flow (`screenshots/w2_07`–`w2_10`) |
| **Shared pantry core**: the same orchestration, grants, receipts, replay and transaction boundary run the pantry scenario; the domain adapter owns only the added semantics | **Pass** (see below the table) | `traces/pantry_dev01_trace.json`, `traces/pantry_dev02_trace.json` (`intact`); 15 focused tests passed (`test_pantry_workflow.py`, `test_pantry_fixture.py`, `test_integration_policy.py`); walkthrough_wave2 pantry flow (`screenshots/w2_01`–`w2_06`) |
| **Stock and service accounting**: the 24/16 to 40/0 handoff conserves stock; the target stays 40; a receipt or commit does not reduce the service deficit; only distribution records achieved service | **Pass** | `reports/pantry_accounting.json` (section 5); 7 focused tests passed (`test_stock_conservation.py`, `test_pantry_workflow.py::test_completion_distribution_and_next_start_order_at_the_inclusive_deadline`) |
| **Quantity failure checks**: overlapping and non-overlapping double allocation reject; release and expiry create no stock; duplicate physical records cannot credit twice; a partial handoff keeps its residual reservation; early distribution cannot exceed attended throughput; late records keep truthful times and fail on-time attainment | **Pass** | 10 focused tests passed (`test_stock_conservation.py`); pantry_dev02's partial handoff in `reports/pantry_accounting.json` |
| **Staff boundary**: the agent cannot call the staff-only receipt or distribution operations; without staff attestation there is no fictional physical success | **Pass** (see below the table) | 11 focused tests passed (`test_stock_conservation.py`, `test_agent_boundary.py`, `test_pantry_workflow.py`, `test_pantry_fixture.py`); `reports/live_pantry_dev01_run.json` |
| **Future comparison parity**: P0–P3 use the same candidates, grants, executor, tools and domain semantics within each suite; policy-specific prompts are recorded | **Partial, not passed** (see below the table) | 43 focused tests passed (`test_runner_isolation.py`, `test_agent_boundary.py`, `test_integration_policy.py`); `reports/live_pantry_dev01_run.json`; KNOWN_LIMITATIONS |

**Live campus behavior, in detail.**

* **dev01, the recovery** (`live_dev01`):
  1. The model read the 16:40 notice as a delay claim on the projector (`mc_0001`, ETA 17:25).
  2. It chose `query:projector:delivery_eta` (`mc_0002`). Call `call_00003` succeeded: delayed,
     ETA 17:25, observation `obs_0001`.
  3. The next model call (`mc_0003`) consumed `call_00003` and chose
     `apply:cand_0002_dc26f35f`.
  4. `call_00006` was applied as `rcpt_0001` at revision 4 → 5. The report was
     `rpt_0002_dc26f35f` from `eval_0002` at revision 4 and goal version 1; the candidate was
     feasible and applicable when evaluated.
  5. The coordinator's next state read (`call_00007`, revision 5) and the final state both hold
     the plan `rcpt_0001` reported.
  6. All activities completed, with $0 committed and 0 violations.
* **dev04, the stale warning** (`live_dev04`):
  * The stale reminder about last month's order P09 (`obs_0002`, 16:44) was read by the model
    (`mc_0003`) as concerning another order and date. The server recorded `inapplicable`
    (`dec_0003`), giving the reasons "order P09 is not projector's booking (P17); referenced date
    2026-10-29 is not the event date".
  * The volunteer's forwarded copy (`obs_0003`) was recorded as `duplicate` of `obs_0002`
    (`dec_0004`).
  * The genuine notice was verified (on schedule, ETA 16:58) and contradicted, so the plan was
    kept.
  * There was no hold, no plan change and no spend.

**Bounded failure behavior, in detail.**

* **Focused tests.** Each failure class has a test, using the real provider client with a
  scripted transport, or a 127.0.0.1 server, against the real executor and store:
  * malformed interpretation and malformed choice after one repair;
  * an option outside the menu;
  * an unknown entity;
  * the model-call, tool-call and per-run caps, and the host's episode caps;
  * provider timeout and HTTP error;
  * the spend cap, with nothing sent;
  * stale revision, refreshed and bounded;
  * lost responses, reconciled or unestablished;
  * prompt injection;
  * the key scan.
* **Live occurrences.**
  * `live_skills_dev02`: the in-flight apply was rejected `REVISION_CONFLICT` after the
    organizer's goal-version change, and recorded as `wait` / `stale_revision` (`dec_0003`). The
    candidates were re-evaluated under goal version 2, and the model's new choice was applied at
    10:07 (`rcpt_0006`).
  * `live_dev06`: the status query was `unavailable` (`STATUS_UNAVAILABLE`, kept visible as
    unverified), and the model then chose the robust free swap.
* **Not induced against the real provider:** malformed output, an unknown entity, exhausted
  caps and timeouts.

**Community workflow, in detail.**

* **A role fact changes planning.** In skills_dev01 the peer lead's own check-in (available until
  11:05) makes keep fail `participant_availability`. The policy applies the free swap of practice
  and peer exchange at 10:06. This holds for the rule policy and in the live run.
* **Unauthorized actions reject.**
  * A participant's `update_goal` and `update_grant` get `GRANT_REQUIRED`.
  * Attesting another volunteer gets `SCOPE_VIOLATION`.
  * Claiming organizer authority in a message grants nothing.
  * The agent's staff tools get `GRANT_REQUIRED`.
* **Offers.** An offer alone reserves and spends nothing. A structured offer activates only a
  preconfigured resource after the owner, capability, availability and terms checks; each
  refusal has a test.
* **Goal versions.** An organizer goal-version change invalidates older reports; skills_dev02
  covers it with the rule policy and in the live run.
* **The fixture.** `dev_fixture_02` loads through the unchanged `campus/1.0.0` adapter.

**Shared pantry core, in detail.**

* The pantry episode runs through the same:
  * executor, sessions, grants, idempotency and receipts;
  * clock engine and runner;
  * snapshots, trace format and replay (the pantry trace replays in the browser in walkthrough
    check `pantry trace replays`).
* `pantry/1.0.0` extends the campus adapter and adds only the stock checks, coverage, readiness
  reporting and scoring (contract section 10).

**Staff boundary, in detail.**

* The agent's grant lacks `record_stock_receipt` and `record_distribution`, and the executor
  rejects them with `GRANT_REQUIRED` and an unchanged revision.
* Without staff attestation, nothing physical succeeds.
* Scoring flags unattested and agent-made records.
* The live pantry run made no attestation: `no_staff_attestation_by_agent` passed.

**Future comparison parity, in detail.**

* **What holds.** P0 (`rules/1.0.0`, `pantry-rules/1.0.0`) and the model-driven `live/1.0.0` use:
  * the same `run_case`, `PolicyHost`, episode caps, scripted actors and staff simulator;
  * the same candidate generator, grants, executor and tool vocabulary;
  * the same isolation rules.

  Every live decision records its prompt ids and sha256.
* **What does not.**
  * P1 and P3 are not built.
  * The live policy has no stock-quantity options, so on the pantry profile it cannot use the
    adapter's candidates the way P0 does. The live pantry run reached 0 of 40 kits.
  * The pantry suite therefore does not yet meet the equal-adapter rule.

## 4. Development cases: deterministic baselines and recorded live runs

**Deterministic baselines** (row 9). The dev01–dev06 lines are byte-identical to the Wave 1
evidence. The episode tool-call counts come from each runner report's `episode_caps`; no cap was
reached.

| Case | goal_complete | infeasibility_reported | applied plans | committed | violations | matches | tool calls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev01 | true | false | 1 | 0 | 0 | true | 22 |
| dev02 | true | false | 1 | 3500 | 0 | true | 30 |
| dev04 | true | false | 0 | 0 | 0 | true | 24 |
| dev05 | false | true | 0 | 0 | 0 | true | 19 |
| dev06 | true | false | 1 | 0 | 0 | true | 21 |
| pantry_dev01 | true | false | 1 | 0 | 0 | true | 22 |
| pantry_dev02 | false | true | 1 | 0 | 0 | true | 27 |
| skills_dev01 | true | false | 1 | 0 | 0 | true | 24 |
| skills_dev02 | true | false | 1 | 0 | 0 | true | 29 |

**Recorded live runs** (`policy="live"`, `live/1.0.0`). Each case ran once, under caps of 48 tool
calls and 8 model calls. The model was `anthropic/claude-sonnet-5.5`, requested and returned on
every call. Spend is the ledger difference over the run, and it equals the sum of the run's
calls' provider-reported costs. Every live trace verifies `intact`.

| Run | Outcome line | Model calls | Tool calls | Model latency | Tokens (prompt / completion) | Spend (USD) |
| --- | --- | --- | --- | --- | --- | --- |
| live_dev01 | `dev01: goal_complete=True infeasibility_reported=False applied_plans=1 committed=0 violations=0 matches_expectation=True` | 3 (1 interpret, 2 choose) | 24 | 10.8 s | 13535 / 897 | 0.03604 |
| live_dev04 | `dev04: goal_complete=True infeasibility_reported=False applied_plans=0 committed=0 violations=0 matches_expectation=True` | 3 (2, 1) | 25 | 11.3 s | 10765 / 827 | 0.02980 |
| live_dev02 | `dev02: goal_complete=True infeasibility_reported=False applied_plans=1 committed=3500 violations=0 matches_expectation=True` | 6 (1, 5) | 32 | 26.6 s | 28445 / 2054 | 0.07743 |
| live_skills_dev01 | `skills_dev01: goal_complete=True infeasibility_reported=False applied_plans=1 committed=0 violations=0 matches_expectation=True` | 2 (1, 1) | 25 | 8.3 s | 6657 / 423 | 0.017544 |
| live_skills_dev02 | `skills_dev02: goal_complete=True infeasibility_reported=False applied_plans=1 committed=0 violations=0 matches_expectation=True` | 3 (1, 2) | 29 | 8.7 s | 10843 / 605 | 0.027736 |
| live_pantry_dev01 | `pantry_dev01: goal_complete=False infeasibility_reported=False applied_plans=0 committed=0 violations=0 matches_expectation=False` | 0 | 10 | — | — | 0 |
| live_dev05 | `dev05: goal_complete=False infeasibility_reported=True applied_plans=0 committed=0 violations=0 matches_expectation=True` | 3 (1, 2) | 20 | 10.4 s | 13582 / 936 | 0.036524 |
| live_dev06 | `dev06: goal_complete=True infeasibility_reported=False applied_plans=1 committed=0 violations=0 matches_expectation=True` | 3 (1, 2) | 22 | 11.1 s | 14128 / 1064 | 0.038896 |

**The model-chosen steps of each run:**

* **dev01:** query projector → apply the free swap.
* **dev04:** query projector (on schedule). The stale notice was recorded `inapplicable` and its
  copy `duplicate` by the server; the plan was kept.
* **dev02:**
  1. query the projector (ETA 17:45);
  2. query the backup's availability;
  3. hold the backup (16:45);
  4. ask the organizer to raise the committed limit from 0 to 3500;
  5. after the scripted organizer's answer, apply the paid backup substitution (16:48,
     `rcpt_0003`, 3500 committed).
* **skills_dev01:** apply the swap of practice and peer exchange at 10:06 after the check-in.
* **skills_dev02:** the apply at 10:06 was rejected `REVISION_CONFLICT` (goal version 2); after
  re-evaluation, the new candidate was applied at 10:07.
* **dev05:**
  1. query the projector (cancelled);
  2. query the backup (booked elsewhere);
  3. the server recorded `infeasible` with the blocking constraints, and nothing was spent.
* **dev06:**
  1. query the projector (`STATUS_UNAVAILABLE`);
  2. apply the robust free swap. One failed query was enough here, where the baseline makes two.
* **pantry_dev01:** **failed**, recorded honestly. There was no notice to interpret and the menu
  had no stock option. The server recorded `wait` and no model call was made. Nothing was
  committed, so 0 of 40 kits were distributed. Stock stayed conserved.

## 5. Pantry accounting (deterministic baseline, `pantry-rules/1.0.0`)

`reports/pantry_accounting.json` holds every frame's counters for `traces/pantry_dev01_trace.json`
and `traces/pantry_dev02_trace.json`. The collector checked the following over all frames, and
none failed:

* every pool's on hand = opening + received − transferred out − distributed;
* the units on hand plus distributed across both pools stay at the opening 40 (an internal
  handoff creates nothing);
* the original target stays `kits_40` = 40 in every frame;
* the expected shipment S20 stays 20 unreceived in every frame.

pantry_dev01 (canonical):

| Local time | Revision | Event | Pantry on hand / reserved | Partner on hand / reserved | Supply gap / unfulfilled | On time |
| --- | --- | --- | --- | --- | --- | --- |
| 12:30 | 3 | episode loaded | 24 / 0 | 16 / 0 | 16 / 40 | 0 |
| 12:35 | 6 | agent holds 16 partner kits (`hold_0001`, stock transfer) | 24 / 0 | 16 / 16 | 16 / 40 | 0 |
| 12:37 | 7 | staff records the handoff (`srec_0001`, `handoff_001`) | 40 / 0 | 0 / 0 | 0 / 40 | 0 |
| 12:38 | 8 | agent holds 40 pantry kits (`hold_0002`) | 40 / 40 | 0 / 0 | 0 / 40 | 0 |
| 12:39 | 9 | agent applies the plan (40 committed, `alloc_0001`) | 40 / 40 | 0 / 0 | 0 / 40 | 0 |
| 13:40 | 16 | staff records the distribution (`distribution_001`, on time) | 0 / 0 | 0 / 0 | 0 / 0 | 40 |

The 24/16 → 40/0 move happens in one revision, through a staff receipt. Holds, the receipt and
the commitment leave the unfulfilled target at 40. Achieved service first appears at the
staff-recorded distribution.

pantry_dev02 (partial handoff):

* Staff hands off 10 of the 16 held kits (pantry 34, partner 6 with 6 still reserved; hold
  remainder 6).
* The policy releases the residual hold at 12:41. The release adds no stock.
* 34 kits are distributed on time, leaving a disclosed 6-kit shortfall against the unchanged
  target of 40.
* Counters: 16/40 → 6/40 → 6/6.

## 6. G-LLM gate

The gate passed once, on 2026-10-24, run by the Build 1 worker. Its record is
`reports/g_llm_gate.json`; this step did not re-run it.

* **Command:** `uv run python -m plan_b.agent.gate --out <file>`.
* **Model:** `anthropic/claude-sonnet-5.5`, requested and returned.
* **Calls:** 3 calls, 12.7 s of model latency, 0.03509 USD (provider usage).
* **Interpretation:** a strict delay claim on the projector (ETA 17:25).
* **Tool call:** the model chose `query_status` (`call_00003`), and the next call (`mc_0003`)
  consumed its result and chose the swap, which was applied as `rcpt_0001`.
* **Configuration:** recorded without secrets: relative key-file path, base URL, caps and prompt
  hashes.

## 7. Spend

`reports/model_spend_summary.json` summarizes the ledger `apps/plan_b/var/model_spend.json` by
run. It holds 26 calls in total, every one with outcome `ok`:

| Run | Calls | Cost (USD) |
| --- | --- | --- |
| G-LLM gate (Build 1) | 3 | 0.03509 |
| live runs of this step (8 runs, section 4) | 23 | 0.26397 |
| **ledger total** | **26** | **0.29906** |

* **Key check:** one read-only `GET /api/v1/key`, made before the live runs, reported limit 50,
  remaining 49.96491 and usage 0.03509. That usage equals the ledger total at that time.
* **Caps:** this step's cumulative cap was 8.00 USD. No call was refused by the spend guard,
  and no episode reached a cap.

## 8. Not run, or not verified

* **W2.4 MBTA (stretch): not built.** No transit adapter exists and the MBTA key was not read.
* **Failure classes against the real provider:** malformed output, unknown entity, caps and
  timeout were tested only with scripted transports (section 3).
* **Repeated live trials and variance:** each live case ran once.
* **The live agent in a real browser session:** the walkthrough selects it but does not run it.
* **Other browsers, screen readers, Python 3.11, comprehension by new viewers, community
  validation:** not run, as in Wave 1.
* **Re-recording the live runs from the committed tree:** not done. The live runs were recorded
  once from the working tree that `bf71e43` commits, and the clean-checkout regeneration only
  re-verified them.
