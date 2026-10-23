# Decision policy: verify, prepare, or commit

Status: proposed policy, 2026-10-23. The heuristics below are implementation specifications and research hypotheses. They are not validated performance claims.

## Decision problem

At a decision time, the agent has a goal, a currently accepted plan, observed facts, unresolved claims, delegated actions, and a remaining time and tool budget. It must choose an action that helps the event succeed while accounting for unnecessary changes and the cost of waiting.

The action set contains:

| Action class | Concrete example | Effect |
| --- | --- | --- |
| Keep | Leave the accepted order of activities in place | No mutation, but schedule a meaningful observation or deadline |
| Verify | Query the current equipment booking or request the volunteer's check-in | Obtain a scoped observation, possibly unknown |
| Prepare | Hold an available backup kit until a specified expiry | Preserve an option while consuming bounded capacity or budget |
| Commit | Apply a checked activity/resource plan | Change the operational schedule and consume or convert holds |
| Ask | Present explicit alternatives to the organizer | Obtain a required priority, missing fact, or authority decision |

These are selectable actions, not a mandatory sequence. A policy that always verifies before doing anything could miss a deadline. A policy that always prepares could waste scarce community resources.

## Hard constraints and soft preferences

Hard constraints include the fixed venue, activity dependencies, maximum capacity, required accessibility provisions, mandatory participant availability, binding resource commitments, and the approved budget ceiling. A required activity has an explicit completion window. A resource can serve at most its configured capacity at an overlapping time.

Soft preferences include preserving the announced order, limiting changed start times, minimizing spending, reducing organizer interventions, and preserving optional activities. The organizer can rank or weight these preferences. The agent cannot silently turn a hard requirement into a preference.

The campus MVP uses feasibility first. It then ranks feasible candidates using a documented cost function such as:

```text
candidate_cost =
    w_start_shift * sum(abs(new_start - accepted_start))
  + w_changes * number_of_changed_activities
  + w_spend * additional_cost_in_cents
  + w_optional_loss * optional_activities_removed
  + w_external_disruption * participant_notifications_required
```

Normalize or scale the terms explicitly because minutes, cents, and counts are different units. Record weights and tie-breaks in the run configuration. Display the individual terms to the organizer. Do not claim that the numerical score represents community welfare.

A candidate that is feasible under assumptions must state those assumptions. Confirmed feasibility in the local store does not guarantee that a volunteer will arrive or a physical device will work later.

## Candidate generation for the MVP

Generate a finite set from configured edit templates:

1. Keep the accepted plan.
2. Swap independent activities when their windows and resources permit it.
3. Shift a permitted activity by one of the declared offsets.
4. Substitute a registered compatible backup resource.
5. Select an organizer-approved alternate activity format.
6. Combine at most two allowed edits, subject to a configured candidate cap.

The initial fixture should be small enough to enumerate every declared candidate. This establishes an exact optimum over the declared candidate set, not over every possible event plan. Report the set size and any truncation. For ties, prefer fewer changed activities, then lower additional cost, then a stable candidate identifier.

Previously started or completed activities are fixed. Committed resources are released only through valid cancellation terms. A change that starts in the past or assumes a resource before its arrival is infeasible.

### Pantry candidate generation and honest partial service

The pantry adapter retains all physical, authority and budget constraints. It additionally checks consumable conservation across time, exact unit compatibility, source ownership, staff throughput, and the service deadline. The original aggregate target remains an explicit success condition. A partial plan can be operationally valid while failing that target. Never silently reduce the goal to make the partial plan appear successful.

Use a bounded set of quantity and workflow candidates: retain the current pantry allocation, reserve confirmed pantry stock, hold a confirmed partner quantity for staff handoff, request the permitted transfer through its local staff task, and commit a distribution allocation supported by received stock. Compare full and partial allocations using only registered stock and authorized operations. The agent can apply a plan within its standing grant, but staff must separately attest physical receipt and distribution.

Rank candidates lexicographically: reject operational constraint violations first, then minimize the **original target's projected on-time unfulfilled quantity**, then compare unnecessary changes, reserved quantities and verification cost. The first pantry profile explicitly permits partial service when full service cannot be achieved. For example, a valid 34-kit allocation is preferable to 24 under the declared objective, but the result must still show a six-kit target shortfall. Report assumed receipts and quantities separately from confirmed achievable quantities.

`ConstraintReport.result` refers to validity of the proposed allocation under its listed assumptions. A feasible partial allocation is not full-goal success. Its report must include the original target, projected on-time distribution, remaining gap, and uncertainty in its existing named `checks` and their explanatory details, with uncertainty in `assumptions` and `execution_preconditions`. These are report contents, not new top-level schema fields. The outcome scorer computes actual success later from state and timestamped receipts. Conditional partner handoff can be a contingency proposal, while immediate distribution commitment requires physical destination stock and its reservation.

Track two useful clocks: the last time a handoff task can finish before the source hold expires, and the last service start that can still meet the target at the configured staffing rate. DEV03 declares a two-minute handoff response and one kit per minute of qualified service. A response cannot be assumed instantaneous, and a later commitment cannot backdate service. The source window ends exclusively at 12:50. The service deadline is inclusive at 13:40, with completion processed before deadline closure at equal timestamps.

Retain the same verify/prepare/commit loop and finite tool budget across both domains. The adapter supplies domain checks and objective components. It must not supply the correct held-out answer or a scenario-specific branch. Optional transit context can justify asking for a volunteer update, but cannot manufacture a personal ETA or a stock receipt.

## Evidence handling

Each `ChangeSpec` links to an immutable `Observation`. Resolve four questions before allowing it to change the planning assumptions:

1. Does it concern this event and the identified booking, resource, or participant?
2. Is its event time relevant to the current activity window?
3. Is it new evidence, a duplicate, a correction, or a conflicting report?
4. What does the source actually have authority or knowledge to report?

Do not count message repetition as independent corroboration. A forwarded warning and its original share the same evidence lineage. A stale observation remains in the audit trail but does not automatically supersede a fresh scoped response.

Use discrete operational states such as unresolved, corroborated, contradicted, superseded, and inapplicable. These describe the evidence record. They are not calibrated probabilities. Source authentication confirms origin, not truth. A status tool can return stale information and should expose its observation time.

Ambiguity should trigger entity resolution or a question, not a guessed booking identifier. An unavailable tool means the status is unknown, not that the resource is unavailable.

## A practical first policy

The first policy uses decision relevance, reversible actions, and deadlines. It does not need a probabilistic model.

1. Read a consistent state snapshot and expire invalid holds.
2. Incorporate new observations and validated changes.
3. Generate candidates and evaluate them against confirmed facts.
4. For each material unresolved claim, consider its declared alternative outcomes, such as delivery before or after the required slot.
5. Check whether those alternatives change which candidate is feasible or preferred.
6. If no alternative changes a permissible decision, keep the current best plan and explain why a query was unnecessary.
7. If a claim matters, identify a scoped query that could resolve it before the last useful action time.
8. Before waiting, check whether an expiring hold preserves a useful option at an authorized, declared cost.
9. Invoke the useful query or prepare the justified contingency. Re-evaluate when its result arrives.
10. Commit a candidate when the necessary checks and authority hold. If time is exhausted, choose a feasible plan robust across the still-plausible outcomes when one exists.
11. If no such plan exists, expose the tradeoff or infeasibility and request the specific organizer decision. Preserve existing commitments unless a separately authorized protective action applies.

The policy can combine a hold and a query, but it must account for both cost and capacity. It cannot infer permission to spend from a mention of a budget in untrusted message content.

“Last useful action time” is computed from the activity deadline, preparation duration, tool latency allowance, and resource cutoff. It is a configured operational calculation. The system should show it as “backup must be confirmed by 14:10,” using the event timezone.

### Robustness under unresolved outcomes

For the small scenario set, evaluate a candidate under each publicly declared plausible outcome. A robust candidate satisfies hard constraints in all of those outcomes. Prefer it when a decision must be made before a useful verification response can arrive, using a declared worst-case or regret criterion for soft costs.

This protection covers only the modeled outcome set. The agent must not invent precision or imply protection against every possible disruption. When the plausible outcome set is empty, incomplete, or internally inconsistent, surface that limitation.

### Preventing oscillation

Maintain the accepted plan as the comparison reference. Include the number and magnitude of changes in candidate cost. Reconsider only when an observation, deadline, user priority, or resource state changes. Use a minimum improvement threshold for purely preferential edits, configured before evaluation.

Do not suppress a required feasibility repair because a cooldown is active. Hard constraint violations take precedence over a preference for plan stability.

## Optional extension: value of verification

A probabilistic extension is useful only when the scenario model supplies declared probabilities or when a separately validated estimator exists. The language model's confidence is not a substitute.

Let `s` denote a possible operational state, `a` a feasible action, `q` a query, and `r` its possible response. For an explicitly declared belief model, compare:

```text
best_without_query = min_a E[cost(a, s) | visible evidence]

best_after_query = E_r[
    min_a E[cost(a, s) | visible evidence, query q returns r]
]

net_query_value = best_without_query - best_after_query
                  - query_cost - modeled_delay_cost
```

Query when positive value exceeds a declared threshold and the response can arrive in time. Include failed, unknown, and misleading query responses in the observation model when those outcomes are possible. Compute costs using the same action and constraint model as the planner.

This is optional after the deterministic policy works. It creates additional assumptions that must be disclosed in results. The hidden realized scenario is unavailable to this computation. Public scenario priors and private realized outcomes must be stored separately.

## Worked decision patterns

| Visible situation | Decision-relevant distinction | Reasonable policy response |
| --- | --- | --- |
| Delivery may miss the equipment slot | Does the current booking actually arrive after the required setup time? | Hold a registered backup if useful and allowed, then query current booking status |
| Warning names last month's reservation | Does it refer to the current resource commitment? | Mark it inapplicable after deterministic identity/time checks |
| Volunteer checks in and declares an available interval | Does that interval cover an unmet role requirement? | Update availability, re-evaluate the affected activity, preserve other commitments |
| Resource offered without capability details | Would the offered item satisfy the activity's requirements? | Request or verify missing fields, avoid treating the offer as ready equipment |
| Tool fails shortly before a cutoff | Is there a feasible response across the remaining plausible outcomes? | Use that response within delegated authority, or present the explicit infeasible tradeoff |
| Organizer prioritizes keeping a community workshop | Does the preference change the best feasible plan? | Re-rank with a new goal version and show the changed tradeoff |

These are intended behaviors, not hard-coded correct answers for every episode. Vary costs, deadlines, and resource availability so that the winning action sometimes changes.

## Meaningful comparisons

Use the same visible observations, allowed tools, initial resources, candidate set, latency model, and action authority for all relevant policy comparisons.

| Comparison policy | Purpose |
| --- | --- |
| Keep the initial plan where possible | Measures whether adaptation is useful at all |
| Deterministic event rules | Tests whether language and agentic selection add value over straightforward automation |
| Capable tool-using LLM with common constraint checks | Measures the contribution of the proposed decision policy under an equally safe executor |
| Verify every material claim | Measures whether selective queries reduce cost or delay without harming outcomes |
| Commit on each interpreted alert | Measures sensitivity to misleading updates and unnecessary changes |
| Proposed policy without provisional holds | Tests the value and opportunity cost of reversible preparation |

A separate interface ablation may give the deterministic rule policy typed messages, but disclose that information difference. A full-stack comparison should also include natural-language variants, entity ambiguity, and parsing failures for the language-based systems.

Do not compare a guarded policy against an unrestricted baseline and attribute every gain to reasoning. Keep executor protections common. A privileged oracle can be a diagnostic upper bound but must be labeled separately from deployable policies.

## What would support the contribution

The proposed mechanism earns its complexity if it improves task completion or commitment preservation, or achieves comparable outcomes with fewer unnecessary actions and lower query cost, across matched scenarios. Report the cases where verification consumes too much time, holds block another participant, or a conservative policy fails to exploit a beneficial opportunity.

A successful showcase demonstrates the mechanism. A comparative study establishes its observed performance within the declared setting. A novel theorem or general guarantee would require additional research beyond this plan.
