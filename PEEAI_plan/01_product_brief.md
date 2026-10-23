# Product brief: Plan B

**Status:** Approved direction for planning. No Plan B application is implemented by this documentation.  
**Planning date:** October 23, 2026, America/New_York.  
**First demonstration:** *The Show Must Go On*.  
**Purpose:** A community event agent that checks uncertain updates, prepares useful contingencies, and changes an operating plan within explicit constraints.

## The decision

Build one agent with configurable operation profiles. Start with a campus showcase. Demonstrate that community members can change the available options through a check-in, a resource offer, or an organizer's updated priority. Pantry Continuity is the second showcase, using a quantity-aware adapter for a fictional staff-directed distribution session. A community skills exchange remains the simplest configuration regression. A neighborhood cleanup is a later extension.

The product promise is:

> Keep a community event viable when circumstances change. Check what matters, prepare a feasible alternative, and explain each committed change.

The planned first version operates a stateful sandbox. A reservation, check-in, hold, or plan change must produce an inspectable record in the prototype. Production university bookings, purchases, and messaging require separate integrations and operating authority.

## The problem and the current hypothesis

An organizer may receive a delivery warning, a participant update, and a conflicting resource notice within minutes. Each message can affect several activities. Acting immediately can cause avoidable disruption. Waiting can remove a useful backup. Reading the messages is only one part of the job. The organizer must identify the relevant dependency, decide what to verify, and preserve the commitments that still work.

Our product hypothesis is that a small agentic operating loop can reduce the effort of these decisions while keeping the organizer in control of consequential commitments. This is a hypothesis for interviews and testing. We have not established customer demand, adoption, or real-world impact.

UMass Boston's official student event workflow connects room requests, confirmation, equipment, catering, and promotion. It gives designated event planners a role in the reservation process and describes advance coordination with Event Services. Those dependencies support the relevance of an event operations use case. They do not establish that the university endorses this project or grants it booking access. [Official student event procedures, checked October 23, 2026](https://www.umb.edu/event-services/student-organizations/)

## Who the product serves

| Person | Situation | What they need from Plan B | What they retain control over |
| --- | --- | --- | --- |
| Student or community organizer | Coordinating a small event with a fixed venue and deadline | A short, feasible action recommendation and an updated operating board | Event goals, allowed actions, final commitments outside delegated limits |
| Volunteer or facilitator | Has a specific role and limited availability | A quick way to state readiness, a delay, or an available resource | Their participation, availability, and offers |
| Resource steward | Controls a room item, equipment kit, or approved backup | Clear requests with time windows and release conditions | Whether a resource is actually available and may be used |
| Attendee or audience member | Needs to understand what will happen next | A stable public schedule and a simple way to participate in the demo | Whether to contribute information or join an activity |
| Evaluator or technical reviewer | Wants to know whether the agent made a good decision | Source-linked actions, checked constraints, and comparative results | Their assessment of the evidence |

Personas describe roles in a hypothetical deployment. They do not represent confirmed users or partners.

## Core job to be done

> When an unexpected update threatens an event, help me identify the affected commitments, obtain the missing fact that matters, and implement the smallest feasible adjustment so that the event can still achieve its purpose.

The phrase "smallest feasible adjustment" is an objective, not a universal rule. An organizer can explicitly prioritize completing a particular activity or preserving a participant's available time over minimizing schedule movement. The system must show the selected priorities and honor hard constraints before optimizing preferences.

## The agent's operating contract

| Element | MVP definition |
| --- | --- |
| Goal | Complete required event activities within the event window while preserving specified commitments |
| Hard constraints | Fixed confirmed venue, resource capacity, activity dependencies, explicit participant availability, total permitted spend, and action authorization |
| Preferences | Fewer unnecessary changes, lower spend, shorter delays, lower verification cost, and organizer-specified priority among optional outcomes |
| Inputs | Event configuration, current state, timestamped messages, resource status, delivery status, participant check-ins, and human priority changes |
| Tools | Read state, check a relevant status, evaluate allowed candidates, create or release a hold, request a commitment, and apply an authorized change |
| Output | A concrete state transition plus a concise action record, or a clear statement that the current constraints cannot all be satisfied |
| Feedback | Tool success or failure, expiry of a hold, new observations, and later activity outcomes |

The three decision modes are:

1. **Verify:** Read a source that could change the selected response. Record the answer, its scope, and its time.
2. **Prepare:** Create a reversible contingency within the permitted budget and lifetime. A hold consumes capacity according to the resource model and expires explicitly.
3. **Commit:** Apply a checked plan change with the authority configured for that action. Re-read relevant state if the proposal has become stale.

The organizer can delegate a bounded set of sandbox actions at setup. The agent then acts within that standing grant without repeated approval clicks. A proposed action beyond the grant shows its concrete consequences and the particular permission needed.

Doing nothing can also be correct. A stale message or an update that leaves all relevant commitments feasible should not cause a plan change merely to demonstrate activity.

## Why the community is part of the mechanism

People contribute actionable state, not just audience feedback. A facilitator can check in for their own role. A resource steward can confirm a registered backup. The organizer can change a preference after learning that a participant has limited time.

An offer is distinct from confirmed availability. The system first records who offered what, for which event, and for which time window. Only a validated registered resource with explicit capacity and compatibility can enter a feasible plan. A new unregistered offer remains a proposal until reviewed.

The community interaction should be small enough to explain in one sentence and meaningful enough to change the plan. It must remain optional. The demonstration has a presenter-operated equivalent when a second device or volunteer is unavailable.

See [community scenarios](02_community_scenarios.md) and [user experience](03_user_experience.md) for the interaction design.

## The contribution we want to demonstrate

The research question is:

> Can selective verification and reversible contingencies preserve task success while reducing unnecessary changes under uncertain updates?

The proposed contribution combines a source-linked change representation, a verification policy, a finite candidate planner, and controlled state transitions. Its value must be established against capable alternatives with equivalent information and actions.

Plan repair, tool use, and information gathering are established research topics. Avoid a market-first or research-first claim for the combination before completing the literature review and evaluation. The defensible hackathon claim is a working, understandable, evaluated mechanism for this bounded setting.

The project can be technically ambitious through careful problem formulation, explicit assumptions, meaningful baselines, and well-instrumented failures. A large number of agents or integrations is not necessary to establish that depth.

## Relationship to COLLIE

COLLIE offers a useful design pattern: language proposes structured changes and a separate numerical process controls their influence on actions. Its scenario comparisons, trajectory records, and cached execution also support a repeatable demo and evaluation.

The event task introduces discrete schedules, resource commitments, participant availability, and reversible holds. Those require new models and tooling. Do not present the existing inventory controller as an implemented event planner or transfer inventory-specific theoretical guarantees without a new argument.

The existing evidence also motivates a serious non-LLM baseline. The new prototype should isolate whether interpretation and selective tool use add value beyond a deterministic response to the same observations.

## MVP boundary

### Required for the first complete slice

- One event with a fixed venue and four to six activities.
- A small registered resource catalog with capacities, compatible uses, and costs.
- One equipment or supply delivery dependency.
- A timestamped update inbox with relevant object references.
- A participant check-in and one registered resource offer or confirmation.
- A finite set of allowed schedule or resource alternatives.
- Real sandbox records for holds, releases, approvals, and committed changes.
- A side-by-side view of the prior plan and the current proposal.
- One true delay, one stale or conflicting notice, and one infeasible case.
- A repeatable episode log and a recorded replay.

### Add after the first slice passes

- A community skills exchange configuration using the same contract.
- The [Pantry Continuity](15_pantry_showcase.md) profile, with conserved consumable stock, staff-confirmed handoff, and aggregate target completion. This is required for the planned full second-domain build in Wave 2.
- Multiple wording variants of the same underlying update.
- A second participant device for a live contribution.
- Read-only retrieval over a small curated policy pack.
- Selective verification comparisons across a fixed scenario bank.

### Later product work

- Integration with actual reservation or communications systems.
- Cross-venue travel, weather-sensitive outdoor work, or citywide resource matching.
- Multi-organization ownership and identity management.
- Perishable food handling, recipient eligibility or priority decisions, household records, and dietary substitutions. The bounded aggregate kit-distribution example is covered by Wave 2.

The first version is a decision and coordination prototype. Any operational pilot begins with an organizer's validated event model and a bounded action agreement.

## Product acceptance criteria

| ID | Acceptance condition | How it is checked |
| --- | --- | --- |
| P1 | A new viewer can identify the event goal and the threatened activity within 20 seconds | Short walkthrough with a participant unfamiliar with the project |
| P2 | A message becomes a source-linked structured update with an explicit time and target | Inspect the record and its corresponding inbox item |
| P3 | A successful action changes persisted sandbox state and appears in the action history | Read the resulting resource, hold, or plan record |
| P4 | An incompatible or unavailable resource cannot appear in a committed feasible plan | Controlled negative scenario and validator result |
| P5 | A stale warning produces the appropriate verification or rejection without an unsupported commitment | Replay against a known older booking record |
| P6 | A community contribution can alter the set of feasible candidates | Compare candidates immediately before and after a validated check-in or resource confirmation |
| P7 | The organizer can see and change a preference without silently changing a hard constraint | UI walkthrough and state diff |
| P8 | An infeasible situation produces an explicit unsatisfied-constraint explanation | Scenario with every allowed backup unavailable |
| P9 | The same agent entry point runs campus and pantry workflows through explicit domain adapters, while skills exchange loads through the campus adapter | Run all profiles, inspect adapter boundaries, and verify pantry stock conservation and service accounting |
| P10 | The seven-minute demonstration has a complete live path and a clearly labeled replay fallback | Timed rehearsal |

These are proposed acceptance criteria, not completed results.

## Measures of success

Track task completion, constraint violations, number of changed commitments, time to recovery, unnecessary actions, tool calls, and execution cost. For usability, ask whether participants can explain why the agent checked a source and why it accepted or rejected an alternative.

Report the full set of tested scenarios, including quiet conditions and failures. Report observed organizer benefit only after an organizer participates in a defined test. A simulation's cost or completion score is not evidence of community impact.

## Working positioning

**One sentence:** Plan B helps community organizers keep an event viable when plans change by deciding what to verify, what to prepare, and when to commit.

**Technical sentence:** A tool-using agent converts uncertain updates into typed changes, evaluates bounded contingencies against event constraints, and executes authorized state transitions with explicit evidence and feedback.

**First demo invitation:** "Choose what goes wrong at our showcase, then help the community recover."

**What we can claim when built and checked:** The prototype executes this bounded workflow, makes its decisions inspectable, and has been compared with specified alternatives on a disclosed scenario bank.

## Decisions still open

- Final public product name and visual identity.
- Which organizer will review the first workflow.
- The exact resource, cost, and operation limits in the organizer's standing grant.
- Exact preference weights and their interpretation with an organizer.
- Which external system, if any, is appropriate for a future read-only pilot.

The default implementation can proceed using a synthetic campus profile, an explicit event-scoped authority grant, and a documented finite candidate set. Commitments outside that grant require an organizer's concrete decision.
