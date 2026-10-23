# Pantry Continuity: a bounded transfer showcase

**Status:** Proposed synthetic scenario and additive planning contracts, October 23, 2026. No runtime implementation, U-ACCESS partnership, inventory access, or pilot results are claimed.  
**Decision:** Pantry is selected for the second showcase in the build plan. Keep the campus event as the hero and use a 45-second pantry segment to demonstrate planning with consumable quantities and a measured service target.  
**Profile ID:** `pantry_continuity`.

## Why this is a useful second showcase

The campus showcase asks whether required activities finish with reusable equipment and available people. Pantry Continuity asks whether a fixed team can distribute a specified quantity before the session ends when expected supplies are late. Completing a schedule does not prove that a quantity target was met, and rescheduling cannot make consumed stock available again.

U-ACCESS provides a local discovery context. Its published pantry page describes restocking and delivery closures, and its student roles describe inventory and volunteer scheduling responsibilities. Those responsibilities motivate investigating a staff logistics task. They do not establish that staff use standardized kits, have this particular problem, or want this product. Sources checked October 23, 2026: [U-ACCESS Food Pantry](https://www.umb.edu/campus-life/current-students/u-access/food-pantry/), [U-ACCESS Student Leadership Team](https://www.umb.edu/campus-life/current-students/u-access/u-access-student-leaders/).

The service has an existing intake workflow linked through PantrySoft. That link is context for respecting the existing process; it does not establish API availability or integration permission. [U-ACCESS](https://www.umb.edu/campus-life/current-students/u-access/)

The skills-exchange fixture remains useful as an inexpensive regression of the original event schema and as a live-demo fallback. Pantry earns its separate showcase slot only if it exercises the added stock rules through the same planning loop.

### Why select pantry over coffee/Dunkin for this build

Both could make consumable stock concrete. UMass Boston lists a Campus Center Dunkin, and its dining operator documents mobile ordering through Everyday. Those pages confirm a familiar campus example; they do not establish access to orders, stock, recipes, or an API. Sources checked October 23, 2026: [Campus Center dining](https://www.umb.edu/campus-center/services/dining/), [UMass Boston dining operator's Dunkin listing](https://umb.sodexomyway.com/en-us/locations/dunkin-donuts).

| Consideration | Pantry Continuity | Coffee/Dunkin illustration |
| --- | --- | --- |
| Bounded task | A fixed team distributes a staff-defined count of standardized kits | A fixed team fulfills a count of prepared items or orders |
| Transfer value | Consumable reservations, confirmed receipt, and a service target | Also supports stock and service targets, with possible queue and preparation dependencies |
| Fit to the current pitch | Extends the community coordination goal through staff logistics | Adds a relatable commercial service setting |
| Extra work for an operationally faithful version | Staff validation of units, receipt rules, and throughput | Operator validation of queue priorities, recipes, ingredient conversion, fulfillment rules, and vendor data |
| Build-plan decision | Selected as the second synthetic showcase | Retain as a future illustration; no third implementation or vendor integration |

This is a scope choice, not evidence that pantry demand is stronger or that coffee is less useful. A single prepackaged coffee-service fixture could be small, but building both would add a second domain narrative before either has operator validation. Pantry supplies the desired community setting and distinct stock/service semantics within one extension.

## The fictional operating boundary

The prototype coordinates one session in one venue with a fixed, registered staff/volunteer roster, explicit activity windows, declared throughput, and a contingency budget. Staff specifies a standardized shelf-stable kit as the counted unit. The example does not model the kit's contents, infer nutritional equivalence, or choose substitutes for dietary needs.

The target is an aggregate count of kits distributed by a deadline. It is not a count of unique people served, a measure of food security, or a recipient allocation policy. No names, eligibility, household needs, benefit records, or intake data are required. Staff determines service policy outside this planning scope.

All stock, people, timings, costs, and observations are fictional. The alternate pool is registered at the same fictional venue under a separate steward; the identifier `partner_stock` does not represent a real partner. Its handoff requires no transport route, purchase, or external reservation. Any budget use follows the fixture's existing terms and approval rules.

## Canonical episode

| Fact | Synthetic value | Operational meaning |
| --- | --- | --- |
| Service target | 40 standardized kits by the session end | Success requires timely completed distribution |
| Session stock, `pantry_stock` | 24 kits on hand | Physically confirmed, not yet distributed |
| Expected shipment | 20 kits | An expectation; zero usable units until a matched staff-confirmed receipt |
| Alternate pool, `partner_stock` | 16 kits on hand | Registered, compatible, at the same venue, available for a scoped local hold |
| Staff and volunteers | Existing registered roster | Availability and task capacity must suffice; the agent cannot invent extra help |
| Venue and budget | Fixed profile constraints | Reservations and schedule changes must remain within them |

Initially, the expected shipment can support an explicitly conditional future plan. Once a current observation places its arrival beyond the usable window, the session has a 16-kit confirmed supply gap. The candidate generator compares waiting, allowed schedule changes, and the confirmed alternate pool. The stock validator rejects any candidate claiming that a reorder alone fills the gap.

Keep two counters distinct. The initial **supply shortfall** is `40 - 24 = 16` because only 24 kits are under session control. The **remaining service target** is `40 - 0 distributed = 40`. After the local handoff the supply shortfall is zero while the remaining service target is still 40. Both reach zero only after timely distribution of all 40 kits. Reserving the alternate pool establishes recovery coverage; it does not erase either actual-state distinction.

The successful recovery is:

1. Verify that the registered alternate pool really has 16 usable kits and that the confirmation is current.
2. Reserve its 16 kits through `hold_resource`. This reduces alternate availability but moves no stock and achieves no service.
3. Propose the allowed preparation/distribution schedule using the existing roster. The agent's standing grant permits the local plan change; staff retains the physical handoff decision and attestation.
4. Staff confirms the physical handoff through `record_stock_receipt`. In one transaction, alternate on-hand stock falls from 16 to zero, its matching reservation closes, and session on-hand stock rises from 24 to 40. The unrelated expected shipment remains 20.
5. Reserve the session's 40 kits, refresh the revision, and revalidate the candidate against stock, throughput, time, roles, and budget. The agent applies the plan within its standing grant, without an additional approval click. Committed service coverage is now 40; completed service is still zero.
6. Staff or the explicitly labeled simulator records aggregate distribution through `record_distribution` before the deadline. It consumes the 40 committed session kits and records 40 against the target. Session and alternate on-hand stock are now zero; the delayed shipment is still unreceived.

The machine-readable fixture owns exact dates, roster, durations, capacity, cost terms, and identifiers. The [data model](07_data_model.md), [tool contracts](06_tool_contracts.md), and [planning schema](schemas/planning.schema.json) own the shared contract. This narrative describes the intended sequence rather than establishing a second set of timing or budget constants.

## Additive contract and stock rules

Keep event/goal identity, revisions, observations, grants, candidate reports, holds, and action receipts. Add consumable capability only to profiles that need it; the existing campus and skills-exchange fixtures remain valid without these optional fields.

| Contract addition | Fields and required bindings | Required meaning |
| --- | --- | --- |
| `EventGoal.service_targets[]` | `target_id`, `unit`, `quantity`, `deadline`, `activity_id` | Staff-defined quantity tied to a registered activity and deadline |
| `Resource.consumable_stock` | `unit`, `on_hand_quantity`, `reserved_quantity`, `distributed_quantity`, `expected_quantity` | Integer stock projection with explicit expected/on-hand separation |
| `Assignment.consumable_allocations[]` | `resource_id`, `quantity`, `service_target_id` | Candidate demand for a particular stock pool and service target |
| `EventState.service_progress[]` | `target_id`, `distributed_quantity` | Cached projection of unique target-linked distribution records; timely achievement also checks their completion times |
| `EventState.expected_shipments[]` | `shipment_id`, `destination_resource_id`, `quantity`, `received_quantity`, `expected_at`, `source_ref` | Identified expected supply; outstanding quantity is reconciled only by a matching receipt |
| `ScenarioDefinition.pantry_parameters` | `service_activity_id`, `staff_resource_id`, `service_rate_units_per_minute`, `handoff_duration_minutes`, `handoff_window` | Typed service capacity and staff-response timing available to every policy |
| Consumable hold remainder | `Hold.remaining_quantity` | Initially equals held quantity; partial transfer, release, or consumption decrements only the remaining reservation |
| Stock receipt action | `resource_id`, `quantity`, `unit`, `source_observation_id`, `receipt_reference`; `source_resource_id` and `source_hold_id` for a registered internal handoff; `shipment_id` for a matched external receipt | Staff-attested receipt with unique source provenance; internal movement debits one registered stock and credits another |
| Distribution action | `resource_id`, `quantity`, `unit`, `service_target_id`, `distribution_reference`, current goal version, distribution activity, and committed reservation IDs | Staff-attested aggregate completion that consumes committed stock and supports target accounting |

The two action rows specify tool inputs in addition to the common event, revision, idempotency, and grant envelope. They do not imply a complete HTTP API. `source_hold_id` is required for the canonical internal transfer. Reject an expired, ambiguous, foreign, or insufficient source hold; reconcile the transferred quantity with its reservation atomically.

The semantic rules are:

- `on_hand_quantity` includes reserved but unconsumed stock. Available quantity is `on_hand_quantity - reserved_quantity`. Holds and committed allocations are disjoint parts of the reserved total, never two copies of the same units.
- `expected_quantity` is the sum of `quantity - received_quantity` for the resource's outstanding expected shipments and contributes zero to on-hand or achieved service. An ETA query changes evidence about arrival, not the stock balance. A matched external receipt reconciles the corresponding expected shipment once; an internal handoff does not decrement an unrelated expectation.
- Consumable reservations apply across the remaining session, not only overlapping activity intervals. Two non-overlapping activities cannot each allocate the same 16 kits.
- Releasing or expiring an unused hold reduces reserved quantity. It creates no stock. Completed distribution reduces both on-hand and the relevant committed reserved quantity, and increases the distribution projection. Finishing an activity never replenishes consumed stock.
- A partial source handoff transfers only the confirmed quantity, decreases the source hold's `remaining_quantity` by that amount, and leaves its unused remainder reserved under the original terms. A transfer of 10 out of 16 held kits creates 10 destination kits and leaves six in the source reservation. A fully transferred or consumed reservation has a zero remainder and terminal `fulfilled` status. Release or expiry affects only a live remainder, never units already transferred or distributed.
- A registered internal handoff conserves the sum of on-hand stock across source and destination. Receipt processing must debit the source, reconcile its matching reservation, credit the destination, increment the revision, and write the durable receipt atomically.
- A hold with `purpose: stock_transfer` and `destination_resource_id` creates a local pending staff task. Its response latency begins after the valid request; the agent includes that latency and the exclusive source cutoff when computing the last useful action time. A hold alone cannot cause a backdated handoff.
- Distribution capacity accumulates only during actual qualified staffed execution with committed physical stock. The fixture's one-kit-per-minute rate cannot justify 40 units after a 13:10 start and a 13:40 deadline. At the inclusive service deadline, process completed distribution before deadline closure and the next activity; provisional-hold expiry remains exclusive.
- An external receipt requires trusted staff evidence and unique shipment/receipt identity. Idempotency prevents a request retry from duplicating a write; provenance identity also prevents the same physical receipt from being resubmitted with a fresh request key.
- `service_progress.distributed_quantity` records cumulative actual distribution. Timely achievement derives from unique, target-linked records with completion times no later than the service deadline. A plan commitment, hold, receipt, or activity status alone cannot establish achievement. Authorized staff may record actual late distribution within the event and grant window, even after the planned distribution activity has ended; the late event is retained as a violation and excluded from timely achievement. It cannot retroactively alter the plan or meet the service deadline.
- Target units and resource units must match. The first pantry profile has one preapproved kit type; the model cannot infer equivalent foods or manufacture a conversion ratio.
- JSON validation checks field shape. The executor must separately enforce cross-record conservation, identity, authority, deadlines, and physical-readiness evidence.

For the canonical episode, stock conservation is visible: initial confirmed stock is `24 + 16 = 40`; handoff produces `40 + 0 = 40`; distribution produces zero remaining plus 40 distributed. The expected 20 never enters that equation. If no alternative is usable, the correct result is a disclosed 16-kit shortfall, with the existing target preserved until staff explicitly changes the goal version.

## Planned tools and authority

| Actor | Permitted role in the showcase |
| --- | --- |
| Coordinator agent | Read scoped state, query registered sources, evaluate candidates, hold/release authorized quantities, and request or execute a permitted plan change |
| Stock steward or pantry staff | Confirm stock evidence and physical handoff within the issued grant; attest receipt and completed aggregate distribution |
| Assigned volunteer | Submit their own availability/check-in; that update does not grant stock or goal authority |
| Session organizer | Set the target and constraints, review required commitments, and explicitly version a changed target when recovery is infeasible |
| Scenario runner | Supply disclosed simulated staff actions and completion events in the sandbox, without exposing hidden future truth to the agent |

`record_stock_receipt` and `record_distribution` are the two pantry-specific additions to the local tool service. The agent can request evidence but cannot attest a physical receipt or distribution on staff's behalf. Both mutations follow the existing revision, receipt, and idempotency rules. Grant checks remain server-side.

`hold_resource` gains consumable quantity semantics; `evaluate_candidates` gains stock conservation and service-target checks; `apply_plan` converts valid local stock holds to committed consumption allocations after revalidation. These are declared capabilities with common tool contracts. They are not special instructions to always choose a specific action when the profile name is `pantry_continuity`.

No third-party pantry API is required for the showcase. A local fixture and staff-role input screen provide the state and observations. A future approved aggregate import could use the same typed ingestion boundary after the operator validates it. PantrySoft, university account systems, donation platforms, messaging, purchases, and external inventory writes are outside the promised build.

## The 45-second transfer demonstration

Keep this inside the existing presentation budget. Use a tested, resettable sequence and label all counts and staff actions as synthetic. The campus episode has already introduced the shared planner and action record.

| Time | Visible action | Audience takeaway |
| --- | --- | --- |
| 0–7 seconds | Switch to Pantry Continuity; show target 40, session stock 24, expected 20, and alternate local stock 16 | The goal now includes a quantity that scheduling alone cannot satisfy |
| 7–15 seconds | Reveal the delivery delay; show a 16-kit gap and a rejected candidate that counts unreceived supply | Expected supplies are not confirmed stock |
| 15–24 seconds | Agent reserves the confirmed alternate 16; show the local reservation receipt | A bounded preparation step secures units without claiming delivery |
| 24–33 seconds | Staff demo control confirms handoff; show balances 24/16 becoming 40/0; agent reserves and applies the revised plan | Human receipt evidence changes stock; the same validator checks staff, time, and budget |
| 33–40 seconds | Advance the sandbox to the scheduled distribution; staff/simulator records 40 completed units and remaining stock zero | Consumed stock and measured service are separate from a committed plan |
| 40–45 seconds | Show common planning-loop label and the added stock/service rules | This is an explicit capability extension beyond changing activity labels |

Suggested narration: "The event planner protects activities. Here it must also protect a quantity target. A promised delivery is not stock. The agent reserves 16 confirmed local kits; staff records their handoff. Only completed distribution counts toward the 40-kit target."

If the staff action is replayed, label it as replayed at the moment it appears. If the model or tool service is unavailable, use a disclosed deterministic replay with the same state transitions and receipts. A recording illustrates a tested path; it is not a fresh live run.

## Evaluation and release gate

The [evaluation plan](08_evaluation.md) owns the common comparison protocol. Add pantry cases as a separately reported transfer suite so the original campus benchmark remains comparable. All policies receive the same public observations, permitted tools, stock rules, and execution guards.

At minimum, exercise these distinct conditions:

| Case | Required result |
| --- | --- |
| Delayed 20, confirmed alternate 16 | Feasible recovery reaches 40 only after handoff and completed distribution |
| Expected delivery unreceived | Neither usable stock nor achieved service increases from an ETA or message alone |
| Same stock requested twice in different slots | Second allocation is rejected; time separation does not restore consumables |
| Duplicate receipt/distribution with same or fresh request key | Idempotency or provenance identity prevents additional stock or service credit |
| Handoff fails or receipt authority is absent | Source and destination balances remain unchanged; agent reports the unresolved step |
| Alternate unavailable or fixed roster lacks capacity | Specific shortfall or throughput conflict is reported without inventing stock or staff |
| Completion after target deadline but within event/grant window | Actual distribution is recorded with its lateness; cumulative service and stock update, but timely-target success remains false |

Report timely kits distributed, remaining shortfall, stock-conservation violations, unreceived-stock violations, duplicate credits, cost, unnecessary reservations, and staff-confirmation burden. Report service quantity separately from explanation quality. A successful sandbox run does not measure real food access or validate the workflow with an operator.

The live segment passes its release gate only when state resets, the main recovery, and the adverse cases above are reproducible. Interface comprehension is part of the gate: viewers must be able to distinguish expected stock, a reservation, a receipt, a commitment, and completed distribution.

## Placement in the three implementation waves

1. **Wave 1 — deterministic campus vertical slice:** Complete the campus state engine, validator, local holds, receipts, organizer board, and scripted recovery. Keep skills exchange as a same-schema regression. Pantry work is limited to this specification and fixture design.
2. **Wave 2 — agent, community input, and pantry extension:** Connect the agent to the proven tools; add scoped check-ins and offers; implement optional stock/service contracts and staff receipt/distribution inputs; run the pantry recovery and failure paths. Optional MBTA context stays a source of uncertain information and cannot prove a volunteer's arrival or stock receipt.
3. **Wave 3 — full evaluation, reliability, demo, and release:** Complete common-policy comparisons and the separately labeled pantry suite, verify replay/reset and authority boundaries, run comprehension checks, rehearse the 45-second segment, and prepare the release artifacts. Add no new domain capability during the release gate.

## Operator validation and fallback

Use the [community validation plan](10_community_validation.md) to ask staff about counted units, receipt evidence, reservation practice, throughput, useful service targets, and reporting burden. One bounded tabletop is more informative than assuming that an inventory-themed prototype fits an existing service.

If no usable pantry pilot or reviewer is available, the synthetic showcase may still demonstrate the tested capability. State that operational usefulness remains unvalidated, use fictional counts, and make no U-ACCESS affiliation claim. The campus hero and hackathon release do not depend on institutional access.

If the pantry extension is incomplete, unreliable, or difficult to explain, use the working skills-exchange fixture in the live transfer slot. Keep pantry as a clearly marked next capability with its specification and tests planned. Do not call an event reskin a completed stock-planning extension.
