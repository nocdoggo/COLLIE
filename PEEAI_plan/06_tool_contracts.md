# Stateful tool contracts

Status: proposed contracts, 2026-10-23. Tool names in this document define the planned API surface. No tools are implemented by the planning documents.

The initial executor operates on the local event sandbox. A resource hold has real effects inside that sandbox. It does not reserve university property or create an external purchase. Every visible action receipt includes the environment boundary.

## Common request and response rules

Read operations require an event identifier and an authenticated caller resolved from the session. Mutations additionally require `expected_revision`, `idempotency_key`, and `grant_id`. The server resolves caller identity. Text supplied to a model or a message body cannot impersonate an organizer or participant.

The planning artifact schema is [schemas/planning.schema.json](schemas/planning.schema.json). Its initial version covers the example artifacts and selected request shapes. It is not a complete HTTP API schema. The semantics below define requirements for the future runtime. Cross-record references, capacity overlap, and authority scope require runtime checks even when JSON is valid.

All tool responses carry an explicit status, event scope, resulting or observed revision, server time, and either typed data or a structured error. Mutations produce an `ActionReceipt`, including the operation, result, relevant identifiers, and before/after revisions. Errors are available to the agent as errors, not fabricated natural-language success.

Use the following transport and read-result envelope vocabulary:

| Outcome | Meaning |
| --- | --- |
| `succeeded` | Requested operation completed and the receipt is durable |
| `rejected` | A known precondition or authorization condition failed |
| `unknown` | The requested real-world or modeled fact could not be established |
| `unavailable` | The tool service could not respond successfully |

Within a successful status query, the resource can itself be unavailable. Keep that domain result distinct from tool-service failure. Structural schema naming can vary, but this semantic distinction is mandatory.

`ActionReceipt.status` uses the artifact schema's separate vocabulary: `applied`, `rejected`, or `unknown`. A successful mutation returns a `succeeded` transport envelope containing an `applied` receipt. A received rejection can return its durable `rejected` receipt. A transport timeout or unavailable service does not prove the mutation failed. Reconcile the original idempotency key before deciding whether its receipt is `applied`, `rejected`, or still `unknown`.

## MVP tool surface

| Tool | Inputs beyond common envelope | Output | State behavior |
| --- | --- | --- | --- |
| `get_event_state` | Optional projection selector | Visible `EventState` and revision | Read only, with expiration reflected correctly |
| `get_action_receipt` | Original idempotency key, caller resolved from session | Original durable receipt, pending, or not-found status | Read only. Scoped to the caller/event or explicit organizer review authority |
| `list_resources` | Capability and time-window filters | Registered resources, terms, availability observations | Read only |
| `query_status` | Target identifier, requested fact | Scoped `Observation`, source time, validity, unknown if unresolved | May append a new observation and advance revision |
| `evaluate_candidates` | Current goal version, allowed edit templates or candidate IDs | Feasibility reports, scored candidates, assumptions | Pure evaluation against one snapshot |
| `hold_resource` | Resource, interval, quantity, expiry, bounded cost | Hold identifier, terms, expiry, receipt | Reserve local capacity and budget atomically |
| `release_hold` | Hold identifier and reason | Released or already-terminal receipt | Release local capacity and refundable reserved budget |
| `apply_plan` | Candidate identifier, expected goal version, constraint-report reference | Accepted plan, commitments, receipt | Load candidate and its supporting holds, revalidate, then atomically replace active plan |
| `check_in` | Participant identity resolved or scoped by grant, availability interval, assigned role | Availability observation and receipt | Update participant's declared availability |
| `submit_observation` | Message or structured community update, referenced entity if known | Immutable observation identifier and revision | Append input without treating its content as an authorized action |
| `record_stock_receipt` (Wave 2, staff only) | Destination, quantity, unit, source observation, unique receipt reference, optional registered source and its hold, optional shipment ID | Handoff/receipt state changes and durable receipt | Atomically transfer registered stock or receive a verified external shipment |
| `record_distribution` (Wave 2, staff only) | Resource, quantity, unit, service target, committed reservation IDs, unique distribution reference | Consumption and service-progress receipt | Consume reserved physical stock and record target-linked distribution once |

An organizer goal update can use a dedicated UI endpoint in the MVP. It must create a new `EventGoal` version and invalidate candidates based on the old goal. This endpoint follows the same revision and authority rules as other mutations.

## Read and evaluation contracts

### `get_event_state`

Return only facts visible to the caller's role. Agent access includes current activities, resources, accepted plan, relevant observations, active holds, cost accounting, deadlines, and applicable authority. Exclude private scenario labels, hidden future schedules, evaluation truth, and private participant contact details.

An expired hold must never appear as usable simply because a cleanup job has not run. The projection evaluates expiry against the server's current time, and the mutation path independently checks it.

### `query_status`

Queries target a specific resource, booking, participant role, or other registered entity. Responses identify what was checked, when the source observed it, and when the query occurred. A query can legitimately return unknown, conflicting, or stale information.

For a sandbox supplier query, the scenario runner supplies a response from the declared observation model at the current scenario time. It does not supply the entire incident truth or future trajectory. For participant availability, the agent may read the participant's submitted check-in, not fabricate a response on their behalf.

If a result introduces new evidence, ingest it through the observation pipeline and return the resulting state revision. Repeated retrieval of the same source record should not manufacture a fresh independent observation or advance the revision unnecessarily.

### `evaluate_candidates`

Evaluate against one fixed `EventState` revision and `EventGoal` version. The result records the candidate's feasibility, reasons for rejection, objective components, required holds, and unresolved assumptions.

Evaluation has no booking side effects. A candidate that was feasible when evaluated may later fail to commit. The caller must use the latest post-hold revision and re-evaluate or revalidate after acquiring resources.

## Mutation contracts

### `hold_resource`

Validate resource existence, capability, owner terms, quantity, requested interval, expiry, budget, and caller authority. Check overlap against both accepted commitments and other live holds. Create one hold and one receipt in a transaction.

A hold is useful only if its expiry extends past the intended commitment decision. It can still expire before the activity itself if it is converted to a confirmed reservation in time. Display the commitment cutoff separately from the activity start.

Represent reserved spending separately from incurred spending. A resource may have a nonrefundable holding fee and a later commitment fee only if those terms were configured and shown before the hold. The total potential exposure must fit the grant and event budget.

A failed hold creates no partial capacity reservation or budget deduction. Repeating the same request with the same idempotency key returns the original receipt.

### `release_hold`

Only the holder, an authorized organizer, or a delegated agent can release a hold. A release returns refundable reserved budget according to its terms. It does not erase incurred holding fees.

Already released or expired holds return a terminal-state result without another refund. A hold converted into a commitment cannot be released as though it were still provisional. Commitment cancellation requires an explicitly supported plan update and valid cancellation terms.

### `apply_plan`

The application server loads the stored candidate and performs the following checks inside the write transaction:

1. The idempotency key has not already completed an equivalent request.
2. The caller, event, authority grant, goal version, and expected state revision match.
3. The candidate was generated from valid inputs and references current registered entities.
4. Every required hold is live, owned by the event, and convertible under its terms.
5. Dependency, time, role, capacity, resource, accessibility, and budget constraints still pass.
6. The proposed changes are permitted by the authority grant and preserve locked activities.

If all checks pass, update the active plan, convert the required holds to commitments, release superseded resources only where terms permit, update cost accounting, increment the revision, and insert the receipt atomically. If any check fails, leave the operational state unchanged and return the failure details.

The mutation can reject a candidate for missing evidence that its assumptions require. It must distinguish “current resource is unconfirmed” from “candidate violates a known hard constraint.” Neither is resolved by a confident model explanation.

A schedule can be accepted conditionally on an expected future arrival if the declared scenario policy permits that uncertainty and the assumption remains explicit. This action reserves the future schedule, not a claim that the equipment has arrived. The execution guard checks actual observed arrival before starting the dependent activity. This permits the example's early schedule swap while preserving honest treatment of unknown arrival time. A plan needing an immediately available resource cannot use the same assumption to bypass its readiness check.

### `check_in`

A participant can declare their own arrival and availability through an event-scoped link. A volunteer coordinator may update an assigned volunteer only if their grant permits it. A public audience member cannot check in every volunteer or change organizer priorities.

Check-in means a participant has declared presence or availability. It does not establish qualifications, accessibility capabilities, or equipment competence unless those were already part of the registered role. It does not automatically assign the participant to an activity. Assignment occurs through a checked plan update.

The prototype can use predefined participant aliases and scoped demo tokens. Avoid collecting unnecessary identifying information for a public showcase.

Declared future availability and observed check-in are separate facts. A facilitator may have agreed to cover a later slot while still being absent now. The planner may retain that future assignment under its stated assumptions, and the execution guard checks the required readiness at the activity's start. A coordinator grant does not automatically grant the participant's own check-in operation. The participant session resolves to its separate event-scoped grant.

### `submit_observation`

Store the source, receipt time, source time if provided, event scope, raw content, and references. Assign trusted provenance on the server. Interpret instructions in the content as statements to analyze, not privileged commands.

An offer such as “I can bring a projector” is a claim. Activating a preconfigured backup entry requires the expected owner confirmation and capability fields. The offer itself cannot create a reservation, exceed capacity, or grant spending permission.

## Revision and idempotency behavior

### Pantry mutation semantics

These additions are required for the second-domain build. They do not change the campus resource model. See [the pantry specification](15_pantry_showcase.md) and [data model](07_data_model.md).

For a resource carrying `consumable_stock`, `hold_resource` reserves physical units globally across future time windows. A kit cannot be allocated again merely because two activities do not overlap. Check `quantity <= on_hand_quantity - reserved_quantity`, maintain the reservation ledger atomically, and ensure its sum matches the stock projection. Expected shipments supply zero reservable physical units. A provisional hold's expiry releases only its still-unconsumed units. A committed allocation survives provisional expiry until explicit authorized cancellation or consumption. Distribution is irreversible in the first adapter.

`record_stock_receipt` takes `resource_id` (destination), `quantity`, `unit`, `source_observation_id`, `receipt_reference`, and the common mutation envelope. A registered internal transfer additionally requires `source_resource_id` and `source_hold_id`. Verify distinct source/destination, identical registered units, staff scope over both, physical source stock, destination storage capacity, and an active source hold owned by this event with sufficient remaining quantity. Atomically debit source on-hand and reserved quantities by the received amount, credit destination on-hand, decrement the source hold's `remaining_quantity`, and write a receipt. Partial handoffs preserve the unconsumed reservation under its original expiry. When remaining quantity reaches zero, mark the hold `fulfilled`. The destination is not automatically reserved. An internal handoff does not change an unrelated expected shipment or record distribution.

For a genuinely external receipt, require an authorized staff attestation and unique physical receipt reference. A matched expected shipment also requires `shipment_id`, verifies destination and remaining quantity, increments `received_quantity`, and reduces the corresponding expected stock projection. A newly reported donation without an expected shipment needs its own source observation and explicit staff authority. The demo does not require this extra donation path. Reject unmodeled returns, unregistered unit conversions, and negative corrections rather than guessing their accounting.

`record_distribution` additionally binds `service_target_id`, the current goal version and distribution activity, and the committed reservation IDs being consumed. Staff attest an aggregate quantity without recipient records. Check unit compatibility, available committed physical quantity, staff readiness, original target, and remaining modeled throughput. Decrement on-hand and reserved quantities together, advance the resource distribution total and `EventState.service_progress`, and consume reservation quantities atomically. Reject quantity beyond the original remaining target. A late physical distribution within the staff grant/event window can be recorded truthfully, but retain its actual time and missed-deadline outcome. It cannot retroactively count toward on-time achievement or rewrite a completed activity. Partial service remains visibly incomplete. Resource counters and cumulative service progress come from receipts; the evaluator separately sums only timestamp-eligible distribution toward the original deadline.

Deduplicate `receipt_reference` and `distribution_reference` within the appropriate event/source namespace as well as transport idempotency keys. A fresh transport key must not create a second credit for the same physical handoff. Store enough immutable request fields to reject a conflicting reuse of a physical reference. Both new tools are absent from the coordinator agent's grant. Their existence in the interface does not let the agent impersonate staff.

In the development fixture, a staff session can receive 16 units from partner stock into pantry stock, and later record distribution under a committed allocation. The two operations occur at distinct scenario times. An agent-held backup is useful preparation, but receipt and service remain separately observed actions.

For a stock transfer, `hold_resource` additionally records `purpose: stock_transfer` and `destination_resource_id`. A valid hold creates a pending local staff task. This is an in-application request, not an external notification or physical action. Staff can accept, decline or partially fulfill it. The evaluator exposes an identical response rule to all policies. DEV03 declares a two-minute response interval in `pantry_parameters`, ending before the exclusive 12:50 hold cutoff. A hold acquired too late does not trigger a backdated staff response. Uncompleted tasks and expired holds remain visible. In DEV03 the two minutes are response latency, and same-venue confirmation is permitted as part of setup. It is not modeled as a separate exclusive staff activity. A later workflow with transport or additional physical work must schedule that labor and check capacity explicitly.

The typed pantry parameters specify one kit per qualified staff minute. The runner records actual execution intervals after committed allocation, reserved stock and staff readiness hold. Available distribution capacity is the floor of the rate times those elapsed minutes, minus units already distributed. A commitment at 13:10 cannot claim forty minutes of service at 13:40. A completion exactly at the inclusive 13:40 service deadline is processed before the deadline-close and reconciliation-start events at that timestamp. Expiry cutoffs for provisional holds remain exclusive. Declare this same-time event order in the runner and test it.

## Shared revision and idempotency behavior

Use a unique key scoped by event, authenticated caller, and idempotency key. Store a canonical request digest with the result. If the same key arrives with a different request body, reject it as an idempotency conflict.

For an identical retry, return the original durable receipt before rechecking the original expected revision. Otherwise a successful write followed by a lost response would be mistaken for a stale new request. For a new request, validate the current revision before applying any write.

The exact transaction order is:

```text
begin transaction
  resolve actor and event
  find prior idempotency record
  if identical completed request exists: return stored result
  if same key has different digest: reject conflict
  validate current revision and authority
  evaluate expiry and all operation preconditions
  apply mutation and update cost/capacity ledgers
  advance event revision
  store durable receipt and idempotency record
commit transaction
```

Concurrent writes use SQLite transaction serialization plus revision checks. A generic compare-and-swap check without a transaction is insufficient because two requests can both observe the same capacity before either writes.

If a mutation response is lost, reconcile by idempotency key. Do not automatically create a new key and repeat the action. Read requests can use bounded retries. Mutation retries must preserve identity.

Use `get_action_receipt` for that lookup, scoped by event and authenticated actor. `pending` is not failure. A not-found response is not permission to create a fresh request identity: retry the original key, whose transaction-level deduplication resolves races. An identical completed retry returns its original receipt before checking the now-stale expected revision.

## Time semantics

Use server-owned UTC timestamps and an explicit event timezone for display. `America/New_York` is the initial display timezone. A scenario uses an injected clock so accelerated playback, expiry, and evaluation share one time source.

Do not mix browser wall time with scenario time. Participant messages are received at the current scenario time during a live sandbox session. The original wall-clock receipt can be recorded separately for diagnostics if useful.

Advance the clock only through the scenario runner or a designated moderator control. The language model cannot move time backward, extend a hold by changing a field, or create an action before it was authorized.

## Authority as data

An `AuthorityGrant` names the actor, event, permitted operations, resource or activity scope, cost limits, validity period, and any required human decision. A goal can allow the agent to make low-cost holds and reorder independent activities while reserving cancellations or higher-cost alternatives for the organizer.

The authority boundary should support a fluid demo. Setup can explicitly delegate the ordinary sandbox actions once. The agent then acts within that grant without asking for repetitive confirmation. Actions beyond the grant produce a concrete proposed change and the specific missing permission.

A message saying “ignore the budget” cannot modify the grant. A legitimate organizer changes it through the authenticated control, creating a recorded revision.

## Structured error cases

| Error | Recovery |
| --- | --- |
| `REVISION_CONFLICT` | Refresh state and recompute affected candidates |
| `GOAL_VERSION_CONFLICT` | Re-evaluate using the current goal |
| `IDEMPOTENCY_CONFLICT` | Correct the client request identity, preserve existing result |
| `GRANT_REQUIRED` or `GRANT_EXPIRED` | Present the exact requested authority change |
| `HOLD_EXPIRED` | Reacquire if still possible and authorized, then revalidate |
| `RESOURCE_CONFLICT` | Evaluate alternatives or request a specific tradeoff |
| `BUDGET_EXCEEDED` | Show the cost gap and permitted options |
| `CONSTRAINT_VIOLATION` | Return violated constraints and affected activities |
| `STATUS_UNKNOWN` | Preserve uncertainty and evaluate time-sensitive alternatives |
| `INVALID_EVIDENCE_REFERENCE` | Repair the interpretation using actual observations |

These error names are proposed implementation constants. Their substantive meanings should be retained even if the final API uses a different spelling.

## Required contract checks

Prioritize tests that could expose consequential bugs: two competing holds, a lost mutation response, a hold expiring between evaluation and commitment, a grant expiring mid-session, duplicate check-in submission, a stale status response, and an attempted cross-event action. Verify both the returned receipt and resulting database state. An assertion that a mocked tool was called is insufficient evidence of correct execution.
