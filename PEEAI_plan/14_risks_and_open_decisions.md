# Risks, assumptions, and open decisions

This register prioritizes issues that can change the product, demonstration, or interpretation of results. It is a build-management tool, not a request to stop ordinary work.

## Resolve before implementation choices become expensive

| Decision | Current working assumption | Resolution method | Affected artifact |
| --- | --- | --- | --- |
| Available time and team size | Three acceptance-gated waves, assign owners at kickoff | Team kickoff | Roadmap and ownership |
| Submission requirements | Public dates are known, Canvas details are not | Read enrolled course instructions | Packaging checklist |
| First community workflow | Campus showcase, then bounded Pantry Continuity. Skills exchange is a configuration regression | Organizer walkthrough, then pantry operator review if accessible | Product brief and profiles |
| Initial resource dependency | Projector delivery affects demonstrations | Validate whether the audience recognizes the situation | Example fixtures and demo |
| Model and serving endpoint | Existing client infrastructure may be reused | Smoke-check structured outputs, latency, failure handling, and cost | Run manifest |
| Spending and execution authority | Sandbox operations with explicit per-event grants | Choose grants at scenario creation | Tool contracts and UI |
| Objective weights | Hard feasibility first, explicit penalties for delay/cost/churn | Organizer preference review and sensitivity runs | Decision policy |
| Community input mechanism | Scoped participant check-in plus optional resource offer | Accessibility and trust-boundary walkthrough | Participant view |
| Transit API | Supplied MBTA key saved and a route request returned HTTP 200 | Implement source timestamps, scope filtering, cache and outage behavior in Wave 2 | API and access plan |
| Pantry transfer semantics | Staff-recorded handoff and distribution, one standardized kit unit | Validate conservation and aggregate target tests before the second demo | Pantry adapter and fixtures |

## Prioritized risks

| Risk | Why it matters | Concrete treatment | Completion evidence |
| --- | --- | --- | --- |
| Broad event promise outruns implementation | Rooms, catering, transport, staffing, and participant needs have different models | One fixed venue and a small resource/activity model for the first build | Scope and UI agree on supported actions |
| Product adds little beyond a deterministic planner | Prior COLLIE results leave primary incremental language value unresolved | Include a strong deterministic comparison and language-paraphrase cases | Separate extraction and outcome results |
| Verification delays useful action | A missed decision window can make a correct diagnosis useless | Bound the loop and include reversible preparation and explicit deadlines | Late-check and deadline tests |
| Confident text becomes unsupported numerical certainty | It can make expected-cost decisions misleading | Use declared scenario assumptions or uncertainty ranges. Do not interpret model confidence as probability | Assumption record and sensitivity results |
| Duplicate or stale notices inflate evidence | Multiple copies may refer to one outdated event | Track source record, entity, validity time, correlation group, and supersession | Duplicate/stale scenario outcomes |
| Participant input changes someone else's authority | A resource offer is not permission to spend or cancel | Resolve authenticated role and event grant outside the model | Authority-negative tests |
| Concurrent changes invalidate a plan | A resource may be held or lost after planning | Compare state revision and revalidate atomically before commit | Conflict rejection and successful recompute |
| Retry creates duplicate holds or spending | Network uncertainty can cause repeated mutations | Idempotency keys, request fingerprints, durable receipts, and atomic transitions | Retry test changes state once |
| Hidden future reaches planning tools | It makes the agent appear more capable than it is | Separate evaluator files, private transitions, and public observations | Isolation check and inspected prompt/tool logs |
| A sandbox action is presented as an institutional action | It misstates what was achieved | Label operational fixtures and receipt origin | Presentation and UI review |
| Live presentation depends on a model or network | A delay can consume the seven-minute window | Labeled replay, cached fixtures, manual equivalent of participant input | Timed rehearsal with network disabled |
| Community adaptation becomes cosmetic | Changed labels do not prove a useful new workflow | Validate goals, constraints, roles, and actions with each profile | Profile fit checklist and operator feedback |
| Promised stock becomes claimed service | A reservation or expected delivery cannot feed the service counter | Separate expected, physical, reserved, transferred, and distributed units | Conservation checks and target-linked distribution receipts |
| A transit alert becomes a personal ETA | Public route conditions do not establish a person's journey | Use route alerts as optional context and seek the volunteer's own update | Irrelevant-alert and stale-source checks |

## Evidence boundaries

Do not transfer inventory profit gains, e-process guarantees, or benchmark reproduction results into claims about event recovery. Prior work explains the design lineage. New event-sandbox results establish only behavior under the stated model and scenario set.

Avoid counts such as people served, meals saved, or emissions reduced unless the data model and measurement support those units. A fulfilled resource request is not automatically a person helped. Use modeled cost, satisfied activities, violated constraints, and state changes for the initial evaluation.

## Later decisions

The following are outside the critical path until the first end-to-end loop and comparative evaluation work: a full institutional integration, arbitrary citywide routing, procurement from real vendors, cross-event optimization, participant profiling, inferred sensitive needs, and a new general theorem.

## Stop or simplify conditions

- If current information makes every candidate infeasible, show the conflict and ask the organizer to relax a specific constraint. Do not fabricate a feasible plan.
- If a source is unavailable, preserve unknown status and compare alternatives under the declared uncertainty. Do not silently treat failure as no disruption.
- If the selected community workflow cannot be represented by the fixed-venue model, keep it as a discovery result and choose a fitting profile for the first build.
- If the proposed policy does not beat a simpler baseline, report that outcome and emphasize demonstrated workflow capability only. Inspect the failure before expanding the claim or model.
- If time is short, retain one profile and deterministic replay while reducing optional live feeds and visual effects. Preserve goal checks and actual sandbox state transitions.
