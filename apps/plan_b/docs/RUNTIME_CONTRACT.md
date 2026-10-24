# Plan B runtime contract 1.0.0 (Wave 1)

This is the frozen interface for the Wave 1 deterministic campus sandbox. The Pydantic models
in [`plan_b/domain/models.py`](../plan_b/domain/models.py) are the machine-readable form; this
document gives their semantics. Where they disagree, fix the disagreement rather than choosing one.

Everything here is a **fictional local sandbox**. A hold, booking, check-in, or plan change is a
real mutation of the local SQLite store and nothing else. No university booking, purchase,
delivery, or message is made.

## 1. Versions and relationship to the planning bundle

| Contract | Version | Where |
| --- | --- | --- |
| Planning artifacts | 0.2.0 | `PEEAI_plan/schemas/planning.schema.json` (unchanged by Wave 1) |
| Runtime contract | 1.0.0 | `models.RUNTIME_VERSION`, this file |
| Trace format | 1.0.0 | `models.TRACE_VERSION`, section 13 |
| Store schema | migrations `0001_initial.sql`, `0002_scheduled_actions.sql`, `0003_history_guards.sql` | `plan_b/store/migrations/` |

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

## 2. Identity, sessions and authority

Identity comes only from a server-validated session. A request body never establishes actor,
role, grant or source: `ToolRequest` has no such fields and unknown fields are rejected.

* **Bearer tokens.** `Authorization: Bearer <token>`. Tokens are 32 random bytes (urlsafe); the
  store keeps only their SHA-256. Sessions bind `(episode_id, principal_id, role, grant_id)`.
* **Moderator.** The sandbox operator signs in with the moderator code (environment
  `PLAN_B_MODERATOR_CODE`, or generated at startup and written to `var/moderator_code.txt`,
  mode 0600). The moderator session is not an event principal: it can load/reset episodes,
  advance the clock, run the deterministic policy, issue join codes and export traces. It
  cannot call event tools.
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

## 3. HTTP API

All responses are JSON. Tool calls always return a `ToolEnvelope` body; the HTTP status is
200 for any envelope produced after authentication (including business rejections), 401 for a
missing/invalid/closed session, 403 when a moderator session calls an event tool, and 400 for
a body that fails `ToolRequest` or argument validation. Other endpoints return FastAPI errors
`{detail: {code, message}}`: 401 (no or bad session), 403 (not a moderator), 400 (bad input),
404 (unknown replay), 409 `NO_EPISODE` (moderator state read before any episode is loaded).

| Method and path | Auth | Request → response |
| --- | --- | --- |
| `GET /api/health` | none | → `{ok, runtime_version, mode}` |
| `POST /api/auth/moderator` | none | `{code}` → `{token, role, principal_id, display_name}` |
| `POST /api/auth/join` | none | `{code}` → `{token, role, principal_id, display_name, episode_id, event_id, grant_id}` |
| `GET /api/auth/whoami` | any | → `{role, principal_id, display_name, episode_id, grant_id}` plus `{event_id, episode_status}` for event sessions |
| `GET /api/state` | any session | → `EventStateView` for the caller (moderator: organizer-level visibility of the current episode) |
| `POST /api/tools/{tool}` | event session | `ToolRequest` → `ToolEnvelope` |
| `GET /api/moderator/cases` | moderator | → `[{case_ref}]` only (no private descriptions) |
| `POST /api/moderator/episodes` | moderator | `{scenario_id, case_ref}` → `{episode_id, event_id, clock, revision}`; loads a clean episode and closes every other active episode (reset) |
| `GET /api/moderator/current` | moderator | → `{episode_id}` (null before the first load) |
| `POST /api/moderator/sessions` | moderator | `{principal_id}` → `{join_code, join_path, principal_id, role, display_name}`; refuses `coordinator_agent`; codes are one-time and expire after 10 wall-clock minutes |
| `POST /api/moderator/clock` | moderator | `{advance_minutes: 1..240}` → `{clock, revision, transitions}` |
| `POST /api/moderator/policy/run` | moderator | `{max_tool_calls?: 1..64}` → `PolicyRunResult` plus `episode_id`, `episode_status` |
| `POST /api/moderator/run` | moderator | `{minutes: 1..240, policy: bool}` → `{clock, revision, policy_runs}`; advances minute by minute, running the policy when public state changed (no scripted actors) |
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
| `hold_resource` | mutation | 1 | Provisional hold: capacity + reserved exposure |
| `release_hold` | mutation | 1 | Releases an active hold, returns its reserved exposure once |
| `apply_plan` | mutation | 1 | Revalidates a stored candidate and replaces the active plan |
| `check_in` | mutation | 0 | Participant's own presence and availability interval |
| `submit_observation` | mutation | 0 | Append an immutable observation; content is data |
| `update_goal` | organizer control | 0 | New goal version (preference preset) |
| `update_grant` | organizer control | 0 | New version of another principal's grant (limits, revoke) |

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
| `apply_plan` | `{plan: PlanView, converted_hold_ids: [...], commitment_ids: [...]}` |
| `check_in` | `{checkin: CheckInView, observation: ObservationRecord}` |
| `submit_observation` | `{observation: ObservationRecord, deduplicated: bool}` |
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
`apply_plan`, `check_in`, `submit_observation`, `update_goal` and `update_grant`. The other tools
are reads.

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
   session by the same executor, in registration order.
3. **Hold expiries** (`expires_at == t`). A hold is usable only while `clock < expires_at`.
4. **Grant expiries** (`expires_at == t`). A grant is valid only while `clock < expires_at`.
5. **Activity starts** (`scheduled start == t`): strict execution readiness; ready → `started`,
   otherwise → `failed` with the unmet reasons.
6. **Event close** at `goal.hard_end`.

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

## 10. Planner (campus adapter)

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
  grant and registered resources.

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

## 11. Deterministic rule policy (P0, `rules/1.0.0`)

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
(`max_tool_calls`, 16) bounds one policy run; a run that exhausts it is woken again with a fresh
budget, so Wave 1 has no per-episode cap. It stops if the episode is reset meanwhile: a closed episode's clock never moves, no session is
issued for it, a policy run that loses its episode returns `stopped`, and its decisions are not
written into the closed episode. Moderator controls that race a reset answer 409
`EPISODE_CLOSED`, and run responses carry `episode_id` and `episode_status`.

Scripted exogenous actors (participant check-ins and observations; the simulated organizer that
answers an open, in-bounds `AuthorizationRequest` after its declared latency via `update_grant`)
are registered as **scheduled actor actions** (`scheduled_actions` table, private) with the
actor's own server-held session. The clock engine executes each one at its exact instant
(section 6) through the same executor, so the instant does not depend on what any policy is
doing: a policy's tool duration that spans the instant processes it like a world event. A
scheduled organizer action is validated against the state at that instant (as if read just
before acting). Scheduled tools must have zero duration. Scripted actors are identical for every
policy. The runner never writes check-ins, observations or grants directly and never tells the
policy what to do. In the browser, scripted actors are off: people act through role tabs.

**Scoring.** `evaluation/scoring.py:score_episode(final, history, case)` scores from persisted,
visible records only. It dispatches on `final.profile_id` to
`DomainAdapter.score_outcome(final, history) -> DomainOutcome(activities, goal_attained, unmet,
violations)`, then appends the domain-independent spend-limit violations (`budget`,
`reserved_negative`, `grant_limit`). The goal is complete when the adapter finds it attained and
no violation was executed. The campus adapter's part is `domain/adapters/campus_outcome.py`.
Readiness goes through `DomainAdapter.check_readiness(..., mode=)`: the clock engine uses
`execution`, and the projection uses `preview` for the episode's own profile. Still
campus-specific in the core are `scoring.HARD_CHECK_IDS` (used by the `infeasibility_reported`
predicate) and the `equipment_before_arrival` category named by the
`no_equipment_start_before_arrival` predicate.

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
`plan-b run-case` records the id of the policy its runner ran.

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
