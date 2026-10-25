# Plan B runtime contract 1.1.0 (Waves 1 and 2; Wave 3 calibration and freeze)

This is the interface of the Plan B sandbox: the Wave 1 deterministic campus core (contract
1.0.0) and its additive Wave 2 extensions (contract 1.1.0). Wave 2 adds consumable stock and
staff-only attestations for the pantry profile (sections 4, 15), resource offers (section 9), a
second event configuration (section 1), the live coordinator policy P2 with its pantry stock
options (section 16), per-episode caps and policy selection for every coordinator policy
(section 17), and the comparison policies P1 and P3 with the development runs (section 18). Wave
3 calibrates the policies before the comparison (section 19) and freezes it (section 20). The
Pydantic models
in [`plan_b/domain/models.py`](../plan_b/domain/models.py) are the machine-readable form; this
document gives their semantics. Where they disagree, fix the disagreement rather than choosing one.

Everything here is a **fictional local sandbox**. A hold, booking, check-in, or plan change is a
real mutation of the local SQLite store and nothing else. No university booking, purchase,
delivery, or message is made.

## 1. Versions and relationship to the planning bundle

| Contract | Version | Where |
| --- | --- | --- |
| Planning artifacts | 0.2.0 | `PEEAI_plan/schemas/planning.schema.json` (unchanged by Waves 1 and 2) |
| Runtime contract | 1.1.0 | `models.RUNTIME_VERSION`, this file. Stored records keep the version they were written with: `PublicScenario`, `PrivateCase`, `ActionReceipt`, `ToolEnvelope` and `EventStateView` accept `1.0.0` and `1.1.0` (`models.RuntimeVersion`), and the campus fixtures remain 1.0.0 documents |
| Trace format | 1.0.0 | `models.TRACE_VERSION`, section 13 (unchanged in Wave 2) |
| Store schema | migrations `0001_initial.sql`, `0002_scheduled_actions.sql`, `0003_history_guards.sql`, `0004_consumable_stock.sql` (Wave 2) | `plan_b/store/migrations/` |
| Model policy prompts | P2 and P3: `interpret.v1`, `choose_action.v1`, and `choose_action_pantry.v1` on consumable profiles; P1: `tool_use.v2` (`tool_use.v1` is kept because the first recorded P1 development runs cite it) | `plan_b/agent/prompts/`; every model-driven decision records each prompt's sha256 (sections 16 and 18) |

Planning objects set `additionalProperties: false`, so runtime records never add fields to them.
Each runtime record *contains* the planning fields unchanged and adds runtime fields beside them.
`plan_b/domain/planning_map.py` projects runtime candidates, constraint reports, receipts and
observations back to planning 0.2.0 artifacts; tests validate those projections against the
planning schema. Mapping rules:

| Planning artifact | Runtime model | Mapping |
| --- | --- | --- |
| `public_scenario` | `PublicScenario` | Same goal, activities, resources, assignments, observations, grants, assumptions. Resource `booking_cost_cents` → `terms.commitment_cost_cents`. Activity `started` → `initial_state.lifecycle`. `checked_in_roles` → `initial_state.checked_in`. Extensions listed in `fixture_extensions`. |
| `private_evaluator` | `PrivateCase` | `tool_response_available` events → `status_model`; `resource_arrival` → `world_events`; `outcome_checks` prose → typed `outcome_predicates`. |
| `observation_record` | `ObservationRecord` | `observation` is the planning Observation; runtime adds `channel`, `submitted_by`, `revision_after`, `structured`. |
| `change_spec` | policy `Interpretation` (decision `details`) | Same change vocabulary plus `inapplicable`/`duplicate` evidence states. |
| `candidate_plan` | `CandidateResult` | `plan_id`=`candidate_id`, `constraint_report_ref`=`report_id`, `required_hold_ids` = bound hold ids. |
| `constraint_report` | `CandidateResult.checks` etc. | `passed` = (`status == "passed"`); `not_applicable` checks are omitted from the planning projection (never emitted as a successful placeholder); `unsupported` → `passed: false`. |
| `mutation_request` | `ToolRequest` | Same field names minus `artifact_type`/`schema_version`. |
| `action_receipt` | `ActionReceipt` | Same fields; runtime adds `episode_id`, `grant_version`, `actor_role`, `requested_at`, `error_message`, `summary`. |

**Runtime 1.1.0 additions** are optional fields with defaults, so 1.0.0 documents still validate
(`test_pantry_fixture.py::test_runtime_1_0_0_records_still_parse` parses a Wave 1 trace's
records): `EventGoal.service_targets`, `ResourceDef.consumable_stock` and
`ResourceView.consumable_stock`, `Assignment.consumable_allocations`,
`InitialState.service_progress` and `.expected_shipments`, `PublicScenario.pantry_parameters` and
`.stock_options`, the consumable fields of `HoldView`, `CandidateResult.required_stock_holds`,
`.stock_transfers` and `.service_coverage`, `EventStateView.stock`, `.pantry_parameters` and
`.stock_options`, the `OutcomeReport` service, stock and policy fields, the staff rule actor
scripts, `SubmitObservationArgs.offer` and the `organizer_goal_update` actor script. New JSON keys
with defaults therefore appear in campus snapshots and traces; outcomes, request bodies,
idempotency keys and digests are unchanged. `planning_map.py` does not yet project the pantry
fields to planning artifacts.

### Public fixtures

| `scenario_id` | File | Profile | Adapter |
| --- | --- | --- | --- |
| `dev_fixture_01` | `scenarios/public/campus_showcase.json` | `campus_showcase` | `campus/1.0.0` |
| `dev_fixture_02` | `scenarios/public/community_skills_exchange.json` | `community_skills_exchange` | `campus/1.0.0` (the same adapter; configuration reuse) |
| `dev_fixture_03` | `scenarios/public/pantry_continuity.json` | `pantry_continuity` | `pantry/1.0.0` (section 10) |

`dev_fixture_02` derives field by field from
`PEEAI_plan/examples/community_skills_exchange.public.json`, with extensions x01-x09 listed in its
`fixture_extensions`. Compared with the campus showcase, guided practice depends on the
demonstration and shares the single learning kit, the mentor and the one-activity room, so a
single swap with the flexible activity does not recover from a late kit; only the swap of
skills_demo and peer_exchange combined with the +20 minute practice shift does. The coordinator
may reserve 4000 cents but commit none. `dev_fixture_03` derives from
`PEEAI_plan/examples/pantry_continuity.public.json` (its `derived_from` pins the sha256), with
extensions x01-x10; the one departure is x03: the staff principal's role is `participant`, not
`organizer` (section 2). These are development fixtures: fictional and synthetic, not community
validation.

## 2. Identity, sessions and authority

Identity comes only from a server-validated session. A request body never establishes actor,
role, grant or source: `ToolRequest` has no such fields and unknown fields are rejected.

* **Bearer tokens.** `Authorization: Bearer <token>`. Tokens are 32 random bytes (urlsafe); the
  store keeps only their SHA-256. Sessions bind `(episode_id, principal_id, role, grant_id)`.
* **Moderator.** The sandbox operator signs in with the moderator code (environment
  `PLAN_B_MODERATOR_CODE`, or generated at startup and written to `var/moderator_code.txt`,
  mode 0600). The moderator session is not an event principal: it can load/reset episodes,
  advance the clock, choose and run the coordinator policy (section 17), issue join codes and
  export traces. It cannot call event tools.
* **Join codes.** The moderator issues a one-time join code (10 wall-clock minutes) for one
  principal of the current episode; a code from an episode that was reset answers
  `EPISODE_CLOSED`. A browser tab exchanges it at `POST /api/auth/join` for that
  principal's session. Each tab keeps its token in `sessionStorage`, so a role switch is an
  explicit, distinct session. The browser bundle contains no credentials.
* **Coordinator agent.** Its session is created server-side by the policy host and is never
  sent to a browser.
* **Episode binding.** Reset closes the episode and revokes its sessions. A closed episode's
  token gets `EPISODE_CLOSED` (HTTP 401); it cannot reach the new episode, and no new session is
  issued for a closed episode.
* **Grant checks** (in this order): session valid → request `event_id` equals the episode's
  event (`EVENT_MISMATCH`) → `grant_id`, if supplied, equals the session's grant
  (`GRANT_MISMATCH`) → tool in `allowed_tools` (`GRANT_REQUIRED`) → grant not revoked
  (`GRANT_REVOKED`) → scenario clock `< expires_at` (`GRANT_EXPIRED`) → resource/activity scope
  (`SCOPE_VIOLATION`) → monetary limits (`BUDGET_EXCEEDED`).
* **Review authority.** An organizer may read any receipt in its event (`get_action_receipt`
  with `actor_id`). Every other caller reads only its own receipts. Reading one's **own**
  receipts stays possible after the caller's grant is revoked or has expired, so a lost response
  can always be reconciled; reading another actor's receipts needs a valid grant.
* **Participant scope.** `check_in` only for a resource in the participant's
  `grant.resource_ids` (its own role). Message content is data: text that claims organizer
  status or asks to ignore the budget changes nothing.

### Demo principals (fixture `dev_fixture_01`)

| Principal | Role | Grant | Can |
| --- | --- | --- | --- |
| `agent_demo` | coordinator_agent | `grant_coordinator_demo` | read, query, evaluate, hold/release, apply; committed limit 0, reserved limit 3500 |
| `organizer_demo` | organizer | `grant_organizer_demo` | read any receipt, evaluate, submit observations, `update_goal`, `update_grant` (bounded by the 15000 budget) |
| `participant_facilitator` | participant | `grant_facilitator_self` | own check-in, observations |
| `participant_presenter` | participant | `grant_presenter_self` | own check-in, observations |
| `participant_host` | participant | `grant_host_self` | own check-in, observations |

### Demo principals (fixture `dev_fixture_02`)

| Principal | Role | Grant | Can |
| --- | --- | --- | --- |
| `agent_demo` | coordinator_agent | `grant_community_agent` | read, query, evaluate, hold/release, apply; committed limit 0, reserved limit 4000 |
| `organizer_demo` | organizer | `grant_organizer_demo` | read any receipt, evaluate, submit observations, `update_goal`, `update_grant` (bounded by the 8000 budget) |
| `participant_host` | participant | `grant_host_self` | own check-in, observations |
| `participant_mentor` | participant | `grant_mentor_self` | own check-in, observations |
| `participant_peer_lead` | participant | `grant_peer_self` | own check-in, observations |
| `participant_kit_steward` | participant | `grant_kit_offer` | observations and resource offers for `backup_learning_kit` only; no check-in, hold or allocation |

### Demo principals (fixture `dev_fixture_03`)

| Principal | Role | Grant | Can |
| --- | --- | --- | --- |
| `agent_demo` | coordinator_agent | `grant_pantry_agent` | read, query, evaluate, hold/release quantities, apply; no money; no staff tools |
| `fictional_staff` | participant | `grant_pantry_staff` | the planning grant's tools, including the staff-only `record_stock_receipt` and `record_distribution` |
| `fictional_partner_steward` | participant | `grant_partner_steward` | read, observations about `partner_stock` |

**Staff authority is a grant, not a role.** The executor refuses the two staff tools to any
session whose grant does not list them (`GRANT_REQUIRED`, an attempt without a receipt), so the
coordinator, whose grant lacks them, can never attest a physical receipt or a distribution. The
browser derives a staff session from its grant (`allowed_tools` includes a staff tool), not from a
role; the session's role stays `participant`.

## 3. HTTP API

All responses are JSON. Tool calls always return a `ToolEnvelope` body; the HTTP status is
200 for any envelope produced after authentication (including business rejections), 401 for a
missing/invalid/closed session, 403 when a moderator session calls an event tool, and 400 for
a body that fails `ToolRequest` or argument validation. Other endpoints return FastAPI errors
`{detail: {code, message}}`: 401 (no or bad session), 403 (not a moderator), 400 (bad input the
handler detects, e.g. `UNKNOWN_ENTITY`, `SCENARIO_MISMATCH`, `MODEL_NOT_CONFIGURED`), 404 (unknown
replay), 409 `NO_EPISODE` (moderator state read before any episode is loaded). A request body
that fails validation gets FastAPI's 422, whose `detail` is a list, not `{code, message}`.

| Method and path | Auth | Request → response |
| --- | --- | --- |
| `GET /api/health` | none | → `{ok, runtime_version, mode}` (`runtime_version` is `1.1.0`) |
| `POST /api/auth/moderator` | none | `{code}` → `{token, role, principal_id, display_name}` |
| `POST /api/auth/join` | none | `{code}` → `{token, role, principal_id, display_name, episode_id, event_id, grant_id}` |
| `GET /api/auth/whoami` | any | → `{role, principal_id, display_name, episode_id, grant_id}` plus `{event_id, episode_status}` for event sessions |
| `GET /api/state` | any session | → `EventStateView` for the caller (moderator: organizer-level visibility of the current episode) |
| `POST /api/tools/{tool}` | event session | `ToolRequest` → `ToolEnvelope` |
| `GET /api/moderator/cases` | moderator | → `[{case_ref, scenario_id, profile_id}]` (public ids only; no private descriptions) |
| `POST /api/moderator/episodes` | moderator | `{case_ref, scenario_id?, policy?}` → `{episode_id, event_id, scenario_id, clock, revision, policy, mode_label}`; `scenario_id` defaults to the case's own (another one is 400 `SCENARIO_MISMATCH`); `policy` is a `PolicyChoice` (section 17): `rules` (default; the profile's deterministic baseline), `tool-use`, `live` (alias `selective`, returned as `live`) or `verify-all`; a model-driven choice is refused with 400 `MODEL_NOT_CONFIGURED`, checked before anything is reset, when the endpoint configuration is missing or invalid or its key file is absent; loads a clean episode and closes every other active episode (reset) |
| `GET /api/moderator/current` | moderator | → `{episode_id}` (null before the first load) |
| `POST /api/moderator/sessions` | moderator | `{principal_id}` → `{join_code, join_path, principal_id, role, display_name}`; refuses `coordinator_agent`; codes are one-time and expire after 10 wall-clock minutes |
| `POST /api/moderator/clock` | moderator | `{advance_minutes: 1..240}` → `{clock, revision, transitions}` |
| `GET /api/moderator/policy` | moderator | → `{episode_id, policy, policy_id, label, requested_model, returned_model_id, model_id, live_available, reason, caps, locked}`; no key or local path |
| `POST /api/moderator/policy` | moderator | `{policy}` → the same view; only before the episode's coordinator first acts (409 `POLICY_LOCKED`); a live choice reads the endpoint configuration and calls no model (400 `MODEL_NOT_CONFIGURED` when it is missing) |
| `GET /api/policy` | any session | → `{episode_id, policy, policy_id, label, caps}` of the caller's episode |
| `GET /api/participation/me` | event session | → the caller's principal, own grant, the resources it speaks for (check-in, or the registered facts an offer must confirm), organizer goal controls and staff tools; contributions themselves use `POST /api/tools/{tool}` (403 for a moderator session) |
| `POST /api/moderator/policy/run` | moderator | `{max_tool_calls?: 1..64}` → `PolicyRunResult` plus `episode_id`, `episode_status`, `mode_label` |
| `POST /api/moderator/run` | moderator | `{minutes: 1..240, policy: bool}` → `{clock, revision, policy_runs, mode_label}`; advances minute by minute, running the selected policy when public state changed (no scripted actors) |
| `POST /api/moderator/export` | moderator | → `{name, trace}`; also writes `var/traces/<name>` |
| `GET /api/replays` | none | → `[{name}]` of sanitized traces available for replay |
| `GET /api/replays/{name}` | none | → one sanitized trace, byte-exact (read-only; replay never calls tools) |

The production server also serves the built browser app (`web/dist`) at `/`.

## 4. Tool requests and envelopes

`ToolRequest = {tool, event_id, grant_id?, idempotency_key?, expected_revision?,
expected_goal_version?, arguments}`. Argument models: `TOOL_ARGUMENT_MODELS`. Required envelope
fields per tool: `TOOL_REQUIREMENTS` ("optional" fields are enforced when supplied).

`ToolEnvelope.status` is the transport/read vocabulary:

| Status | Meaning |
| --- | --- |
| `succeeded` | Operation completed; any receipt is durable |
| `rejected` | A known precondition or authorization failed (`error` set; mutations also return a durable `rejected` receipt once past authentication and idempotency) |
| `unknown` | The requested fact could not be established (e.g. no status record yet) |
| `unavailable` | The tool's service could not answer (e.g. supplier status service down) |

`ActionReceipt.status` is separate: `applied`, `rejected`, `unknown`. A succeeded status query
can report an unavailable *resource*; an `unavailable` envelope is a service outage, never an
all-clear. `replayed_receipt: true` marks an identical retry returning the original receipt.

### Tool surface and modeled durations

| Tool | Kind | Duration (min) | Effect |
| --- | --- | --- | --- |
| `get_event_state` | read | 0 | Role-filtered `EventStateView` |
| `get_action_receipt` | read | 0 | `{lookup_status: found|not_found|pending, receipt?}` scoped to (episode, actor) |
| `list_resources` | read | 0 | Resources with terms, status, occupancy; optional capability/window filter |
| `query_status` | read + evidence | 2 | Scoped status from the registered source; may append one observation |
| `evaluate_candidates` | read + record | 0 | Pure evaluation, stored as an immutable evaluation and candidates |
| `hold_resource` | mutation | 1 | Provisional hold: capacity + reserved exposure; on a consumable pool, a quantity reservation (section 15) |
| `release_hold` | mutation | 1 | Releases an active hold, returns its reserved exposure once |
| `apply_plan` | mutation | 1 | Revalidates a stored candidate and replaces the active plan; converts the candidate's bound stock holds into allocations |
| `check_in` | mutation | 0 | Participant's own presence and availability interval |
| `submit_observation` | mutation | 0 | Append an immutable observation; content is data; a structured resource offer may activate a preconfigured resource (section 9) |
| `record_stock_receipt` | staff mutation | 0 | Staff-attested receipt: an internal handoff from a held alternate pool, or a matched external shipment (section 15) |
| `record_distribution` | staff mutation | 0 | Staff-attested aggregate distribution consuming committed stock (section 15) |
| `update_goal` | organizer control | 0 | New goal version (preference preset) |
| `update_grant` | organizer control | 0 | New version of another principal's grant (limits, revoke) |

`TOOL_REQUIREMENTS` (runtime 1.1.0): `record_stock_receipt` needs `idempotency_key` and
`expected_revision`; `record_distribution` also `expected_goal_version`. `hold_resource` gains
optional `purpose` (`activity` | `stock_transfer`), `destination_resource_id` (exactly for
`stock_transfer`) and `service_target_id`. They are serialized only when set, so a reusable
resource's hold body, and therefore its digest and idempotency key, is byte-identical to 1.0.0.
`quantity` is a strict integer >= 1.

Durations are read from `scenario.tool_durations_minutes`. A tool's duration is modeled
latency **before** its effect: the executor advances the scenario clock by the duration
(processing every intermediate event, section 6), then validates and applies at the new time.
Requests rejected during authentication, validation, idempotency, static prechecks or the grant
check at arrival (revoked or expired) consume no time: a principal without authority cannot move
the shared clock. Reads with duration 0 never move the clock.

Request-argument times (hold windows, check-in availability, `observed_at`, hypothesis times,
resource filters) must be whole minutes between the years 2000 and 2100; anything else is
`INVALID_REQUEST` (400). An
unexpected server error inside a call rolls back everything the call did (SQLite savepoint) and
is recorded as an `INTERNAL_ERROR` attempt (HTTP 500 with an envelope). The envelope is
authoritative that none of the call's effects were kept; a client that only sees a 5xx without a
readable envelope treats the outcome as unknown and reconciles with the original key.

### `data` payloads (on `succeeded`; on `rejected`, `data` is null and `error` explains)

| Tool | `data` |
| --- | --- |
| `get_event_state` | `EventStateView` (includes `status_checks`: every `query_status` call with its envelope outcome, so unknown and unavailable answers are visible, and `status_sources`) |
| `get_action_receipt` | `{lookup_status, receipt: ActionReceipt or null}` |
| `list_resources` | `{resources: [ResourceView]}` |
| `query_status` | `{entity_id, fact, observation: ObservationRecord, deduplicated: bool, freshness: {observed_at, retrieved_at, age_minutes, stale}}`; on `unknown`/`unavailable`: `{entity_id, fact, reason}` |
| `evaluate_candidates` | `EvaluationResult` |
| `hold_resource` | `{hold: HoldView}` |
| `release_hold` | `{hold: HoldView}` |
| `apply_plan` | `{plan: PlanView, converted_hold_ids: [...], commitment_ids: [...]}`, plus `allocation_ids` when it commits stock holds |
| `check_in` | `{checkin: CheckInView, observation: ObservationRecord}` |
| `submit_observation` | `{observation: ObservationRecord, deduplicated: bool}`; with an `offer`, also `activation: {resource_id, activated, status, reported_eta, approved_for}` |
| `record_stock_receipt` | `{stock_receipt, hold_status?}` |
| `record_distribution` | `{distribution}` |
| `update_goal` | `{goal: EventGoal}` |
| `update_grant` | `{grant: GrantView}` |

A replayed identical request returns `data` reconstructed from the stored receipt only:
`{replayed: true}` plus the receipt.

`get_action_receipt` vocabulary: `found` (durable receipt), `not_found`. `pending` is reserved:
in this single-process store, a request's idempotency record and receipt commit in the same
transaction, so a lookup never observes a half-finished request. Neither `pending`,
`not_found`, nor a timeout authorizes a fresh idempotency key: the caller retries the original
key, and transaction-level deduplication resolves races.

## 5. Mutation transaction, idempotency and digest

Every mutation runs in one `BEGIN IMMEDIATE` SQLite transaction (write lock taken before any
read, so two writers cannot both read the same capacity):

```text
BEGIN IMMEDIATE
  resolve session -> actor, role, grant, episode; check event_id and tool authorization
  look up idempotency (episode, actor, key)
    identical digest  -> return the stored receipt (replayed_receipt=true), no time consumed
    different digest  -> reject IDEMPOTENCY_CONFLICT (no receipt; attempt logged), no time
  static prechecks; grant revoked or expired at arrival -> rejected receipt, no time consumed
  advance the clock by the tool duration, processing events (including scheduled actor actions)
  SAVEPOINT handler_<call_id>
    re-check grant validity at the new time
    validate expected_revision, expected_goal_version, grant validity/scope/limits, expiry,
      resource terms, budget and domain constraints at the new time, and apply effects
  on failure: ROLLBACK TO the handler savepoint (every handler write), then store a rejected
    receipt + idempotency record; operational state unchanged
  on success: apply state, ledger, revision+1, transition, snapshot, receipt, idempotency
COMMIT
```

* **Digest.** `sha256(canonical_json(ToolRequest.model_dump(mode="json")))`, canonical JSON =
  sorted keys, `(",", ":")` separators, UTF-8, non-ASCII preserved (`domain/digest.py`). The
  same convention reproduces the planning example digest `eb37a604…a123`.
* **Identical retry first.** The stored receipt is returned before the now-stale
  `expected_revision` is checked, so a lost response after a successful commit is reconciled
  rather than mistaken for a stale request.
* **Rejected receipts** have no state changes and zero deltas, and do not advance the revision.
  An identical retry of a rejected request returns the same rejection.
* **Handler rollback.** The execution-time grant check and the handler run inside their own
  savepoint. A domain rejection raised at any point rolls back every row the handler wrote: a
  plan version, `plan_version`, holds, commitments, ledger rows and id counters. This holds even
  when the rejection comes after the handler has written. The rejected receipt, idempotency
  record and call log are written after the rollback. The tool duration's clock advance (with
  the events it processed) and the allocated call and receipt ids lie outside the savepoint, so
  they are kept. An unexpected error still rolls back the whole call as `INTERNAL_ERROR`.
* **Attempts without receipts** are failures after the session is resolved but before a receipt
  exists. They are recorded in `tool_calls` and surface as `EventStateView.attempts`. The log
  stores the validated request; for a body that failed validation it stores field names only,
  never values. The failures are:
  * episode closed, validation, unknown tool, event or grant mismatch;
  * a tool outside the grant, and an idempotency conflict;
  * any rejection of a tool that has no receipts (the read tools).
* **Not persisted.** Authentication failures (missing, unknown, revoked or expired token) and
  tool calls made with a moderator session. No actor and episode are resolved for them.

**Failure vocabulary** (`models.ErrorCode`). "Receipt tools" are `hold_resource`, `release_hold`,
`apply_plan`, `check_in`, `submit_observation`, `update_goal`, `update_grant`,
`record_stock_receipt` and `record_distribution`. The other tools are reads.

| Code | Raised for | Recorded as | HTTP |
| --- | --- | --- | --- |
| `AUTH_REQUIRED`, `SESSION_INVALID` | missing, unknown, revoked or expired token (also an unusable join code) | not persisted | 401 |
| `GRANT_REQUIRED` (moderator session) | a moderator session calling an event tool | not persisted | 403 |
| `EPISODE_CLOSED` | a session of an episode closed by reset | attempt | 401 |
| `INVALID_REQUEST` (request shape) | body fails validation, the body's tool differs from the endpoint, a required field is missing | attempt | 400 |
| `UNKNOWN_TOOL`, `EVENT_MISMATCH`, `GRANT_MISMATCH` | unknown tool name; another event's id; a `grant_id` that is not the session's | attempt | 200 |
| `GRANT_REQUIRED` | the session has no grant, its grant is gone, or the tool is not in `allowed_tools` | attempt | 200 |
| `IDEMPOTENCY_CONFLICT` | the same key with a different request body | attempt | 200 |
| `SCOPE_VIOLATION`, `STATUS_SOURCE_NOT_REGISTERED` (precheck) | `query_status` outside the grant's scope or without a registered source | attempt | 200 |
| `GRANT_REVOKED`, `GRANT_EXPIRED` | the grant is revoked or expired at arrival, or at execution after the tool duration | rejected receipt (receipt tools) or attempt (reads) | 200 |
| `REVISION_CONFLICT`, `GOAL_VERSION_CONFLICT` | a stale `expected_revision` or `expected_goal_version` | rejected receipt (receipt tools) or attempt (`evaluate_candidates`) | 200 |
| `SCOPE_VIOLATION` (handler) | a resource, activity, receipt or grant outside the caller's scope | rejected receipt (receipt tools) or attempt (`get_action_receipt`) | 200 |
| `REVIEW_REQUIRED`, `BUDGET_EXCEEDED` | an apply or hold beyond the grant's authority, limits or the event budget | rejected receipt | 200 |
| `UNKNOWN_ENTITY`, `INVALID_REQUEST` (domain) | an unregistered resource, activity, hold, grant or evidence target; a domain-invalid argument | rejected receipt (receipt tools) or attempt (reads) | 200 |
| `HOLD_NOT_SUPPORTED`, `HOLD_NOT_ACTIVE`, `HOLD_CONVERTED`, `HOLD_EXPIRED` | hold terms missing; releasing a terminal or converted hold; a candidate's bound hold expired | rejected receipt | 200 |
| `RESOURCE_CONFLICT`, `RESOURCE_UNAVAILABLE`, `COMMITMENT_CUTOFF_PASSED`, `CONSTRAINT_VIOLATION` | hold checks (section 8); a candidate that fails a hard check at apply | rejected receipt | 200 |
| `CANDIDATE_NOT_FOUND`, `CANDIDATE_STALE`, `CANDIDATE_REPORT_MISMATCH`, `CANDIDATE_HYPOTHETICAL`, `CANDIDATE_NOT_APPLICABLE` | `apply_plan` revalidation (section 10) | rejected receipt | 200 |
| `UNSUPPORTED_ACTION` | applying a candidate that keeps the plan; releasing a hold whose terms are not refundable | rejected receipt | 200 |
| `DUPLICATE_CHECK_IN` | a check-in repeating the caller's latest one with the same availability | rejected receipt | 200 |
| `INVALID_EVIDENCE_REFERENCE` | `supersedes` names an observation that does not exist; a source record id reused for different text | rejected receipt | 200 |
| `STATUS_UNKNOWN`, `STATUS_UNAVAILABLE` | `query_status` without an answer (envelope `unknown` / `unavailable`); `STATUS_UNAVAILABLE` also for a hold whose steward cannot be reached | attempt (query) or rejected receipt (hold) | 200 |
| `DUPLICATE_REFERENCE` | a physical `receipt_reference` or `distribution_reference` already recorded in the episode, whatever the request key | rejected receipt | 200 |
| `INSUFFICIENT_STOCK` | a quantity beyond the globally available stock, a hold's remainder, or the committed stock | rejected receipt | 200 |
| `UNIT_MISMATCH` | a quantity in another unit than the pool's | rejected receipt | 200 |
| `THROUGHPUT_EXCEEDED` | a distribution beyond the accrued staffed capacity | rejected receipt | 200 |
| `HANDOFF_WINDOW_CLOSED` | a handoff or transfer hold outside the handoff window, including when the staff latency cannot complete before its exclusive end | rejected receipt | 200 |
| `INTERNAL_ERROR` | an unexpected server error; every effect of the call is rolled back | attempt | 500 |
| `EVENT_CLOSED` | reserved; not raised in Wave 1 (a call after the hard end fails `GRANT_EXPIRED`) | — | — |

## 6. Clock, revisions and event ordering

One server-owned scenario clock per episode (`episodes.clock`, UTC, whole minutes). It moves
only through the moderator clock control, the runner, and tool durations. Browser time is never
consulted.

**Advancing** from `t0` to `t1` repeatedly takes the earliest pending event time in `(t0, t1]`,
sets the clock there, and processes every event at that instant in this fixed order:

1. **Activity completions** (`end == t`). The 18:00 deadline is inclusive: closing ending at
   18:00 completes.
2. **World events** due at `t` (arrivals, message deliveries), in fixture order; then
   **scheduled actor actions** due at `t` (section 12), each executed through its actor's own
   session by the same executor, in registration order; then the staff simulator's handoff
   responses due at `t` (`engine.run_due_handoffs`, pantry profile).
3. **Hold expiries** (`expires_at == t`). A hold is usable only while `clock < expires_at`.
4. **Grant expiries** (`expires_at == t`). A grant is valid only while `clock < expires_at`.
5. **Activity starts** (`scheduled start == t`): strict execution readiness; ready → `started`,
   otherwise → `failed` with the unmet reasons.
6. **Event close** at `goal.hard_end`.

At an inclusive service deadline (pantry: 13:40) the service activity completes (1), the
scheduled staff distribution is recorded (2, so it counts on time), and then the next activity
starts (5). Hold expiry and the handoff cutoff are exclusive.

After each state-changing event the revision increments by one and a transition and a public
snapshot are stored. Readiness previews (`planned`↔`ready`) are recomputed after every change
and recorded as lifecycle records at the current revision without a separate increment.

**Revision increments** on: ingested observation, check-in, hold, release, expiry, plan apply,
goal/grant version, lifecycle start/complete/fail, grant expiry, event close. Reads, duplicate
observations, repeated status records, and clock moves with no events do not increment it.
Completion of an already started (authorized) activity needs no grant; a new mutation after a
grant expires is rejected.

Source observation time (`observed_at`), retrieval/receipt time (`received_at`), receipt
execution time (`executed_at`), and scenario time are distinct fields.

## 7. Activity lifecycle and readiness

States: `planned`, `ready`, `started`, `completed`, `failed`, `canceled` (no Wave 1 operation
cancels an activity; the state exists for later waves). `activity_events` is append-only. DB
triggers (migrations 0001 and 0003) allow only these lifecycle moves: `planned`↔`ready`,
`planned`/`ready` → `started`/`failed`/`canceled`, and `started` → `completed`/`failed`. So
`completed` comes only from `started`, `started` only from `planned` or `ready`, and nothing
leaves `completed`, `failed` or `canceled`. Setting a planned or ready activity to its own state
is accepted and changes nothing. Activities are never deleted and their definitions are fixed;
`plans` and `goals` rows are never updated or deleted, so a new version is a new row. Every
store connection sets `recursive_triggers`, so REPLACE cannot rewrite a guarded row. Setup is
loaded as `started` at 16:30.

Readiness (`domain/readiness.py`) uses visible evidence only. Execution mode at the scheduled
start requires: predecessors `completed`; space `available`; equipment `available` (an
`expected` delivery needs an observed arrival; an ETA is never readiness), plus an active
commitment when the resource requires booking; each person checked in with availability
covering the window; no other program activity in progress. A missed start is an honest
`failed` record. Wave 1 has no late start in place; recovery happens by re-planning before the
start.

## 8. Resources, holds, commitments and money

* **Holds** apply only to resources with `terms.booking_required`. `hold_resource` checks the
  following in this order, and the first failing check is the answer:
  1. `expected_revision` is current (`REVISION_CONFLICT`);
  2. the resource and the activity are registered (`UNKNOWN_ENTITY`), and both are in the grant's
     scope (`SCOPE_VIOLATION`);
  3. the resource has booking terms (`HOLD_NOT_SUPPORTED`);
  4. the resource is a required resource of the activity or an approved substitute
     (`CONSTRAINT_VIOLATION`);
  5. the quantity is at most the resource capacity (`RESOURCE_CONFLICT`);
  6. the window lies within the resource and activity windows and starts after now
     (`CONSTRAINT_VIOLATION`);
  7. the visible resource status is not `unavailable` (`RESOURCE_UNAVAILABLE`);
  8. `now < commitment cutoff` (`COMMITMENT_CUTOFF_PASSED`);
  9. capacity over the window, counting the active plan's other assignments, active holds and
     active commitments (`RESOURCE_CONFLICT`);
  10. grant reserved usage + exposure `<=` `max_total_reserved_cents` (`BUDGET_EXCEEDED`);
  11. grant committed usage + hold fee `<=` `max_total_committed_cents` (`BUDGET_EXCEEDED`);
  12. event committed + reserved + exposure + hold fee `<=` budget (`BUDGET_EXCEEDED`);
  13. last, immediately before the hold is written, the resource's steward confirms the hold.
      The steward is its registered status source in the private world, answering at execution
      time. If it reports the resource unavailable the hold is `RESOURCE_UNAVAILABLE`; if it
      cannot be reached the hold is `STATUS_UNAVAILABLE`. The refusal discloses no private
      record.

  Because the steward is consulted only after every public check passes, a hold that fails for a
  public reason is refused for that reason. The hold lifetime is `min(requested,
  terms.hold_max_minutes)` (10 minutes when the terms set none); it shortens a hold but never
  refuses one.
* **Accounting** is an append-only ledger: `reserve`, `release_reserve`, `expire_reserve`,
  `convert_reserve`, `commit_charge`, `hold_fee`. Unique indexes allow one reservation and one
  return per hold, so release/expiry/conversion can never refund twice. Committed (incurred)
  and reserved (refundable exposure) are separate totals.
* **Commitment cutoff** = use start − `commitment_cutoff_minutes_before_use` (backup: 15 min). It
  is shown separately from the activity start. A hold may expire before the activity if it is
  converted in time; a commitment survives its former hold's expiry.
* **Conversion** happens only inside `apply_plan`: hold `active → committed`, a commitment row,
  `convert_reserve` (−exposure) and `commit_charge` (+cost). The same amount is never reserved
  and charged at once.
* **Release** of a terminal hold → `HOLD_NOT_ACTIVE` (with its terminal state); of a converted
  hold → `HOLD_CONVERTED`. A committed allocation is not released through `release_hold`;
  campus terms declare no cancellation in Wave 1.
* **Grant expiry or revocation** does not erase accepted commitments.
* **Consumable pools** (pantry profile): `hold_resource` on a pool reserves a quantity, not a
  booking, and `apply_plan` converts it into a stock allocation; the money ledger is untouched.
  Section 15 gives the rules.
* **Backup projector terms (fixture):** booking required; free hold for at most 10 minutes;
  reserved exposure 3500; commitment cost 3500; cutoff 15 minutes before use. The coordinator
  (committed limit 0) can hold it but cannot convert it unless the organizer raises its committed
  limit through `update_grant` (a recorded grant version, receipt and revision).

## 9. Observations and status queries

`submit_observation` stores immutable content with server-assigned provenance:
`source_id = principal_id`, `authority_scope = self_report` (participant) or
`organizer_instruction` (organizer), `channel` from the session, `received_at` = now,
`observed_at` = supplied or now (never in the future). `source_record_id` = `client_record_id`
or a generated id. `(source_id, source_record_id)` is unique per episode: a duplicate returns the
existing observation without a revision change. Instructions embedded in text are data. The
browser sends a `client_record_id` (`web-obs-<uuid>`) fixed per logical observation, so a
resend under the same key, or a retyped identical update after an unknown outcome, is
deduplicated; reusing a record id for different text is rejected.

**Resource offers (runtime 1.1.0).** `submit_observation` with `kind: resource_offer`, the
resource as `entity_id` and an `offer: {available, capabilities, terms_ref}` asks to activate a
preconfigured resource. The text stays data; only the structured fields are checked, in this
order, and the first failure is a durable rejected receipt that changes nothing:

1. a current `expected_revision` when supplied (`REVISION_CONFLICT`) and a registered resource
   (`UNKNOWN_ENTITY`);
2. the submitter speaks for the resource and it is in its grant (`SCOPE_VIOLATION`);
3. the resource is a preconfigured option, i.e. an approved substitute of a registered resource,
   not a person's role (availability is a check-in) and not consumable stock (an offer cannot add
   stock) (`UNSUPPORTED_ACTION`);
4. the stated capabilities are registered for it and cover the capabilities of a resource it
   stands in for (`CONSTRAINT_VIOLATION`, with `details.needed`);
5. the interval has not ended (`INVALID_REQUEST`), lies inside the registered window and reaches
   its end (`CONSTRAINT_VIOLATION`; the planner models the registered window), and no status or
   arrival record reports the resource unavailable (`RESOURCE_UNAVAILABLE`);
6. `terms_ref` equals `terms.terms_source_ref` (`CONSTRAINT_VIOLATION`).

An accepted offer is one `resource_offer` observation (self_report, valid for the offered window,
correlation group `offer_<resource_id>`, superseding the same owner's earlier offer) and one
revision. Unless a status or arrival record already speaks for the resource, its status becomes
`available` (offered from now) or `expected` with `reported_eta` = the offered start, with basis
`status_observation` and `status_observation_id` = the offer; otherwise the offer is recorded with
`activated: false`. It creates no hold, commitment, ledger entry or stock movement: the
coordinator still holds and, when money is needed, asks for authorization under its own grant. An
offer without `offer` fields is an unverified proposal that changes no status. `offer` requires
`kind: resource_offer` and `entity_id`, and excludes `observed_at` (400 otherwise). In
`dev_fixture_01` no participant speaks for equipment, so campus offers are always refused.

`query_status {entity_id, fact}` requires a registered status source for that entity and fact
(`STATUS_SOURCE_NOT_REGISTERED` otherwise). The private world answers from the latest
`status_model` record whose `available_from <= request time`:

* `ok` → `succeeded` with the observation (kind `status`, scope `resource_status`,
  `observed_at` = the source record's time, `received_at` = after the 2-minute duration). Its
  `correlation_group` is the lineage the private status record names
  (`response.correlation_group`, optional), or `<entity_id>_status` when it names none. The
  campus fixtures name `projector_delivery_01` for order P17, the same group as the delivery
  notice and the arrival. The dev01 status observation therefore reproduces
  `PEEAI_plan/examples/observation_after_query.json` field for field, except the store-assigned
  `observation_id`. A record already ingested returns the existing observation
  (`deduplicated: true`, no revision change). Resource status/ETA update from the typed
  `structured` facts.
* `unknown` or no record → `unknown` with `STATUS_UNKNOWN`. `unavailable` → `unavailable` with
  `STATUS_UNAVAILABLE`. Neither ingests anything nor changes resource status; both consume the
  duration.
* `data.freshness = {observed_at, retrieved_at, age_minutes, stale}`; `stale` when the record is
  older than the source's `freshness_minutes`.

A query never returns the private scenario, future records, or arrival times. An arrival is
visible only when the clock reaches it (observation channel `arrival_record`).

## 10. Planner (campus and pantry adapters)

`evaluate_candidates` builds a `PlanningSnapshot` from public state and calls
`CampusAdapter.evaluate`. Evaluation has no side effects on holds, money or the plan.

**Loading a scenario.** `create_episode` refuses a public scenario unless
`CampusAdapter.validate_config` reports no problem. Every reference must resolve:

* ids of activities, resources, principals, grants and status sources are unique;
* `initial_state.event_id`, every grant's `event_id` and every visible observation's `event_id`
  equal the scenario's event id;
* initial lifecycle records name defined activities, one each;
* an initial check-in names a registered person resource. If it names a principal, that
  principal is registered and speaks for the resource;
* a visible observation concerns a registered resource, an activity, or the event;
* every grant's principal is registered, and each principal's grant was issued to that
  principal with that role;
* `speaks_for_resource_ids` are registered resources;
* a resource's `terms.status_source_id` is a registered source that lists the resource and
  answers each of its `queryable_facts`, and queryable facts require a source;
* there is exactly one `coordinator_agent`.

The keep candidate of the initial plan is then assessed with the planner's own hard checks.
Any failed check other than `resource_status` and `arrival_assumptions` refuses the load; those
two depend on status and arrival evidence that the episode is designed to change. A required
activity without an assignment, or a not-started assignment outside its window, therefore
refuses the load.

A private case is checked against its public scenario by
`plan_b/world/validate.py:validate_case`, in both `create_episode` and `run_case`, before
anything is written:

* the case's `scenario_id` matches;
* each `status_model` record names a registered resource and one of its queryable facts;
* a `resource_arrival` names a registered resource, and a `message_delivery` names a
  registered resource, an activity or the event;
* actor scripts name registered principals; check-in scripts name a registered resource;
  observation scripts name a registered entity or none; organizer rules name a registered
  grant and registered resources;
* organizer goal-update scripts name an organizer principal;
* staff rules (pantry): a handoff rule needs the scenario's `pantry_parameters`, names two
  consumable pools and a visible source observation, and its principal's grant allows
  `record_stock_receipt`; a distribution rule names a registered service target and its
  principal's grant allows `record_distribution`.

A refusal raises `ValueError`. The moderator reset route then answers a generic 500 with no
detail.

**Single edits** from `planning.edit_templates`, in configuration order:

* `keep` → no edits (always generated, first).
* `swap(a, b)`: the activity that starts later takes the earlier one's start; the earlier
  activity starts when the moved one ends. Durations unchanged.
* `shift(a, d)`: start and end of `a` move by `d` minutes, one edit per offset.
* `substitute(a, r, s)`: in `a`'s assignment, `r` is replaced by `s`, for each listed `s`.
* `alternate_format(a, f)`: `a`'s assignment uses `f`'s duration and resources (none
  configured in the campus fixture).

**Combinations** of 2..`max_combined_edits` non-keep edits in generation order, excluding
combinations where two edits change the timing of the same activity (swap changes both of its
activities), two edits substitute the same (activity, resource), or a substitute and an
alternate format touch the same activity. Timing edits apply before resource edits. Edits that
touch started/completed activities are generated and then rejected by `started_history`.
If more than `candidate_cap` candidates are generated, the first `cap` in generation order are
evaluated and `truncated=true`; `generated_count` is the full count.

**IDs.** `signature = sha256(canonical_json([edit.model_dump(mode="json") ...]))`;
for evaluation `eval_NNNN`: `candidate_id = cand_NNNN_<sig[:8]>`, `report_id = rpt_NNNN_<sig[:8]>`.

**Hard-constraint checks** (`CandidateCheck.constraint_id`), evaluated for every candidate:

| Check | Fails when |
| --- | --- |
| `required_activities` | a required activity has no assignment |
| `fixed_venue` | a not-started activity's assignment lacks `goal.fixed_venue_id` |
| `started_history` | a started/completed/failed/canceled activity's assignment differs from the active plan |
| `no_past_change` | a changed activity's new start is `<=` the effective time (below) |
| `activity_windows` | start/end outside the activity window, or length differs from its (format) duration |
| `event_window` | an assignment ends after `goal.hard_end` |
| `dependencies` | an activity starts before a predecessor's assigned end |
| `program_exclusivity` | more than `goal.program_concurrency` program activities overlap |
| `occupancy_capacity` | `goal.attendance_target` exceeds the fixed venue's capacity (separate from concurrency) |
| `resource_capacity` | usage over an assignment window exceeds capacity, or the window is outside the resource's window. Usage = overlapping candidate assignments + active holds/commitments on the resource that do not belong to that assignment (same resource, same activity, window covering it) |
| `resource_status` | an assigned resource of a not-started activity is `unavailable` or `unknown` |
| `arrival_assumptions` | an `expected` equipment resource has a reported ETA (or hypothesis) after the activity's start. With ETA `<=` start, or no ETA evidence, the check passes and records an `arrival_by_start` assumption |
| `substitute_compatibility` | a substitute is not in the original's `approved_substitute_ids`, is unregistered, or lacks the original's capabilities |
| `participant_availability` | a person's latest check-in availability (or, without a check-in, the declared resource window) does not cover the assignment. A declared window without check-in passes with a `declared_availability` assumption |
| `accessibility` | a configured `venue_capability` requirement is not met. No requirements, or only requirements that concern no activity still to run → `not_applicable`; any other kind → `unsupported` and the candidate's result is `unknown`. `validate_config` rejects a requirement with no activity ids |
| `commitment_cutoff` | a booking-required resource without a covering commitment is used at or after its cutoff, judged at the effective time |
| `budget` | event committed + reserved − exposure of holds this candidate converts + incremental committed exceeds `goal.budget_cents` |

**Effective time.** Time-dependent checks are judged at `snapshot.effective_at`: the moment an
`apply_plan` issued now would take effect (evaluation snapshot: clock + the apply duration;
apply_plan's own revalidation: the clock, since it already runs after its duration). This covers
`no_past_change`, `commitment_cutoff`, hold binding (a hold must still be live then), the
budget's reserved total (holds lapsing by then are excluded) and grant validity, so a candidate
reported applicable is still valid when its apply executes. People's availability uses each
role's latest check-in.

`constraint_status` = `infeasible` if any check failed, else `unknown` if any is `unsupported`,
else `feasible_under_assumptions`. A `catalog_availability` assumption is recorded when a
booking-required resource's availability rests only on the authored catalog. Infeasibility
statements apply only to the declared action space.

**Required holds** are preconditions, not hard checks: each booking-required resource used by
a not-started activity without a covering active commitment needs a live hold *by this actor*
whose window covers the assignment (`bound_hold_id`), else it is unbound. Incremental committed
cost = the commitment cost of those resources.

**Authorization** (`AuthorizationAssessment`, separate from feasibility): grant present and
valid now; `apply_plan` in `allowed_tools`; changed activities ⊆ `grant.activity_ids`; resources
of changed assignments ⊆ `grant.resource_ids`; `committed_used + incremental <=
max_total_committed_cents` (a shortfall names the review item "increase committed spending").

**Objective** (integers, shown per term): `start_shift_minutes = Σ|new start − active-plan
start|`; `changed_activities` = activities whose start, end or resources differ;
`additional_committed_cents`; `optional_activities_removed`; `participant_notifications` =
person resources in activities whose start changed. Weighted:
`start_shift*w_start + changed*w_change + cents*w_spend // 100 + removed*w_optional +
notifications*w_notify`. Balanced weights 1/10/4/1000/5: swap = 40+20+10 = 70; backup
substitution = 10+140 = 150.

**Ranking.** Feasible candidates sorted by `(total, changed_activities,
additional_committed_cents, signature)`; `rank` 1..n. Others follow, sorted by signature, with
`rank = null`. `applicable_now` = feasible ∧ authorized ∧ every required hold bound ∧ not
hypothetical. `best_candidate_id` = rank 1; `best_applicable_candidate_id` = first applicable in
rank order; `keep_candidate_id` = the keep candidate. When nothing is feasible,
`infeasibility` names the declared action space and the failed constraint ids.

**Hypotheses** override a resource's ETA/status for robustness checks. Such evaluations are
`hypothetical` and their candidates are never applicable.

**`apply_plan`** loads the stored candidate by `candidate_plan_id` and requires
`constraint_report_ref` to be that candidate's `report_id` (`CANDIDATE_REPORT_MISMATCH`), a
non-hypothetical evaluation (`CANDIDATE_HYPOTHETICAL`), and the current revision and goal
version (`CANDIDATE_STALE`). It then calls `revalidate` inside the write transaction and
requires feasibility, authorization and bound holds (`CONSTRAINT_VIOLATION`,
`BUDGET_EXCEEDED`, `HOLD_EXPIRED`, `CANDIDATE_NOT_APPLICABLE`). A client-supplied feasibility
flag does not exist.

### Pantry adapter (`pantry/1.0.0`, `domain/adapters/pantry.py`)

The pantry adapter extends the campus adapter: the event checks above run unchanged on schedule
and resources (consumable holds are excluded from them, and allocations are judged only by the
stock checks). The executor, sessions, grants, receipts, clock, snapshots and trace format are
shared; the adapter owns only the added stock semantics (`domain/stock.py`, `tools/stock.py`).

* **Menu:** keep, the configured event edits, and one candidate per `stock_options` entry
  (`allocate_stock`, `transfer_stock`, `await_shipment`), not combined. An option's allocation is
  what was already distributed from the pool plus what it can count (usable units; plus
  transferable alternate units; plus outstanding expected units), capped by the target and by
  what staff can distribute before the event end.
* **Checks:** `consumable_allocation`; `stock_on_hand` (demand summed across activities whatever
  their windows; expected units never count, so `await_shipment` is infeasible while the shipment
  is unreceived); `stock_transfer` (the shortfall can still be handed off: held and before the
  cutoff, or a new hold whose staff response fits before it); `service_throughput` (new
  reservations distributable before the event end).
* **Coverage:** `service_coverage` reports allocated, on-time achievable (by the deadline at the
  declared rate) and unfulfilled = target - on-time; each unfulfilled unit costs 100 objective
  points (`weighted.unfulfilled_units`).
* **Preconditions:** `required_stock_holds`: the actor's live activity holds on the pool for the
  target and activity must sum exactly to the uncommitted allocation. `stock_transfers`: alternate
  units still to be handed off; a candidate with any is never applicable.
* **Readiness:** the core rules for non-stock resources; a pool is reported, not a start
  condition.
* **Scoring:** `score_outcome` = the core outcome plus every target attained on time against its
  original quantity; violations `stock_not_conserved`, `unattested_stock_record`,
  `attestation_by_agent`, `distribution_without_service`.

## 11. Deterministic rule policies (P0: `rules/1.0.0`, `pantry-rules/1.0.0`)

The policy sees only tool envelopes through a `ToolClient` bound to the coordinator session. It
never imports the store, world, runner or private cases.

```python
class ToolClient(Protocol):
    principal_id: str
    def call(self, tool: str, *, arguments: dict, idempotency_key: str | None = None,
             expected_revision: int | None = None,
             expected_goal_version: int | None = None) -> ToolEnvelope: ...
# raises TransportLost when a response is lost after the request may have executed
```

`run(client, max_tool_calls) -> PolicyRunResult` executes one bounded loop and returns
decisions; the host stores them (they are narration, not evidence). Idempotency keys are
`rules-r<revision>-<tool>-<sha8(arguments)>`, so an identical intended request at the same
revision is an idempotent retry.

**Supported message forms** (parser `rules-parser/1.2.0`). A notice is read sentence by sentence
after a leading `Fwd:`/`Fw:` is stripped (and the copy marked as forwarded), the text is
lowercased, its whitespace collapsed and the dots of `a.m.`/`p.m.` masked. A sentence ends at `.`,
`!`, `?` or `;` followed by whitespace. Every sentence must match one of these forms in full
(case-insensitive, optional trailing period):

* Delay claim: `[<determiner/possessive>] <subject: 1-3 words> delivery may be [about] N
  minute(s) later than the promised H[:MM] a.m./p.m. arrival`. Claimed ETA = promised time (event
  date and timezone) + N minutes; N = 0 is `no_change`; an hour outside 1-12 leaves
  `promised_time` unresolved.
* Cancellation claim: `[Reminder: | Update: | Notice:] [<subject: 0-2 words>] order P<digits>
  [for the <Month> <day> <0-3 words>] was|has been|is cancel(l)ed[, so no <word> will arrive
  for that booking]`.
* Status pointer: `Please check order P<digits> for the latest status`.
* Greeting or sign-off: `Hi`, `Hello`, `Thanks`, `Thank you`, `Regards` (optionally `.` or `!`).

Subject words must be words of a registered resource's id or label. A cancellation subject may
start with a determiner or possessive (the, a, an, our, your, their, my, its, his, her, this,
that). The words after a date must be such words or one of: event, showcase, workshop, session,
booking, delivery, rental, hire, meeting, seminar, lecture, class, conference, talk. A message
holds exactly one claim sentence. Any other sentence, a second claim, no claim, or a claim
sentence that does not match its form exactly makes the whole message `unresolved` (field
`wording`, reason "wording outside the supported message forms"); nothing is parsed partially and
nothing in it causes a plan change. Questions, negations, conditions, retractions, reported
speech and hedges are therefore never asserted, because no form admits those words: "Order P17
has been cancelled." is a claim, while "Order P17 was cancelled because the van broke down." and
"If the van breaks down, order P17 will be cancelled." are both `unresolved`.

* Subject: the record's entity when it is a registered resource, else the resource whose
  `terms.booking_ref` equals the order, else the subject phrase. A phrase equal to a resource id
  or label names it; otherwise its last word must be a word of the resource and every other word
  one of that resource's words ("Backup projector delivery" names `backup_projector`). A phrase
  that matches several resources stays unresolved (field `subject`) with an ambiguity reason and
  the candidates listed, and never defaults to one of them. A phrase that contradicts the subject
  given by the entity or order leaves the subject unresolved.
* Identity checks: an order reference must equal the subject resource's `terms.booking_ref`; a
  date anywhere in the text must be the event date. Mismatch → `inapplicable`. Same correlation
  group and normalized text as an already handled notice → `duplicate` (one evidence lineage, not
  corroboration). Words such as "ignore", "approve", "authorize", "grant", "budget" are flagged
  as embedded instructions and have no effect.
* Forwarded copies: a leading `Fwd:`/`Fw:` is stripped and marked as forwarded.
* Retraction: an observation's `supersedes` naming an earlier notice from the **same source**
  retracts it (evidence `superseded`, decision `inapplicable`); a supersedes from a different
  source is refused.
* Hearsay: a delay/cancellation claim about equipment submitted through a participant or
  organizer session (the submitter does not speak for the supplier's equipment) may trigger
  verification, but while unverified it is never a robustness hypothesis, so on its own it causes
  no hold, ask or robust plan change. Claims delivered by the scenario (the external contact,
  channels `scenario_delivery`/`fixture_initial`) keep the robustness rule.
* Verification only: an `unresolved` notice (not `inapplicable`, not `duplicate`) that identifies
  exactly one registered equipment resource carries `verify_subject_id`. The resource can be
  identified by the observation's `entity_id`, by an order reference equal to its `booking_ref`,
  by its exact id or label in the text, or by a claim form's subject phrase. Where names overlap in
  the text the longer one wins ("backup projector" names `backup_projector`), and a name directly
  preceded by an other-item modifier (spare, other, another, second, extra, new, replacement,
  rental, borrowed, different, old) identifies nothing. A notice that says nothing about delivery
  status (no word such as late, delay, cancelled, ETA, arrival, available, status) identifies
  nothing. An order reference that names no registered booking, or a second identified equipment
  resource, leaves `verify_subject_id` unset. A verify-only notice is answered by a successful
  check of its resource *requested* at or after the notice arrived (a check answers as of its
  request time, section 9), or by a status observation observed at or after it. A check that
  was already in flight when the notice arrived does not answer it. If the resource is being
  checked for a supported claim anyway, the notice joins that check. Otherwise the policy queries
  the resource's registered status source *after* its decision step, under the claim bounds
  below, so a verify-only check never delays a hold, an ask or a commit; new typed status from it
  starts another decision cycle. No check is made, and a `verify` decision with
  `details.outcome = "not_checked"` records why, in two cases. (1) A notice submitted in a
  session (participant or organizer) waits while a successful check of that resource was
  requested within its source's freshness window. (2) Any verify-only notice waits while such a
  fresh check left the resource `unavailable`, or `expected` only after the start of every
  not-started activity that uses it in the active plan: the plan cannot rely on the resource
  whatever a check returns, so a check would only spend time (value of information). The policy
  records a decision stating that the wording is not a supported form and that only
  verification is done. The notice is never a claim: no hypothesis, hold, ask
  or robust plan change comes from it, and the typed status that the query returns drives
  planning as usual.
* Typed evidence: status and arrival observations carry `structured` facts and are used
  directly; their text is never pattern-matched. A `resource_status` observation received after
  a notice supersedes the notice's claim for planning.

**Decision rules** (bounded loop): read state → interpret new observations → for each material
applicable claim on an equipment resource used by a not-started activity, verify with
`query_status` if a source is registered (at most 2 attempts per claim; `unknown`/`unavailable`
leave it unverified) → `evaluate_candidates` → keep if the keep candidate is applicable and
evidence does not contradict it → if verification failed, also evaluate the claimed ETA as a
hypothesis and restrict to candidates feasible in both (robust over the declared outcomes) →
apply the best applicable candidate → otherwise, for the best feasible candidate needing a
booking: verify the substitute's availability if it rests on the catalog, hold it if the
reserved limit allows, and record an `ask` decision with an `AuthorizationRequest` when the
committed limit is short → if nothing is feasible, record `infeasible` with blocking constraints
and preserve the plan → release own holds the current plan no longer needs → verify unanswered
verify-only notices (same bounds; new typed status re-enters the loop) → wait. A lost mutation
response is reconciled with `get_action_receipt` and the original key.

When nothing is feasible but some candidates are `unknown` (an unsupported requirement), the
decision is `unresolved`, not `infeasible`, naming the unsupported requirement and the undecided
candidates. `AuthorizationRequest.reason` is one sentence of at most 400 characters that always
states the missing permission (field, grant, current and requested values).

**Settled state.** The policy remembers the `(revision, goal_version)` of the last state view
its decision loop decided on, not the revision of the last envelope it received. A wake whose
state differs from it, including a change that landed during the previous run's last tool call,
runs a new decision cycle. State-level decisions are de-duplicated, so a repeated cycle records
nothing twice.

Decision `details` keys used by consumers: `infeasible` → `blocking_constraints` (sorted check
ids) and `evaluation_id`; `unresolved` (notice) → `interpretation` and, for a verify-only notice, `verify_only` (the
resource id); `verify` → also `verify_only` (the ids of the verify-only notices in that check);
`unresolved` (undecided) → `unsupported_requirements`,
`undecided_candidate_ids`, `blocking_constraints`, `evaluation_id`; `ask` → `evaluation_id`, `missing` (MissingPermission list); `verify`
→ the query outcome. An `AuthorizationRequest` has no stored open/answered status. The board treats it as
open until a later grant version of its target meets `requested_value`; the scripted organizer
in headless runs answers each `request_id` at most once.

### Pantry rule policy (`pantry-rules/1.0.0`, `evaluation/policies/pantry_rules.py`)

The deterministic baseline of the pantry profile. It reads the state; queries each outstanding
expected shipment once and, while a supply gap exists, each declared transfer source once (at most
two attempts); evaluates; for the best feasible candidate with alternate units still to hand off,
holds the shortfall on the source (`purpose: stock_transfer`, the staff task), records an `ask`
and waits for the staff response, one request per source; once that is answered (fully or
partly) or lapsed, plans without pending handoffs; holds exactly what the chosen candidate still
needs, re-evaluates and applies. When the plan covers less than the target it records
`infeasible` with `details.shortfall_quantity` and `blocking_constraints`. It releases its own
transfer holds that are no longer awaited (one retry after a stale revision), never calls the
staff tools, reconciles a lost response by its original key, and uses keys
`pantry-r<revision>-<tool>-<sha8(arguments)>`. It is statically isolated from the store, world,
scenarios, tools and API, like `rules/1.0.0`.

## 12. Runner and scripted actors

`scenarios/runner.py` drives an episode minute by minute and advances the clock one minute at a
time to the hard end. It wakes the policy when the public revision changed, when the policy's
`wait_until` passed, and on the next tick after a run that exhausted its tool budget, ended
`incomplete` (for example a lost state read), or saw any revision it did not produce itself
(an actor action, a world event or an engine transition during its own tool durations). It
never wakes the policy at or after the event close (the engine's `event_closed` record, or the
clock at `goal.hard_end`), or once the coordinator's current grant has expired. A clean run
therefore does not end with a rejected `get_event_state` (`GRANT_EXPIRED`), and
`rejected_attempts_without_receipt` counts only real rejections. The tool budget
(`max_tool_calls`, 16) bounds one policy run, and every coordinator policy also runs under the
per-episode caps of section 17: a run gets at most the remaining episode budget, and once a cap is
reached the policy is not woken again. It stops if the episode is reset meanwhile: a closed episode's clock never moves, no session is
issued for it, a policy run that loses its episode returns `stopped`, and its decisions are not
written into the closed episode. Moderator controls that race a reset answer 409
`EPISODE_CLOSED`, and run responses carry `episode_id` and `episode_status`.

Scripted exogenous actors (participant check-ins and observations; the simulated organizer that
answers an open, in-bounds `AuthorizationRequest` after its declared latency via `update_grant`;
an `organizer_goal_update` script that changes the goal's preference preset at its instant via
`update_goal`, citing its `expected_goal_version`; and the labeled pantry staff simulator below)
are registered as **scheduled actor actions** (`scheduled_actions` table, private) with the
actor's own server-held session. The clock engine executes each one at its exact instant
(section 6) through the same executor, so the instant does not depend on what any policy is
doing: a policy's tool duration that spans the instant processes it like a world event. A
scheduled organizer action is validated against the state at that instant (as if read just
before acting). Scheduled tools must have zero duration. Scripted actors are identical for every
policy. The runner never writes check-ins, observations or grants directly and never tells the
policy what to do. In the browser, scripted actors are off: people act through role tabs.

**Labeled staff simulator (pantry).** A `staff_handoff_rule` is a standing scheduled action: the
engine answers each matching stock-transfer hold once, `handoff_duration_minutes` after the hold
was created, through the staff session and the executor (`record_stock_receipt`), confirming the
live remainder (capped over the episode by the rule's `max_quantity`) while the hold and the
window are valid. A `staff_distribution_rule` records at its instant `min(committed
undistributed, original target - distributed, accrued capacity)` (`record_distribution`). Both
decide from the visible state at their instant and are identical for every policy. In the
browser the simulator is off, and a human staff tab records directly (its latency is not
enforced).

**Cases and policies.** `run_case(db, case_ref, *, scenario_id=None, policy="rules",
policy_factory=None, caps=DEVELOPMENT_CAPS, live_config=None, max_tool_calls=16)` runs a case on
its own `scenario_id` unless one is passed explicitly. `policy` is a `PolicyChoice`: `rules` is
the profile's deterministic baseline, P0 (`policy_host.baseline_policy_factory`: `rules/1.0.0`,
or `pantry-rules/1.0.0` for `pantry_continuity`); the model-driven choices are `tool-use` (P1,
`tool-use/1.0.0`, section 18), `live` or its alias `selective` (P2, the live coordinator
`live/1.0.0`, section 16) and `verify-all` (P3, `verify-all/1.0.0`, section 18), each with its
endpoint configuration read server-side. An explicit `policy_factory` (tests) takes precedence.
The profile selects a policy and its declared rules, never a scripted outcome.

**Scoring.** `evaluation/scoring.py:score_episode(final, history, case)` scores from persisted,
visible records only. It dispatches on `final.profile_id` to
`DomainAdapter.score_outcome(final, history) -> DomainOutcome(activities, goal_attained, unmet,
violations)`, then appends the domain-independent spend-limit violations (`budget`,
`reserved_negative`, `grant_limit`). The goal is complete when the adapter finds it attained and
no violation was executed. The campus adapter's part is `domain/adapters/campus_outcome.py`.
Readiness goes through `DomainAdapter.check_readiness(..., mode=)`: the clock engine uses
`execution`, and the projection uses `preview` for the episode's own profile.
`scoring.HARD_CHECK_IDS` (used by the `infeasibility_reported` predicate) includes the pantry
check ids (`stock.PANTRY_CHECK_IDS`). Consumable profiles fill `OutcomeReport.service`, `.stock`,
`staff_confirmations`, `duplicate_records_rejected` and `unnecessary_reservations`; their
predicates are `service_on_time_equals`, `service_unfulfilled_equals`, `stock_on_hand_equals`,
`expected_unreceived_equals`, `stock_conserved` and `no_staff_attestation_by_agent`. Every report
also carries `mode_label` and `episode_caps` (section 17). Still campus-specific in the core is the
`equipment_before_arrival` category named by the `no_equipment_start_before_arrival` predicate.

## 13. Trace export and replay

`evaluation/export_trace.py` writes `plan_b.trace` 1.0.0:

```text
{trace_version, runtime_version, kind: "plan_b_sanitized_trace", mode_label: "Recorded replay",
 source: {episode_id, scenario_id, profile_id, public_fixture_sha256, policy_id, generator},
 frames: [{seq, revision, scenario_time, cause_kind, cause_ref, summary, state: EventStateView}],
 tool_calls: [ToolCallRecord], decisions: [PolicyDecision], receipts: [ActionReceipt],
 final_state: EventStateView,
 integrity: {algorithm: "sha256", frame_hashes: [...], chain_sha256, content_sha256}}
```

`frame_hashes[i] = sha256(canonical_json(frames[i]))`;
`chain = ""; for h in frame_hashes: chain = sha256(chain + h)` (hex strings, UTF-8);
`content_sha256 = sha256(canonical_json(trace without "integrity"))`. Each evaluation is stored
once in `evaluations` (keyed by `evaluation_id`): frames' `state.latest_evaluation` and
`evaluate_candidates` envelope data hold `{evaluation_ref}`, and readers rehydrate before
rendering (`export_trace.rehydrate_state`, `web/src/replay/ReplayView.tsx`). Hashes are computed
over the stored, compacted form. `final_state` is stored in full. Frames come from the per-revision public
snapshots: a frame's `scenario_time` is when its revision came into being, and its state is
refreshed by later same-revision facts (status checks, evaluations, rejected receipts,
decisions), so `state.clock` can be later than `scenario_time`. A trace contains no tokens, join codes, moderator code, private case reference,
status model, world events or predicates. The browser replay shows a persistent **Recorded
replay** label, labels each tool result with its recorded scenario time, and issues no tool or
moderator calls.

`source.policy_id` names the policy that actually ran. It is read from the distinct `policy_id`
values of the episode's recorded decisions: `null` when none were recorded (clock moves and
participant actions only), the id when one policy decided, and the distinct ids sorted and
joined with `,` when several did. `POST /api/moderator/export` derives it this way, and
`plan-b run-case` records the id of the policy its runner ran. Decisions in traces carry
`details.policy_mode.label`, which names the policy that ran ("Deterministic policy", or
"Tool-use agent · <model>", "Live agent · <model>" or "Verify-all agent · <model>" with the model
id as returned, section 17). Live decisions also carry the model call records
of section 16. Live traces are evidence of one run, not reproducible artifacts: model choices
and the calls' wall-clock `started_at` vary between runs.

**Verification.** `plan-b verify-trace` (`export_trace.verify_trace_bytes`) and the browser
replay (`web/src/replay/integrity.ts`) make the same checks and accept and reject the same
traces. Both read the file's exact bytes; the browser decodes them itself (TextDecoder, fatal,
`ignoreBOM`), because `Response.text()` and `Blob.text()` drop a byte order mark. The checks are:

* the bytes are UTF-8 without a byte order mark, and the text is one JSON object;
* no string or key holds a lone UTF-16 surrogate;
* objects and arrays nest at most 256 levels, and no integer is longer than 4300 digits;
* `integrity.algorithm` is `sha256`, `kind` is `plan_b_sanitized_trace`, and `trace_version` is
  `1.0.0`;
* `integrity.frame_hashes` is a list, and it, `chain_sha256` and `content_sha256` match their
  recomputation;
* the last frame's `state.revision` is an integer equal to `final_state.revision` (vacuous with
  no frames).

Every failure is a reported problem, never a traceback. The CLI prints "intact" or the problems
and exits 0 or 1. The browser distinguishes a hash mismatch ("not consistent with its own
hashes") from a structural failure ("consistent with its own hashes, but it fails a structural
check: …"), and marks the board when any check fails. It reports a verifier that throws as a
failed check ("could not be checked"), never leaving the banner at "checking". A byte order mark
or invalid UTF-8 is refused when the file loads, so such a file never renders. The shared
`trace_cases` in `web/tests/fixtures/canonical_vectors.json` (generated by
`web/tests/make_vectors.py`) run through both suites (`web/tests/integrity.test.ts`,
`tests/test_trace_verifier.py`), and each must fail exactly its named check in both.

The hashes are not signed. "Intact" means a trace is consistent with its own hashes; it detects
corruption, not deliberate edits.

**Replay loading and rendering.** The replay loader (`web/src/replay/loader.ts`) calls fetch only
as `fetch(url, GET_ONLY)`. `GET_ONLY` is a frozen object with no prototype whose own keys are
exactly `method: "GET"`, `cache: "no-store"` and `credentials: "omit"`; it has no headers and no
body. The browser reads every RequestInit member through the prototype chain, so options with a
prototype could pick up a key that some module put on `Object.prototype`. With no prototype, no
inherited key reaches the request. The boundary lint (`web/scripts/check-boundaries.mjs`)
requires this construction.

A trace the replay cannot render never blanks the page. If a frame, the summary or the board
throws, the banner shows the integrity check as failed whatever the hashes say, and a notice
("This trace could not be rendered.") takes the board's place. A frame state without
`latest_evaluation` shows no evaluation.

## 14. Public/private boundary

Private runner input (`scenarios/private/*.json`, `PrivateCase`) is loaded only by
`plan_b/world/` and the runner. It is linked to an episode only through `episode_private`, which
no projection reads. The world returns to tools only what the observation model allows at the
current time. Policy inputs, planner inputs, HTTP responses, browser assets and public traces
must not contain `PrivateCase` fields or values that are not yet public (future arrival times,
future status records, case labels, predicates, `never_expose_to_agent`, `ground_truth`).
Tests check this by scanning every payload. Case files use opaque names (`dev01`, …).
Runner-side outcome reports with predicates are written to the private evidence location only.
Besides `world/` and the runner, `evaluation/export_trace.py` loads the case, and only to refuse an
export that would leak it. A status record's optional `correlation_group` becomes public with the
observation made from it. Before that it is a private marker, unless an observation received by
that scenario time already carries the same lineage. That includes the episode's own
observations and the public scenario's visible observations, which every episode holds from its
start (the shipped fixtures use `projector_delivery_01`, public from 16:40 through
`obs_notice_01`). `plan_b/world/leakcheck.py:private_markers` implements this.

The model-driven policies (sections 16 and 18) build their model inputs only from the tool
envelopes they received, so the same rule covers what is sent to the model provider:
`tests/test_agent_boundary.py` scans the model request bodies and the policy's envelopes for
private markers. The static import rule lives in `tests/test_runner_isolation.py::ISOLATED_MODULES`.
It covers every module of `plan_b/agent/` (the policies in `agent/policies/` included) except
`agent/gate.py`, a harness that creates its own episode like the runner; `agent/provider.py` is
exempt only from the literal `open(` check (its ledger, lock file and HTTP transport). It also
covers the pantry rule policy, the pantry adapter and the stock modules. Relative and from-imports
are resolved, and `import_module` and `__import__` are refused. A test fails when a new module
under `agent/` or `evaluation/policies/` is left out.

## 15. Consumable stock (pantry profile)

A pool is a resource with `consumable_stock` (kind `supply`). Its live projection
(`ResourceView.consumable_stock`, `EventStateView.stock`, `PlanningSnapshot.stock`) is computed
from append-only ledgers by `plan_b/domain/stock.py`:

* **on hand** = opening + receipts - transfers out - distributions (`stock_movements`);
* **reserved** = live hold remainders + undistributed committed allocations (disjoint);
* **available** = on hand - reserved;
* **expected** = outstanding registered shipments, never on hand.

**Quantity holds.** `hold_resource` on a pool reserves a quantity across the whole session and is
refused with `INSUFFICIENT_STOCK` above the global available quantity, so two activities,
overlapping or not, cannot claim the same units. Its window lies inside the resource and activity
windows and must not have ended. A `stock_transfer` hold names a registered `transfer_stock`
source and its destination, lives at most until `pantry_parameters.handoff_window.end`, and is
refused (`HANDOFF_WINDOW_CLOSED`) before the window's start or when now +
`handoff_duration_minutes` is not before its end (`HOLD_NOT_SUPPORTED` when the event declares no
handoff timing).
Its lifetime is `min(requested, terms.hold_max_minutes)`. The steward check ignores records about
an expected shipment. `apply_plan` converts the candidate's bound stock holds into
`stock_allocations` (hold `committed` with remainder 0; the allocation takes the remainder) in the
plan's transaction and revision. `release_hold` and expiry end only a live remainder and never add
stock; a committed allocation is not released (`HOLD_CONVERTED`; this adapter has no
cancellation).

**`record_stock_receipt`** (staff only). An internal handoff needs both pools in the grant, the
same unit, a cited observation about the source or the destination, a live `stock_transfer` hold
into that destination, a time inside the handoff window, a quantity at most the hold's remainder
and the source's on hand, and the destination's storage bound. One revision writes the
`transfer_out` and `receipt` movements, lowers the hold's remainder (`fulfilled` at zero; a
partial handoff leaves the rest reserved) and one `stock_receipts` row. An external receipt names
a `shipment_id` registered for that destination with a quantity at most the outstanding one; the
shipment's `received_quantity` rises once.

**`record_distribution`** (staff only). The target's activity has started or completed; the named
allocations commit at least the quantity; the quantity is at most the original target minus what
was distributed and at most the accrued capacity. `on_time` = recorded at or before the original
deadline (inclusive). A late record is accepted truthfully and never counts on time.

**Physical provenance.** `receipt_reference` and `distribution_reference` are unique per episode
(unique indexes), separately from request idempotency: a resubmission under a fresh request key
is `DUPLICATE_REFERENCE` and credits nothing.

**Capacity.** A qualified minute accrues while the service activity has started, the staff
resource's latest check-in covers it, committed undistributed stock exists, and before the hard
end. Capacity = rate x qualified minutes - distributed; a late commitment cannot backdate it.

**Counters.** Supply gap = `max(target - distributed - pantry-controlled on hand, 0)`, where the
pantry-controlled on hand excludes units held for a transfer out or for other targets.
Unfulfilled = original target - distributed on time. Holds, receipts and commitments never change
the unfulfilled count; only a staff-recorded distribution does. For the canonical fixture the
counters move 16/40 (initial) → 16/40 (partner 16 held) → 0/40 (handoff: pantry 40, partner 0)
→ 0/40 (40 committed) → 0/0 (40 distributed on time), and the expected 20 stays unreceived.

**Store guards (migration 0004).** `stock_movements`, `stock_receipts` and `distributions` refuse
UPDATE and DELETE; `stock_allocations` refuse DELETE, definition updates and a growing remainder;
`expected_shipments` refuse DELETE, definition updates and a falling received quantity. `holds` is
rebuilt with `consumable`, `remaining_quantity`, `purpose`, `destination_resource_id`,
`service_target_id` and status `fulfilled`, and refuses DELETE, a status update once terminal,
definition updates, a growing remainder and any remainder change once terminal.

## 16. Live coordinator policy (`live/1.0.0`, P2)

`plan_b/agent/orchestrator.py:LivePolicy` implements the same `Policy` protocol as `rules/1.0.0`
and sees only tool envelopes. It is P2, the selective policy of the evaluation plan;
`agent/policies/selective.py` re-exports it (`SelectivePolicy`, `selective_policy_factory`), and
its policy id stays `live/1.0.0`. It writes its own `policy_id` into decisions and results, so a
subclass (P3, section 18) keeps its own id. One run:

1. read the state (stop when the event is over, the episode is closed or the grant is invalid);
2. interpret new notices with the model into planning `change_spec` records (prompt
   `interpret.v1`, at most 6 notices per call). Observation text is sent as quoted JSON (with `<`,
   `>` and `&` escaped) inside `<untrusted_observations>`. The server validates every reading:
   an unknown subject stays `unresolved` (`unknown_entity`) and is never kept; evidence ids that
   name no visible observation are dropped; an order reference must be the subject's
   `booking_ref` and a date must be the event date, else the notice is `inapplicable`; a claim
   about equipment submitted through a session is hearsay. Duplicates (same correlation group and
   normalized text) and same-source retractions are resolved by the server without a model call.
   One structured-output repair is allowed; after it the notice stays `unresolved`
   (`malformed_output`);
3. `evaluate_candidates`, and, when verification of a weighed claim failed, again with the claimed
   outcome as a hypothesis, keeping only candidates feasible under both;
4. build a closed menu (`plan_b/agent/menu.py`: keep, `query:<entity>:<fact>`,
   `hold:<resource>:<activity>:<window>`, `apply:<candidate_id>`, `ask:<candidate_id>`,
   `release:<hold_id>`, wait, and on consumable profiles the stock options below) whose options
   carry the exact tool, arguments and expectations.
   Queries are offered only for a stated reason (an unanswered material notice, the catalog-only
   availability of a resource a hold would be offered for, or a one-time deadline watch); apply,
   hold and ask only while the plan is in question; only tools in the grant's `allowed_tools`;
5. the model returns one `option_id` (prompt `choose_action.v1`, strict JSON schema with the menu
   ids as an enum) and the server rejects any id outside the menu (`invalid_choice`). A menu with
   only keep and wait needs no model call: the server records keep, infeasible, unresolved or
   wait with `details.chosen_by = "server"`;
6. the option runs through the `ToolClient` with key `live-r<revision>-<tool>-<sha8(arguments)>`,
   and the next model call carries the real tool result (`consumed_tool_call_ids`); then stop or
   wait. At most 6 model-chosen steps run in one run.

The policy only ever sends `get_event_state`, `get_action_receipt`, `evaluate_candidates`,
`query_status`, `hold_resource`, `release_hold` and `apply_plan` (`AGENT_TOOLS`); anything else is
refused before it reaches the client, and the executor refuses ungranted tools in any case.

**Consumable profiles (the pantry).** The menu offers the pantry adapter's own stock candidates:

* `handoff:<source>:<destination>:<qty>`: `hold_resource` with purpose `stock_transfer` on the
  source pool for the destination pool, which is the local staff task. It is offered once per
  (source, destination) pair, within the grant's scope and never above the source's available
  units. It is offered only while a staff answer (now + hold duration + staff latency) still
  lands inside the handoff window and before the need's cutoff. It is recorded as an `ask`
  decision (`details.ask = "stock_handoff"`, with `hold_id`, `quantity`, `source_resource_id`
  and `destination_resource_id`) that waits for the staff response;
* `hold:<pool>:<target>:<qty>`: a quantity hold on a pool for a service target
  (`service_target_id`), for the units a candidate with no pending transfer still needs, when
  the pool has them available;
* `apply:<candidate_id>` for a stock candidate. On every profile, an apply that would change
  nothing (no changed activity, required hold or required stock hold: the executor's no-op rule,
  `menu.keeps_the_plan`) is never offered.

The plan stays in question (`menu.stock_improvable`) while a pursuable candidate leaves less of a
target unfulfilled than keeping the plan. Pursuable means applicable now, a handoff that can be
requested or is awaited, or units that can be held. The choice prompt is
`choose_action_pantry.v1`; the model context gains a `stock` block and per-candidate stock
fields; verification needs are an unanswered expected shipment and, while a supply gap exists,
the transfer source. Commit and keep summaries state the coverage ("covers 40 of 40 kits_40 on
time"). While a handoff is awaited the server records `wait` with a wake time (the staff task's
`respond_after`, then its cutoff). Two server-chosen steps mirror `pantry-rules/1.0.0`:

* at the start of each step, a `release` of the policy's own `stock_transfer` holds whose staff
  task is no longer open or is past its cutoff (a stale rejection is retried on a later step);
* once the plan is no longer in question, one `infeasible` decision per under-covered target
  (`details.target_id`, `covered_quantity`, `shortfall_quantity`, `blocking_constraints`,
  `evaluation_id`; `menu.shortfalls` reads the shortfall as P0 does). It is not recorded while a
  handoff is awaited, nor before the handoff window opens while `stock_transfer` blocks better
  coverage.

No option names `record_stock_receipt` or `record_distribution`: only staff attest receipts and
distributions. The recorded P2 development run of pantry_dev01 completed the canonical sequence
with the real model (section 18).

**Caps and failures.** One instance per episode, under the episode caps of section 17: 8 model
calls and 48 tool calls through the host, counting failed calls, repairs, retries and receipt
lookups (`LivePolicy` constructed directly defaults to 8 and 32). A host that rebuilds the
policy for an episode with recorded usage, after a restart, continues its model- and tool-call
counters and seeds its spend guard with the episode's recorded model spend (`resume_usage`), so
the per-run USD cap stays a per-episode cap. Failures are decisions, never invented successes:

| Failure | Decision | `details.failure` |
| --- | --- | --- |
| malformed or invalid output after one repair | `unresolved` notice, or `wait` | `malformed_output`, `invalid_choice` |
| unknown entity | `unresolved` notice | `unknown_entity` |
| model-call or tool-call cap exhausted | `stop`; the episode halts | `model_call_cap`, `tool_call_cap` |
| spend cap (nothing is sent) | `stop` | `spend_cap` |
| missing endpoint configuration | `stop` | `provider_config` |
| provider timeout or error | `wait`, retried 2 minutes later | `provider_timeout`, `provider_error` |
| stale revision | `wait`; re-read and re-evaluate, at most 2 per run | `stale_revision` |
| lost mutation response | reconciled with `get_action_receipt` and the original key (at most 2 lookups and one identical retry); `reconcile` when it cannot be established, and no further mutation in that run | `lost_response` |

**Decision records.** Every decision cites the observation, candidate, report, receipt and
tool-call ids it rests on; `details.evaluation_id` and `details.report_id` name the evaluation.
`details.model` records the requested model, the model id as returned and, for each model call
attributed to the decision, its purpose, outcome, latency, prompt, completion and reasoning
tokens, cost and cost basis, its `provider` and `max_tokens`, plus the episode's usage counters;
each call is attributed to exactly one decision. `details.choice` records the chosen option, the cited ids that name visible records
(others are dropped), the menu, the consumed tool-call ids, and the model's rationale as
`rationale_untrusted` (model text; label it as such wherever it is shown). `details.prompts` maps
each prompt id to its sha256. Summaries are composed by the server from facts. Ask decisions
carry an `AuthorizationRequest` in the rule policy's format.

**Model endpoint.** `PLAN_B_MODEL_PROVIDER`, `PLAN_B_MODEL_BASE_URL`, `PLAN_B_MODEL_KEY_FILE`,
`PLAN_B_MODEL_ID` (default `anthropic/claude-sonnet-5.5`), `PLAN_B_MODEL_MAX_RUN_COST_USD`
(default 0.50) and `PLAN_B_MODEL_MAX_TOTAL_COST_USD` (default 20.00), each from the environment,
else from `.local/keys/model_endpoint.env` (see `apps/plan_b/.env.example`); relative paths
resolve against the repository root. The base URL must be https (plain http only for
127.0.0.1), without credentials or a query. The provider (`plan_b/agent/provider.py`, standard
library only) requests strict structured output (`response_format` json_schema, `strict: true`;
on OpenRouter also `usage.include` and `provider.require_parameters`), has a bounded total
timeout (90 s), never follows a redirect and caps responses at 2 MB. It reads the key file on
each call and sends the key only in the `Authorization` header; error text is scrubbed of it.
`ModelConfig.public()` is the only form of the configuration that leaves the process (no key, no
absolute path).

**Spend.** A spend guard refuses, before sending, a call whose upper-bound cost would exceed the
per-run cap (per episode: each policy instance has its own guard, and a rebuilt instance resumes
the episode's recorded spend) or the cumulative cap of the
ledger `apps/plan_b/var/model_spend.json` (gitignored, mode 0600, written atomically under a file
lock; an unreadable ledger fails closed). The ledger records every call's model as requested and
returned, tokens, cost, cost basis (`provider_usage`, `computed_from_prices`,
`upper_bound_estimate`, `not_billed`, or `not_sent` for a call refused before sending, recorded
at cost 0) and outcome.

**G-LLM gate.** `uv run python -m plan_b.agent.gate --out <file>` runs one `LivePolicy` on a
fresh dev01 episode in a temporary database (caps 6 model calls, 16 tool calls) and passes only
when a strict interpretation validated, a model-chosen query, hold, apply or release ran through
the executor, and a later model call consumed that tool call's result. It exits 0 on pass, 1 on
fail and 2 on a configuration error; the record holds no secret.

## 17. Per-episode caps and policy selection

**Caps** (`scenarios/policy_host.py:EpisodeCaps`). Every coordinator policy, the rule baselines
and the live agent alike, runs under one set of per-episode caps: 48 tool calls and 8 model calls
(`DEVELOPMENT_CAPS`, phase `development`; Wave 3 freezes the final values). Tool calls are counted
from the coordinator's persisted tool-call log, so failed calls, retries and receipt lookups
count; model calls are counted from the decisions that carry them (or the live instance's own
count when that is higher). A run gets at most `min(max_tool_calls, remaining episode budget)`.
Once a cap is reached the host records one `stop` decision (`details.recorded_by = "host"`,
`failure` `tool_call_cap` or `model_call_cap`, `reached`, `caps`, `usage`; the policy's own
`policy_id`) and the runner never wakes the policy again; a direct `host.run` returns `stopped`
with 0 calls. Configurable through `run_case(caps=)`, `plan-b run-case
--max-episode-tool-calls/--max-episode-model-calls`, and `PLAN_B_EPISODE_MAX_TOOL_CALLS` /
`PLAN_B_EPISODE_MAX_MODEL_CALLS` for the server (`api/config.py`). Values below 1 are refused. The
rule baselines use 19-30 tool calls in the development cases; `OutcomeReport.episode_caps`
records the caps and the usage.

**Selection** (`policy_host.PolicyChoice`, `POLICY_CHOICES`, `canonical_choice`). `rules` is the
profile's deterministic baseline (P0). The model-driven choices are `tool-use` (P1,
`tool-use/1.0.0`), `live` (P2, `live/1.0.0`; `selective` is an alias, stored as `live`) and
`verify-all` (P3, `verify-all/1.0.0`); all three share the endpoint configuration and the caps.
`plan-b run-case <case|all> --policy rules|tool-use|live|selective|verify-all` selects it on the
command line; for a model choice, a missing or invalid endpoint configuration prints a message
and exits 2 before any database is created. The moderator chooses per episode with the same
names (422 otherwise; the response carries the canonical choice), at load
(`POST /api/moderator/episodes` `policy`) or later with `POST /api/moderator/policy`, but only
before the episode's coordinator first calls a tool or records a decision (409 `POLICY_LOCKED`
afterwards), so policies never mix within an episode. Selecting a model policy calls no model; it
is refused with 400 `MODEL_NOT_CONFIGURED` when the endpoint configuration is missing or invalid
or the configured key file is absent (a presence check: the key is not read). After a server
restart an episode keeps the policy of its last decision (`choice_of(policy_id)`) and continues
its counters and its recorded model spend; one without decisions reverts to `rules`. A restart without the endpoint
configuration answers 400 `MODEL_NOT_CONFIGURED`, and `/api/moderator/run` resolves the policy
before it moves the clock.

**Mode labels.** The host stamps every stored decision with `details.policy_mode = {policy,
label, caps}`. The label is `Deterministic policy`, `Tool-use agent · <model>`, `Live agent ·
<model>` or `Verify-all agent · <model>`, with the model id returned by the provider; before the
first reply it is the configured model marked `(requested; no reply yet)`.
`OutcomeReport.mode_label`, `GET /api/moderator/policy`, `GET /api/policy`, and the run and
episode responses carry it. `EventStateView` has no label field: before an episode's first
decision only the endpoints show it.

## 18. Comparison policies P1 and P3, and the development runs

P0-P3 are the four policies of `PEEAI_plan/08_evaluation.md`. P0 is the deterministic baseline
(section 11) and P2 the live coordinator (section 16). All four run through `run_case`, the same
`PolicyHost`, episode caps, scripted actors and labeled staff simulator, the same coordinator
grant, tool vocabulary and executor, and the same planner candidates
(`tests/test_policy_parity.py`, `tests/test_live_workflow.py`). P1-P3 use one endpoint, model id
and set of caps, and record their prompts by sha256 on every decision. Their output-token limits
differ, and each call records its own (`max_tokens`): P1 4096 per turn; P2 and P3 1024 per
choice and 2048 per interpretation. Reasoning tokens count against each limit.

**P1, the tool-using baseline** (`plan_b/agent/policies/tool_use.py`, `tool-use/1.0.0`, prompt
`tool_use.v2`). There is no menu: each model turn returns strict JSON (schema
`plan_b_tool_turn`) with `calls` (up to 3; each a `tool` from the grant's `allowed_tools` minus
the staff tools, and `arguments_json`, a JSON object encoded as a string), `done`, a `decision`
(`none`, `keep`, `wait`, `ask`, `infeasible`, `unresolved`, `inapplicable` or `duplicate`),
`ask` (`candidate_id`, `resource_id`, `requested_value`, or null), `wait_minutes`, `rationale`
and `cited_refs`. One run:

1. read the state; stop when the event is over, the episode closed or the grant not valid;
2. the attention rule: when nothing material changed since the model last decided and its wake
   time has not passed, wait without a model call. Material means the plan version, the goal
   version, the observations, the grants, holds, commitments, stock balances, staff tasks,
   distributions and failed or cancelled activities; clock ticks and activity starts and
   completions alone are not;
3. at most 6 model turns. Each turn sees the state, the planner's current evaluation (read with
   `evaluate_candidates` whenever the revision moved, as P2 reads it before each choice; the
   model may also call it, with hypotheses), its previous calls' results and the visible
   observations as quoted untrusted data. The calls run in order through the `ToolClient` with
   key `tooluse-r<revision>-<tool>-<sha8(arguments)>` and the latest observed revision and goal
   version. A turn with `done`, or with no calls, ends the run with its decision, unless its
   calls brought news the model decided without (a status answer with a new observation, or a
   rejection with a new receipt): then the next turn shows the results. After a sent mutation or check, or a lost
   mutation, the next turn sees a fresh state (the model's own state read, when that was its
   last call).

The prompt covers the objective, source timestamps, the budget, the deadline, every tool's
arguments, failure handling and preserving valid commitments. `tool_use.v2` adds what a hold's
window is (the activity's window in the candidate held for, never the handoff window or the
hold's lifetime) and how a `stock_transfer` hold follows a candidate's `stock_transfers` entry
(no service target). A turn may produce up to 4096 tokens, the model's reasoning tokens
included. Holds, applies, releases and checks are recorded from their receipts and envelopes with
server-composed summaries; a `stock_transfer` hold is an `ask` (`details.ask =
"stock_handoff"`). An `ask` decision becomes an `AuthorizationRequest` that the server builds and
checks as the menu checks P2's: a feasible candidate of the latest evaluation short only of
`committed_spend_limit`, one of its bookings, and `current < requested <= used + incremental`.
Its request id is `authreq_r<rev>_<sig8>_<sha8(grant version, resource, value)>`, so a corrected
ask is a new request. An `infeasible` end on a partial stock plan carries
`details.blocking_constraints` and `details.shortfalls`. `details.choice` holds the model call id,
the decision, the calls, `rationale_untrusted`, the cited ids that name visible records and the
consumed tool-call ids.

Failures, as for P2: malformed output, or a tool, decision or request outside what is offered,
gets one repair and is then a `wait` (`malformed_output` or `invalid_choice`), refused before any
call; a cap, the spend cap or missing configuration is `stop`; a provider timeout or error is a
`wait` retried 2 minutes later; a rejected call is recorded with its error code and shown to the
next turn (a stale one with `stale_revision`); a lost mutation response is reconciled with
`get_action_receipt` and the original key (at most 2 lookups and one identical retry), then
`reconcile`, and every later mutation of that run is refused with `lost_response`.

**P3, the verify-all ablation** (`plan_b/agent/policies/verify_all.py`, `verify-all/1.0.0`). P2's
downstream logic (interpretation, evaluation, the robustness rule, the closed menu and its
execution, the same prompts) with one change. Before each decision step the server requests every
due relevant status check, without asking the model which, and only then builds the menu. The
relevance rule `verify-all-relevance/1.0.0` is fixed in the module docstring and names event and
resource identifiers only:

* the current unresolved update is the set of notices held as claims or verify-only notices about
  this event (never `inapplicable`, `duplicate` or retracted) that no successful check of their
  subject requested at or after their arrival has answered, plus, on a consumable profile, an
  open supply gap;
* its relevant resources are each such notice's subject, each approved substitute of that
  subject, and for a supply gap every pool a declared stock option of the target names; a
  resource named by several notices belongs to the latest one's arrival;
* a relevant check is a (resource, fact) whose registered status source lists the resource, in
  the grant's scope, for each fact both the source and the resource's terms declare, while
  `query_status` is granted;
* a check is due when no successful check of it was requested at or after the update's arrival
  and fewer than 2 of this principal's checks of it failed since then (P2's bound); only the
  remaining attempts are made, and nothing waits on a failed source.

Notices that arrive during the checks join the update: the checks are recomputed after each
batch, at most 3 batches per step (`MAX_VERIFY_ROUNDS`). Each check is a `verify` decision chosen
by the server (`details.verify_all = {rule, why, attempt, max_attempts}`), and its result reaches
the next model call. P3 settles after its own checks, so a quiet step makes no model call. Because
P3's checks cost no model call, its model-call counts and P2's measure different things.

**Development runs** (`scripts/run_live_cases.py --policy`, `scripts/write_development_results.py`,
`plan_b/evaluation/development/`). One live trial each of P1, P2 and P3 on dev01, dev02, dev04,
pantry_dev01 and skills_dev01, under the development caps, with `anthropic/claude-sonnet-5.5`
through OpenRouter. The records, traces and evaluator-side reports are in
`PEEAI_plan/handoffs/wave_2/evidence/` (`live_p1-tool-use_*`, `live_p2-live_*`,
`live_p3-verify-all_*`); `plan_b/evaluation/development/README.md` tabulates them with one
sentence per run read from its trace. They are development runs: not the held-out evaluation, no
variance measured, and no comparison between policies is drawn from them.

## 19. Wave 3 pre-freeze policy changes (development-only calibration)

Made before any held-out case or evaluation manifest existed, and checked on the development
cases only. They settle the freeze items of the Wave 2 packet (`PEEAI_plan/handoffs/wave_2/`,
README "What remains" and KNOWN_LIMITATIONS). Where sections 1, 11, 16, 17 and 18 say otherwise
about the items below, this section supersedes them. The runtime contract stays 1.1.0 and the
trace format 1.0.0; no stored record changes shape. Policy ids were bumped only where behaviour
changed:

| Policy | Wave 2 | Now | Why the id changed |
| --- | --- | --- | --- |
| P0, event profiles | `rules/1.0.0` | `rules/1.0.0` | Unchanged |
| P0, pantry | `pantry-rules/1.0.0` | `pantry-rules/1.1.0` | Handoff-window wake; no handoff-blocked shortfall reported before the window opens |
| P1 | `tool-use/1.0.0`, prompt `tool_use.v2` | `tool-use/1.1.0`, prompt `tool_use.v3` | The shared attention rule and wake schedule, the window wake, an ask checked against the state it is made in, the open request remembered; the prompt says when the server calls the model |
| P2 | `live/1.0.0` | `live/1.1.0` | One output limit (choice 1024 → 4096, interpretation 2048 → 4096 tokens), the window wake, the commit of a held planned allocation |
| P3 | `verify-all/1.0.0` | `verify-all/1.1.0` | As P2 (it inherits P2's logic); its relevance rule `verify-all-relevance/1.0.0` is unchanged |
| Provider | `plan_b.provider/1.0.0` | `plan_b.provider/1.1.0` | Generation settings recorded per call, seeds, ledger reservations |

The prompts `interpret.v1`, `choose_action.v1` and `choose_action_pantry.v1` are unchanged.
`tool_use.v3` is `tool_use.v2` plus one paragraph, "When you are called", and a corrected wording
of `wait_minutes`; v1 and v2 stay in `agent/prompts/` because recorded runs cite them. On every
development case (dev01-dev06, skills_dev01/02, pantry_dev01/02) P0, P2 and P3 make exactly the
decisions and tool calls they made before these changes, with scripted models (P0: the
`run-case all` lines are identical to Wave 1 and Wave 2); only P1's changed.

**One attention rule for P1, P2 and P3** (`plan_b/agent/attention.py`, `AttentionMixin`). The
code P2 used to decide whether its menu needs the model now lives in one mixin that P1, P2 and P3
all inherit (the same functions; `tests/test_w3_fix_attention.py`). A model call is warranted when
a new notice arrives that the server cannot resolve (a repeat with the same correlation group and
normalized text is a server-recorded `duplicate`), or when the decision menu built from the
visible state and the current evaluation (`menu.build_menu`) offers an option that acts: a status
check for a stated need, an apply, hold, handoff request or ask while the plan is in question, or
the release of an unused own hold. Otherwise the server records what the state determines (keep,
a shortfall, infeasible, undecided, or a wait for staff or the organizer), `chosen_by =
"server"`, once per state. P2 and P3 interpret each new notice (`interpret.v1`); P1 has no
separate interpretation step, so a new notice warrants its next turn and the rule otherwise
weighs only what rests on no model reading (no claims, no robustness restriction). P1 still sees
every visible observation when it is called, every notice not yet shown included
(`tool_use._observations`). Effect on the development cases, with the scripted P1: 2-4 model
calls per episode instead of 5-7, none after a check-in or arrival record that changes nothing
actionable (`dev01`), and still a turn when a check-in breaks the plan (`skills_dev01`, 10:05).

**Wakes.** Every policy (P0-P3) wakes when the pantry handoff window opens while it is still
ahead (`domain/stock.handoff_window_opening`; no state change marks that moment), besides its
existing wakes. P1, P2 and P3 share one wake schedule (`AttentionMixin._compute_wait`): the
deadline watch (expected equipment ahead of a not-started activity: the earlier of start - 5 min
and reported ETA + 1 min, with one status check offered per watch), the lapse of an open
authorization request's hold, an awaited staff handoff's due time, and the window opening; P1
adds its own `wait_minutes`, retries and turn-bound continuation. A wake is not a model call: the
attention rule decides. No policy reports a shortfall that only a handoff could close before
the window opens (P2 and P3 already did not; P0 now does not either, and P1's server narration
shares P2's). Both development pantry cases open the window at load, so they are
unaffected; `tests/test_w3_fix_window.py` builds a development-only variant whose window opens at
12:42 (P0-P3 now request the handoff after 12:42 and serve 40 of 40; on the Wave 2 code all four
missed it).

**A held planned allocation is committed** (`menu.stock_improvable`). While the keep candidate's
allocation rests only on holds (it still lists required stock holds, so nothing of it is
committed, and uncommitted stock serves nobody), an applicable candidate that commits as much
puts the plan in question, so the menu offers its apply. On the Wave 2 code P2 and P3 held the
24 kits on hand and then kept the plan uncommitted when no handoff was possible, and served
nothing (`test_w3_fix_window.py`, the closed-window variant; P0 already committed them).

**Generation settings** (`agent/provider.py`). Every model call of P1, P2 and P3 uses the same
settings: `max_tokens = MAX_OUTPUT_TOKENS = 4096` (P1's Wave 2 turn limit, which W2-D11 showed is
needed once reasoning tokens count; ample for the shorter replies), strict JSON schema output,
OpenRouter `usage.include` and `provider.require_parameters`, and no sampling parameter: none of
the 8 OpenRouter endpoints of `anthropic/claude-sonnet-5.5` lists `temperature` or `seed`
(public endpoint list, 2026-10-25), and `require_parameters` would refuse a request carrying one,
so every call runs at the provider's default temperature. Each `CallRecord` (in
`details.model.calls`) records `provider`, `max_tokens`, `temperature` (null: not sent), `seed`,
`seed_sent`, `seed_echo` and `system_fingerprint`. The larger limit raises each call's spend
upper bound (about 0.04 USD more at this model's prices), not its actual cost.

**Seeds.** `run_case(db, case_ref, *, policy=..., seed=None, live_config=..., ...)` takes a
keyword-only `seed` and passes it through `policy_factory_for` and the P1-P3 factories to the
provider (P0 ignores it: nothing to seed). The provider sends it as the OpenAI-compatible `seed`
unless the configured model's endpoints refuse it (`provider.SEED_UNSUPPORTED`). The configured
model is in that set: one seeded request on 2026-10-25 was refused by OpenRouter with HTTP 404
"No endpoints found that can handle the requested parameters" and was not billed. Its seeds are
therefore recorded on every call with `seed_sent = false`, and repeated trials are independent
runs, not reproducible ones (the protocol's unsupported-seed case, `08_evaluation.md`).

**The spend ledger across processes** (`provider.SpendLedger`, `SpendGuard`). Several episode
processes may share `var/model_spend.json`. Every ledger update holds a thread lock and an
`fcntl` lock on `model_spend.json.lock`, and replaces the file atomically. Before a call the
guard reserves its upper bound under that lock, against the per-run cap (in the process: one
guard per episode) and the cumulative cap counted as the charged total plus every live
reservation; the charge then replaces the reservation with the actual cost, and a call never sent
releases it. A reservation whose process has ended is charged at its bound (outcome `abandoned`),
so the ledger never counts less than may have been spent. While calls are in flight the file
carries a `reservations` list; once settled it has its Wave 2 shape. `tests/test_w3_fix_ledger.py`
checks this with real processes: no lost update among 8 writers, and with 8 concurrent episodes
the per-run and cumulative caps hold. With the Wave 2 sequence (an unlocked check before the
call, the charge after it) the same 8-episode scenario passed the cumulative cap: 13 calls,
0.052 USD against a 0.026 cap.

**P1's ask is checked against the state it is made in.** Reproduced: an `ask` decided in the
same turn as the hold its candidate needs was checked against the evaluation the turn started
from (revision before the hold, the hold unbound), and the request named that evaluation's
candidate. Now, when the turn's calls moved the state, the server evaluates it again and checks
the ask against the candidate with the same signature there, so the request names the candidate
whose hold is bound (`tests/test_w3_fix_ask.py`). The open request is remembered, as P2 remembers
its own, so the menu offers no repeat of it and the wake schedule looks again before its holds
lapse.

**Changes from the freeze audit** (development-only, before the freeze; the ids above stand,
because none of them was frozen or recorded in a committed run before; the scripted
development decisions of P2 and P3 are unchanged on all nine development cases, P0's
`run-case all` lines are unchanged, and P1's differ on `dev02` only by one more
`evaluate_candidates` read at the 17:05 deadline watch):

* **P1's own wakes are its turns.** A wake the model asked for (its `wait_minutes`, the retry two
  minutes after a failed model call, the continuation after `MAX_TURNS`) now calls the model
  within the caps instead of being judged by the attention rule. Before, a P1 that deferred on
  `dev01` was next called at the 17:05 deadline watch, while P2, whose open claim keeps its plan
  in question, was called again at 16:50; and the failed-call record's "the next wake tries
  again" was not true. `tool_use.v3` was amended before the freeze to say so ("When you are
  called" and the `wait_minutes` wording); the fix sub-wave's scratch smoke used its first text.
* **P1 re-evaluates on a timed wake.** When a wake (its own, the deadline watch, an open
  request's hold, the handoff window) finds the evaluation made at an earlier scenario time at
  the same revision, P1 reads `evaluate_candidates` again: the clock-dependent checks (the
  handoff window, arrival assumptions) may have changed with no new revision. Before, a window
  opening at 12:39 with no state change after P1's 12:36 evaluation was read as "too early" and
  P1 never requested the handoff (24 of 40 kits).
* **A check answers a notice as of its request time** (P2, P3; `AttentionMixin._answer`): a
  status whose checks were all requested before the notice arrived (one in flight when it came)
  no longer answers it, as `menu.VerifyNeed` and P3's relevance rule already said; a status no
  check produced (an arrival record) answers as of its observation time. P3 now checks a notice's
  subject again when the notice arrived during a check of it.
* **P0 retries a transfer hold rejected by a retryable conflict** (`pantry_rules._hold_transfer`):
  a `REVISION_CONFLICT` at the window's opening (an activity starting during the hold's minute)
  re-reads the state and holds again, within `MAX_CYCLES`, as its applies already did.
* **A shortfall is held back only while a handoff could still serve it**
  (`domain/stock.handoff_still_possible`, P0-P3): before the window opens, a shortfall only a
  handoff could close is not reported only if the window opens before the target's deadline.
* **The spend ledger never counts less than may have been spent**: a reservation an earlier call
  of the same run left (an unexpected error after the reply) is charged at its bound before the
  next call; a connection lost after the request went out (reset, closed, a reply cut short) is
  charged at its bound, as a timeout is (an HTTP error status and a failure before sending stay
  unbilled: no completion is returned); abandoned reservations are settled on every ledger
  update; a reservation records its process's start time, so a reused process id is not taken
  for its owner.

## 20. Wave 3 freeze

The comparison is frozen by `plan_b/evaluation/manifests/freeze.json`, written with
`uv run plan-b eval freeze` after the freeze audit and committed with the code it hashes;
`uv run plan-b eval verify-freeze` must pass, and a held-out `plan-b eval run` refuses to start
otherwise. [`docs/EVALUATION.md`](EVALUATION.md), "Wave 3 freeze", lists what the manifest
holds; in short:

| Frozen | Value |
| --- | --- |
| Policies | P0 `rules/1.0.0` (event) and `pantry-rules/1.1.0` (pantry); P1 `tool-use/1.1.0` (prompt `tool_use.v3`); P2 `live/1.1.0` (`interpret.v1`, `choose_action.v1`, `choose_action_pantry.v1`); P3 `verify-all/1.1.0` with relevance rule `verify-all-relevance/1.0.0` |
| Model | `anthropic/claude-sonnet-5.5` through OpenRouter (`https://openrouter.ai/api/v1`), one configuration for P1-P3 |
| Generation | `max_tokens` 4096 on every call, no temperature (none of the model's endpoints accepts one), strict JSON schema output, `usage.include`, `provider.require_parameters` |
| Seeds | 101, 202, 303 for P1-P3, recorded on every call; not sent (`seed_sent = false`: the model's endpoints refuse a seed), so the three trials are independent runs, not reproducible ones. Policy order seed 20261025 |
| Caps | 48 tool calls and 8 model calls per episode (every failed call and retry counts); 0.50 USD per episode (the per-run spend cap); 900 s of wall time per episode |
| Retry rules | one repair of a malformed reply; a provider failure is a visible wait retried at a later wake; a retryable rejection is re-read and retried a bounded number of times; P3 retries a failed source once |
| Measured code | every file under `plan_b/` but the fixture data, manifests, development records, `api/`, `cli.py`, `scenarios/demos.py` and `evaluation/report.py`, plus `pyproject.toml` and `uv.lock`; the runtime (Python and the runtime dependencies' versions) |

Once `freeze.json` exists, every file it hashes is frozen: a change to a measured file, a
setting or the runtime is drift, and invalidates the freeze and any comparison made under it
(`PEEAI_plan/waves/03_evidence_showcase.md`). The held-out cases are locked separately
(`heldout.json`, `plan-b eval lock-heldout`) against this freeze.

## 21. Policy 1.2 (Wave 3b): fixes of the post-release defects

Policy 1.2 fixes the defects that `evaluation/results/wave3_heldout_20261025T1625Z/FAILURES.md`
and `PEEAI_plan/handoffs/wave_3/KNOWN_LIMITATIONS.md` name. That run stays the evaluation of
record of 1.1. Its 12 held-out cases are spent: a run of 1.2 on them is a post-hoc diagnostic
rerun and is labelled so. Only cases locked before the first 1.2 model call can give a new
held-out result.

| Item | 1.1 behavior | 1.2 behavior | Where |
| --- | --- | --- | --- |
| Ids | P1 `tool-use/1.1.0`, P2 `live/1.1.0`, P3 `verify-all/1.1.0` | P1 `tool-use/1.2.0`, P2 `live/1.2.0`, P3 `verify-all/1.2.0`. P0 keeps `rules/1.0.0` and `pantry-rules/1.1.0` (its code is unchanged). Prompts are unchanged, so their ids stay | `agent/orchestrator.py`, `agent/policies/` |
| Unavailable pool | A status check that reports an alternate pool `unavailable` left its handoff ranked `feasible_under_assumptions` and requestable in the menu | The planner fails the candidate's `stock_transfer` check ("reported unavailable") unless the handoff is already held, and `handoff_quantity` offers no handoff from such a pool. `stock_improvable` then no longer keeps the plan in question, so the call-free shortfall report is not withheld | `domain/adapters/pantry.py`, `agent/menu.py` |
| A person's delay | Only equipment notices were material, and `participant_availability` read only check-ins and the declared window | A notice about a person a not-started activity uses is material (`MATERIAL_KINDS`). Without a status source its verification fails at once, so the claimed ETA reaches the planner as a hypothesis. `participant_availability` fails when a person's reported or hypothetical ETA is after the activity's start | `agent/attention.py`, `domain/constraints.py` |
| Repeated non-progress calls | Every wake the P1 model asked for was its own turn. P2 and P3 could be asked again on the same menu at a timed wake | Shared rule (`AttentionMixin._declined_repeat`): when the model passed on a menu (P2 and P3 chose wait or keep, P1 ended its turn without an ask), the same acting options in the same state (revision, goal version) do not warrant another call. A P1 wake from its own `wait_minutes` is its own turn the first time, but a wait asked again on a state unchanged since the model's last wait goes through the shared rule. A retry after a failed call and the turn bound's continuation stay their own turns. On dev01, a scripted P1 that only ever waits makes 4 model calls, against 8 (the cap) with both rules off | `agent/attention.py`, `agent/orchestrator.py`, `agent/policies/tool_use.py` |
| Stale rejection | After `REVISION_CONFLICT` (or another retryable rejection) the state was re-read and the model chose again | P2 and P3 re-issue the rejected option when the re-read menu still offers the same intent with the same candidate signature. The model's choice stands and no model call is spent. The re-reads stay bounded by `MAX_STALE_RETRIES` | `agent/orchestrator.py` |
| HTTP 429 | A rate-limit answer was a failed model call, retried at a later wake | `OpenAICompatibleProvider.complete` waits and sends the same request again: 3 s first (or the reply's `Retry-After`, if longer), doubled per further 429 up to 20 s, at most 60 s of waiting per call (`RETRY_429_*`). Each 429 is its own unbilled ledger entry. The caller sees one call, so a 429 uses no model call of the episode. The final record carries `rate_limit_retries` and `rate_limit_wait_ms`. A 429 that outlasts the bound reaches the caller as before. Provider version `plan_b.provider/1.2.0` | `agent/provider.py` |
| Report | The "Policy identifiers" line was sorted alphabetically | The line lists `P0 <id>`, `P1 <id>`, `P2 <id>`, `P3 <id>` in that order | `evaluation/report.py` |

Equal treatment is unchanged. P1, P2 and P3 keep one model, one output limit (4096 tokens) and
the same caps (48 tool calls and 8 model calls per episode, 0.50 USD per run, 900 s per
episode). No cap changed. The 429 wait adds at most 60 s to a call's wall time, so an episode
whose every call is rate limited for the full bound can reach the 900 s episode timeout. Run
one LLM episode at a time (`--jobs 1`).

The planner changes are shared code, so P0 reads them too. On the development cases P0's
outputs are unchanged: `plan-b run-case all` before and after the change gives the same 27
files once each run's random episode ids and the hashes that cover them are masked. P0 can
differ from 1.1 only on a case where an alternate pool is checked unavailable or a person has a
reported ETA. P0's policy ids (`rules/1.0.0`, `pantry-rules/1.1.0`) stay, because its own code
did not change and its development outputs are unchanged. The shared planner carries its own
version instead: `PLANNER_VERSION = "plan_b.planner/1.2.0"` in `domain/constraints.py`, which
the freeze records as `planner_version` and `verify-freeze` checks like the other settings. A
P0 result under the v1.2 freeze is therefore a result of `rules/1.0.0` or `pantry-rules/1.1.0`
on planner 1.2.0, not on the 1.1 planner.

Known limits of 1.2, found by the `audit2` audit before the freeze and left as frozen. The
audit changed no policy behavior. The auditor had already seen the fresh held-out cases, and a
change by the auditor would break the rule that whoever changes policies never sees them.

- A person's delay hypothesis outlives a later check-in. `orchestrator._hypotheses` keeps the
  claimed ETA while the claim's verification has failed, and a check-in is not a status, so it
  never answers the claim. `_participant_availability` reads the ETA before the check-in. A
  person who reports a delay and then checks in on time still fails the check until the
  activity starts, for P2 and P3 alike (P1 writes its own hypotheses).
- The declined-menu key is (revision, goal version, acting intents) and holds no time. When
  only the clock moves, a timed wake (the deadline watch, a passed ETA, an ask's expiry) with
  the same acting options gets the server's default record, not a model call. This is the
  trade-off named above, and it reaches the deadline watch too.
- P1 notes a declined menu with the view after its own turn, so the key can pair a new
  revision with the menu offered before the turn. This mostly makes the rule miss, not
  over-suppress.
- A stale re-issue is recorded as the model's choice (`chosen_by` `model`) with the earlier
  call's id, and only a run note marks it. Metrics that count model choices count it twice.
- A `Retry-After` above 20 s is cut to 20 s, and the 60 s bound counts waiting only, not the
  time of each attempt.

Tests: `tests/test_w3b_policy_fixes.py` (a synthetic pantry_dev01 variant whose partner desk
reports the kits booked elsewhere, a person hypothesis on the development fixture, the declined
menu rule, P1's repeated waits on dev01, the 429 backoff, the stale re-issue on the dev01
sandbox, the report order). `tests/test_w3b_heldout2_harness.py` covers the second held-out
set's harness.
`tests/test_agent_boundary.py::test_stale_revision_retries_are_bounded` now makes every apply
stale at the tool boundary, since 1.2 re-issues the choice without asking the model.
