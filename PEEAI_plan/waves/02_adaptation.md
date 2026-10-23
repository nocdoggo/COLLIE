# Wave 2 — Live agent and bounded adaptation

Status: proposed implementation tasks, 2026-10-23. No live agent or pantry adapter is claimed implemented. This is the second of the [three implementation waves](../11_implementation_roadmap.md).

Build on the accepted Wave 1 state/tool boundary. This wave adds live interpretation and tool choice, meaningful community input, a second event configuration, and Pantry Continuity as an explicit consumable-stock extension. The campus event remains the primary demonstration. MBTA is an optional read-only evidence source.

## Entry gate and parallel work

M1 must pass before enabling live model-driven writes. The shared tool executor must already reject stale, unauthorized, duplicate, expired, and infeasible operations. The provider access check, community UI shell, and pantry contract review can proceed in parallel without allowing unfinished code to bypass that executor.

The nonsecret model registry and provider patterns already exist, but current app-compatible access is unvalidated. Follow [API and access requirements](../16_api_and_access.md): reuse authorized existing configuration if usable; otherwise identify the missing endpoint, model ID, or key. Freeze an allowed spend cap before live tests. No paid call is claimed to have occurred during this planning work.

## File ownership and task dependencies

All paths are proposed under `apps/plan_b/`. E/A/U/V roles are defined in the [roadmap](../11_implementation_roadmap.md#work-ownership-and-proposed-files).

| Task | Owner / reviewer | Proposed files | Dependencies | Required deliverable and check |
| --- | --- | --- | --- | --- |
| W2.1 — Provider and bounded live loop | A / E | `agent/provider.py`, `agent/interpret.py`, `agent/orchestrator.py`, `agent/prompts/`, `api/config.py`, `.env.example`, `tests/test_agent_boundary.py` | M1; G-LLM for live checks | Typed interpretation with evidence references; validated tool selection; caps and failure behavior; one actual live request and successful tool-backed continuation |
| W2.2 — Selective policy and community workflow | A with U / E | `agent/policies/selective.py`, `web/src/views/Participation.tsx`, `web/src/components/DecisionCard.tsx`, `api/participation.py`, `scenarios/public/community_skills_exchange.json` | W2.1 for live policy; W1 contracts for UI/config | Keep/verify/prepare/commit/ask behavior; role-scoped check-in; registered resource offer; organizer goal-version change; same event adapter loads skills exchange |
| W2.3 — Pantry adapter and staff controls | E with U / V | `domain/adapters/pantry.py`, `domain/stock.py`, `tools/stock.py`, `store/migrations/`, `web/src/views/PantryBoard.tsx`, `web/src/views/StaffActions.tsx`, `scenarios/public/pantry_continuity.json`, `scenarios/private/pantry_dev.json`, `tests/test_stock_conservation.py` | M1; frozen additive pantry contracts | 40/24/20/16 fixture; global quantity reservations; atomic handoff; staff-only receipt/distribution; service scoring; shared core and trace format |
| W2.4 — Optional MBTA adapter | A / E | `integrations/mbta.py`, `integrations/transit_observation.py`, `tests/fixtures/mbta/`, `tests/test_mbta_adapter.py` | Common query interface; G-MBTA; W2.1 if used by live agent | Scoped read-only source behind `query_status`; freshness, no-data and failure semantics; deterministic fixture mode; no credential in browser/logs |
| W2.5 — Integrated adaptation gate | V with U / E and A | `tests/test_live_workflow.py`, `tests/test_pantry_workflow.py`, `evaluation/policies/`, `README.md`, `evaluation/development/` | W2.1–W2.3; W2.4 only if included | Live campus and community traces; conserved pantry trace; failure checks; candidate/authority parity for future P0–P3; M2 completion record |

W2.3 can run alongside W2.1 and W2.2 because it shares stable core contracts. Keep one orchestrator, transaction store, grant system, and receipt format. A domain name may select an adapter; it must not select a hidden scripted success path.

## Live agent contract and API gate

The provider adapter supplies strict `ChangeSpec` interpretation and bounded tool requests. The server assigns trusted source identity and resolves referenced entities. Prompt text cannot create entities, grant authority, overwrite evidence, or call arbitrary endpoints. All model-selected mutations use the Wave 1 executor and its authoritative candidate store.

Implement the [decision policy](../05_decision_policy.md) with an explicit loop: read consistent state, interpret supported observations, evaluate the declared alternatives, assess decision-relevant uncertainty, choose a useful query or reversible hold, and apply a checked plan when authorized. Keep and ask are legitimate outcomes. The agent should explain the chosen action using cited observations, constraint reports, and receipts; it need not expose private reasoning or generate confidence scores.

Use proposed practice caps of eight model calls and sixteen total tool calls per episode, including failed calls and retries; adjust only on development cases and freeze the final values for Wave 3. Allow one structured-output repair, then retain an unresolved interpretation. Tool timeout leaves uncertainty visible. An ambiguous mutation result requires receipt reconciliation by its original idempotency key. A stale revision triggers refresh and re-evaluation. No recursive retry or continuing loop is unbounded.

G-LLM passes when the selected provider performs one strict interpretation and a bounded tool invocation through the actual application adapter, a continued turn consumes the real tool result, and the logs record model identity, configuration, actual latency, usage when available, and failures without secrets. A plain chat response or a stubbed success does not pass. If access fails, continue deterministic pantry, UI, fixtures, and evaluation-harness work. Mark live-agent and stochastic-comparison work blocked by the specific missing configuration; replay remains a labeled fallback, not proof of a live gate.

## Community interaction and authority

Provide a participant view for one registered volunteer alias, with a scoped availability interval and check-in. The resulting observation must change candidate feasibility or remove an unresolved role assumption in at least one development episode. A natural-language resource offer can activate only a preconfigured resource after required capability, owner, availability, and terms are checked. An offer alone cannot increase inventory, reserve equipment, or spend money.

Provide an organizer view for changing a preference or authorized goal constraint. A valid change creates a new goal version and invalidates older candidate reports. A participant session cannot change that goal, attest another volunteer's arrival, or obtain organizer privileges by saying so in a message.

Load `community_skills_exchange` through the existing event adapter, with at least one meaningful changed staffing, window, or resource constraint and a state-based success check. This is configuration reuse. It is distinct from the consumable-stock capability in Pantry Continuity. A local two-tab walkthrough suffices for implementation acceptance; call it community validation only if actual participants provide recorded voluntary feedback under the [validation plan](../10_community_validation.md).

## Pantry adapter: exact operational contract

Use [Pantry Continuity](../15_pantry_showcase.md) and the shared schema as the source of truth. Add optional `EventGoal.service_targets`, `Resource.consumable_stock`, and `Assignment.consumable_allocations`. Existing event-only fixtures remain valid without those optional fields. Add stock tables/ledger projections through a migration; do not retrofit reusable equipment with an unexplained consumption flag.

The canonical fixture contains target 40 kits, `pantry_stock` on hand 24, expected shipment 20 arriving too late, and `partner_stock` on hand 16 under a separate fictional steward at the same venue. There is no transport route or real partner connection. Staff defines the kit unit, service policy, session, deadline, and existing roster; the agent does not infer nutritional equivalence or recipient eligibility.

Two counters must remain separate:

| State | Pantry-controlled supply gap | Unfulfilled service target |
| --- | --- | --- |
| Initial: pantry 24, partner 16, distributed 0 | `max(40 - 24, 0) = 16` | `40 - 0 = 40` |
| Partner 16 held, handoff not recorded | 16 | 40 |
| Staff handoff complete: pantry 40, partner 0 | 0 | 40 |
| All 40 committed to distribution, none completed | 0 | 40 |
| Staff-confirmed distribution of 40 before deadline | 0 for the completed session target | 0 |

After distribution begins, calculate remaining supply needs against the **remaining** service target, so consumed stock does not falsely create a new supply shortage. Keep the original target visible throughout. Reservation, plan acceptance, and receipt each have zero direct effect on service achievement.

Implement the following sequence using common tools and authenticated staff actions:

1. Agent queries current alternate availability and calls `hold_resource` for 16 partner kits. The hold reduces globally available partner stock but moves nothing and serves nobody.
2. Staff or the explicitly labeled simulator calls `record_stock_receipt` with the source stock, destination stock, matching reservation, quantity, observation reference and unique receipt reference. The transaction debits partner 16 to 0, closes its reservation, credits pantry 24 to 40, increments the revision, and persists one receipt. Expected late supply remains 20.
3. Agent reserves the 40 local pantry kits and refreshes state/candidate validation. Under the existing standing grant, `apply_plan` converts valid holds to committed consumable allocations without counting the same units twice.
4. Staff or the labeled simulator calls `record_distribution` with the target, stock, quantity, time and unique distribution reference. On-time distribution consumes 40 on-hand and committed reserved kits and records 40 achieved. Both local on-hand balances are now zero; the expected 20 is still unreceived.

`record_stock_receipt` and `record_distribution` are staff-only operations. The agent can request the missing evidence or handoff, but cannot attest physical arrival or service on staff's behalf. The simulator may provide controlled staff actions to all evaluation policies under the same frozen rules.

Reservations for a consumable persist across the session's planning horizon; disjoint time slots cannot reuse already allocated stock. `on_hand_quantity` includes reserved, unconsumed units; available quantity is on-hand minus reserved. Active holds and committed allocations are disjoint components of reserved quantity. `release_hold` and expiry release the claim, creating no stock. Distribution consumes stock and cannot be reversed by releasing a hold or ending an activity.

For each stock, enforce `closing_on_hand = opening_on_hand + valid_receipts - transfers_out - distributions`. Internal handoffs preserve the total across source and destination. Expected units never enter that equation before valid receipt. A matched external receipt credits stock once and reconciles its shipment expectation once; an internal handoff cannot decrement an unrelated expected shipment. Enforce both transport idempotency and unique physical receipt/distribution provenance, including retries with fresh request keys.

Support a partial source-hold handoff atomically. Transferring 10 of 16 held kits debits and credits 10, reduces the hold's `remaining_quantity` to 6, and leaves those six reserved until authorized release or expiry. A hold becomes fulfilled only at zero remaining quantity. The residual stock cannot disappear, become available twice, or count as received by the pantry. Distribution of the available 34 kits leaves a six-kit service deficit against the unchanged target.

Candidate checks combine quantities with throughput, time, roster, dependencies and budget. Use the fixture's typed `pantry_parameters` for distribution rate, attended execution, handoff latency and source cutoff; validate their cross-field feasibility rather than burying these values in prompts. Actual distribution cannot exceed throughput accumulated while required staff and physical stock were ready. Unit mismatch, overdraw, negative/fractional quantities, unreceived supply, forged evidence, or unauthorized staff actions must reject.

Partial receipt records the actual amount and keeps the remaining service deficit visible. Staff may record a late physical distribution under a still-valid grant and using the actual server/scenario clock: reduce physical stock correctly, but exclude late units from on-time achievement. A late receipt or distribution cannot retroactively meet the original deadline. Freeze the runner's ordering of receipt, distribution, and close events at an inclusive deadline; the browser or model cannot backdate evidence. No target reduction is permitted without an explicit authorized goal-version change; evaluation still reports attainment against the original target.

## Optional MBTA read adapter

The credential has been supplied, and a header-bearing read-only `GET /routes/Red` probe returned HTTP 200. This supports access setup, not readiness of an application adapter or proof of account quota. No additional transit key is needed now. Follow [API and access requirements](../16_api_and_access.md) for current probe limits and configuration.

Implement an allowlisted route/stop query behind `query_status`, normalize its source identifier, source timestamp when available, retrieval time, active period, scope, and public evidence text. Preserve unknown fields. A transit alert is advisory context; actual volunteer availability still comes from their check-in. Empty results are not confirmation that a person will arrive on time. No transit inference is needed for the same-venue pantry handoff.

Use bounded timeouts, cached queries, response-aware rate-limit handling, and fixed fixtures for no-data, irrelevant/inactive notices, missing timestamps, duplicates, malformed output, timeout, and rate-limit errors. Credentials remain server-side and cannot enter tool observations, browser assets, logs, or replays.

Keep wall-clock live evidence distinct from the simulated fixture clock. Frozen evaluations use fixture mode. Live October information cannot silently drive a fictional November event after retimestamping. A current-time feed panel can demonstrate connectivity separately; integrating it into decisions requires a matching current-time event and relevance configuration. Any failure falls back to disclosed fixture data or disables transit context without blocking M2.

## Mandatory M2 checks and exit criteria

| Check | Evidence required |
| --- | --- |
| Live campus behavior | One real model-driven end-to-end recovery with a useful tool call, validated action and fresh-state agreement; a stale warning produces a distinct justified response |
| Bounded failure behavior | Malformed model output, unknown entity, exhausted cap, timeout and stale revision remain visible and produce no invented success |
| Community workflow | Participant input changes a role fact and affects planning; unauthorized goal or stock actions reject; skills exchange loads through the event adapter |
| Shared pantry core | Same orchestration, grants, receipts, replay and transaction boundary run the pantry scenario; domain adapter owns only added semantics |
| Stock and service accounting | 24/16 to 40/0 handoff conserves stock; target remains 40; receipt/commit do not reduce service deficit; distribution alone records achieved service |
| Quantity failure checks | Overlapping and non-overlapping double allocation reject; release/expiry do not create stock; duplicate physical records cannot credit twice; partial handoff preserves residual reservation; early distribution cannot exceed attended throughput; late records retain truthful times and fail on-time attainment |
| Staff boundary | Agent cannot call staff-only receipt/distribution operations; missing staff attestation prevents fictional physical success |
| Future comparison parity | P0–P3 use the same candidates, grants, executor, tools and domain semantics within each suite; any policy-specific prompts are recorded |

M2 requires W2.1–W2.3 and these checks. W2.4 is stretch. Retain actual development traces, focused check results, configuration versions, shared-interface changes, adapter implementation effort, and unpassed items in the M2 record. These are development evidence, excluded from held-out evaluation.

If pantry semantics or staff controls fail, keep the campus application usable and identify the pantry criterion as incomplete. A skills-exchange example can fill a presentation slot but cannot establish pantry transfer. If the second live presentation is too fragile, use its actual recorded trace or omit it. Neither action excuses incorrect inventory accounting. Hand off the frozen-capable build and development findings to [Wave 3](03_evidence_showcase.md).
