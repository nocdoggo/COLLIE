# Data model, provenance, and scenario boundaries

Status: proposed domain model, 2026-10-23. Machine-readable planning artifacts live in [schemas/planning.schema.json](schemas/planning.schema.json), version **0.2.0**. The bundle covers example records and selected request shapes, including the pantry quantity extension. The complete runtime must also enforce the behavioral invariants in this document and store the supporting records described below. Examples in [examples/](examples/) are synthetic design fixtures, not evidence of a running application. Updating these planning artifacts does not establish runtime backward compatibility or a deployed-data migration.

## Canonical entities

| Entity | Meaning | Essential invariants |
| --- | --- | --- |
| `EventGoal` | What the organizer is trying to achieve, with explicit constraints and preferences | Versioned, event-scoped, changed only by an authorized actor |
| `Activity` | One scheduled unit of the event, with duration, dependencies, requirements, and allowed alternatives | Stable identifier, valid time window, no dependency cycles |
| `Resource` | A registered item or capacity usable by an activity, including approved volunteer roles | Capability, quantity, availability, owner, and cost terms are explicit |
| `Observation` | A received message, check-in, status response, or outcome record | Immutable content and provenance, distinct observation and receipt times |
| `ChangeSpec` | A typed interpretation of observations that could affect the plan | References real observations and entities, makes uncertainty explicit |
| `CandidatePlan` | A proposed schedule and allocation with assumptions and a constraint report | Bound to a state revision and goal version, has no effect until applied |
| `ActionReceipt` | A durable record of a tool action and its result | Binds actor, request identity, state transition, cost, and execution status |
| `AuthorityGrant` | Explicit permission to perform scoped operations | Server-issued scope and limits, validity interval, revocation behavior |
| `ScenarioDefinition` | A profile and configured scenario specification | Public planning inputs separated from private future truth |
| `EventState` | Current visible operational state at one revision | Internally consistent projection of accepted observations and executed actions |

Additional implementation records include resource holds, committed allocations, cost ledger entries, participant role assignments, and idempotency records. They support the canonical entities rather than introducing competing concepts.

The campus showcase and community skills exchange use the activity/resource core. [Pantry Continuity](15_pantry_showcase.md) adds explicit consumable stock and aggregate service accounting. The additions are capability fields, not instructions to reinterpret an equipment count as people served. They reuse the state, authority, evidence, and receipt mechanisms while extending the domain semantics.

## `EventGoal`

A goal includes the event window, required outcomes, venue boundary, capacity, budget, required accessibility provisions, fixed commitments, and preferences among feasible alternatives. Every goal has a version. Changing a priority produces a new version, so the system can explain why a formerly preferred candidate changed rank.

Distinguish a hard budget ceiling from a preference for lower spending. Distinguish a mandatory activity from an optional activity whose loss incurs a penalty. Do not infer priorities from demographic labels or a participant's social position. Let organizers state them explicitly.

Store the event timezone alongside UTC time values. Fictional future fixtures should be labeled as examples. They do not imply actual university dates, venue reservations, or program deadlines.

`EventGoal.service_targets[]` is optional for profiles without quantity goals. Each entry has `target_id`, `unit`, positive integer `quantity`, `deadline`, and `activity_id`. Resolve each target to an existing activity and compatible stock unit. The pantry fixture has target `kits_40`, unit `standard_kit`, quantity 40, linked to `distribution`. The original quantity and deadline remain the evaluation reference. An authorized later goal version must not rewrite the record of whether the original target was met.

`attendance_target` remains an occupancy-planning quantity. Its pantry value of 12 does not count unique recipients or kits distributed. The separate 40-kit service target supplies that quantity objective without introducing recipient records. The modeled staff capability of 40 kits during 40 minutes is an authored scenario assumption, not measured pantry throughput.

## `Activity`

An activity has a duration, earliest allowed start, latest allowed finish, dependencies, resource requirements, and participant roles. The activity graph must be acyclic. An activity cannot begin before its prerequisites complete.

Separate the activity definition from its placement in a plan. The same workshop can move from one permitted slot to another without becoming a new activity. An approved equipment-free alternative is an explicit variant with its own requirements and duration.

Lifecycle states should distinguish planned, ready, started, completed, canceled, and failed. Started or completed activities become fixed history. The agent cannot rewrite their times to make a final score look better.

For the first campus profile, the common activity concepts are setup, welcome, demonstrations, skills exchange, and closing. The community profile can change labels, durations, priorities, and resource requirements while using the same planner. It must not require a new hard-coded agent workflow.

## `Resource` and allocation records

Resources include equipment kits and registered role capacity. An item has a stable identifier, compatible capabilities, quantity, available windows, and terms. A volunteer's role eligibility is established separately from the volunteer's observed availability.

The initial fixture's `expected` resource status means a future arrival or availability is assumed, not physically observed. A person's declared future availability also differs from their check-in. Retain both facts and enforce the scenario's readiness requirements at execution time.

Resource availability should distinguish known available, known unavailable, and unresolved. A fresh source observation can update that status. A verbal offer alone does not establish technical suitability or availability.

Allocation records distinguish:

| Allocation state | Operational meaning |
| --- | --- |
| Offered | A community source has suggested availability, pending required confirmation |
| Available | Registered resource has usable availability under the modeled facts |
| Held | Capacity is temporarily reserved until expiry or explicit release |
| Committed | Capacity is assigned to the accepted plan under its terms |
| Released | A provisional hold or cancellable allocation was relinquished |
| Expired | The provisional reservation lost validity at its cutoff |
| Fulfilled | A consumable reservation has no remaining units after its recorded handoff or distribution; it cannot release units again |

These are allocation or availability concepts, not necessarily a single resource status enum. A resource with capacity two can have one committed unit and one available unit. Model intervals and quantities explicitly.

A fixed venue's attendee capacity is a different quantity from concurrent program capacity. The example room can accommodate its declared number of attendees while still allowing only one main activity at a time. Check these two limits separately.

Budget accounting should separate total budget, incurred spending, refundable reserved exposure, and remaining spendable amount. Holding and commitment fees must not be counted twice. Expiration cannot refund an already incurred fee.

## Consumable stock, reservations, and conservation

The optional quantity fields in schema 0.2.0 are:

| Field | Exact contents | Operational meaning |
| --- | --- | --- |
| `Resource.consumable_stock` | `unit`, `on_hand_quantity`, `reserved_quantity`, `distributed_quantity`, `expected_quantity` | Integer projections of stock physically controlled, reserved, consumed through distribution, and still expected |
| `Assignment.consumable_allocations[]` | `resource_id`, `quantity`, `service_target_id` | Proposed consumption demand tied to a stock pool and service target; an assignment alone reserves nothing |
| `Hold.remaining_quantity` | Nonnegative integer, bounded by the original `quantity` | Unconsumed or untransferred part of a consumable reservation; structurally optional for other profiles but required by the pantry runtime |
| `Hold.purpose`, `Hold.destination_resource_id` | Purpose `activity` or `stock_transfer`; registered destination for a transfer | Distinguishes a service reservation from a source reservation that initiates a local staff handoff task |
| `EventState.service_progress[]` | `target_id`, `distributed_quantity` | Cumulative accepted aggregate distribution for the target, including any truthfully recorded late distribution |
| `EventState.expected_shipments[]` | `shipment_id`, `destination_resource_id`, `quantity`, `received_quantity`, `expected_at`, `source_ref` | Registered expected supply with separately reconciled receipts; `expected_at` can be unknown |
| `ScenarioDefinition.pantry_parameters` | `service_activity_id`, `staff_resource_id`, `service_rate_units_per_minute`, `handoff_duration_minutes`, `handoff_window` | Explicit modeled throughput and handoff timing, required for the pantry profile |

Use integer units throughout the first adapter. Reject negative, fractional, excessive, or incompatible quantities. A stock resource's `capacity` is its storage bound: the pantry fixture uses 100 for each pool. It is neither current supply nor a replenishing activity-slot capacity. Require `0 <= reserved_quantity <= on_hand_quantity <= capacity`. Cumulative `distributed_quantity` can exceed the storage bound over a longer hypothetical history, because the bound constrains stock held at one time rather than all prior distributions.

Available quantity is `on_hand_quantity - reserved_quantity`. On-hand includes reserved stock until actual handoff or distribution consumes it. Reserve consumables globally across time windows: allocating the same kit to a later nonoverlapping slot does not create another kit. Time windows still constrain authorized use and readiness, but do not replenish consumed units.

The authoritative reservation ledger records an immutable original `quantity` and changing `remaining_quantity` for each hold or committed allocation. `reserved_quantity` equals the sum of the remaining quantities of its live provisional and committed reservations. Conversion by `apply_plan` changes a provisional reservation into a committed allocation without adding a second reservation for the same units. Revalidate the latest state and bind the committed reservation to its activity, target, and goal version.

Expiry applies only to the unconsumed remainder of a provisional hold. It decrements reserved quantity and leaves on-hand unchanged. A committed allocation survives its former provisional expiry; only an explicitly authorized cancellation of an unconsumed remainder or actual consumption can release that reservation. Distribution is irreversible in this bounded adapter. A fulfilled, released, or expired reservation cannot later release or recreate stock. `fulfilled` is terminal when a handoff or distribution reduces its remainder to zero; partial consumption leaves its positive remainder under the applicable active or committed state.

For each resource, enforce the ledger identity:

`on_hand = initial_on_hand + valid_physical_receipts - valid_transfers_out - actual_distributions`

Reservations do not enter that stock equation. Across an internal handoff, the source debit exactly equals the destination credit, so total stock across both pools is conserved. The same unit cannot be in both pools after a transaction. No schedule completion, promise, check-in, or status query changes physical stock.

### Physical receipt and shipment reconciliation

Only a staff principal with a matching grant may use `record_stock_receipt`. Record the physical event time, server recording time, source identity, source observation, receipt reference, quantity, and affected resources. A status response can support source availability; it cannot attest that a physical transfer happened.

For the registered internal handoff, validate the source resource, matching source hold, positive quantity no greater than its remaining reservation and physical source stock, destination unit/storage bound, and staff authority. In one transaction, debit source on-hand and reserved quantity, decrease the source hold's `remaining_quantity`, credit destination on-hand, advance the revision, and persist the receipt. A partial handoff is allowed: transferring 10 of a 16-kit reservation leaves 6 reserved at the source until subsequent handoff, release, or expiry. Mark the source hold fulfilled only when its remainder reaches zero. The receiving stock requires its own hold and commitment before distribution; an internal handoff does not automatically commit destination units or satisfy a service target.

A source hold with purpose `stock_transfer` and a valid `destination_resource_id` creates a local pending staff handoff task. The pantry parameters specify a two-minute modeled handoff duration and a window from 12:30 inclusive to 12:50 exclusive. The conditional staff response is evaluated after the valid task's two minutes elapse, while the hold, grant, stock, and handoff window still permit it. It is not a single fixed 12:35 opportunity and does not guarantee staff acceptance. The source reservation and task provide the same opportunity to every compared policy; the model cannot supply the staff attestation itself.

For an external receipt, match the registered shipment and destination. Increment that shipment's `received_quantity` by the newly received amount without exceeding its registered quantity, and update the resource's expected projection. `expected_quantity` is the sum of `quantity - received_quantity` for the resource's outstanding registered shipments. A delay changes ETA evidence; it does not reduce the expectation or add stock. In the canonical internal handoff, the independent shipment `S20` remains at quantity 20, received quantity 0, and expected quantity 20. Its late arrival opportunity is not an automatic receipt.

Request idempotency and physical-event uniqueness are separate. An identical request retry returns its original receipt. A new request key cannot credit a physical handoff or supplier receipt twice: use unique registered receipt references and reconciliation records. Partial arrivals need distinct physical references tied to their parent shipment or handoff, with a bounded cumulative quantity. Conflicting reuse of a reference must reject without mutation. A transaction failure cannot leave a source debit without its matching destination credit.

### Distribution, progress, and the original deadline

Only a separately authorized staff principal may use `record_distribution`. The record binds a unique distribution reference, target, activity, goal version, physical completion time, server recording time, and the committed reservations consumed. Check unit compatibility, physical stock, reservation remainder, staff readiness, declared throughput, and permitted activity execution. Decrement on-hand and reserved quantities, decrease the consumed reservation remainders, and increment resource and target distribution projections atomically. Preserve the target-linked distribution ledger as the authority for those projections. A plan, reservation, receipt, or completed activity label alone proves no distribution.

The runner records the actual distribution start only when the plan is committed, physical quantities are reserved, dependencies are satisfied, and the declared staff resource is ready. Qualified execution time accrues only while these conditions continue to hold. Newly distributable throughput is `floor(service_rate_units_per_minute * elapsed_qualified_execution_minutes) - already_distributed`. The permitted new quantity is bounded by that throughput, committed physical stock, and remaining target. With the fixture's rate of one kit per minute, starting at 13:10 permits at most 30 kits by 13:40, even if 40 are in stock. The proposed 13:00 assignment cannot be substituted for an actual late start.

The original service deadline is inclusive for physical completion: process a legitimate 13:40 completion before closing the service window and beginning reconciliation at that timestamp. The handoff cutoff at 12:50 is exclusive. Keep these boundary rules explicit; a generic timestamp sort must not turn them into inconsistent outcomes. Late physical distribution is recorded only within applicable grant/event permissions and readiness rules, and does not repair the original deadline miss.

Physical truth and deadline achievement are different records. A validly attested physical distribution that happened late must still reduce stock and increase cumulative `service_progress`; it does not count as timely completion. Preserve its actual timestamp and deadline miss rather than rejecting truthful accounting solely to keep a success metric clean. A late recording of an earlier supported event likewise retains both times; it cannot be backdated merely by model assertion. Evidence corrections require an auditable authorized correction process, not rewritten history.

Compute timely fulfilled quantity from unique distribution-ledger entries with physical completion times at or before the original target deadline. Compute the deadline service deficit as `max(0, original_target - timely_fulfilled_quantity)`. The cumulative `service_progress.distributed_quantity` has no time field and therefore cannot by itself establish deadline success. Report late quantities separately, including after the display's current remaining-service counter reaches zero.

The current supply shortfall is `max(0, original_target - fulfilled_so_far - usable_pantry_stock)`, where usable stock includes stock already reserved for this target. Expected stock and the alternate pool before handoff are excluded. Initially pantry stock is 24, alternate stock is 16, expected supply is 20, and distribution is 0: supply shortfall is 16 and service deficit is 40. A full internal handoff yields pantry/alternate stock 40/0 and supply shortfall 0 while service deficit remains 40. Only timely distribution of 40 produces deadline deficit 0 and final stock 0/0. An internal handoff creates no service and leaves `S20` unreconciled.

## `Observation`

Every observation carries an event identifier, source identifier and type, immutable received content, server receipt time, source observation time when known, referenced entities, and evidence lineage. Tool responses also carry query identity and source freshness information.

Source type answers “where did this come from?” Source authority answers “what can this actor legitimately state or change?” Factual support answers “what does the evidence establish?” Keep these fields and concepts separate.

Examples:

- A participant's authenticated check-in establishes their declared presence and available interval.
- A supplier query reports the supplier system's current status at a stated observation time.
- A forwarded message preserves its original reference when known, so it is not treated as independent corroboration.
- An organizer preference update is an authorized goal mutation, not evidence that a resource is available.

Retain contradictory observations. Add supersession or correction links rather than overwriting history. Do not label a claim false merely because it has not yet been confirmed. The evaluation runner may know a claim is false while the agent still has unresolved evidence.

## `ChangeSpec`

The language model interprets observations into a bounded vocabulary of changes, such as resource delay, resource unavailability, participant availability, capacity change, or an ambiguous update requiring resolution. A specification identifies the affected entity, relevant time window, proposed planning implication, and its evidence references.

Server-controlled provenance, model configuration, schema version, and interpretation time are attached after validation. The model cannot supply trusted role grants or rewrite source timestamps.

Do not store an unconstrained confidence score as an action trigger. Evidence status can change as new observations arrive. An interpretation that was plausible at receipt time may later become contradicted or inapplicable.

If an update includes two independent claims, represent them separately or give the combined specification explicit dependencies. This makes it possible to confirm a delivery delay while rejecting the message's unrelated claim about a venue closure.

## `CandidatePlan`

A candidate refers to a goal version and base state revision. It contains proposed activity placements, resource allocations, assumptions, changes relative to the accepted plan, and deterministic constraint results.

An exact required resource identifier cannot be replaced with an arbitrary similarly named item. Resource substitution requires a declared compatibility mapping or capability rule. The first fixture can explicitly register the backup projector as an approved substitute for the primary projector. The model cannot invent compatibility.

Each constraint result identifies the requirement checked and the entities involved. A failed candidate remains inspectable for explanation and evaluation. It does not become executable merely because it has the lowest soft cost.

Record objective components individually. Preserve tie-breaks and candidate-generation settings so the decision can be reproduced. Mark any candidate cap or incomplete search.

Candidates can require fresh evidence or a provisional hold. Those preconditions must be rechecked at execution. Candidate validity is temporary, because a check-in, competing resource hold, or goal update can change feasibility.

Accepting a candidate with an explicit future-arrival assumption changes the schedule while preserving that unresolved assumption. It does not certify successful activity execution. An observed arrival can later discharge the assumption. A missed arrival can invalidate readiness and trigger a new decision.

For a consumable profile, candidate evaluation must check both operational constraints and the amount of service the candidate covers. Distinguish a valid partial allocation from a plan that can achieve the full original target. A positive constraint-validity result for a disclosed 24-kit partial plan must not be displayed as feasibility of the 40-kit goal. Reports must state original target, proposed coverage, missing quantity, assumptions, and execution preconditions in their checks and details. Permitting partial service does not permit a hidden target change.

The pantry fixture deliberately begins with a 24-kit partial assignment and **no holds**. It is a valid planning input with unresolved full-target attainment; it is not an execution-ready commitment. The runtime must reserve physical stock and validate readiness before execution. Receipt of the alternate 16 supports execution covering 40 only after destination stock is reserved and the revised plan is applied; a proposal may describe that conditional path earlier. The accepted schedule does not invent a completed activity or retroactively move its start to fit an outcome.

## `ActionReceipt`

A receipt records the actor, tool, event, idempotency key, canonical request digest, authority grant, state revisions, server time, relevant resource and candidate identifiers, outcome, and cost effects. Use explicit execution states. An attempted action, a rejected action, and a successful mutation must look different.

The receipt schema uses `applied`, `rejected`, and `unknown`. These describe action execution rather than the transport status described in [tool contracts](06_tool_contracts.md). Candidate and constraint-report references are nullable for actions that do not concern a plan, such as a participant check-in, or for an early rejection before candidate resolution.

For a failed precondition, the before and after operational revisions can be identical. The failed attempt still has an audit record. For an identical retry, return the original receipt rather than inventing another action.

An explanation can be generated from the receipt, the relevant constraint report, and cited observations. This gives the audience a factual action summary without exposing or fabricating private model reasoning.

## `AuthorityGrant`

Grants scope operations to an event, actor, action types, resource or activity sets, time period, and spending limit. A grant can permit provisional holds and schedule swaps while reserving cancellation of a mandatory activity for an organizer.

Revocation and expiry affect subsequent actions. An accepted reservation remains part of recorded state even if the agent's permission later expires. Any cancellation or rollback still requires an authorized operation and valid resource terms.

Store authority independently from untrusted observations. A message that claims to come from the organizer does not update permissions until its origin and authorization are established by the application session.

In the pantry fixture, the agent grant includes `hold_resource`, `release_hold`, and `apply_plan`; `review_required_for` is empty. The agent may apply a validated plan within that grant without an invented extra staff-approval step. `record_stock_receipt` and `record_distribution` require the separate staff grant. Staff-controlled physical attestations, agent plan authority, and optional review requirements are distinct. A steward's availability observation does not give the agent a staff credential or establish a receipt.

## `ScenarioDefinition` and private evaluator data

The public definition includes the profile, visible initial goal, resources, activity graph, configured tool contracts, allowed edits, and any declared uncertainty assumptions. The profiles are `campus_showcase`, `community_skills_exchange`, and `pantry_continuity`. The first two exercise event configuration; the third requires the declared quantity extension.

Private evaluator input contains latent disruptions, future arrival or availability schedules, message truth labels, response-generation seeds, and outcome-scoring references. Keep it outside agent-visible objects and tool outputs. Public examples and private evaluator fixtures belong in separate files.

The root demo fixture uses the fictional event identifier `e_showcase_01`. The planning documents intentionally avoid asserting that this example corresponds to an actual institutional event.

An episode's private truth may determine how a future status tool responds. The tool returns only the information that would be available at the current time under its declared observation model. It does not return the private scenario class or the future outcome.

The presentation can reveal a disruption label to the audience after the decision. That reveal belongs to the moderator/evaluator interface, not the agent context. An audience-selected card must have a sanitized agent-facing message.

Private pantry events include `staff_response_rule` and `resource_arrival_opportunity`. The development fixture uses a `staff_response_rule` for conditional handoff and distribution behavior; its event time activates or evaluates the rule rather than proving that an action happened. These are conditional simulation opportunities, not preexecuted actions. The same staff-response rule applies to every policy, and actual stock or service changes occur only if the declared reservation, stock, timing, readiness, and actor prerequisites hold. An opportunity absent its prerequisites produces no invented receipt or distribution. Future opportunity times and evaluator outcome checks remain hidden; only genuinely available observations and executed results enter the public projection.

## `EventState` and revision rules

The state projection includes the current goal and accepted plan, resource allocations, participant availability, relevant observations, unresolved changes, budget accounting, logical time, and revision. Consumable profiles add stock, expected-shipment, and cumulative service-progress projections backed by their own authoritative ledgers.

Use one monotonic revision per event for the MVP. Advance it on changes that can affect decisions, such as a new material observation, check-in, hold, release, goal update, or committed plan. A repeated read or duplicate observation should not advance it simply because it was requested again.

Store immutable observation and action history alongside the current projection. Full event sourcing is optional. The essential property is that the displayed state can be traced to actual accepted inputs and executed operations.

Candidate creation uses a snapshot. Mutations use compare-and-swap revision checks inside a transaction. A successful hold advances the revision, so a subsequent commitment must use the post-hold state and refreshed validation. The application should handle this sequence automatically.

A pantry handoff changes two stock records and the source reservation at one revision. Destination reservation and plan application then use refreshed revisions. Distribution updates stock, reservation remainders, target progress, and its durable receipt in one transaction. Failed quantity, grant, or revision checks leave all these operational records unchanged. Repeated requests and physical references cannot advance projections twice.

## Persistence proposal

| Logical table | Key relationships |
| --- | --- |
| Events and goal versions | Event to ordered versions, one current version |
| Activity and resource registry | Stable event-scoped entities |
| Observations and evidence links | Immutable received records and source lineage |
| Changes | Validated interpretations referencing observations |
| Plans and candidate evaluations | Goal version, base revision, proposed allocations, constraint reports |
| Holds and commitments | Resource, original and remaining quantities, provisional/committed status, target/activity linkage, ownership, expiry, terms |
| Participant availability | Scoped participant declaration and observation reference |
| Authority grants | Actor, scope, limits, validity |
| Action receipts and idempotency | Unique request identity and durable outcome |
| Cost ledger | Hold fees, commitment fees, refundable reserves, releases |
| Stock movements and receipt reconciliation | Unique physical receipt/handoff reference, source and destination, quantities, event and recording times, source observation, actor |
| Expected shipments | Shipment identity, destination, registered and received quantities, ETA evidence, matched receipt records |
| Aggregate distribution ledger | Unique distribution reference, target and goal version, activity, consumed reservation quantities, actual completion time, actor |

Use foreign keys and uniqueness constraints where possible. Validate cross-field and interval constraints in the domain layer inside the same transaction as writes. A valid JSON document alone cannot prevent double booking.

Stock, reservation, expected-supply, and service-progress counters are materialized projections, not independently editable truth. Reconcile them against accepted ledger entries after reset and when exporting an episode. Store original target versions and timestamped distribution records so a partial or late result remains scoreable even after a new plan or goal is accepted. The schema specifies example shapes; it does not implement transactions, projection rebuilding, or persistence migrations.

## Privacy and community participation

Use synthetic names or participant aliases in the public demo. A participant link can represent one predefined volunteer role. Display role availability rather than personal contact information. Resource offers should avoid collecting addresses or sensitive personal details unless a later real deployment has a specific need.

Community participation should affect the plan through visible, bounded facts: a check-in, an available interval, an approved resource offer, or an organizer priority. It should not become an opaque score ranking people by inferred reliability.

Pantry records contain aggregate standardized kit quantities and fictional staff roles. They contain no recipient identity, eligibility decision, allergen decision, or claim about real stock or institutional partnership. Optional transit observations remain source-and-time-labeled context; they cannot establish a person's location, check-in, or ETA.

## Data validation checklist

Before the first live demo, verify that fixtures parse, references resolve, times use an explicit clock, the activity graph is acyclic, capacities and money are nonnegative, holds obey their terms, and private evaluator fields never appear in agent or frontend projections. Check the event profiles' initial feasibility and explicitly identify the pantry's valid but incomplete 24-kit initial proposal. Verify that all three profiles load through the common application with the declared pantry capability extension; a successful JSON parse does not establish runtime support.

For pantry, test reservation sums and remaining quantities, global consumption across nonoverlapping slots, conversion without double reservation, provisional-only expiry, partial handoffs, atomic source/destination conservation, shipment reconciliation, unique physical references under new request keys, staff-only attestations, and partial/late distribution scoring against the original target. Check storage, occupancy, and service throughput as separate quantities. These are required implementation checks, not claims that runtime tests have passed.

After each scenario, export the manifest, visible observations, interpretations, candidate evaluations, action receipts, and final state. Keep private truth in a separate evaluator artifact. This is enough to reproduce a decision and compute state-based outcomes without treating the agent's narration as the source of truth.
