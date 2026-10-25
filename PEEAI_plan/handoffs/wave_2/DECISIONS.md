# Wave 2 decisions

Each entry gives the decision, the reason, and where it is enforced. The authoritative runtime
semantics are in [`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md)
(runtime 1.1.0; sections 15–18 are new). The Wave 1 decisions in
[`../wave_1/DECISIONS.md`](../wave_1/DECISIONS.md) still hold; this file records what Wave 2 chose
on top of them and where it departed from [`waves/02_adaptation.md`](../../waves/02_adaptation.md).
Decisions were taken by headless workers without a human in the loop; each one names its reason.

## W2-D1. Model provider, model and spend

* **OpenRouter, OpenAI-compatible, standard library only.** `plan_b/agent/provider.py` uses
  `urllib`, so the runtime dependencies stay FastAPI, uvicorn and Pydantic. It requests strict
  structured output (`response_format` json_schema with `strict: true`, plus OpenRouter's
  `usage.include` and `provider.require_parameters`), has a bounded 90-second total timeout,
  never follows a redirect and caps a response at 2 MB. Every failure is a typed error carrying a
  call record.
* **Model `anthropic/claude-sonnet-5.5`** (the default of `PLAN_B_MODEL_ID`). On 2026-10-24 the
  OpenRouter public model list showed this id with structured-output support at 2 / 10 USD per
  million prompt / completion tokens (`PRICES_PER_MTOK`). Every recorded call returned this same
  id.
* **Spend caps.** The defaults are 0.50 USD per run, which is per episode (each policy instance has
  its own guard), and 20.00 USD cumulative over the ledger `apps/plan_b/var/model_spend.json`. The
  guard refuses a call before sending it when its upper-bound cost would exceed either cap. The
  recorded Wave 2 runs set the cumulative cap to **8.00 USD**
  (`PLAN_B_MODEL_MAX_TOTAL_COST_USD=8.00`), the limit allowed for this step. That figure includes
  the gate's earlier 0.03509 USD. Before the runs, one `GET /api/v1/key` reported limit 50,
  remaining 49.96491 and usage 0.03509, the same as the ledger.
* **The key** is read by the provider only, from the key file, on each call. It is sent only in
  the `Authorization` header. Error text is scrubbed of it, and exceptions are raised without
  their urllib context. `ModelConfig.public()` is the only configuration that leaves the process:
  it holds relative paths and no key.

## W2-D2. The model chooses among server-built options; it never builds plans

* **Closed menu** (`agent/menu.py`). The server builds every option from the visible state and
  one stored evaluation: keep; query; hold; apply with its report; ask with an
  `AuthorizationRequest`; release; wait. The model returns one `option_id`, constrained by a JSON
  schema enum. An id outside the menu is rejected on the server (`invalid_choice`). The option's
  tool, arguments and expectations come from the server, so the model cannot name an arbitrary
  endpoint, entity or plan. It applies only stored candidates, exactly like `rules/1.0.0`.
* **The model is called only when there is a real choice.** A menu holding only keep and wait is
  decided by the server, which records keep, infeasible, unresolved or wait with
  `chosen_by = "server"`. Queries are offered only for a stated reason. Apply, hold and ask are
  offered only while the plan is in question. This keeps calls few: the recorded `live/1.0.0`
  and `verify-all/1.0.0` runs used 0–6 model calls per episode (0 in the failed
  `live_pantry_dev01`).
* **Rationale is untrusted text.** It is stored as `details.choice.rationale_untrusted` and
  labelled in the browser as "untrusted model text, not evidence". Summaries are composed by the
  server from facts. Cited ids that name nothing visible are dropped.

## W2-D3. Interpretation is validated by the server

The model reads notices into planning `change_spec` records (`agent/interpret.py`). The server
then applies the same identity rules as the rule parser:

* an order reference must be the subject's `booking_ref`, and a date must be the event date;
  otherwise the notice is `inapplicable`;
* an unknown subject stays `unresolved` (`unknown_entity`);
* evidence ids that name no visible observation are dropped;
* duplicates and same-source retractions are resolved without a model call;
* hearsay follows the observation channel.

Observation text reaches the model as escaped, quoted JSON inside `<untrusted_observations>`.
This is what gives the stale P09 reminder in dev04 its distinct response in the live run. The
model read it as concerning another order and date. The server confirmed both mismatches
(P09 ≠ P17, 29 October ≠ the event date) and recorded `inapplicable`. The forwarded copy became
`duplicate`.

## W2-D4. Per-episode caps: 48 tool calls and 8 model calls, for every policy

The plan proposed 8 model calls and 16 tool calls per episode. Wave 2 uses **48 tool calls and 8
model calls**, phase `development`, for every coordinator policy (`policy_host.EpisodeCaps`).

* **Why the tool cap changed.** The runner wakes the policy on every revision change, and every
  wake costs at least a state read and an evaluation.
* **Measured usage.** The rule baselines used 19–30 tool calls per development episode. The live
  policy used 20–32 on the campus and community cases (10 in the failed `live_pantry_dev01`, 21
  in `live_p2-live_pantry_dev01`; the details are in VERIFICATION.md). A cap of 16 would stop
  dev01 before the event ends, under either policy.
* **The plan allows this.** It says to adjust the caps only on development cases and freeze them
  for Wave 3; these are development values.
* **What counts.** Failed calls, retries and receipt lookups count. A run gets at most the
  remaining budget. A reached cap is one host-recorded `stop` decision, after which the policy is
  not woken again.
* **One leftover.** `orchestrator.DEFAULT_MAX_TOOL_CALLS` is still 32 for a `LivePolicy` built
  directly. Every factory built through the host, `run_case`, the CLI and the API passes 48.
* **The development runs of P1-P3** (W2-D12) stayed within 48 tool calls (15–32 per run). The
  8 model calls were reached by P1 in three of its current runs (dev01 at 17:24, dev02 at 17:44,
  skills_dev01 at 10:06) and in three superseded ones (dev02, skills_dev01, and the first
  pantry_dev01 run at 12:35), and not by P2 or P3 in these runs. The Wave 3 freeze should weigh
  this; the values were not changed here.

## W2-D5. Policy selection and labels

* `run_case(policy=...)`, `plan-b run-case --policy`, and the moderator's per-episode choice take
  `rules` (P0), `tool-use` (P1), `live` (P2; alias `selective`, stored as `live`) and `verify-all`
  (P3). The choice locks once the coordinator has acted (`409 POLICY_LOCKED`), so policies
  never mix within an episode.
* `rules` means the profile's own deterministic baseline: `rules/1.0.0` for the event profiles
  and `pantry-rules/1.0.0` for the pantry profile. The profile selects a policy and its
  published rules, never a scripted outcome.
* Every stored decision carries `details.policy_mode.label`: "Deterministic policy", "Tool-use
  agent · <model>", "Live agent · <model>" or "Verify-all agent · <model>", with the model id as
  returned. The label therefore travels into state, traces and the board.

## W2-D6. Resource offers extend `submit_observation`

* The community fixture's kit-steward grant already allows `submit_observation`, so an offer is
  a `resource_offer` observation with a structured `offer: {available, capabilities, terms_ref}`
  rather than a new tool.
* Only the structured fields are checked, in a fixed order: owner, preconfigured option,
  capability, availability, then terms. The first failure is a durable rejected receipt.
* An accepted offer changes only the resource's visible status. It creates no hold, money,
  stock, grant or plan change.
* The offered window must reach the registered window's end, because the planner models only the
  registered window.
* An offer for later makes the resource `expected`. A status or arrival record outranks an
  owner's offer.
* No new `StatusBasis` value was added, because migration 0001's CHECK constraint would need a
  new migration. The offer uses `status_observation`.

## W2-D7. The second event configuration is configuration reuse

* `community_skills_exchange.json` (`dev_fixture_02`) derives field by field from the planning
  example and records extensions x01–x09. It loads through the unchanged campus adapter.
* **The changed constraint.** Practice depends on the demonstration and shares the single kit,
  the mentor and the one-activity room. The campus-style single swap therefore fails, and only a
  rotation recovers.
* **The cases.** `skills_dev01` makes a participant's own check-in change feasibility.
  `skills_dev02` changes the goal version while an apply is in flight.
* Both cases set `derived_from` to null, because no planning evaluator exists for this profile.
  Their predicates are state-based.

## W2-D8. Pantry: an additive runtime 1.1.0 extension on the shared core

* **Runtime fields.** All new fields are optional, and stored 1.0.0 records still parse.
* **Store.** Migration `0004_consumable_stock.sql` adds append-only stock ledgers, shipment
  reconciliation, quantity holds with `remaining_quantity`, and unique physical references. The
  money ledger is not overloaded.
* **Staff tools.** `record_stock_receipt` and `record_distribution` are mutation tools gated by
  the grant. The coordinator grant lacks them, so the executor rejects them for the agent with
  `GRANT_REQUIRED` and no adapter code is involved.
* **Departures and choices**, each recorded in the fixture or the contract:
  * **The staff principal's role is `participant`** (extension x03). The planning example says
    organizer, but staff authority is a grant, and no new role was needed.
  * **Stock is not a start condition.** Throughput accrues only while committed stock exists, so
    a session without a commitment starts and serves nobody.
  * **Allocations are capped** by what staff can distribute before the event end. On-time
    coverage is reported separately; capping by the deadline made exact-hold binding chase a
    moving target after a late start.
  * **The pantry baseline asks for each alternate pool's handoff once.**
  * **Physical references are opaque** (`handoff_001`, `distribution_001`) instead of the
    evaluator's `..._DEV03_001`, so traces carry no case label.
  * **The staff simulator is labelled, frozen, and identical for every policy.** It answers
    after the declared 2-minute latency and acts through the staff session and the executor.

## W2-D9. Evidence production

* **Live runs are recorded once**, by `scripts/run_live_cases.py`, and kept as recorded. The
  evidence collector (`scripts/collect_wave2_evidence.py`) copies them and verifies their traces
  again, but makes no model call, so regenerating the deterministic evidence costs nothing.
  Failed live runs (pantry_dev01) are kept.
* **The deterministic evidence comes from a clean checkout of the packet commit `fd04d48`.** It
  was first produced from the working tree, before the integrator's commit (no worker may
  commit). After the commits it was regenerated from a fresh worktree of `fd04d48`, as Wave 1's
  was, so `environment.json` records `app_tree_clean: true`. The regeneration made no paid call:
  the recorded live runs were copied and re-verified. The non-secret endpoint settings were
  passed as environment variables, because a clean checkout has no `.local/`.
* **The collector checks that the five Wave 1 case lines are unchanged**, against the Wave 1
  evidence's `checks.json`.
* **Each M2 check is mapped to its focused tests** in the same pytest run's JUnit report. A
  pattern that matches no test is itself a failure.
* **Credential-shaped text is scanned for by pattern**: an OpenRouter key prefix or a bearer
  token. No key is read, as the rule that only server-side code may read the key requires. The
  identifier scan of `collect_evidence.py` covers every file, the copied live runs included.
* **No Wave 2 `manifest.json`.** `scripts/write_manifest.py` computes the Wave 1 M1 status, and
  it was not adapted. `reports/checks.json` and VERIFICATION.md carry the record instead.

## W2-D10. P1 and P3, built on the shared harness

* **P1 (`tool-use/1.0.0`) calls tools itself**, with no menu. Each turn is strict JSON: up to 3
  calls (a tool from the grant's `allowed_tools`, its arguments as a JSON object encoded in a
  string, which stays portable under strict mode), `done`, a decision and an optional ask; at most
  6 turns per run. Every call goes through the same `ToolClient` and executor as P0 and P2.
* **Harness choices that make P1 a serious baseline**, recorded in `agent/policies/tool_use.py`:
  * each turn sees the planner's current evaluation, read whenever the revision moved, as P2 has
    before each choice, so seeing candidates costs no model call;
  * the attention rule skips a model call when nothing material changed (plan, goal,
    observations, grants, holds, commitments, stock, staff tasks, failed activities);
  * a `done` turn whose calls brought unseen news (a new status observation or rejection) goes
    on to the next turn;
  * an `ask` is built and checked by the server exactly as P2's menu checks it;
  * an `infeasible` end on a partial stock plan carries the blocking constraints and shortfalls.
* **P3 (`verify-all/1.0.0`) subclasses P2** and changes one thing: before each decision step the
  server makes every due relevant status check, with no model call, under the relevance rule
  `verify-all-relevance/1.0.0` written in the module docstring before any P3 run. The audit
  amended its text (latest notice per resource, notices arriving during the checks, the retry
  bound across runs) before any run and kept the id. P3's checks cost no model call, so its
  model-call counts and P2's measure different things.
* **P2 is `live/1.0.0` itself.** `agent/policies/selective.py` re-exports it, closing the
  departure noted in the first version of this packet.
* **Pantry parity.** P2 and P3 now offer the pantry adapter's own stock candidates (a staff
  handoff request, quantity holds and stock applies; contract section 16) and record the
  shortfall and release closed handoff holds server-side, as P0 does. P1 gets the same
  candidates through `evaluate_candidates` and the same tools.

## W2-D11. P1's prompt v2 and turn budget, after its first live pantry run

* **What happened.** The first P1 development run of pantry_dev01 (`live_p1-tool-use_pantry_dev01`,
  prompt `tool_use.v1`) sent six staff-handoff holds that the executor refused. First it added a
  service target to the transfer hold, then it used the 12:30–12:50 handoff window as the hold
  window, then it sent arguments without an activity. Two of its replies were cut off at the
  1536-token turn limit, and it reached the 8-call cap at 12:35 with 0 of 40 kits served.
* **Why it is our defect, not the model's judgment.** `tool_use.v1` never said what a hold's
  window is (the activity's window in the candidate held for). It described only the handoff
  window, and the scripted test model encoded the right window without the prompt saying so. The
  turn limit also counts the model's reasoning tokens, which reached 1134 in that run.
* **The fix.** A new prompt `tool_use.v2` documents the hold window and how a `stock_transfer`
  hold follows a candidate's `stock_transfers` entry, with no service target. The turn limit is
  now 4096 tokens. `tool_use.v1` stays in `agent/prompts/` because the P1 runs recorded under it
  (all five now superseded) cite its sha256. `tests/test_tool_use_hold_window.py` checks the prompt against the real
  executor (the v1 run's requests are refused, the documented hold is accepted) and the
  request settings of a scripted P1 run.
* **The rerun.** P1 ran pantry_dev01 again under v2 (`live_p1-tool-use_pantry_dev01_r2`). The
  first run is kept and marked superseded. The other four P1 runs were not repeated at first:
  they completed, and no cut-off or window error occurred in them.
* **The other four, rerun (audit step, 2026-10-25).** They no longer reflected the shipped P1
  (prompt and turn budget), so dev01, dev02, dev04 and skills_dev01 ran once more under
  `tool_use.v2` and 4096 tokens (`live_p1-tool-use_<case>_r2`, at most 1.50 USD, through the
  ledger). All four matched expectation; they cost 0.91328 USD over 30 calls. The `tool_use.v1`
  runs are kept as recorded and marked superseded by the prompt change, not by their outcome.
  Every current P1 run now uses the shipped prompt.

## W2-D12. Development runs of P1-P3

* **One live trial each** of P1, P2 and P3 on dev01, dev02, dev04, pantry_dev01 and skills_dev01,
  by `scripts/run_live_cases.py --policy`, under the development caps. P0 was already recorded
  deterministically and was not re-run. The runs are development evidence, never the held-out
  evaluation, and no comparison between policies is drawn from them.
* **Names carry the policy.** Without `--policy` the script keeps the Wave 2 names
  (`live_<case>`). With it, the files are `live_p1-tool-use_<case>`, `live_p2-live_<case>` and
  `live_p3-verify-all_<case>`, and a rerun takes `--label` (`..._r2`). The collector copies every
  `live_*` file and summarizes the runs per policy (`checks.json`: `live_runs`,
  `live_runs_by_policy`).
* **Results.** `plan_b/evaluation/development/` holds one JSON (`development_runs.json`, an entry
  per run) and one markdown table (`README.md`, a row per run), not a file per run. Each row has
  one sentence of what happened. The sentence is written by hand from that run's trace
  (`run_notes.json`), never from the model's rationale. P0's lines for the same cases are listed
  for reference only.
* **Spend.** This step's limit was 5 USD, enforced by the ledger's cumulative cap:
  `PLAN_B_MODEL_MAX_TOTAL_COST_USD=5.29` over a ledger that started at 0.29906 USD. One
  `GET /api/v1/key` was made first (limit 50, remaining 49.70094, usage 0.29906, equal to the
  ledger).
* **The M2 record follows the runs.** "Future comparison parity" is now passed: the parity tests
  hold, P1-P3 ran end to end with the real model through the same harness with recorded prompts,
  and P2 and P3 completed the pantry sequence. The live pantry result is the P2 run
  `live_p2-live_pantry_dev01`; the failed Wave 2 run `live_pantry_dev01` is kept as recorded.

