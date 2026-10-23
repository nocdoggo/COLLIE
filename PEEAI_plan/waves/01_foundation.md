# Wave 1 — Deterministic foundation

Status: proposed implementation tasks, 2026-10-23. No task or gate is claimed complete. This is the first of the [three implementation waves](../11_implementation_roadmap.md).

The wave delivers one end-to-end campus slice with trustworthy state and useful behavior before a live model is connected. Load `campus_showcase`, inject a supported update, enumerate permitted repairs, execute an authorized choice, read the resulting state, and replay its visible history. Use a documented deterministic policy for this wave. Natural-language generation is not a prerequisite.

## Inputs and decisions to freeze

Use [architecture](../04_architecture.md), [tool contracts](../06_tool_contracts.md), [data model](../07_data_model.md), and the [public campus fixture](../examples/campus_showcase.public.json). Keep its [evaluator fixture](../examples/campus_showcase.evaluator.json) private to the runner. The public fixture is a development example; it does not replace the eight future held-out cases.

E owns the initial contract review with A, U, and V. Freeze stable entity IDs, goal versioning, simulated time and timezone, integer money units, activity windows/dependencies, source identities, grant scopes, the finite edit menu, expiry rules, and final-state success predicates. A resource expected later is not physically ready now. An activity starts only when its execution prerequisites are observed to hold.

Keep a narrow domain adapter interface from the start: validate public configuration, enumerate allowed candidates, check readiness, apply domain transitions through the executor, and score final state. Implement the campus adapter now; defer consumable behavior to Wave 2. The core owns authority, revisions, receipts, and persistence for every adapter.

## File ownership and task dependencies

Paths below are proposed under `apps/plan_b/`. Roles E/A/U/V are defined in the [roadmap](../11_implementation_roadmap.md#work-ownership-and-proposed-files).

| Task | Owner / reviewer | Proposed files | Dependencies | Required deliverable and check |
| --- | --- | --- | --- | --- |
| W1.1 — Contract and fixture | E / V | `domain/models.py`, `domain/adapters/base.py`, `domain/adapters/campus.py`, `scenarios/public/campus_showcase.json`, `scenarios/private/dev01.json` | Existing planning artifacts | Strict typed contracts; public/private fixtures; references resolve; initial plan is feasible; hidden future absent from public projections |
| W1.2 — Persistent state and tools | E / A | `store/database.py`, `store/migrations/`, `domain/authority.py`, `domain/clock.py`, `tools/reads.py`, `tools/mutations.py`, `api/routes.py` | W1.1 | State reads, observations, status query, hold/release, plan apply and check-in; atomic receipts; grants, expiry, versions, and idempotency enforced |
| W1.3 — Candidate planner | E / V | `domain/candidates.py`, `domain/constraints.py`, `domain/objective.py` | W1.1 | Enumerate configured edits; accepted/rejected candidate reports; deterministic ranking; no reservation side effects |
| W1.4 — Runner and rule policy | V with E / A | `scenarios/runner.py`, `evaluation/policies/rules.py`, `evaluation/scoring.py`, `tests/test_runner_isolation.py` | W1.2, W1.3 | One clock and common tool boundary; current-time observations only; activity execution and final-state scoring; development cases with honest success/infeasibility |
| W1.5 — Campus board | U / E | `web/src/views/EventBoard.tsx`, `web/src/components/EvidenceCard.tsx`, `web/src/components/ActionHistory.tsx`, `web/src/api.ts` | W1.1 for shell; W1.2 and W1.3 for integration | Goal, schedule, uncertainty, constraints, action state and receipts visible; result agrees with fresh API read |
| W1.6 — Replay and gate | V with U / E | `evaluation/export_trace.py`, `web/src/replay/`, `tests/test_stateful_tools.py`, `tests/test_campus_workflow.py`, `README.md` | W1.4, W1.5 | Sanitized trace export and read-only replay; consequential checks pass; clean startup instructions and M1 record |

W1.2, W1.3, and the UI shell can proceed in parallel once W1.1 is stable. The UI uses the public contract, not duplicated guesses about database structure. Any change to revision or receipt semantics must update all consumers before integration.

## Implementation contract

Use the proposed single-process API and SQLite store, or record an equivalent choice before coding. Every mutation loads state and authority inside a transaction, checks the expected revision and idempotency digest, validates domain constraints, and commits both state and receipt. A stale write rejects without partial mutation. An identical retry returns its original receipt; reuse of the key for a different request rejects. A failed precondition still has a traceable rejected attempt.

Implement synchronous expiry checks on both reads and mutations. A background timer can help the UI, but correctness cannot depend on it running on time. Resource holds consume capacity and modeled budget under their terms. Release, expiry, and conversion must leave accounting consistent. After a hold changes the revision, refresh candidate validation before applying the plan.

Start with a finite action set: keep, configured independent-activity swaps, allowed time offsets, registered backup resources, approved alternate formats, and at most the configured number of combined edits. Record candidate count and truncation. The planner checks dependencies, capacity, windows, volunteer availability, accessibility, and budget. It ranks feasible candidates with visible objective terms and deterministic tie-breaks. It proves infeasibility only over the declared action space.

The runner advances modeled time and checks actual execution prerequisites. Schedule acceptance can retain a clearly displayed future-arrival assumption; acceptance does not count an activity as completed or turn expected equipment into delivered equipment. The policy sees current public observations and its requested tool results, never the future schedule or case truth.

The deterministic policy supports documented development message forms and leaves unknown wording unresolved. It exercises the same tools, planner, grants, and scorer that future live policies use. Do not give it evaluator truth or hard-code a successful action sequence into the runner.

## Minimum visible workflow

1. Load the fixture into a clean sandbox and display the goal, active schedule, modeled budget, and authority envelope.
2. Submit an update through `submit_observation`; show source, relevant time, and affected entity.
3. Perform a scoped sandbox status query when the rules require one; show the actual result, including unknown/unavailable outcomes.
4. Display alternatives and assumptions from `evaluate_candidates`. A preview produces no reservation.
5. Place an allowed hold or apply a checked plan, then show the receipt and subsequent state read.
6. Advance the clock to observe readiness and actual activity completion or supported failure.
7. Reset to a new episode, then play the visible trace under a persistent **Recorded replay** label. Replay creates no new actions or apparent fresh tool responses.

Separate **attempted**, **rejected**, **unknown**, and **applied** action states. An explanation, preview, or UI toast cannot establish success. Give the UI readable text, keyboard operation, and an explicit sandbox/deterministic/replay mode label from the first slice.

## Mandatory checks and M1 exit criteria

Use focused tests for consequential state behavior and a browser walkthrough. No live model calls or external APIs are needed.

| Check | Pass condition |
| --- | --- |
| Genuine disruption | A development case produces a feasible repair and completed required activities, with matching receipts and final state |
| Stale or duplicate update | Identity/time handling preserves valid commitments; duplicate receipt/observation handling causes no second mutation |
| Impossible case | Planner exposes blocking constraints; no fabricated success, unauthorized budget increase, or invalid commitment occurs |
| Authority boundary | Participant text, offers, and injected instructions cannot expand a grant or impersonate an organizer |
| Transaction behavior | Stale revision rejects; identical retry returns one receipt; conflicting idempotency payload rejects; budget/capacity remain consistent |
| Time and holds | Expiry and release restore correct capacity/funds; an expired hold cannot support a commit |
| Failure reconciliation | An ambiguous mutation result is reconciled by its original key; no blind duplicate reservation is created |
| Readiness and scoring | A future-arrival assumption cannot count as physical readiness or completed activity |
| Isolation and reset | Projections/tool responses/browser export exclude private fields; reset clears episode-specific holds, memory, receipts and commitments |
| UI and replay | Displayed receipts match API state; a sanitized trace reproduces the visible result without evaluator truth |

M1 passes only when a clean checkout/startup executes the workflow and all required checks have recorded outcomes. Retain fixture hashes, a successful trace, a rejected-action trace, an impossible-case trace, and an M1 completion record. These requirements are not evidence that the checks currently pass.

## Scope, failure fallback, and handoff

Mandatory scope is one campus fixture, persistent state, authority, planner, tools, deterministic runner, board, and replay. Extra visual treatments, multiple simultaneous rooms, a general scheduler, and external services are stretch. Keep the slice small enough to inspect its complete action set.

If integration fails, isolate the boundary with a direct tool request and a state read. A static screen or hand-authored success transcript cannot pass M1. An API/CLI trace can support debugging while UI work continues, but the complete wave still needs the board. If replanning cannot be made reliable, reduce allowed edit templates and record the narrower scope rather than relaxing constraints.

Hand off versioned public contracts, the adapter interface, deterministic fixtures, tool failure vocabulary, trace schema, startup instructions, and M1 evidence to [Wave 2](02_adaptation.md). Provider access can be checked in parallel; no credential blocks Wave 1.
