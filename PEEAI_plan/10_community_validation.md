# Community discovery and validation plan

**Status:** Proposed research and pilot procedure. No outreach, interviews, partnership agreements, or pilot results are represented as completed.  
**Planning date:** October 23, 2026.  
**Objective:** Determine whether Plan B solves a recognizable coordination problem, whether its decisions are understandable, and which actions an organizer would delegate. Validate the campus hero first and use Pantry Continuity to test a distinct consumable-stock workflow.

## Questions that matter first

1. Do event organizers encounter uncertain updates that create meaningful coordination work?
2. Which facts determine whether they wait, prepare a backup, or change a plan?
3. Which constraints are genuinely fixed, and which can an organizer change?
4. Can participants and resource stewards contribute useful updates with a very small interaction?
5. Does the proposed interface make a consequential action easier to assess?
6. Does the prototype improve a measured outcome relative to the tools and habits the organizer already uses?
7. For a pantry session, do staff distinguish expected supply, confirmed stock, reservations, receipts, and completed distribution in the way the proposed model assumes?
8. Does a staff-set aggregate service target improve decisions without introducing recipient-level decisions or more reporting work than it saves?

Public information establishes context. Direct observation and explicit participant feedback are needed to answer these product questions.

## Discovery participants

Start with people who already coordinate modest events and can describe a recent concrete example. A useful initial mix is:

| Role | Desired perspective | Suggested count for exploratory interviews |
| --- | --- | --- |
| Student organization event planner | Small budgets, volunteer roles, campus process | Two |
| Faculty or staff seminar organizer | Speaker timing, equipment, dependencies | One |
| Community workshop or volunteer organizer | Participant availability and shared resources | One or two |
| Volunteer or resource steward | Burden and clarity of submitting status | Two |
| Pantry operations staff member or stock steward | Receipt evidence, aggregate stock accounting, session capacity, and staff authority | One, if a willing operator is available |

These counts are a discovery target, not a representative study design. Recruit through the team's existing authorized relationships or an explicitly approved outreach process. This document does not authorize sending invitations, contacting organizations, or claiming affiliation.

The official campus procedure identifies event-planning responsibilities and existing workflows that interview questions should respect. Treat their requirements as constraints to understand, not as an integration already available to the prototype. [UMass Boston event procedures](https://www.umb.edu/event-services/student-organizations/)

For pantry discovery, U-ACCESS is one relevant local context. Its published student roles include stock and volunteer responsibilities, and its existing service intake uses PantrySoft. Review the proposed logistics boundary with an operator before treating it as a faithful model. The website does not establish a supported inventory API or access to service records. [U-ACCESS Student Leadership Team](https://www.umb.edu/campus-life/current-students/u-access/u-access-student-leaders/), [U-ACCESS](https://www.umb.edu/campus-life/current-students/u-access/)

## Twenty-minute organizer interview

### Opening, two minutes

Explain that this is an exploratory prototype about handling changes during a small event. Ask permission to take brief notes and state how the notes will be used. Offer to use role labels and omit names or event details. Recording is optional and requires separate agreement.

### A recent event, seven minutes

- Tell us about the most recent event you helped coordinate.
- What were you responsible for personally?
- What changed unexpectedly?
- How did you learn about it, and what did you check next?
- Which part was uncertain at the time?
- What action did you take, and what did that affect?
- What would have happened if you had waited longer?

Ask for chronology and artifacts only when the person is comfortable sharing them. A synthetic reconstruction is sufficient for the first prototype. Do not ask for attendee lists or private message histories by default.

### Constraints and authority, five minutes

- Which commitments could you change without asking someone else?
- Which resources required confirmation from a particular person or system?
- What counted as an adequate confirmation?
- When was a backup no longer useful?
- Could a temporary hold cost money or prevent another group from using a resource?
- Which rule could an assistant easily misunderstand?
- What would an infeasible situation look like in your workflow?

### Prototype relevance, four minutes

Show a short static or interactive example after discussing their existing workflow.

- Does this resemble any decision you actually make?
- What important detail is missing or incorrectly represented?
- Which suggested action would you want to inspect first?
- What would you allow the system to do on its own?
- What would make the system more work than it saves?

### Close, two minutes

Summarize the problem in the participant's terms and ask whether the summary is accurate. Ask whether a later tabletop test would be useful. An expression of interest is not a partnership agreement or permission for a live deployment.

## Participant and resource-steward interview

Use a shorter ten-minute session:

1. Ask how they currently tell an organizer that they are ready, delayed, unavailable, or able to lend a resource.
2. Show the proposed one-task participant page.
3. Ask them to submit a synthetic availability update.
4. Ask what they expect the system to do after submission.
5. Ask how they would correct or withdraw the update.
6. Check whether the requested fields feel necessary and understandable.

The system should not convert an offer into an obligation without the person's clear agreement. The testing task should expose whether users understand that distinction.

## Pantry discovery addendum

Ask an operations staff member about one past supply delay or stock discrepancy, using aggregate counts and synthetic names. A pantry recipient interview is unnecessary for the proposed logistics task. Keep this review focused enough to run alongside the campus work in Wave 2.

- What is the unit that staff actually count, and when is an expected item accepted as usable stock?
- Who can confirm receipt, correct a quantity, reserve stock for a session, and record completed distribution?
- Can a confirmed local pool be reserved and handed over at the same venue, or is that assumption unrealistic?
- What limits the session's throughput: existing staff, preparation time, space, or another explicit constraint?
- Would a session target of a particular count be useful? What exactly counts as completion, and what does the number fail to capture?
- What should happen if the target cannot be met under current constraints? Who may change it, and how should the original shortfall remain visible?
- Which information already exists in an approved aggregate form, and what new entry burden would these updates create?

The review can invalidate the standardized-kit example. It must not be generalized to actual food assortment, nutrition, dietary substitutions, recipient eligibility, household allocation, or donation acceptance rules. If these concerns dominate the proposed workflow, retain the synthetic capability test and revise the operational use case with staff.

Record three outputs: corrected stock/service definitions, an explicit staff-versus-agent action boundary, and a judgment about whether the proposed task is useful enough for another tabletop. Interest in the idea does not authorize data access or an integration.

## Tabletop test

### Purpose

Test the workflow with an organizer using synthetic scenarios before giving the agent any operational responsibility. The unit of study is a planning decision and its resulting state.

### Procedure

1. Let the organizer review and correct the event profile's goals and constraints.
2. Present a baseline plan and a realistic update.
3. Ask the organizer what they would normally check and do.
4. Present the agent's proposed verification or contingency.
5. Ask the organizer to explain what they expect the action to change.
6. Execute the action in the sandbox and inspect the resulting state.
7. Introduce a conflicting or stale notice.
8. Introduce one condition where no permitted candidate works.
9. Record differences between the organizer's process, the agent's process, and the actual feasible outcomes.

For a comparison study, counterbalance scenario order and use comparable variants to reduce learning effects. Do not call an unbalanced demonstration a causal evaluation.

### Pantry transfer tabletop

Use the [Pantry Continuity specification](15_pantry_showcase.md) after the campus path is stable. The team may run this tabletop with simulated staff roles; label that evidence as an internal sandbox exercise.

1. State the fictional target: 40 standardized kits by session end. Show 24 kits in session stock, 20 expected but unreceived, and a separate confirmed local pool of 16 kits.
2. Ask the operator which quantities are usable, reservable, and already delivered to recipients. Record whether the interface encourages anyone to add expected stock to on-hand stock. Keep the initial supply shortfall of 16 separate from the remaining service target of 40; no distribution has yet occurred.
3. Delay the expected delivery beyond the usable window. Compare waiting, reordering within existing volunteer windows, and reserving the local 16. An activity reorder can improve timing; it cannot create missing stock.
4. Reserve the alternate 16. Try a competing reservation for the same units in another time slot; it must fail despite the absence of a schedule overlap.
5. Let the staff role confirm the local handoff. Verify that alternate stock falls from 16 to zero as session stock rises from 24 to 40, and that a duplicate receipt changes neither balance.
6. Reserve and commit the session's 40 kits after checking the existing staff, time, and budget constraints. Ask whether the displayed 40 is a commitment or an achieved outcome; it is still a commitment.
7. Record aggregate completion through the authorized staff/simulator path. Verify that distribution consumes 40 kits, achieves the target once, and does not return stock when the activity ends.
8. Remove the alternate pool or shorten staff availability. The agent must report the remaining quantity or capacity gap, preserve the original target, and request a concrete staff decision.

This tabletop adds evidence about stock conservation and action comprehension. It does not demonstrate improved food access, nutritional outcomes, or operational performance at U-ACCESS.

## Comprehension test for a broad audience

Recruit a small exploratory group from different disciplines. Three to five participants can reveal obvious communication problems, but that sample does not establish broad usability or adoption.

After a short demonstration, ask each person:

- What was the system trying to preserve?
- Why did it check that source?
- What did the temporary hold change?
- What fact caused the committed plan to change?
- Why did the later notice not necessarily apply?
- What would happen if none of the allowed plans worked?

After the pantry transfer, also ask: "Which supplies were only expected?", "Did the reservation move the kits?", and "What evidence established that 40 kits were distributed?" If the audience cannot distinguish these states after the 45-second segment, simplify the display before adding another integration.

Ask the questions without showing a multiple-choice explanation first. Record correct understanding, uncertainty, and the exact misleading interface element. A participant's confident misunderstanding is especially useful evidence for revision.

## Decision log template

Use one record per meaningful observation:

| Field | Entry |
| --- | --- |
| Session identifier | Anonymous local ID |
| Participant role | Organizer, volunteer, steward, or audience member |
| Date and method | Interview, walkthrough, or tabletop test |
| Concrete problem | A specific event or decision described by the participant |
| Evidence | Paraphrase or explicitly permitted short quote |
| Current workaround | Tool, communication channel, or manual process |
| Cost or consequence | Participant-reported impact, clearly labeled as reported |
| Constraint correction | What the prototype got wrong or omitted |
| Requested authority boundary | Actions allowed, approval required, and actions out of scope |
| Design implication | Proposed change tied to the evidence |
| Confidence and limitations | One account, repeated across accounts, or observed in the task |
| Follow-up | Specific open issue and owner |

Keep product conclusions separate from source observations. For example, "two organizers checked a steward before changing equipment" supports a verification requirement. It does not establish the size of a market or a measured reduction in wasted time.

## Proposed go/no-go criteria

These are internal planning thresholds to revise after initial discovery, not validated performance standards.

| Stage | Continue when | Revise or stop when |
| --- | --- | --- |
| Problem relevance | At least two organizers provide a concrete recent example that fits the bounded workflow | Accounts center on a different problem, such as initial recruitment or institutional approval |
| Model fidelity | An organizer can validate the required constraints and permitted actions for one profile | Important decisions depend on unmodeled facts that dominate the result |
| Participant interaction | Test users understand what their update authorizes and can correct it | Users think an offer is automatically a reservation or cannot withdraw it |
| Action comprehension | Users can explain the main consequence of a proposed commitment before accepting it | Explanations repeatedly cause mistaken expectations |
| Prototype reliability | State changes obey the stated invariants and fail visibly when needed | Tools silently fail, double-commit, or accept stale resource state |
| Pilot readiness | A willing operator agrees to a specific scope, data set, and authority boundary | Operational responsibility or success criteria remain ambiguous |
| Pantry model fidelity | A staff reviewer can explain the unit, receipt evidence, reservations, service target, and limits; or the demo is clearly labeled as an unvalidated synthetic model | The pitch presents fictional kits or quantities as actual pantry inventory or practice |
| Pantry transfer reliability | Reservations conserve quantity, duplicate records do not alter totals, unreceived stock cannot satisfy the target, and a fixed-roster plan is feasible | The demo reaches its target by counting expected stock, reusing consumed kits, or inventing volunteers |

A failed criterion should produce a narrower product or a revised model. It should not be hidden by selecting a more flattering demonstration.

## A bounded pilot after the hackathon

### Stage 1: Historical reconstruction

Recreate one past event with an organizer using synthetic names and approved facts. Compare the agent's decisions with what the organizer remembers and with the constraints that actually applied. This evaluates fidelity and reveals missing tools. It does not measure prospective impact.

### Stage 2: Shadow operation

During a low-stakes event, allow the prototype to read only the explicitly approved event state and generate proposals. The organizer continues operating through their usual process. Record what the agent would have done and which assumptions were wrong.

### Stage 3: Limited delegated action

Only after the preceding stages work, consider a narrow action such as managing internal sandbox-equivalent holds in an approved system or updating an internal operations board. Agree on allowed actions, spending limits, expiry behavior, who can pause the system, and how outcomes are reviewed.

A possible pantry shadow scope is one staff-controlled session with approved aggregate stock and staff-submitted receipt/distribution observations. Staff retains every physical handoff and service decision. Start with manual structured input or an explicitly approved aggregate export; a public PantrySoft link is not permission or a technical contract for connecting to that service. No recipient data is needed for this scope.

No stage grants the system general authority over attendees, institutional bookings, or communications. The authorization follows the particular event and integration.

## Data minimization and community trust

Use the least event-specific data needed to answer the operational question:

- Role label or alias instead of a full profile.
- Explicit availability interval instead of continuous location tracking.
- Resource identifier and usable capacity instead of unrelated personal details.
- Submitted updates instead of inferred attendance or inferred need.
- Aggregated or anonymized public display when individual identity is unnecessary.

Define retention and deletion before collecting non-synthetic participant information. For the hackathon, synthetic fixtures and disposable demo-role sessions are sufficient. A separate research study should follow the applicable institutional process before recruitment or collection begins.

## Reporting findings honestly

Use labels that identify the evidence level:

| Evidence | Appropriate wording |
| --- | --- |
| Public operating procedure | "The workflow includes these dependencies." |
| One exploratory interview | "One organizer described this difficulty." |
| Repeated interview theme | "Several interviewed organizers raised this issue." |
| Sandbox evaluation | "The controller achieved this result on the disclosed synthetic scenario bank." |
| Tabletop observation | "Participants completed this task under the tested conditions." |
| Shadow pilot | "The system proposed these actions, which were not executed by it." |
| Operational pilot | "Within the agreed pilot scope, these outcomes were observed." |

Keep the distinction between measured outcomes, participant reports, and planned benefits in the pitch and documentation.

## What can be done before submission

If time is short, prioritize one organizer interview, one constraint review, and two or three comprehension walkthroughs. Report the small sample and its purpose. If none can be completed, say that the product hypothesis remains unvalidated and show the rigorous sandbox evaluation instead.

Lack of a usable pantry pilot does not block the hackathon. Run Pantry Continuity with fictional counts and clearly labeled simulated staff inputs if its Wave 2 capability and Wave 3 reliability gates pass. State that the domain workflow remains unvalidated. If that implementation is incomplete or unreliable, use the existing skills-exchange fixture as the live transfer fallback and show pantry only as a planned capability. Keep the campus episode as the main demonstration in every case.

The immediate deliverable is a concise discovery log with specific changes to the profile or interface. A list of organizations we might contact is not evidence that the workflow is useful.

## Open decisions

- Who owns recruitment and participant consent.
- Which organizer can validate the first profile.
- Where approved notes will be stored and how long they will be retained.
- Which outcome matters most to the operator.
- Who can review the pantry unit, receipt semantics, and service target without requiring access to recipient records.
- Whether pantry capability and reliability gates pass in time for the 45-second transfer segment; the skills-exchange fallback remains available.
- Whether a future pilot requires institutional research review or only product testing approval under the applicable process.

The team can build and evaluate synthetic workflows while these discovery decisions remain open.
