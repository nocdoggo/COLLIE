# Adaptive community scenarios

**Status:** Scenario design, not a record of live events or partnerships.  
**Planning date:** October 23, 2026.  
**Design rule:** Keep one planning loop and shared authority, observation, and evaluation contracts. Change configuration for similar events; add an explicit capability when a new domain needs different state semantics.

## What adaptive means

Plan B adapts in three ways:

1. **Across communities:** A configuration supplies the activity graph, resource catalog, roles, constraints, and permitted actions for an event.
2. **During an event:** New observations change what the agent knows about a delivery, resource, or participant.
3. **Through human intent:** An authorized organizer can revise a preference or explicitly amend a constraint. A participant can update their own availability or offer a resource within the event.

Changing the title and colors alone does not demonstrate adaptation. At least one configuration difference must change the feasible set or the selected response. A skills-exchange facilitator's limited window is a cheap test of configuration transfer. Pantry Continuity is the diverse second showcase: consumable stock decreases when distributed, expected supplies require confirmed receipt, and a quantified service target can remain unmet even when every scheduled activity finishes.

The campus showcase remains the hero. Build its deterministic vertical slice in Wave 1. Wave 2 adds the agent, community input, the pantry capability, and optional MBTA context. Wave 3 completes evaluation, reliability, the rehearsed demonstration, and release. The [implementation roadmap](11_implementation_roadmap.md) owns the gates and detailed task order.

The runtime must separate public observations from the simulator's hidden future. Scenario authors can know which warning is true. The agent learns only from permitted observations and tool responses available at that point in the episode.

## Shared event contract

| Component | Example | Why it matters |
| --- | --- | --- |
| Purpose | Complete the required activities before the venue window ends | Defines task success |
| Activity graph | Welcome precedes a demonstration, pack-down follows resource use | Exposes dependencies |
| Resources | One equipment kit, one approved backup, one fixed room | Makes capacity and substitution explicit |
| Optional consumable stock | Confirmed kits, expected deliveries, quantity reservations, and distribution records | Prevents spending the same stock twice or treating an ETA as receipt |
| Optional service target | Distribute a configured number of standardized kits by the session end | Separates schedule completion from a delivered service outcome |
| Roles | Organizer, facilitator, equipment steward, participant | Determines who can report or authorize what |
| Time windows | A facilitator is available only for a declared interval | Prevents impossible substitutions |
| Budget | A fixed contingency allowance and nonrefundable costs | Makes preparation a consequential choice |
| Observation history | Delivery notices, confirmations, check-ins, and corrections | Supports source and freshness checks |
| Action rules | Prepare a hold, release a hold, request approval, commit a feasible change | Bounds the agent's authority |
| Outcome record | Completed activities, missed commitments, cost, and state changes | Enables evaluation |

Exact machine-readable field names and fixture values belong to the [data model](07_data_model.md) and [public campus fixture](examples/campus_showcase.public.json). The narratives below explain intended behavior without creating a second configuration authority.

## Profile A: Campus showcase

**Priority:** MVP and first seven-minute presentation.  
**Profile ID:** `campus_showcase`.  
**Canonical example event:** `e_showcase_01`, November 5, 2026, `America/New_York`. This is a fictional fixture date, not the symposium schedule.

**Audience promise:** "Our showcase has to finish on time. Help us handle the disruption without losing the activities people came for."

**Community:** A student organizer, a presenting team, a volunteer, and a resource steward. These can be played by the project team and an optional audience volunteer.

**Canonical activity names:** Setup, welcome, demonstrations, skills exchange, and closing. Their identifiers are `setup`, `welcome`, `demonstrations`, `skills_exchange`, and `closing`. The machine-readable fixture defines exact durations, dependencies, required activities, resource use, and permitted movement. The two central repairs are exchanging the demonstrations and skills-exchange slots when feasible or holding a compatible backup projector.

**Goal:** Complete the required program within a confirmed venue window while respecting participant availability and contingency spend.

**Dependency:** A projector delivery supports the demonstrations activity. A registered backup projector is possible but has its own availability, compatibility, and holding cost.

### Core episode

| Beat | Observation or interaction | Agent's decision | Visible consequence |
| --- | --- | --- | --- |
| Baseline | Organizer loads the confirmed plan | Check initial feasibility | Goal, timeline, budget, and resource dependencies appear |
| Uncertainty | A current message reports that the equipment may arrive late | Determine which commitment is affected and whether a status check could change the response | The threatened activity is highlighted with the referenced message |
| Preparation | Delivery information remains uncertain and an approved contingency exists | Compare continued waiting with a reversible hold | A hold record appears with cost, capacity use, and expiry |
| Community contribution | A participant checks in or a steward confirms a registered backup | Update only that event-scoped availability fact | The set of feasible alternatives changes |
| Commitment | A verified delay makes the original plan infeasible | Request or execute the authorized feasible adjustment | The board changes and the record states what was committed |
| Misleading update | A notice says the backup is unavailable but refers to an older reservation | Check object identity, booking reference, and effective time | The current commitment remains valid if the source does not apply |
| Resolution | The relevant activity completes or a resource is released | Reconcile remaining holds and schedule | Outcome view reports actual sandbox results |

The agent should not always create a hold. A low-impact warning, an expensive hold, or a definitive status response can make another choice better. Scenario variants should expose these tradeoffs.

### Audience choices

Offer two or three tested disruption cards, such as "Delivery delayed," "Volunteer unavailable," or "Conflicting resource notice." Reveal their plain-language effects without exposing the hidden resolution before the relevant tool is called.

For the community interaction, one participant can select "I am ready for my assigned role" or "The registered backup is available during this window." The demo role token determines which update they can submit. A presenter can perform the same action through a clearly labeled demo control.

### Why this is the first profile

The problem is understandable in a room of students, faculty, and company representatives. It has visible deadlines and discrete consequences. It permits a complete stateful prototype without production access to university systems. It also supports a meaningful failure case when no allowed alternative can satisfy all constraints.

Official campus procedures ground the general event dependencies. The specific demonstration schedule, people, inventory, and costs are synthetic. See the source context in the [product brief](01_product_brief.md).

## Profile B: Pantry Continuity

**Priority:** Diverse second showcase in Wave 2, after the campus vertical slice works.  
**Profile ID:** `pantry_continuity`.  
**Scope:** A fictional, staff-controlled distribution session using standardized shelf-stable kits and aggregate counts.

**Audience promise:** "Keep a distribution session on track when expected supplies arrive late, using only confirmed stock and the volunteers already assigned."

U-ACCESS is a relevant discovery context because its published roles include inventory, donation organization, distribution, and volunteer scheduling. Its food-pantry page describes restocking and delivery closures. These establish real logistics responsibilities; they do not establish demand for this prototype, access to inventory, or a university partnership. Sources checked October 23, 2026: [U-ACCESS Food Pantry](https://www.umb.edu/campus-life/current-students/u-access/food-pantry/) and [U-ACCESS Student Leadership Team](https://www.umb.edu/campus-life/current-students/u-access/u-access-student-leaders/).

**Goal:** Distribute 40 standardized kits before the fictional session ends, within a fixed volunteer roster, room window, and contingency budget. This is an operator-set synthetic target, not a claim about U-ACCESS demand or service practice.

**Concrete disruption:** The session has 24 confirmed kits. A delivery of 20 additional kits is expected, then reported late. A separately registered stock pool at the same fictional venue has 16 compatible kits confirmed by its steward and available for reservation. The agent can reserve those 16 and apply a checked schedule using the existing volunteers within its standing grant. Staff confirms the local handoff before the 16 kits enter session stock. Merely moving activities cannot fill the 16-kit shortfall. Expected delivery, local reservation, confirmed receipt, and completed distribution remain distinct records.

**Community contribution:** An authorized stock steward confirms a registered pool's quantity and an assigned volunteer submits a check-in. A general donation offer is evidence to verify; it is not immediately usable stock. No recipient record is needed.

**Distinct counters:** The initial session supply shortfall is 16 kits; the remaining service target is 40 because none has been distributed. A confirmed handoff closes the supply gap, while only timely distribution reduces the remaining service target.

**What changes from Profile A:** Add explicit consumable stock balances, quantity reservations, receipt and distribution records, and a service target. A projector can be reused in later time slots; a distributed kit cannot. The validator must reject cumulative over-allocation even when two distributions occur at different times.

**What stays common:** The planning loop, event/goal revisions, observation provenance, authority grants, hold expiry, budget checks, participant availability, candidate evaluation, human review, and durable action receipts. Pantry rules are selected by declared capabilities and typed requirements, not by a hard-coded scenario-name branch.

### Profile acceptance test

1. Show the 40-kit target, 24 confirmed session kits, 20 expected kits, and 16 confirmed alternate kits as separate quantities.
2. Inject the expected delivery delay. Reject a plan that treats its 20 kits as already received or claims that a schedule reorder alone meets the target.
3. Reserve the alternate 16 atomically; a competing reservation cannot reuse them, including in a later time slot.
4. Have the authorized staff role confirm the 16-kit handoff. Debit the alternate stock and credit session stock atomically; then reserve the 40 session kits and revalidate staff availability, distribution capacity, the service deadline, and budget before the agent applies the plan within its standing grant.
5. Show achieved service as zero until trusted completion records exist; after the sandbox records distribution of all 40 kits before the deadline, show 40 achieved and the stock consumed.
6. Replay a receipt or distribution update and verify that it neither creates stock nor counts service twice. If the alternate pool is absent, report the 16-kit gap and escalate without silently reducing the target.

The [pantry showcase specification](15_pantry_showcase.md) defines the 45-second transfer demonstration, stock semantics, domain boundaries, and fallback. Exact fixture values belong in its machine-readable profile. This extension does not promise PantrySoft access, real reservations, purchases, eligibility decisions, dietary substitutions, or allocation among recipients.

## Profile C: Community skills exchange

**Priority:** Low-cost regression profile and presentation fallback using the existing event schema.  
**Profile ID:** `community_skills_exchange`.

**Audience promise:** "Neighbors bring skills and equipment. Keep the exchange useful when a facilitator or resource becomes unavailable."

**Community:** A local organizer, volunteer facilitators, and participants. Possible activities include a short creative workshop, a device-learning session using prepared demo devices, a conversation circle, or a peer practice activity. Choose a bounded topic with clear equipment needs for the implemented profile.

**Goal:** Complete the required learning activities while preserving declared facilitator windows and access requirements.

**Illustrative change:** A facilitator can attend only the first portion of the event, while a shared equipment kit arrives late. A different ordering may preserve both activities, or an explicitly compatible alternative activity may avoid the equipment dependency.

**Community contribution:** Another registered facilitator confirms availability for a specific activity. This confirmation can unlock a candidate plan. A general offer to help does not automatically establish qualification or authority for a different role.

**What changes from Profile A:** The activity graph and participant windows should make at least one previously valid recovery invalid. A priority such as preserving a promised beginner session can change the candidate ranking.

**What stays common:** Typed updates, source checks, registered resources, scoped role actions, holds, constraint validation, action records, and final-state evaluation.

### Profile acceptance test

1. Load the skills-exchange configuration through the same entry point as the showcase.
2. Inject an equipment delay and a declared facilitator window.
3. Confirm that the validator rejects a candidate outside that window.
4. Submit a role-scoped contribution that enables a different candidate.
5. Show the revised plan and the specific fact that made it feasible.

There should be no special instruction in the agent code saying that a named skills-exchange scenario always chooses a particular alternative.

Keep this fixture because it cheaply detects assumptions tied to the campus program. It is not the main evidence of transfer to consumable stock. If the pantry extension fails its reliability gate, use this working profile in the live demo and label pantry as a planned extension.

## Profile D: Neighborhood cleanup

**Priority:** Stretch profile and discovery target.

**Audience promise:** "A shared tool delivery is late. Organize the work that can still happen and preserve the promised return time."

Boston's spring 2026 Love Your Block program describes volunteer coordination, shared cleanup tools, and pickup and return windows. Its listed April and May 2026 cleanups are past operating examples as of this plan's October 23, 2026 date. They establish a recognizable coordination pattern. They are not a current event invitation or evidence of a partnership. [City of Boston Love Your Block 2026](https://www.boston.gov/departments/civic-organizing/love-your-block-2026)

**Illustrative event:** One preselected site, a limited set of ordinary cleanup tasks, a fixed roster of consenting demo participants, and a shared tool catalog.

**Illustrative change:** Some tools arrive late. The agent compares starting a compatible task, reallocating a validated tool, or reducing optional scope while preserving the return deadline.

**Community contribution:** A steward confirms a registered tool set and its return window. Volunteers check in for tasks they have explicitly accepted.

**New modeling work:** Task suitability, tool counts, location and pickup dependencies, actual organizer rules, and the consequences of changing assignments. Outdoor conditions and site permissions require validation before an operational pilot. These are domain requirements rather than fields to invent from language.

This profile should not displace the first showcase build. It is valuable as a future test that the underlying event model transfers to a different community workflow.

## Scenario coverage and extensions

The first benchmark uses cases C01 through C08 as defined in the [evaluation plan](08_evaluation.md). They cover a genuine projector delay, quiet conditions, a false warning, a stale and duplicate notice, conflicting updates, a volunteer delay followed by check-in, a verification outage, and infeasible recovery. That definition is authoritative for the initial comparison.

The table below is a broader design checklist. Offer withdrawal, human-priority changes, and other extensions need not become extra benchmark cases before the first submission.

| Scenario class | Underlying condition | What the agent must demonstrate |
| --- | --- | --- |
| Quiet event | No relevant change | Preserve a feasible plan without avoidable intervention |
| True delay | A current update affects a required dependency | Verify or prepare as useful, then recover within constraints |
| False alarm | A warning is not borne out by the relevant source | Avoid an unnecessary commitment |
| Stale notice | A message applies to a prior booking or expired interval | Match identity and effective time correctly |
| Conflicting sources | Two current messages disagree | Preserve uncertainty and use a defined authority or verification rule |
| Community rescue | A validated contribution enables a candidate | Recompute feasibility from new state |
| Offer withdrawn | A proposed or held resource becomes unavailable | Release or invalidate the affected proposal and explain the change |
| Tool unavailable | A needed status check fails | Use the specified timeout behavior and preserve unresolved uncertainty |
| Deadline pressure | Verification consumes time needed for a backup | Account for time and the cost of waiting |
| No feasible recovery | Every permitted candidate violates a hard constraint | Identify the conflict and ask the organizer for a specific change |
| Human priority update | Organizer changes a preference | Rerank feasible candidates and explain the difference |
| Duplicate input | The same observation or action is retried | Avoid duplicate commitments and duplicate costs |
| Consumable shortfall | Confirmed stock cannot cover a service target | Reserve a valid alternate quantity or expose the remaining gap |
| Unreceived delivery | A supplier reports an expected quantity or revised ETA | Keep expected quantity separate from usable stock and achieved service |
| Stock conflict | Two proposals claim the same kits | Enforce cumulative quantity conservation across time slots |

These are scenario-design targets. The evaluation plan determines which are in the first benchmark, the number of episodes, and the reporting procedure.

## Scenario-authoring rules

1. Give each resource, activity, participant role, reservation, and observation an explicit identity.
2. State which data the agent can see at each time and which outcomes remain hidden.
3. Include a feasible baseline before the first disruption unless infeasibility is the case being tested.
4. Assign real consequences to holds, tool time, and commitments in the simulator.
5. Make a false warning look plausible in wording while preserving enough reference information for a competent agent to reject it.
6. Keep the policies' available information and action sets equivalent in comparisons.
7. Define success from resulting state and completed activities rather than the quality of the explanation alone.
8. Record whether a participant interaction is live, simulated, or replayed.
9. Provide an explicit recovery or escalation condition when all permitted candidates fail.
10. Keep the exact fixture values in one machine-readable source.

## Community involvement boundary

Participation is invited within a specific event. A check-in represents the submitting person's declared state for an assigned role. A resource offer represents a scoped offer that still needs compatibility and availability checks. No absence, need, skill, or willingness is inferred from a person's demographics, silence, or unrelated online activity.

A public audience view can show anonymous role status or aggregate readiness. The organizer view can show the minimum event-specific detail needed for coordination. No external organization has been contacted through this planning work.
