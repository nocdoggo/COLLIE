# Connected development example

These files describe a fictional campus event on **November 5, 2026**, in the `America/New_York` timezone. This is not the symposium schedule or a real university booking. All names, prices, availability, and messages are authored fixtures.

The scenario is **DEV01**, a development example. Do not include it in the held-out comparison in [the evaluation protocol](../08_evaluation.md). Evaluation cases must be authored separately with distinct details and frozen before comparison runs.

## Initial task

The event opens at 17:00 and ends at 18:00 in one fixed room. It has five activities: setup, welcome, demonstrations, skills exchange, and closing. Demonstrations need a projector. The skills exchange can run without it. Both middle activities last twenty minutes and may exchange positions.

The contingency budget is 15,000 cents. The agent's initial grant permits zero new committed spending and up to 3,500 cents held against a free provisional backup reservation. A purchase needs additional organizer authority. Reordering the two middle activities costs nothing and is already delegated. The room, required activities, public start, and hard end remain constraints.

A participant grant allows the facilitator to update their own check-in or submit an observation. It does not permit schedule changes or speaking for other participants. Future declared availability is not the same as observed arrival.

## Artifacts and sequence

| File | Stage | Meaning |
| --- | --- | --- |
| [campus_showcase.public.json](campus_showcase.public.json) | Revision 3, 16:40 | Public starting state and visible ambiguous delivery message |
| [change_spec.json](change_spec.json) | Interpretation of revision 3 | A possible delay, linked to the message, with a proposed status check |
| [observation_after_query.json](observation_after_query.json) | Revision 3 to 4, 16:42 | The relevant status query reports an estimated 17:25 arrival |
| [candidate_plan.json](candidate_plan.json) | Candidate based on revision 4 and goal version 1 | Swap demonstrations and skills exchange while preserving other commitments |
| [constraint_report.json](constraint_report.json) | Snapshot evaluation | Known constraints pass under explicit readiness assumptions |
| [commit_request.json](commit_request.json) | `apply_plan` request | Bind the candidate, report, grant, expected revision, goal version, and idempotency key |
| [commit_receipt.json](commit_receipt.json) | Revision 4 to 5, 16:43 | Record the two changed slots and zero additional spending |
| [campus_showcase.evaluator.json](campus_showcase.evaluator.json) | Private runner input | Future resource arrival and outcome predicates, unavailable to the agent |

The visible status response reports an ETA. The actual arrival occurs later in the private fixture and is exposed only when the scenario clock reaches it. The example does not let a planning tool inspect that future arrival.

These are connected records for a proposed implementation. Reading them is not executing an application. The implementation must store the candidate and constraint report, resolve their identifiers, ingest the new observation at revision 4, and perform the mutation transaction before it can truthfully emit the illustrated receipt.

## What the plan update means

The revised schedule puts skills exchange at 17:10 and demonstrations at 17:30. It is feasible under the stated arrival and participant-availability assumptions. The executor still checks actual equipment and role readiness before starting each activity.

If the equipment has not arrived by the last useful contingency time, the agent must query, prepare a permitted alternative, or explain the remaining conflict. It cannot turn the reported ETA into a guaranteed arrival. If no feasible recovery remains, the correct result is an explicit unresolved or infeasible outcome.

The backup projector is an approved compatible resource in the fixture. A free hold reserves capacity and 3,500 cents of spending headroom for ten simulated minutes. Conversion to a paid booking would exceed the initial zero-spend grant. The illustrated schedule-only update requires no hold and adds no spending.

## Authority and idempotency

The server binds `agent_demo` to `grant_coordinator_demo`. The request body cannot create that identity. The receipt carries a SHA-256 digest of the example request serialized as UTF-8 JSON with sorted keys and compact separators. The runtime must define and apply one canonical serialization rule.

An identical retry of `demo_commit_swap_001` returns the original receipt. It does not produce revision 6 or move the activities again. Reusing the same key with different request arguments is a conflict. A genuinely new request based on revision 4 after the successful mutation is stale and must be re-evaluated.

## Use during implementation

Start with a deterministic loader and validator. Check all references and invariants, then implement observation ingestion, candidate evaluation, and `apply_plan`. Connect the language model only after this path works without it.

For community adaptation, replace declared activities, resource capabilities, authorized roles, and goals through a profile. Do not expose evaluator labels to the agent or count a wording change as a new independent operational case.

## Configuration regression: community skills exchange

[community_skills_exchange.public.json](community_skills_exchange.public.json) is a second fictional development profile on November 7, 2026. It has six activities and a two-hour public program. Guided practice depends on a demonstration, while peer exchange can move independently. The budget, priorities, resource terms, and time windows differ from the showcase.

The community contribution is a tentative offer from a registered kit steward. It can become useful evidence after confirmation, but does not itself allocate the resource. A separate participant grant permits the peer facilitator to check in for their own role. Neither participant can change organizer priorities or spend money.

This public fixture establishes that the proposed schema can represent a second workflow. It has no supplied private outcome trajectory and is not a completed evaluation episode. Planner behavior, participant usability, and actual community usefulness still need implementation and validation.

## Second showcase: Pantry Continuity

[pantry_continuity.public.json](pantry_continuity.public.json) is DEV03, a fictional November 9 distribution session. [pantry_continuity.evaluator.json](pantry_continuity.evaluator.json) contains private conditional response rules and later events. Neither file is a measured result, and DEV03 is excluded from the held-out pantry suite. The public file uses the shared `0.2.0` contract with the pantry quantity and service extensions.

The target is 40 standardized kits distributed by 13:40. Pantry stock contains 24, partner stock at the same fictional venue contains 16, and a separate expected shipment promises 20. Its delivery warning may lead to a status query. The public initial allocation proposes 24 kits, has no stock hold, and is not execution-ready or a completed 40-kit plan.

| Stage | Pantry physical / reserved | Partner physical / reserved | Expected shipment | Cumulative distribution | Remaining service target |
| --- | --- | --- | --- | --- | --- |
| Initial state | 24 / 0 | 16 / 0 | 20 | 0 | 40 |
| Agent holds partner stock for transfer | 24 / 0 | 16 / 16 | 20 | 0 | 40 |
| Staff records the full internal handoff | 40 / 0 | 0 / 0 | 20 | 0 | 40 |
| Agent holds and commits pantry allocation | 40 / 40 | 0 / 0 | 20 | 0 | 40 |
| Staff records authorized on-time distribution | 0 / 0 | 0 / 0 | 20 | 40 | 0 |

These are expected arithmetic states for a possible successful development path, not an execution log. The runtime must generate its own revisions and receipts. The agent may choose another valid path, and failed handoff, partial receipt, expiry, or inadequate service time must produce a different final state.

The initial **pantry supply shortfall** is 16, while the remaining service target is 40. After handoff, supply shortfall is zero but nothing has yet been distributed. Forty kits do not imply forty people served. `attendance_target: 12` is a fixture occupancy planning bound. `Resource.capacity: 100` for stock is a storage bound, while the consumable ledger determines physical units.

`pantry_parameters` declares one unit per qualified service minute, the registered staff role, a two-minute handoff response, and the 12:30–12:50 handoff window. A transfer hold includes `purpose: stock_transfer` and a destination, creating a local pending staff task. The private staff rule begins after a valid task and checks current stock, grant and hold at completion. A response must arrive before the exclusive 12:50 cutoff. The private rule is not an automatic 12:35 stock credit.

The runner records actual staffed service intervals only after allocation, reservation and readiness are valid. A late 13:10 start provides at most 30 units of capacity by 13:40. Completion at the inclusive 13:40 deadline is processed before service-close and reconciliation-start events at that timestamp. Actual late distribution can be recorded while staff authority remains valid, with its lateness preserved and no retrospective success claim.

Staff identity is separate from the agent. `record_stock_receipt` and `record_distribution` cannot be invoked through the agent's grant. The same staff response rule and latency apply to every compared policy. In the live demo a presenter can use the staff view, with the role change visible. A planned JSON outcome cannot substitute for these executed actions.

All eleven JSON examples use planning contract `0.2.0`. The original campus request digest was recomputed when the version field changed. See [schema validation](../schemas/README.md) for the structural check and [the pantry specification](../15_pantry_showcase.md) for behavioral requirements.

The campus resource `source_ref: fixture_catalog_v1` and skills-exchange `source_ref: community_fixture_catalog_v1` identify their authored initial catalogs embedded in those public fixtures. They are provenance labels for scenario setup, not observation IDs or claims of external verification. Pantry resources instead cite their visible fictional stock/staff observations. The runtime source registry must preserve this distinction when projecting evidence.
