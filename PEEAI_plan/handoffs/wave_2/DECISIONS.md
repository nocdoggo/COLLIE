# Wave 2 decisions

Each entry gives the decision, the reason, and where it is enforced. The authoritative runtime
semantics are in [`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md)
(runtime 1.1.0; sections 15–17 are new). The Wave 1 decisions in
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
  offered only while the plan is in question. This keeps calls few: the recorded runs used 2–6
  model calls per episode.
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
  policy used 20–32 (the details are in VERIFICATION.md). A cap of 16 would stop dev01 before the
  event ends, under either policy.
* **The plan allows this.** It says to adjust the caps only on development cases and freeze them
  for Wave 3; these are development values.
* **What counts.** Failed calls, retries and receipt lookups count. A run gets at most the
  remaining budget. A reached cap is one host-recorded `stop` decision, after which the policy is
  not woken again.
* **One leftover.** `orchestrator.DEFAULT_MAX_TOOL_CALLS` is still 32 for a `LivePolicy` built
  directly. Every factory built through the host, `run_case`, the CLI and the API passes 48.

## W2-D5. Policy selection and labels

* `run_case(policy="rules"|"live")`, `plan-b run-case --policy`, and the moderator's per-episode
  choice. The choice locks once the coordinator has acted (`409 POLICY_LOCKED`), so policies
  never mix within an episode.
* `rules` means the profile's own deterministic baseline: `rules/1.0.0` for the event profiles
  and `pantry-rules/1.0.0` for the pantry profile. The profile selects a policy and its
  published rules, never a scripted outcome.
* Every stored decision carries `details.policy_mode.label`: "Deterministic policy" or "Live
  agent · <model id as returned>". The label therefore travels into state, traces and the board.

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
* **The deterministic evidence was regenerated from the working tree**, before the integrator's
  commit, so `environment.json` records `app_tree_clean: false`. Wave 1's evidence came from a
  clean checkout of a commit. That was not possible here, because no worker may commit. The
  integrator's commit should be compared with this tree. A clean-checkout regeneration needs no
  paid call.
* **The collector checks that the five Wave 1 case lines are unchanged**, against the Wave 1
  evidence's `checks.json`.
* **Each M2 check is mapped to its focused tests** in the same pytest run's JUnit report. A
  pattern that matches no test is itself a failure.
* **Credential-shaped text is scanned for by pattern**: an OpenRouter key prefix or a bearer
  token. No key is read, as the rule that only server-side code may read the key requires. The
  identifier scan of `collect_evidence.py` covers every file, the copied live runs included.
* **No Wave 2 `manifest.json`.** `scripts/write_manifest.py` computes the Wave 1 M1 status, and
  it was not adapted. `reports/checks.json` and VERIFICATION.md carry the record instead.
