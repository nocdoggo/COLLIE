# Planning schemas

[planning.schema.json](planning.schema.json) is a JSON Schema Draft 2020-12 bundle for selected design artifacts. Version **0.2.0** adds the pantry quantity-and-service extension to the planning contract. It is not generated application code or a complete production API. No controller, deployed persistence migration, or runtime backward compatibility is established by this artifact update.

## Included shapes

All top-level artifacts use a discriminator and `schema_version: 0.2.0`:

| `artifact_type` | Definition | Visibility |
| --- | --- | --- |
| `public_scenario` | ScenarioDefinition | Agent-visible starting information, projected by role |
| `private_evaluator` | EvaluatorFixture | Evaluator only, never bundled into the client or agent context |
| `change_spec` | ChangeSpec | Agent interpretation linked to visible observations |
| `observation_record` | ObservationRecord | Visible evidence and the revision created by ingesting it |
| `candidate_plan` | CandidatePlan | Stored proposal tied to a state revision and goal version |
| `constraint_report` | ConstraintReport | Deterministic evaluation result with explicit assumptions |
| `mutation_request` | MutationRequest | Illustrative `apply_plan` request |
| `action_receipt` | ActionReceipt | Durable result of a local action, with simulation label |

Reusable definitions also include EventGoal, Activity, Resource, Assignment, Observation, AuthorityGrant, Hold, EventState, TimeWindow, ServiceTarget, ConsumableStock, ConsumableAllocation, ServiceProgress, ExpectedShipment, and PantryParameters. The [data model](../07_data_model.md) describes broader semantic requirements. The [tool contracts](../06_tool_contracts.md) define the complete proposed surface. Tools other than the illustrated `apply_plan` request still need complete request/response schemas during implementation.

The bundle accepts the campus and community event profiles without consumable fields. `pantry_continuity` additionally requires service targets, stock, progress, expected shipments, and pantry parameters through its profile-specific structural conditions. This is capability-based extension of the shared contract. It does not establish zero-shot transfer, and the old 0.1.0 documents do not automatically validate against a bundle that requires 0.2.0.

## Pantry quantity shapes

| Location | Fields | Meaning |
| --- | --- | --- |
| `EventGoal.service_targets[]` | `target_id`, `unit`, `quantity`, `deadline`, `activity_id` | Original aggregate target and its completion deadline |
| `Resource.consumable_stock` | `unit`, `on_hand_quantity`, `reserved_quantity`, `distributed_quantity`, `expected_quantity` | Integer projections backed by stock, reservation, receipt, and distribution ledgers |
| `Assignment.consumable_allocations[]` | `resource_id`, `quantity`, `service_target_id` | Proposed demand; no reservation or fulfillment is implied by the JSON assignment |
| `Hold` additions | `remaining_quantity`, `purpose`, `destination_resource_id`; terminal status `fulfilled` | Remaining units and `activity` versus `stock_transfer` purpose; destination identifies a registered internal handoff |
| `EventState.service_progress[]` | `target_id`, `distributed_quantity` | Cumulative physical distribution, including accepted late records; deadline success requires the timestamped ledger |
| `EventState.expected_shipments[]` | `shipment_id`, `destination_resource_id`, `quantity`, `received_quantity`, `expected_at`, `source_ref` | Registered expectations and separately reconciled actual receipts |
| `ScenarioDefinition.pantry_parameters` | `service_activity_id`, `staff_resource_id`, `service_rate_units_per_minute`, `handoff_duration_minutes`, `handoff_window` | Authored service throughput and local staff-response timing |

Hold additions are structurally optional for existing event records. Pantry runtime validation must require `remaining_quantity`, an appropriate purpose, and a registered destination for stock transfers, enforce `remaining_quantity <= quantity`, and reconcile the remaining reservations with projected reserved stock. A partially transferred hold retains its remainder; a fully consumed hold is fulfilled. Conversion to committed stock cannot double the reserve, and provisional expiry cannot release a committed or already consumed quantity.

In the fictional fixture, `Resource.capacity: 100` is a storage bound; actual stock is 24 in the pantry and 16 in the alternate pool. `attendance_target: 12` is occupancy planning, not people served. The target is separately 40 standardized kits. The initial assignment proposes only 24 kits and has no holds; it is a constraint-valid partial planning input with an unresolved full target, not an execution-ready success. The expected 20-kit shipment contributes no usable stock until a valid physical receipt.

## Canonical names and versions

The common tool vocabulary is `get_event_state`, `get_action_receipt`, `list_resources`, `query_status`, `evaluate_candidates`, `hold_resource`, `release_hold`, `apply_plan`, `check_in`, and `submit_observation`. Pantry adds staff-only `record_stock_receipt` and `record_distribution`. A vocabulary entry does not imply a completed endpoint. `get_action_receipt` is a read-only way to resolve a previously submitted action's actual recorded outcome.

`EventState.revision` changes when accepted operational state or relevant evidence changes. `EventGoal.version` identifies the objective being checked. A candidate binds both. An `apply_plan` request carries the expected revision and goal version. The executor revalidates the stored candidate inside the transaction.

Dates accept explicit ISO 8601 offsets. The fictional November examples use `-05:00`, the New York offset on those dates. Normalize to UTC internally and display using `America/New_York`. Expiry and deadlines use the injected scenario clock during replay.

Tool envelopes and receipts have different roles. An envelope can report `succeeded`, `rejected`, `unknown`, or `unavailable`. An ActionReceipt records `applied`, `rejected`, or an unresolved `unknown`. A succeeded read can contain a domain status of unavailable. A transport outage is not evidence that a resource is unavailable.

Physical receipt/distribution references also differ from request idempotency keys. A new request key cannot create a second stock credit or service count for the same physical event. Only a staff grant can attest those events; the pantry agent's separate grant permits valid plan application without an additional review step where `review_required_for` is empty.

## What schema validation establishes

Validation with the format checker below checks object shape, required fields, closed vocabularies, timestamp format, basic numeric bounds, profile conditions, and selected receipt consistency rules. It does not check foreign keys, actual authority, the meaning of a message, conserved quantities, valid runtime transitions, or the future.

The application must additionally enforce:

- Matching event IDs, authenticated principal/grant binding, and scope.
- Time ordering, non-overlapping occupancy, activity duration, dependencies, and locked activities.
- Actual capacity and budget accounting, including live holds and incurred fees.
- Consumable stock conservation, global reservations across nonoverlapping time slots, remaining hold quantities, conversion without double reservation, and provisional-only expiry.
- Atomic source debit and destination credit for full or partial internal handoffs; unique physical receipt references, shipment reconciliation, and a separate destination reservation before distribution.
- Staff-only receipt/distribution authority and truthful aggregate accounting. The internal 16-kit handoff leaves unrelated shipment `S20` and its expected 20 units unchanged.
- Original service-target retention and explicit partial coverage; a valid 24-kit proposal is not proof of achieving a 40-kit target.
- Actual qualified service execution time, modeled throughput, and deadline scoring from timestamped distribution records. A proposed start time cannot substitute for a late actual start.
- Resource compatibility. A backup must be an approved substitute with the required capabilities.
- Current state revision, goal version, grant expiry, and idempotency semantics.
- Evidence existence, source record identity, validity interval, and correlated or duplicate records.
- Candidate storage and report integrity. The language model cannot grant feasibility by writing a successful report.
- Physical readiness at activity execution. A future schedule accepted under an ETA assumption is not proof of arrival.
- Rejected mutations leave state unchanged. Applied mutations increment the revision atomically with their receipt.
- Private future events never reach public projections, prompts, retrieval, or planning tools.

For the pantry, a valid `stock_transfer` hold creates a local pending staff task. The fixture declares a two-minute handoff response and a 12:30-inclusive to 12:50-exclusive acceptance window. Validate its timing and prerequisites in the runner; a schema-valid task does not guarantee staff acceptance. Distribution accrues at the declared one kit per minute of qualified actual execution, so a 13:10 start can serve at most 30 kits by 13:40. Completion at the 13:40 deadline is processed before closure and reconciliation at the same timestamp.

Valid late physical distribution must remain visible in stock and cumulative progress when recorded within applicable grants and event permissions. It does not count toward the original deadline. The cumulative `service_progress` projection lacks completion timestamps and cannot replace the authoritative distribution ledger for that score. These arithmetic and temporal invariants require implementation checks beyond JSON validation.

The event examples use one unit of each listed equipment/person resource per activity. Pantry explicitly adds consumable quantities and declared throughput. General costs by time, access requirements, and new cancellation or inventory operations still require explicit support before another profile can use them. Venue occupancy, program concurrency, physical storage, and service throughput are separate constraints.

The private event vocabulary includes conditional `staff_response_rule` and `resource_arrival_opportunity` records. A rule activation or arrival opportunity is not a successful receipt or distribution. Keep the rules and future truth evaluator-only, and expose only observations or action outcomes actually produced by the modeled prerequisites. Public and private examples must remain separate artifacts even when both validate against this bundle.

## Validate the examples

Run from the repository root in an environment with `jsonschema` installed:

```bash
python - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

root = Path('PEEAI_plan')
schema = json.loads((root / 'schemas/planning.schema.json').read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
paths = sorted((root / 'examples').glob('*.json'))
for path in paths:
    validator.validate(json.loads(path.read_text()))
    print(path.name, 'valid')
print(len(paths), 'artifacts validated')
PY
```

The current bundle has **11 JSON examples**, including the public pantry fixture and its separate private development/evaluator future. Validate all of them locally, while excluding private files from agent and frontend bundles. This is artifact validation, not evidence that a controller, executor, stock ledger, or community application has been implemented. See the [three-wave roadmap](../11_implementation_roadmap.md) for the implementation and behavioral checks that remain planned.
