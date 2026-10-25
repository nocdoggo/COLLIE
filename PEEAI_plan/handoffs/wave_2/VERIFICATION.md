# Verification record (M2)

This record says what ran, where, and with what result. Counts come from
`evidence/reports/checks.json`, `evidence/reports/m2_focused_tests.json`,
`evidence/reports/pantry_accounting.json`, the walkthrough reports in `evidence/screenshots/`,
and the live-run records `evidence/reports/live_*_run.json`. Nothing is reported as passing
unless it ran. Scenario times are given in each fixture's local time (America/New_York);
traces store UTC.

All of this is **development evidence** on fictional, synthetic fixtures. It is not held-out
evaluation, it supports no comparative claim, and it is not community validation.

**Finishing Wave 2 (2026-10-25).** P1 (`tool-use/1.0.0`) and P3 (`verify-all/1.0.0`) were
built, P2 (`live/1.0.0`) gained the pantry's stock options, and one development run each of P1,
P2 and P3 was recorded on five cases (section 1b, section 4). The M2 table (section 3) is
updated: "Future comparison parity" is now passed, and the live pantry result is the P2 run
`live_p2-live_pantry_dev01`. The audit step then reran P1's four `tool_use.v1` runs under the
shipped `tool_use.v2` and fixed what its five auditors confirmed (section 1c). The integration
step closed two last audit items, committed the finishing work (`9158793`, the app, and
`c4f7cd9`, the packet) and regenerated the evidence from a clean checkout of `c4f7cd9`
(sections 1, 1d and 2). A final audit of the committed result then fixed two pantry details
and the packet's wording, and disclosed one gap shared by every policy (section 1e).

## 1. How the evidence was produced

Two scripts produced it. The recorded live runs were each made once from a working tree: the 8
Wave 2 runs on 2026-10-24, after every Wave 2 worker had finished, and the 20 P1–P3 development
runs on 2026-10-25 (sections 1b and 1c). The rest of the evidence was then regenerated on
2026-10-25 from a fresh, clean checkout of the packet commit `c4f7cd9`, after the integration
step's commits (the 2026-10-24 regeneration used `fd04d48` in the same way). `environment.json`
records `git_head = c4f7cd9…` and `app_tree_clean = true`. The collector made no paid call: it
copied the 28 recorded live runs and verified each live trace again, and the ledger file was
byte-identical before and after.

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
#    (the P1-P3 development runs and reruns: sections 1b and 1c)
# 2. Every check, the deterministic cases, both walkthroughs, the storyboard and the scans
#    (no paid call), from a clean checkout of c4f7cd9 (git worktree, uv sync --all-groups
#    --locked, npm ci, the ledger copied into the worktree's var/)
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
| Prompts | `interpret.v1`, `choose_action.v1`, `choose_action_pantry.v1`, `tool_use.v1`, `tool_use.v2` (sha256 in `reports/fixture_hashes.json` and on every live decision) |
| Episode caps | 48 tool calls, 8 model calls, phase `development` |
| Spend caps | 0.50 USD per episode; 8.00 USD cumulative over the ledger (this step's limit) |

`reports/fixture_hashes.json` holds the hashes of the three public fixtures, the nine private
cases, the 11 planning examples, the planning schema, the prompts, both lockfiles and migrations
0001–0004.

### 1b. Finishing Wave 2: the P1-P3 development runs (2026-10-25)

Run from the working tree with the finished P1, P2 and P3 code, before the integration commit.
The cumulative spend cap was 5.29 USD over a ledger at 0.29906, so this step could spend at most
5 USD.

```bash
cd apps/plan_b
# 0. one read-only GET /api/v1/key (numeric fields only): limit 50, remaining 49.70094, usage 0.29906
# 1. the development runs (paid; each once; kept as recorded)
PLAN_B_MODEL_MAX_TOTAL_COST_USD=5.29 uv run python scripts/run_live_cases.py --out <live> --policy tool-use dev01
PLAN_B_MODEL_MAX_TOTAL_COST_USD=5.29 uv run python scripts/run_live_cases.py --out <live> --policy tool-use dev02 dev04 pantry_dev01 skills_dev01
PLAN_B_MODEL_MAX_TOTAL_COST_USD=5.29 uv run python scripts/run_live_cases.py --out <live> --policy live dev01 dev02 dev04 pantry_dev01 skills_dev01
PLAN_B_MODEL_MAX_TOTAL_COST_USD=5.29 uv run python scripts/run_live_cases.py --out <live> --policy verify-all dev01 dev02 dev04 pantry_dev01 skills_dev01
# 2. P1's pantry_dev01 run failed on a defect in our P1 harness (DECISIONS W2-D11); after the fix:
uv run pytest -q -o addopts= -p no:cacheprovider        # 756 passed, 1 warning, exit 0
PLAN_B_MODEL_MAX_TOTAL_COST_USD=5.29 uv run python scripts/run_live_cases.py --out <live> \
    --policy tool-use --label p1-tool-use_pantry_dev01_r2 pantry_dev01
# 3. copied into evidence/{reports,traces,runner_private}; then (no model call):
uv run python scripts/write_development_results.py --evidence ../../PEEAI_plan/handoffs/wave_2/evidence
uv run plan-b verify-trace ../../PEEAI_plan/handoffs/wave_2/evidence/traces/live_p<N>-*_trace.json   # 16 x intact
```

Results:

* **The runs.** Every invocation exited 0. 15 of the 16 recorded runs matched expectation.
  The exception is the superseded first P1 pantry_dev01 run. Every trace verifies `intact`.
  The model was `anthropic/claude-sonnet-5.5`, requested and returned on every call. Section 4
  has the table.
* **The defect and its fix.** `tool_use.v1` did not document a hold's window, and the
  1536-token turn limit was shared with the model's reasoning tokens. The fix is a new prompt
  `tool_use.v2` and a 4096-token limit, with `tests/test_tool_use_hold_window.py` (2 tests).
  `tests/test_live_workflow.py` and `tests/test_comparison_policy_fixes.py` were updated to the
  new prompt id and limit. The affected focused tests passed (6), then the full suite passed
  (756) before the rerun.
* **The collector's live-run part, checked in isolation** (not the full collector).
  `copy_live` copied 24 live records (the 8 Wave 2 runs and the 16 new ones). `live_summary`
  and the new `live_by_policy` summarized them per policy id. `spend_summary` labelled every
  ledger run id, and its sum equalled the ledger total. `m2_focused`, on a JUnit report of the
  six parity and workflow test files (140 passed), matched every new pattern with passing
  tests: "Future comparison parity" 82 and "Bounded failure behavior" 22.
* **Scans.** No credential-shaped text and no local path or identifier in the new evidence and
  results files (a pattern search of those files).
* **Not run in this step:** the web checks and the browser walkthroughs (a concurrent worker
  was changing `web/src`), and the full collector. The integration step runs them from a clean
  checkout.

### 1c. Wave 2 audit step: P1 reruns and confirmed fixes (2026-10-25)

Five auditor subagents reviewed the finishing step's tree: claims against evidence, M2
completeness, the contract and docs against the code, security and sanitization, and the demo.
They raised 38 findings, 37 after merging one duplicate. Each was checked by reproduction or by
tracing the code, and every confirmed one was fixed except two outside the audit's files
(KNOWN_LIMITATIONS, "One record path still to harden"; the integration step then closed the
gate's exception text and the staff receipt default). A re-audit reviewed the fixes. The
four P1 runs recorded under `tool_use.v1` no longer reflected the shipped P1, so they were run
again.

```bash
cd apps/plan_b
# 1. P1 under the shipped prompt (paid; one trial each; ledger before: 1.96562 USD, 102 entries)
PLAN_B_MODEL_MAX_TOTAL_COST_USD=3.46562 uv run python scripts/run_live_cases.py --out <live> \
    --policy tool-use --label p1-tool-use_<case>_r2 <case>   # dev01, dev02, dev04, skills_dev01
uv run python scripts/write_development_results.py --evidence ../../PEEAI_plan/handoffs/wave_2/evidence   # 20 runs written; spend 2.5798 USD
uv run plan-b verify-trace ../../PEEAI_plan/handoffs/wave_2/evidence/traces/live_p1-tool-use_<case>_r2_trace.json   # 4 x intact
# 2. browser checks: one press of "Run live agent" on a fresh dev01 (paid; per-run cap 0.10 USD),
#    and one press with PLAN_B_MODEL_BASE_URL=http://127.0.0.1:9/api/v1 (a closed local port)
# 3. the battery, after every fix
uv run pytest -q -o addopts= -p no:cacheprovider --junitxml=<work>/junit.xml   # 762 passed, 1 warning
uv run plan-b run-case all --db <work>/runs.sqlite3 --out <work>/out           # 9 lines, all matching
uv run plan-b verify-trace <work>/out/traces/<each>_trace.json                 # 9 x intact
(cd web && npm run typecheck && npm test && npm run build && npm run lint)      # 390 pass; build and boundary lint pass
uv run python tests/e2e/walkthrough.py --out <work>/wt1                        # 41/41 checks passed
uv run python tests/e2e/walkthrough_wave2.py --out <work>/wt2                  # 30/30 checks passed
uv run python tests/e2e/storyboard.py --out <work>/sb --port 8791              # 32/32 checks passed
uv run python tests/e2e/storyboard.py --port 8791   # 32/32; rewrote evidence/storyboard/
```

Results:

* **The reruns.** All four matched expectation, every call `ok`, every trace `intact`: dev01
  8 model calls (cap at 17:24), 22 tool calls, 0.2408 USD; dev02 8 (cap at 17:44), 24, 0.2425;
  dev04 6, 20, 0.1761; skills_dev01 8 (cap at 10:06), 20, 0.2539. In all, 30 calls and
  0.91328 USD. The `tool_use.v1` runs are kept and marked superseded by the prompt change.
* **The browser checks.** The press made 3 calls in 11.5 s for 0.03655 USD and recorded verify,
  the swap (`rcpt_0001`) and keep: the live button works. Against the closed port, the press
  returned in 0.3 s with a labeled `wait` (`provider_error`) and an unchanged plan, and a clean
  reload, the deterministic run and a replay then worked. The ledger records that check at
  cost 0 (`transport`).
* **The battery.** The 9 case lines are identical to the evidence `checks.json`, and dev01–dev06
  to Wave 1. Mapped with the collector's `m2_focused` on the JUnit of the 762-test run, every
  M2 check's tests passed: live campus 8, bounded failure 57, community 40, shared pantry core
  15, stock and service 7, quantity 10, staff 11, parity 101.
* **Behavioral fixes, with tests.** A restarted server now resumes an episode's model spend, so
  the per-run USD cap stays per episode (`test_comparison_policy_fixes.py`, 4 tests). A recorded
  run's error text names no local path (`test_live_run_script.py`, 2 tests). The web shows the
  pantry capacity tile as "Can still be distributed now" and an unreachable provider as "failed
  or could not be reached" (`web/tests/demo_story.test.ts`, 2 tests). The live badge no longer
  uses the replay's purple. The storyboard places cards under the replay banner, frames the
  organizer at the deck size and guards its secret check. The collector now runs the storyboard
  into `<evidence>/storyboard/`.
* **Security scans** (the security auditor): no key material in 124,534 files of the working
  tree, the evidence, the web bundle and `var/` (a script that read the key in memory and
  printed file names only; see KNOWN_LIMITATIONS); no credential, host name, user name or
  absolute path in the packet or the results; no private truth in browser-visible files,
  replays or public reports; all 31 evidence traces `intact`.
* **Not run here:** the full collector from a clean checkout (the integration step, section 1d),
  and any further browser run of a model-driven policy.

### 1d. Integration step: two last fixes, the commits and the clean regeneration (2026-10-25)

The run coordinator added two small audit items, both fixed with focused tests and checked by
reverting each fix (the new tests then failed):

* **D2:** `agent/gate.py` now records a raised exception's class and a sanitized message:
  credential-shaped tokens become `<redacted>` and local paths `<path>`, cut to 300 characters
  (`tests/test_gate_error_text.py`, 2 tests).
* **E3:** after a handoff receipt, the staff receipt form no longer falls back to the S20
  shipment. A source staff picked stays chosen while it is receivable; otherwise the form shows
  the next open handoff, or nothing until staff pick one (`web/tests/staff_receipt.test.ts`,
  2 tests).

```bash
cd apps/plan_b
# 1. the battery on the working tree, after both fixes
uv run ruff check; uv run ruff format --check; uv run mypy
uv run pytest -q -o addopts= -p no:cacheprovider --junitxml=<scratch>/junit.xml
(cd web && npm run typecheck && npm test && npm run build && npm run lint)
uv run plan-b run-case all --db <scratch>/runs.sqlite3 --out <scratch>/out   # + verify-trace on each
uv run python tests/e2e/walkthrough.py --out <scratch>/wt1
uv run python tests/e2e/walkthrough_wave2.py --out <scratch>/wt2
uv run python tests/e2e/storyboard.py --out <scratch>/sb --port 8791
# 2. commit 9158793 (apps/plan_b) and c4f7cd9 (this packet), explicit paths, no trailers
# 3. the clean regeneration (section 1), into an empty directory that then replaced evidence/
git worktree add --detach <scratch>/clean HEAD    # c4f7cd9
uv run python scripts/collect_wave2_evidence.py --out <empty> \
    --live ../../PEEAI_plan/handoffs/wave_2/evidence \
    --gate ../../PEEAI_plan/handoffs/wave_2/evidence/reports/g_llm_gate.json
```

Step 1 was all green: ruff and format clean (115 files), mypy clean (70 source files), 764
Python tests passed, web typecheck clean, 392 web tests passed, build and boundary lint passed;
`run-case all` exited 0 with 9 lines, all `matches_expectation=True`, identical to the Wave 2
evidence lines and, for dev01–dev06, to Wave 1; the 9 traces `intact`; walkthroughs 41/41 and
30/30; storyboard 32/32. Before each commit a script compared every staged file with the key
file and searched for credential shapes, local paths, the host and user names and attribution
text, printing file names only: nothing was found. The collector in step 3 printed
`all checks passed` (56 checks, section 2) and exited 0. Its output has the same 182 files as
the evidence it replaced. Apart from the regenerated reports, screenshots and storyboard, only
episode ids differ in the deterministic outcomes and traces. The copied live runs are
byte-identical. The worktree was removed afterwards.

### 1e. Final audit of the committed result (2026-10-25)

The audit checked the commits after `65997ac` (author, committer, no trailers, no attribution),
that nothing was pushed, the key and credential scans of the committed tree and of every new
commit's blobs (no match), the evidence (`environment.json`, every check's exit code, every
relative link in this packet, the storyboard frames DEMO.md embeds), and had three read-only
auditors re-read the packet as a first-time judge, spot-check the P1, P3 and pantry code, and
scan the committed evidence and storyboard for secrets and identifiers. Each finding was
checked before it was acted on. The security read found nothing to fix. Fixed:

* **The awaited-handoff `wait` now records its wake time.** P2 and P3 recorded the server's
  "Waiting for staff to record the handoff" decision without `wait_until`, although the run's
  own wake was right and the contract (section 16) promises it. It now carries the staff
  task's `respond_after`, then its cutoff (`agent/orchestrator.py`;
  `tests/test_pantry_live_menu.py`).
* **A handoff requested before its window opens is checked as too early.** The planner's
  `stock_transfer` check said "too late" in that case too. It now says "too early, the handoff
  window opens at …" (`domain/adapters/pantry.py`; `tests/test_comparison_policy_fixes.py`).
  Every policy reads this text, and P1 reads it directly. Neither development case reaches this
  branch: their deterministic traces differ from the evidence only in episode ids and the
  digests that contain them.
* **P1's staff-tool filter has a test that can fail.** No shipped grant lists a staff tool, so
  the parity test could not reach the filter. A new test widens a grant and checks P1's turn
  tools (`tests/test_comparison_policy_fixes.py`).
* **The packet's wording.** README.md now says what Plan B does and what P0 is. Its numbers
  name which runs they count, and its claims say which code the P2 runs came from. In DEMO.md
  the presenter now says that the first four minutes run the rule baseline. The optional
  readout names the superseded runs, the rejected-hold codes are given as the trace has them,
  and the backup P3 frame has its URL. Section 9's table is now read from the committed
  storyboard report.

Each code fix was checked by reverting it: its test then failed. Disclosed, not fixed: no policy
(P0–P3) wakes when the handoff window opens (KNOWN_LIMITATIONS, "No policy wakes when the
handoff window opens"). A probe with a 12:42–12:49 window reproduced it for P0, P2 and P3.

## 2. Commands and results

These are the collector's rows from `reports/checks.json`. `<work>` is its temporary directory
and `<evidence>` is `PEEAI_plan/handoffs/wave_2/evidence`.

| # | Check | Command (from `apps/plan_b`) | Exit | Result |
| --- | --- | --- | --- | --- |
| 1 | Lint | `uv run ruff check .` | 0 | All checks passed |
| 2 | Format | `uv run ruff format --check .` | 0 | 115 files already formatted |
| 3 | Types | `uv run mypy` | 0 | no issues in 70 source files |
| 4 | Web typecheck | `npm run typecheck` (web/) | 0 | `tsc --noEmit` clean |
| 5 | Web build | `npm run build` (web/) | 0 | JS 322.18 kB (95.84 kB gzip) |
| 6 | Python tests | `uv run pytest -o addopts= -q -p no:cacheprovider --junitxml=…` | 0 | **764 passed, 0 failed, 0 skipped** (1 warning: Starlette's httpx deprecation) |
| 7 | Web tests | `npm test` (web/) | 0 | **392 passed**, 0 failed |
| 8 | Web boundary lint | `npm run lint` (web/) | 0 | 25 read-only modules, 40 sources, dist bundle scanned |
| 9 | Development cases | `uv run plan-b run-case all --db <work>/runs.sqlite3 --out <work>/out` | 0 | 9/9 `matches_expectation=True`, `violations=0` (section 4) |
| 10 | Rejections | `uv run plan-b demo-rejections --db <work>/demo.sqlite3 --out <work>/out` | 0 | all 20 steps got their expected result; 7 rejected receipts, 2 attempts without receipt, `violations=0` (`reports/rejected_actions_steps.json`) |
| 11–20 | Trace integrity | `uv run plan-b verify-trace <work>/out/traces/<trace>.json` | 0 | dev01, dev02, dev04, dev05, dev06, pantry_dev01, pantry_dev02, skills_dev01, skills_dev02, rejected_actions: all `intact` |
| 21 | Wave 1 lines | dev01–dev06 lines compared with the Wave 1 evidence | 0 | identical (`reports/wave1_parity.json`) |
| 22 | Pantry accounting | computed from the pantry traces | 0 | section 5 |
| 23 | M2 focused tests | the M2 checks mapped to their tests in row 6's JUnit report | 0 | every mapped test passed (section 3) |
| 24 | Browser, Wave 1 | `uv run python tests/e2e/walkthrough.py --out <work>/shots1` | 0 | **41/41 checks passed** |
| 25 | Browser, Wave 2 | `uv run python tests/e2e/walkthrough_wave2.py --out <work>/shots2` | 0 | **30/30 checks passed** (pantry staff flow, community check-in and offer, policy switch) |
| 26 | Demo storyboard | `uv run python tests/e2e/storyboard.py --out <evidence-out>/storyboard --port <free>` | 0 | **32/32 checks passed**, 24 frames (`storyboard/`) |
| 27–54 | Live trace integrity | `uv run plan-b verify-trace <evidence>/traces/live_<label>_trace.json` | 0 | all 28 recorded live traces `intact` (8 Wave 2 runs, 20 P1–P3 development runs) |
| 55 | Credential scan | every text file written: an OpenRouter key prefix, a bearer token | 0 | none found in 145 text files (no key was read for this scan) |
| 56 | Identifier scan | every text file written: host name, user name, git email, local paths | 0 | none found in 146 text files |

pytest ran after the web build, so the bundle-privacy test scanned the real bundle. The JUnit
report is `reports/pytest_junit.xml`, with its host name replaced and its timestamp removed.

## 3. M2 checks → recorded outcomes

The checks are the "Mandatory M2 checks" of `PEEAI_plan/waves/02_adaptation.md`. Test paths are
relative to `apps/plan_b/tests/`. `reports/m2_focused_tests.json` lists every mapped test with
its outcome in the row-6 run (the clean regeneration from `c4f7cd9`, 764 tests). Its counts are
those of the audit step's full run (section 1c) cited below: live campus 8, bounded failure 57,
community 40, pantry core 15, stock and service 7, quantity 10, staff boundary 11 and comparison
parity 101, all passed.

| M2 check | Recorded outcome | Evidence |
| --- | --- | --- |
| **Live campus behavior**: one real model-driven end-to-end recovery with a useful tool call, a validated action and fresh-state agreement; a stale warning gets a distinct, justified response | **Pass** (one live trial each; see the dev01 and dev04 details below the table; Wave 2 runs from the `bf71e43` tree, reproduced with the finishing step's code by `live_p2-live_dev01` and `live_p2-live_dev04`) | `reports/live_dev01_run.json`, `traces/live_dev01_trace.json`; `reports/live_dev04_run.json`, `traces/live_dev04_trace.json`; also live dev02, dev05, dev06, skills_dev01 and skills_dev02 (section 4); `reports/g_llm_gate.json` (G-LLM pass); 8 focused tests passed |
| **Bounded failure behavior**: malformed output, unknown entity, exhausted cap, timeout and stale revision stay visible and produce no invented success | **Pass on the focused tests; four failure paths also occurred live** (see below the table) | 57 mapped tests passed in the audit step's run (35 in `test_agent_boundary.py`, `test_agent_provider.py`, `test_integration_policy.py`, `test_integration_api.py`, as recorded at `fd04d48`; 22 for every class under P1, P2 and P3 in `test_live_workflow.py`); `reports/live_skills_dev02_run.json`, `reports/live_dev06_run.json`, `reports/live_p1-tool-use_pantry_dev01_run.json`, `reports/live_p1-tool-use_dev02_run.json` |
| **Community workflow**: participant input changes a role fact and affects planning; unauthorized goal or stock actions reject; the skills exchange loads through the event adapter | **Pass** (see below the table) | 40 focused tests passed (`test_community_skills_exchange.py`, `test_resource_offer.py`, `test_integration_api.py`, `test_stock_conservation.py::test_agent_cannot_call_staff_only_tools`); `traces/skills_dev01_trace.json`; `traces/live_skills_dev01_trace.json`; walkthrough_wave2 community flow (`screenshots/w2_07`–`w2_10`) |
| **Shared pantry core**: the same orchestration, grants, receipts, replay and transaction boundary run the pantry scenario; the domain adapter owns only the added semantics | **Pass** (see below the table) | `traces/pantry_dev01_trace.json`, `traces/pantry_dev02_trace.json` (`intact`); 15 focused tests passed (`test_pantry_workflow.py`, `test_pantry_fixture.py`, `test_integration_policy.py`); walkthrough_wave2 pantry flow (`screenshots/w2_01`–`w2_06`) |
| **Stock and service accounting**: the 24/16 to 40/0 handoff conserves stock; the target stays 40; a receipt or commit does not reduce the service deficit; only distribution records achieved service | **Pass** | `reports/pantry_accounting.json` (section 5); 7 focused tests passed (`test_stock_conservation.py`, `test_pantry_workflow.py::test_completion_distribution_and_next_start_order_at_the_inclusive_deadline`) |
| **Quantity failure checks**: overlapping and non-overlapping double allocation reject; release and expiry create no stock; duplicate physical records cannot credit twice; a partial handoff keeps its residual reservation; early distribution cannot exceed attended throughput; late records keep truthful times and fail on-time attainment | **Pass** | 10 focused tests passed (`test_stock_conservation.py`); pantry_dev02's partial handoff in `reports/pantry_accounting.json` |
| **Staff boundary**: the agent cannot call the staff-only receipt or distribution operations; without staff attestation there is no fictional physical success | **Pass** (see below the table) | 11 focused tests passed (`test_stock_conservation.py`, `test_agent_boundary.py`, `test_pantry_workflow.py`, `test_pantry_fixture.py`); `reports/live_pantry_dev01_run.json`; the P1, P2 and P3 pantry runs (`runner_private/live_p*_pantry_dev01*`, `p_staff_only` passed in each) |
| **Future comparison parity**: P0–P3 use the same candidates, grants, executor, tools and domain semantics within each suite; policy-specific prompts are recorded | **Pass** (finishing step, 2026-10-25; see below the table) | `test_policy_parity.py`, `test_live_workflow.py`, `test_pantry_live_menu.py`, `test_comparison_policy_fixes.py`, `test_runner_isolation.py`, `test_tool_use_hold_window.py`, with `test_agent_boundary.py` and `test_integration_policy.py` (101 mapped tests passed in the audit step's 762-test run); the 20 development runs of P1-P3 (`reports/live_p*_run.json`, section 4) |

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
  * `live_p1-tool-use_pantry_dev01` (superseded; DECISIONS W2-D11): two replies were cut off
    at the token limit (`malformed_json`); one was repaired and the other ended at the model-call
    cap. Six refused holds stayed visible as `wait` decisions with their error codes. Nothing
    was invented: 0 of 40 kits, stock conserved.
  * Exhausted caps: P1 reached the 8-call model cap in `live_p1-tool-use_dev01_r2` (17:24),
    `live_p1-tool-use_dev02_r2` (17:44) and `live_p1-tool-use_skills_dev01_r2` (10:06), and in
    the superseded `live_p1-tool-use_dev02` (17:44), `live_p1-tool-use_skills_dev01` (10:06) and
    the run above (12:35). Each is a host `stop`, and the plan and commitments stayed as they
    were.
* **Not induced against the real provider:** an unknown entity and timeouts.

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
* No live pantry run made an attestation: `no_staff_attestation_by_agent` passed in the Wave 2
  run and in the four P1, P2 and P3 pantry_dev01 runs (`p_staff_only`). In the three completed
  runs only the labeled staff simulator recorded the receipt and the distribution.

**Future comparison parity, in detail** (passed in the finishing step).

* **The same harness for P0–P3.** All four run through `run_case`, `PolicyHost`, the episode caps,
  the scripted actors, the labeled staff simulator, one coordinator grant and one executor.
  `test_policy_parity.py::test_each_policy_reads_the_same_grant_tools_and_candidates` runs every
  policy behind a recording client on dev01, skills_dev01 and pantry_dev01. It compares the
  grant (principal, id, body, version), the candidate sets of every evaluation and the tools
  called. It also checks that P1's tool enum is the grant's tools minus the staff tools.
* **Each suite end to end.** `test_live_workflow.py::test_p1_to_p3_complete_each_suite_end_to_end_with_recorded_prompts`
  runs P1, P2 and P3 on the campus, community and pantry suites with scripted models. Every run
  matches expectation with no violation, uses only granted coordinator tools, and records its
  prompts by sha256 on every decision.
* **The pantry suite now meets the equal-adapter rule.** P2 and P3 offer the adapter's own
  stock candidates (`test_pantry_live_menu.py`, 13 tests), and P1 reads the same candidates and
  calls the same tools. P2 and P3 report a shortfall and release closed handoff holds as P0
  does.
* **P3's relevance rule** (`verify-all-relevance/1.0.0`) names event and resource identifiers
  only, and is tested on dev01, dev06 and the pantry.
* **With the real model.** One development run each of P1, P2 and P3 on dev01, dev02, dev04,
  pantry_dev01 and skills_dev01 went through this harness. Each decision records its prompt ids
  and hashes: P1 `tool_use.v1` or `tool_use.v2`; P2 and P3 `interpret.v1`, `choose_action.v1`
  and `choose_action_pantry.v1`. The first P1 pantry run exposed a documentation defect in P1's
  prompt and was rerun after the fix (W2-D11); the audit step reran P1's other four `tool_use.v1`
  runs under `tool_use.v2` too (section 1c). Parity holds on candidates, grants, tools and
  executor, not on instructions: each policy has its own prompts, which are published and
  recorded.
* **Still open for Wave 3:** freeze the prompts (P1's current runs all use `tool_use.v2`; its
  five superseded runs used `tool_use.v1`), the caps, the output-token limits and the model
  before any comparison.

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

**Recorded live runs** (`policy="live"`, `live/1.0.0` as of the `bf71e43` tree, 2026-10-24). The
finishing step later changed `live/1.0.0` without a new id: pantry stock options and
`choose_action_pantry.v1`, server-side shortfall and release steps on the pantry, and no apply
option for a candidate that changes nothing, on every profile. So these runs are not the shipped
code; the P2 runs further below are (`live_p2-live_*`), and on dev01 and dev04 they reproduce
the behavior described here. Each case ran once, under caps of 48 tool calls and 8 model
calls. The model was `anthropic/claude-sonnet-5.5`, requested and returned on
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
  2. apply the robust free swap (one failed status query in this run).
* **pantry_dev01:** **failed**, recorded honestly. There was no notice to interpret and the menu
  had no stock option. The server recorded `wait` and no model call was made. Nothing was
  committed, so 0 of 40 kits were distributed. Stock stayed conserved.
  It is kept as recorded. The live pantry result is now the P2 development run below.

**Development runs of P1-P3** (finishing step, 2026-10-25; section 1b). One trial each, under the
same caps. The model was `anthropic/claude-sonnet-5.5`, requested and returned on every call.
Spend is the ledger difference over the run. Every trace verifies `intact`. "cap" marks a run
that reached the 8-call model cap. These are development runs: no comparison between policies is
drawn from them. `plan_b/evaluation/development/README.md` gives one sentence per run, read from
its trace.

| Run | Policy | Prompts | goal_complete | matches | Model calls | Tool calls | Model latency | Tokens (prompt / completion) | Spend (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| live_p1-tool-use_dev01 (superseded) | tool-use/1.0.0 | tool_use.v1 | True | True | 7 (7 turns) | 21 | 30.9 s | 86294 / 3175 | 0.2043 |
| live_p1-tool-use_dev01_r2 | tool-use/1.0.0 | tool_use.v2 | True | True | 8 (8 turns) cap | 22 | 33.3 s | 102028 / 3675 | 0.2408 |
| live_p1-tool-use_dev02 (superseded) | tool-use/1.0.0 | tool_use.v1 | True | True | 8 (8 turns) cap | 24 | 32.7 s | 101817 / 3634 | 0.2400 |
| live_p1-tool-use_dev02_r2 | tool-use/1.0.0 | tool_use.v2 | True | True | 8 (8 turns) cap | 24 | 32.0 s | 103472 / 3557 | 0.2425 |
| live_p1-tool-use_dev04 (superseded) | tool-use/1.0.0 | tool_use.v1 | True | True | 7 (7 turns) | 20 | 21.6 s | 87635 / 1963 | 0.1949 |
| live_p1-tool-use_dev04_r2 | tool-use/1.0.0 | tool_use.v2 | True | True | 6 (6 turns) | 20 | 19.8 s | 77106 / 2187 | 0.1761 |
| live_p1-tool-use_pantry_dev01 (superseded) | tool-use/1.0.0 | tool_use.v1 | False | False | 8 (8 turns) cap | 15 | 72.2 s | 86360 / 9182 | 0.2645 |
| live_p1-tool-use_pantry_dev01_r2 | tool-use/1.0.0 | tool_use.v2 | True | True | 6 (6 turns) | 18 | 28.8 s | 63160 / 3363 | 0.1600 |
| live_p1-tool-use_skills_dev01 (superseded) | tool-use/1.0.0 | tool_use.v1 | True | True | 8 (8 turns) cap | 21 | 31.2 s | 110590 / 3226 | 0.2534 |
| live_p1-tool-use_skills_dev01_r2 | tool-use/1.0.0 | tool_use.v2 | True | True | 8 (8 turns) cap | 20 | 29.5 s | 110544 / 3279 | 0.2539 |
| live_p2-live_dev01 | live/1.0.0 | choose_action.v1, interpret.v1 | True | True | 3 (2 choose, 1 interpret) | 24 | 10.6 s | 13535 / 955 | 0.0366 |
| live_p2-live_dev02 | live/1.0.0 | choose_action.v1, interpret.v1 | True | True | 6 (5 choose, 1 interpret) | 32 | 20.4 s | 28445 / 1924 | 0.0761 |
| live_p2-live_dev04 | live/1.0.0 | choose_action.v1, interpret.v1 | True | True | 3 (1 choose, 2 interpret) | 25 | 8.4 s | 10765 / 826 | 0.0298 |
| live_p2-live_pantry_dev01 | live/1.0.0 | choose_action_pantry.v1 | True | True | 4 (4 choose) | 21 | 14.9 s | 17544 / 1012 | 0.0452 |
| live_p2-live_skills_dev01 | live/1.0.0 | choose_action.v1, interpret.v1 | True | True | 2 (1 choose, 1 interpret) | 25 | 5.4 s | 6657 / 416 | 0.0175 |
| live_p3-verify-all_dev01 | verify-all/1.0.0 | choose_action.v1, interpret.v1 | True | True | 2 (1 choose, 1 interpret) | 24 | 5.9 s | 7689 / 439 | 0.0198 |
| live_p3-verify-all_dev02 | verify-all/1.0.0 | choose_action.v1, interpret.v1 | True | True | 4 (3 choose, 1 interpret) | 29 | 14.9 s | 17439 / 1269 | 0.0476 |
| live_p3-verify-all_dev04 | verify-all/1.0.0 | interpret.v1 | True | True | 2 (2 interpret) | 24 | 4.9 s | 5017 / 494 | 0.0150 |
| live_p3-verify-all_pantry_dev01 | verify-all/1.0.0 | choose_action_pantry.v1 | True | True | 4 (4 choose) | 24 | 14.5 s | 16932 / 963 | 0.0435 |
| live_p3-verify-all_skills_dev01 | verify-all/1.0.0 | choose_action.v1, interpret.v1 | True | True | 2 (1 choose, 1 interpret) | 28 | 5.0 s | 6861 / 467 | 0.0184 |

The 20 runs made 106 model calls for 2.57984 USD: the finishing step's 16 runs 76 calls and
1.66656 USD, the audit step's four P1 reruns 30 calls and 0.91328 USD. Five runs are superseded
(the P1 runs under `tool_use.v1`), and the 15 current runs all matched expectation. In short:

* **The live pantry result is `live_p2-live_pantry_dev01`.** P2 asked staff for the 16-kit
  handoff at 12:31, waited for the staff simulator's receipt at 12:33 (24/16 → 40/0), held the 40
  pantry kits at 12:34 and committed them at 12:35. Staff distributed 40 of 40 on time at 13:40,
  and S20 stayed 20 unreceived. The counters went 16/40 → 0/40 → 0/0, as in the baseline. P3 did
  the same after its two server-side checks, and so did P1 after its fix.
* **`live_p1-tool-use_pantry_dev01` failed and is superseded** by `..._r2` (DECISIONS W2-D11).
  The failure was a defect in P1's prompt and turn limit, not the model's judgment. The run is
  kept as recorded.
* **P1's v1 runs are superseded by the prompt change.** dev01, dev02, dev04 and skills_dev01
  first ran under `tool_use.v1` and matched; they were rerun once under the shipped `tool_use.v2`
  in the audit step (`..._r2`) and matched again. The v1 runs are kept as recorded.
* **P1 reached the 8-call model cap** in its current dev01 (17:24), dev02 (17:44) and
  skills_dev01 (10:06) runs, after its plan was in place. All three still matched expectation
  (KNOWN_LIMITATIONS).
* **P3's checks are made by the server**, so its model-call counts are not comparable with
  P2's.

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

### Adapter implementation effort and changed interfaces

`02_adaptation.md` asks the M2 record to keep the pantry adapter's implementation effort. Effort
was not timed; its size is the measure recorded here. Line counts are of the current tree; the
pantry files are new since the Wave 1 packet (`d6b9256`):

| Part | Files | Lines |
| --- | --- | --- |
| Domain adapter and stock accounting | `domain/adapters/pantry.py`, `domain/stock.py` | 1338 + 631 |
| Staff and stock tools | `tools/stock.py` | 858 |
| Storage | `store/migrations/0004_consumable_stock.sql` | 249 |
| Pantry rule policy (P0) | `evaluation/policies/pantry_rules.py` | 845 |
| Scenario fixture | `scenarios/public/pantry_continuity.json` | 729 |
| Browser | `web/src/components/PantryBoard.tsx`, `web/src/views/StaffActions.tsx` | 290 + 493 |
| Live agent's pantry options (finishing step; the diff also holds P3's hook and the audit fixes) | `agent/menu.py`, `agent/orchestrator.py` (+358/−9 and +425/−4 over `40b6162`), prompt `choose_action_pantry.v1` (55) | 783 added |

Shared interfaces that changed for the pantry, rather than files added beside them:
`domain/models.py`, `store/engine.py`, `store/repo.py`, `store/projection_db.py` and
`tools/handlers.py`. RUNTIME_CONTRACT.md sections 10 (pantry planner), 15 (consumable stock) and
16 (the live agent's pantry menu) describe them.

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
run. The table below reads the ledger after the audit step. It holds 136 entries: 133 calls with
outcome `ok`, 2 `malformed_json` (the cut-off P1 replies, section 3) and 1 `transport` at cost 0
(the audit's fallback check against a closed local port, section 1c). Every call that was answered
returned `anthropic/claude-sonnet-5.5`, with cost basis `provider_usage`.

| Run | Calls | Cost (USD) |
| --- | --- | --- |
| G-LLM gate (Build 1) | 3 | 0.03509 |
| Wave 2 live runs (8 runs, section 4) | 23 | 0.26397 |
| P1-P3 development runs of the finishing step (16 runs, section 4) | 76 | 1.66656 |
| P1 reruns under `tool_use.v2`, audit step (4 runs, section 4) | 30 | 0.91328 |
| Audit step's browser checks: one press of **Run live agent**, and the fallback check | 3 + 1 | 0.03655 + 0 |
| **ledger total** | **136** | **2.91545** |

`reports/model_spend_summary.json` was rewritten from the ledger by the integration step's
collector run: 136 entries, 2.91545 USD, and its 30 run ids sum to the ledger total. The two run
ids no run record names (`live-e1ac750a5aaf`, 3 calls, 0.03655 USD, and `live-7974806e5fdb`, the
$0 transport entry) are the audit step's browser checks, labelled "not a recorded run". The
integration step made no model call.

* **Key check:** one read-only `GET /api/v1/key`, made before the live runs, reported limit 50,
  remaining 49.96491 and usage 0.03509. That usage equals the ledger total at that time.
* **Caps:** this step's cumulative cap was 8.00 USD. No call was refused by the spend guard,
  and no episode reached a cap.
* **Finishing step:** one read-only `GET /api/v1/key` before the development runs reported limit
  50, remaining 49.70094 and usage 0.29906, which equals the ledger total then. The cumulative cap
  was 5.29 USD (at most 5 USD for the step). The step spent 1.66656 USD. No call was refused by
  the spend guard. The episode model-call cap was reached in three P1 runs.
* **Audit step:** no key check was made. The reruns ran under a cumulative cap of 3.46562 USD
  (1.50 above the ledger at the start); the browser press ran under a 0.10 USD per-run cap. The
  step spent 0.94983 USD. No call was refused by the spend guard. The model-call cap was reached
  in three of the four reruns.

## 8. Not run, or not verified

* **W2.4 MBTA (stretch): not built.** No transit adapter exists and the MBTA key was not read.
* **Failure classes against the real provider:** an unknown entity and a timeout were tested
  only with scripted transports. Malformed output (a cut-off reply) and exhausted model-call caps
  occurred live in P1 runs (section 3).
* **Repeated live trials and variance:** each live case ran once, for each policy.
* **A held-out evaluation and any comparison of P0-P3:** not run (Wave 3). The development runs
  support no comparative claim.
* **The model-driven policies in a real browser session:** the walkthrough selects the live agent
  but does not run it. The audit pressed **Run live agent** once by hand (section 1c); no
  automated browser test runs a model-driven policy.
* **Other browsers, screen readers, Python 3.11, comprehension by new viewers, community
  validation:** not run, as in Wave 1.
* **Re-recording the live runs from the committed tree:** not done. The Wave 2 live runs were
  recorded once from the working tree that `bf71e43` commits, and the P1-P3 development runs from
  the finishing and audit steps' working trees before their commit. The clean-checkout
  regeneration only re-verifies them.
