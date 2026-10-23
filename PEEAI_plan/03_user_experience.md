# User experience and interaction specification

**Status:** Proposed interface behavior and acceptance criteria.  
**Primary audience:** Community event organizers and a mixed hackathon audience.  
**Primary demonstration:** A campus showcase with a fixed venue, a constrained schedule, and an uncertain equipment dependency.

## Experience principle

Every important screen should answer three questions:

1. What are we trying to preserve?
2. What changed or remains uncertain?
3. What action is available, and what will it affect?

The main visual is the operating plan and its consequences. Technical details belong in an expandable evidence view. The product should be understandable before a viewer learns the names of the model, planner, or agent framework.

## Views and roles

| View | User | Main controls | Data shown |
| --- | --- | --- | --- |
| Organizer board | Authorized organizer | Set preferences, review proposals, approve commitments, pause automation | Event plan, constraints, budget, role status, observations, and action history |
| Participant page | Invited event participant or steward | Check in for own role, update own availability, offer or confirm a permitted resource | Own role, relevant time window, own submissions, current public plan |
| Public display | Audience or event attendee | Read-only plan, optional demo disruption choice | Goal, activity state, anonymized readiness, visible changes, outcome summary |
| Demo control | Presenter | Load profile, inject tested disruption, advance simulated time, reset, enter replay | Fixture identity, simulation clock, mode, and scenario controls |
| Evidence drawer | Organizer or evaluator | Inspect the basis of a decision | Relevant messages, tool receipts, constraint checks, candidate comparison, and action result |

A participant does not gain organizer authority by submitting a check-in. A presenter-controlled disruption card is part of the sandbox and is labeled accordingly.

## Main screen layout

```text
+-----------------------------------------------------------------------+
| PLAN B     Campus showcase     SANDBOX / LIVE AGENT     Event clock     |
| Goal: Complete the required program within the confirmed event window |
+---------------------------------------------+-------------------------+
| CURRENT PLAN                                | CURRENT DECISION        |
|                                             |                         |
| Welcome -> Demo -> Peer exchange -> Wrap-up  | Equipment may be late.  |
|              ^                              |                         |
|        Equipment required                   | Check delivery status   |
|                                             | Prepare backup          |
| Changes shown next to the affected activity  | View proposal           |
+---------------------------------------------+-------------------------+
| COMMUNITY READINESS                         | CONSTRAINTS             |
| Presenter ready | Steward confirmation due | Venue window            |
| Registered backup offered                   | Budget spent / held     |
+---------------------------------------------+-------------------------+
| UPDATES AND ACTIONS                                                   |
| Time | New observation / check / hold / commitment | View evidence    |
+-----------------------------------------------------------------------+
```

The labels and activities are illustrative. The actual display reads its names and times from the selected configuration.

### Visual hierarchy

- Show the event goal and simulation mode at all times.
- Place the threatened commitment next to the relevant timeline activity.
- Put the current decision above the complete message history.
- Show proposed changes as an explicit comparison before applying them.
- Give holds a visible expiry and show held budget separately from spent budget.
- Use text and icons in addition to color for ready, uncertain, blocked, held, and completed states.
- Keep the technical evidence accessible in one action from the recommendation.

## Organizer journey

### 1. Start with a concrete goal

The organizer selects a profile and reviews its event window, required activities, resources, and budget. The interface marks which settings are hard constraints and which are preferences.

Example preference controls:

- Preserve the original order when possible.
- Prioritize the specified participant's available window.
- Minimize additional spend.
- Prefer a compatible equipment-free activity when allowed by the profile.

Use a few understandable presets before exposing numeric weights. If a preference changes, show the resulting ranking difference. A preference change cannot silently remove a required activity or extend a confirmed venue window.

### 2. Understand an incoming update

A message appears with source, received time, effective time when known, and its referenced activity or resource. The agent's interpretation is a compact statement such as:

> "This delivery may miss the equipment setup window. The affected activity is the live demonstration."

The user can expand the original message and the extracted target. A missing reference produces an unresolved interpretation rather than an invented booking identifier.

### 3. Watch a relevant check

The current decision card explains the purpose of a tool call:

> "Checking the delivery record because its arrival window determines whether the original program is feasible."

After completion, show the source response and the change in the decision state. Avoid exposing a private chain of reasoning. The evidence drawer contains observable inputs, selected alternatives, constraint results, and action records.

### 4. Review a contingency

A hold card shows:

- Registered resource and usable time interval.
- Compatibility with the affected activity.
- Hold cost, commitment cost, and any nonrefundable amount.
- Capacity consumed while held.
- Expiry and the consequence of expiry.
- Who can confirm or commit it.

Example copy:

> "A compatible backup can be held until the stated expiry. Holding it preserves this option while the delivery is checked."

Use actual fixture values in the interface. Avoid hardcoding a price or expiration in presentation copy.

### 5. Compare and commit

Present no more than three meaningful candidate alternatives by default. Every row must show feasibility and consequence.

| Candidate | Required activities | Schedule changes | Additional cost | Key limitation |
| --- | --- | --- | --- | --- |
| Keep the current plan | Depends on the current delivery window | None | None | May miss the setup requirement |
| Use registered backup | Feasible when confirmed | Resource substitution | Fixture-defined | Requires valid availability and authorization |
| Move a flexible activity | Feasible only if role windows allow it | Defined activity movement | Fixture-defined | Cannot violate required ordering |

These rows illustrate the information structure, not a predetermined winning response.

The approval card names the actual state change and its consequences. For example:

> "Commit the registered backup for the demonstration and release the unused hold. This preserves the venue end time and adds the displayed cost."

If the organizer already delegated this action through a valid standing grant, apply it within that grant and display the resulting receipt. Require an approval click only when the proposal needs a specific additional authorization. The board should make the active delegation visible.

After a commit, replace proposed status with the returned action result. A tool error leaves the action failed or unresolved. The UI must not show success because the model wrote a success sentence.

### 6. Continue from feedback

The board reflects a later check-in, activity completion, delivery update, or offer withdrawal. If a new proposal supersedes an old one, preserve the prior action in history and label the new proposal's current state version.

At completion, show the resulting event state, the commitments preserved, the changes made, and the costs recorded. If the event became infeasible, show the unresolved constraint and the organizer's decision.

## Participant journey

### Join a scoped role

The presenter or organizer provides a short event code or role-specific link. The first screen says what the participant is being asked to do and which event will receive the update. Use a demo alias or role label by default.

The prototype's role token represents a sandbox permission. It is not a production university identity or verified real-world credential.

### Contribute one useful fact

Choose the smallest relevant form:

| Contribution | Required fields | Result |
| --- | --- | --- |
| Role check-in | Assigned role and declared readiness or availability interval | Timestamped observation for that role |
| Registered resource confirmation | Resource identifier, available interval, and explicit confirmation | Observation that can update validated availability |
| New resource offer | Description, interval, and event scope | Unverified proposal for organizer review |
| Withdrawal or correction | Own previous submission and corrected state | New observation linked to the prior one |

Do not ask for unrelated profile information. Do not infer absence from a missing check-in. A timeout can mean "not yet confirmed" without asserting that the person will not attend.

### See the effect

Show a receipt such as:

> "Your availability update was recorded for this event. The organizer's plan now has one additional feasible option."

Only show the second sentence if it is supported by a fresh planner result. Otherwise say that the update is awaiting review or evaluation.

A participant can correct or withdraw their own offer. The system revalidates affected proposals and does not erase the historical record of an action already taken.

## State labels and plain-language copy

| Internal meaning | Suggested label | Explanation |
| --- | --- | --- |
| New interpretation awaiting reference checks | Update received | The message has been recorded |
| Relevant fact missing | Needs a check | A source or confirmation could change the decision |
| Candidate exists but lacks confirmed prerequisites | Possible option | The plan is not yet ready to commit |
| Valid temporary reservation | Held until [time] | The option consumes the stated capacity until expiry |
| Validated plan awaiting authority | Ready for approval | Constraints pass under the displayed state |
| Successful persisted commitment | Committed | The tool returned the resulting record |
| Referenced notice no longer applies | Earlier booking | This notice concerns a different reservation or interval |
| Required tool did not return | Status unavailable | The relevant fact remains unresolved |
| No allowed candidate passes | Decision needed | The listed constraints cannot all be satisfied |

Never label a raw model score as a calibrated probability. Use "supported by the current delivery record," "unconfirmed," or another source-grounded description unless calibration has been established.

## Failure and boundary states

### Conflicting updates

Show both records with their targets and times. Explain which verification or authority rule is being applied. If the conflict remains unresolved, retain that uncertainty in the proposal.

### No feasible plan

The card should identify the smallest relevant conflict supported by the validator. For example:

> "The required activity needs equipment before its latest start. Both registered resources are unavailable. Choose whether to remove that activity or change an explicitly editable requirement."

Only present amendments the organizer is authorized to make. A venue window that is fixed in the profile is not a UI suggestion to overrun the actual booking.

### Stale proposal

Disable commitment of a proposal whose state version or resource validity no longer matches. Show "The event changed. Rechecking this proposal." After recomputation, display the new consequences before another approval.

### Double submission

A repeated check-in or action retry must return the existing receipt or a new version with a clear relationship. It must not create duplicate costs, holds, or commitments.

### Service failure during a presentation

Show a visible connection or model status. Switch deliberately to a labeled recorded episode if necessary. Keep the same goal and outcome view so the audience can follow the mechanism. A replay must not be presented as a live tool response.

## Pantry board and staff workflow

This is the proposed interface for the bounded [Pantry Continuity](15_pantry_showcase.md) extension in Wave 2. It uses the common board, evidence drawer, action history, role sessions, and replay. The [public pantry fixture](examples/pantry_continuity.public.json), [data model](07_data_model.md), and [tool contracts](06_tool_contracts.md) own the exact quantities and action semantics. These screens are requirements, not implemented UI or a claim that an actual pantry participated.

### Keep stock location, expectations, and service separate

The persistent header says **Fictional pantry sandbox**, identifies the current actor and mode, and displays the scenario date, time, and timezone. Keep **Target: 40 standardized shelf-stable kits by [deadline]** visible while proposals, holds, and staff actions change. This target is an aggregate kit count; the board does not collect recipient identities, make eligibility decisions, or claim to measure people served.

Use one compact stock table and two prominent progress counters. The initial state is:

| Board item | Initial display | Meaning |
| --- | --- | --- |
| Pantry stock | 24 on hand; 0 reserved; 24 available | Physically confirmed units already controlled by this session |
| Partner stock at this venue | 16 on hand; 0 reserved; 16 available at source | Separate fictional steward's stock; requires an authorized hold and staff-confirmed handoff |
| Expected shipment | 20 expected; 0 received | A promise with its own source and ETA; contributes zero usable stock before receipt |
| Supply shortfall | **16 kits** | Remaining service need that usable pantry-controlled stock cannot currently cover |
| Service deficit / remaining to distribute | **40 kits** | Nothing has been distributed yet; stock on a shelf is not completed service |

Do not total the three supply rows as 60 usable kits. Partner stock may be physically at the venue without being pantry-controlled. Keep its location/steward label visible. If showing total physical stock across both pools, label it explicitly as **40 across both stocks**, alongside their separate balances and permissions.

Every row displays the registered unit, stock location, on-hand quantity, reserved quantity, available quantity, and an expandable source record. Use integer **kits** throughout. Room occupancy, storage capacity, and service rate are distinct constraints and have their own units. A proposed allocation is labeled **Proposed** until its reservation exists; the initial 24-kit partial proposal has no inventory reservation and cannot appear execution-ready.

For the current supply shortfall, use remaining cumulative service need minus usable pantry stock, including stock already reserved for this target and excluding unrelated reservations. Expected stock and partner stock before handoff contribute zero. After distribution, subtract already completed units from the need so consumption does not create a false new shortage. The model cannot edit these counters directly; each derives from the current ledger projection.

### Show cumulative distribution and deadline achievement

Keep **Distributed so far**, **Distributed by the deadline**, and **Remaining to distribute** distinct. While the deadline is still open and all recorded service is timely, the latter matches the displayed service deficit. At and after the deadline, also show **Deadline service deficit**, derived from the original target minus timely distribution. A green success label requires timely attainment, not just cumulative distribution.

| Observable transition | Stock and reservation display | Service display |
| --- | --- | --- |
| Hold 16 partner kits | Partner on hand 16, reserved 16, available 0; pantry remains 24 | Supply shortfall 16; service deficit 40 |
| Staff records full handoff | Partner 0; pantry 40; source hold fulfilled; destination units not yet reserved | Supply shortfall 0; service deficit remains 40 |
| Reserve pantry 40 and apply plan | Pantry on hand 40, reserved 40, available 0; distinguish committed units from provisional holds | Distribution is still 0; remaining service is 40 |
| Record 40 timely distributions | Pantry on hand and reserved both 0; expected shipment still 20 unreceived | Distributed so far 40; by deadline 40; both service deficits 0 |
| Example: 24 timely, 16 late | Physical stock reflects all 40 consumed units | Distributed so far 40; remaining to distribute 0; by deadline 24; deadline deficit **16**, with **Deadline missed** |

The last row is an adverse-case display example, not a claim about the canonical successful run. Its late service must never replace the earlier outcome with a success badge. Keep actual physical-completion time and server recording time available in the evidence drawer. The default staff action uses the server/scenario clock; an earlier supported event requires an authorized, auditable correction path rather than a free-form backdate.

### Make source freshness and pending handoff visible

A stock-status card shows who reported the count, the source observation time when known, retrieval time, relevant stock, and scope. Label missing source time as unknown. A **Checked** badge links to the successful scoped tool response and states what it established, such as **Partner reports 16 kits available**. It does not say **Received** until a staff receipt exists. An unavailable, stale, conflicting, or wrong-source result retains that label and cannot become a confirmation through generated explanation.

A valid source hold with transfer purpose creates a **Staff handoff requested** card in the local application. Show the source and destination, requested and remaining quantity, hold expiry, modeled response interval, current staff-task status, and next permissible action. Use plain states such as **Waiting for staff**, **Acknowledged**, **Partly received**, **Received**, **Declined**, or **Expired**. Acknowledgement alone changes neither stock nor service. This card is an in-application task; no external message or physical movement has occurred.

Read the response interval and cutoff from `pantry_parameters`. Display the exclusive source cutoff as **Handoff must finish before [time]**. Do not let a countdown or scenario-time advance imply that staff accepted the task. When a hold expires, show the released remaining reservation, unresolved handoff, and resulting planning consequence. Preserve the original task and receipts in history.

The two reservations have different purposes. Before handoff, the source hold protects partner stock. After receipt, the destination stock needs its own reservation and plan commitment for distribution. Give each a separate row or card with source/target, remaining units, provisional or committed state, and its applicable expiry. A transfer receipt must not duplicate the source reservation at the destination or automatically mark the destination reserved.

### Staff forms record physical events

Open staff controls only from an authenticated, scoped staff session. The public display and coordinator agent can view appropriate task state but cannot submit these attestations. The actor is resolved from the session and shown as read-only; a text field cannot impersonate staff.

| Staff form | Visible fields and contextual information | Successful result |
| --- | --- | --- |
| **Record kits received** | Source and destination stock; source hold and remaining units for internal handoff; quantity in kits; source evidence; unique physical receipt reference; matching shipment for an external receipt; actual action time | One receipt showing source debit, destination credit, reservation remainder, and resulting balances |
| **Record kits distributed** | Current target and goal version; distribution activity; committed stock allocation; quantity in kits; unique distribution reference; available stock and earned service capacity; actual completion time | One receipt showing consumed stock/reservation, cumulative progress, timely progress, and remaining deficit |

Prefill registered references from the selected task or allocation. Do not make staff copy internal IDs or choose arbitrary resource names during the 45-second demo. Keep audit identifiers in the expandable receipt. The form button is a factual attestation such as **Record 16 kits received**; accepting a proposed plan is a different action.

Distribution capacity reflects actual qualified staffed execution after stock, reservation, and committed plan prerequisites hold. Show **Up to [quantity] kits can be recorded now** with the service interval when useful. The authored rate is a fixture assumption, not observed real-pantry productivity. Advancing the clock changes the available interval; it cannot fabricate earlier execution or staff readiness. Completion exactly at the inclusive service deadline uses the runner's defined ordering and can count as timely; a source hold's exclusive cutoff follows its separate rule.

Generate one request identity per logical submission and preserve it while a response is pending or retried. Staff need not enter this technical key. The physical receipt/distribution reference is a separate uniqueness control that prevents the same event being credited again with a fresh request identity. Disable accidental repeated submission while pending, but keep an accessible **Check action status** control backed by `get_action_receipt`.

| Condition | Required form feedback |
| --- | --- |
| Negative, fractional, excessive, or incompatible-unit quantity | Name the field and allowed bound; retain the entered context; show rejection without changing balances |
| Stale state or expired/insufficient reservation | Show what changed, refresh current quantities, and require a fresh valid action; no partial write |
| Unknown result or lost response | Show **Checking whether this was recorded**; reconcile the original request; do not create a fresh action or optimistic stock credit |
| Identical retry or repeated physical reference | Show the original receipt or explicit duplicate rejection; quantities change only once; conflicting reference reuse rejects |
| Partial handoff, 10 of 16 | Show pantry 34, partner 6, source hold remaining 6, received 10, and current supply shortfall 6; service deficit stays 40 until distribution |
| Partial service, 34 by the deadline | Show 34 achieved, original target 40, and deadline deficit 6; do not reduce the goal to obtain a success label |
| Late physical distribution within a valid grant/event window | Record actual stock consumption and time; show the missed deadline and unchanged on-time deficit for those late units |
| Missing staff authority or expired event grant | Reject the mutation and show the required role; retain the pending task and unchanged state |

Partial handoff leaves the source remainder reserved until authorized release, expiry, or later handoff. The UI must not silently release it or count it as received. Later distribution consumes only valid committed pantry stock; a physical handoff is never a distribution receipt.

### Preserve standing delegation without extra approval steps

Show **Agent may check sources, reserve/release stock, and apply permitted plans** when the current grant authorizes those actions. In the canonical fixture the agent already has `apply_plan` authority with no additional review requirement. After fresh validation, it applies the allowed plan and displays its receipt without an invented approval click. An organizer's ability to inspect the plan is not an extra mandatory gate.

Staff receipt and distribution controls remain separate because they attest physical events beyond the agent's grant. The agent may request those facts and wait for their receipts. Only a proposal exceeding the actual standing grant should open an authorization card naming the exact missing permission. A rejected operation cannot be repaired by a participant message that claims to grant authority.

### Fit the segment and preserve clear modes

The pantry portion occupies **45 seconds inside the seven-minute presentation**, using the [timed presentation plan](09_seven_minute_presentation.md). Keep the target, source/destination stock, expected 20, supply shortfall, and service progress visible through the whole sequence. Compress explanations with an expandable evidence drawer; do not compress away a staff action, reservation, or physical receipt. An unfinished capability uses a clearly labeled design view; a replay label is valid only for an actual recorded run.

Use large numbers with text labels and units, keyboard-operable staff buttons, visible focus, and text/icon status alongside color. Provide a presenter-operated alternative to any audience phone action. Announce completed state changes accessibly without reading every clock tick. Avoid automatic disappearing error messages, hidden scroll-dependent evidence, or animations that make a handoff look like distribution. A staff mode switch must visibly name the fictional staff role; replayed and simulated staff actions retain their source labels.

Display **Sandbox**, **Live agent**, **Deterministic run**, **Simulated staff action**, and **Recorded replay** as applicable to the component, rather than letting one live model request imply that every observation is live. No authentication key, role token, provider header, or local secret path belongs in public UI, evidence exports, screenshots, or browser configuration. A session role label establishes scope without exposing its credential.

### Separate optional transit context from the fixture clock

If MBTA context is shown, place it in a source-labeled panel with its wall-clock fetch time, source observation time when available, route/stop scope, and freshness. The fictional November event runs on a scenario clock. Current live transit data must not silently enter that event as contemporaneous evidence or be retimestamped to fit the fixture.

Use **Live transit context — separate from this simulated event** for a connectivity display, or use explicitly labeled fixture/recorded transit observations whose times belong to the scenario. Driving decisions with a live feed requires a separate event whose operating clock and relevance configuration match that feed. A stale or failed read remains unknown/unavailable; an empty result is not proof that a volunteer will arrive. Transit data cannot establish a person's location, check-in or ETA, and is unnecessary to the same-venue pantry handoff.

### Pantry acceptance walkthrough

1. Identify pantry 24, partner 16, expected 20, supply shortfall 16, and remaining service 40 without opening a technical panel.
2. Inspect a stock-status source and its freshness; explain why source confirmation is not a receipt.
3. Hold the 16 partner kits and observe the pending staff task, unchanged pantry stock, and unchanged service target.
4. In the staff view, record the handoff and inspect one atomic source/destination receipt; verify that the expected shipment remains unreceived and destination stock is not yet reserved.
5. Observe the agent reserve destination stock and apply a permitted plan under its standing grant, without an additional approval prompt.
6. Advance qualified execution and record aggregate distribution; verify matching physical, cumulative, and on-time counters.
7. Exercise a partial handoff, duplicate/unknown response, invalid quantity, and late distribution; confirm truthful reservations, deficits, and feedback.
8. Repeat via keyboard and labeled replay; verify the actor, mode, event clock, optional transit clock, and source labels remain clear at presentation size.

## Accessibility and presentation requirements

- Support keyboard navigation and visible focus for each action.
- Use legible text at projector distance and a compact participant page on mobile.
- Do not encode feasibility or urgency through color alone.
- Avoid automatic audio and fast flashing changes.
- Make time windows and budget values readable as text.
- Use short labels with optional definitions for terms such as "hold" and "commit."
- Allow the presenter to pause animation and inspect a record.
- Keep user-provided text bounded and escape it when rendered.
- Offer an equivalent presenter action for a participant who cannot use the demo link.

## UI acceptance walkthrough

1. Load the campus profile and identify goal, venue window, and required activities without opening a technical view.
2. Inject a tested update and locate its affected dependency.
3. Inspect the relevant source check and see its actual response.
4. Prepare a hold and confirm that capacity, budget, and expiry appear correctly.
5. Submit an authorized participant contribution and see its receipt.
6. Compare candidate consequences and commit a permitted one.
7. Inspect the resulting state rather than only the recommendation text.
8. Inject a stale notice and see the reference mismatch.
9. Run an infeasible case and identify the needed organizer decision.
10. Load a second profile and repeat the same interaction pattern.

## Implementation priorities

Build the organizer board, stateful action receipts, and complete first episode before visual polish. Add the participant page after role-scoped contributions can be processed correctly. Add animations only where they explain dependencies or state changes.

The first milestone is a complete understandable loop. A static attractive screen with simulated action text does not satisfy the product acceptance criteria.
