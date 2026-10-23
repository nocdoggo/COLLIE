# Evaluation result templates

Status: planned reporting template, 2026-10-23. These tables are intentionally empty and contain no experimental findings. A blank cell means unmeasured, not zero. Follow the exact protocol and P0–P3 policy IDs in [the evaluation plan](../08_evaluation.md), the distinct [Pantry Continuity contract](../15_pantry_showcase.md), and the three-wave [implementation roadmap](../11_implementation_roadmap.md).

Keep the primary campus comparison separate from the secondary pantry transfer comparison. The planned sizes are **80 primary episodes** (`8 held-out cases × (1 deterministic run + 3 LLM policies × 3 seeds)`) and **40 pantry episodes** (`4 held-out cases × the same 10 runs`). These are intended workloads, not completed results. A reduced run must state its actual case IDs, policies, repetitions, and omissions. Neither a stage rehearsal nor a recorded replay counts as a held-out trial.

## Run manifest

- Code commit:
- Suite: primary campus / secondary pantry transfer:
- Scenario-set version and hash:
- Held-out case IDs and excluded development fixtures:
- Protocol version:
- Policy identifiers:
- Model identifier and serving configuration:
- Prompt, parser, planner, adapter, and tool registry versions:
- Equal candidate-generation rules, complete candidate registry, and candidate-set hashes across policies:
- Tool limits, costs, retries, timeouts, and equal authority grants across policies:
- Source trust rules and provenance/freshness requirements:
- Scenario clock and random seeds:
- Provider seed support or recorded independent run IDs:
- Shared exogenous observations and policy-independent staff-response semantics:
- Number of independent cases:
- Number of repeated model runs per case:
- Failed or incomplete runs and treatment:
- Run order and freeze timestamp before the first held-out call:
- Analysis changes after inspecting outcomes:

Pantry runs must record the same agent grants for every policy and separate staff-only `record_stock_receipt` and `record_distribution` authority. Capture any domain-specific prompts or rules introduced for all policies. An adapter added for pantry accounting is an implementation contribution; it is not zero-shot transfer.

## Primary campus aggregate display

| Policy | Goal completion C01–C07 | Appropriate infeasibility C08 | Invalid attempts / executed violations | Unnecessary changes C02–C04 | Recovery time | Tool calls | Modeled cost | Incomplete runs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

Report both denominators and units. Do not average away an infeasible-goal case into ordinary success without the protocol's explicit outcome category.

## Pantry transfer aggregate display

| Policy | Target met T01–T02 | Supported partial fulfillment T03–T04 | Kits fulfilled by deadline / original target | Residual deficit | Conservation failures | Invalid attempts / executed violations | Checks and tool cost | Incomplete runs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

Keep full-target attainment and supported partial fulfillment separate. The original target is 40 kits in the proposed fixtures; reducing it cannot create success. Report staff-confirmed fulfillment, not promised, expected, or reserved quantities. Do not pool this table with event completion or describe the synthetic observations as real pantry impact.

## Per-case display, one table per suite

| Case | Policy | Seed/run ID | Final original-goal status | Invalid attempts / violations | Plan edits | Verification calls | Actual model/tool cost | Outcome note and trace |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

The independent scenario case is the comparison unit; three model runs within one case expose variability and are not three independent worlds. Retain unsuccessful, timed-out, capped, and rejected-action traces alongside successes.

## Pantry quantity and receipt ledger

| Case/run | Resource or target ID | Original target | Initial physical stock | Expected stock | Reserved quantity | Valid receipts / transfers out | Staff-confirmed fulfillment by deadline | Final on-hand | Supply shortfall | Service deficit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | | | |

Reconcile each resource: initial on-hand + valid physical receipts − valid transfers out − actual aggregate fulfillment = final on-hand. A same-venue partner handoff must debit the registered partner stock exactly once and credit pantry stock exactly once. Expected stock and reservations do not add physical stock. Record quantities at the deadline and after it separately; a later receipt cannot retroactively satisfy the deadline. Initially the fictional fixture has a supply shortfall of 16 and a service deficit of 40. The alternate handoff removes the supply shortfall; only staff-confirmed distribution reduces the service deficit.

| Case/run | Request/handoff ID | Actor and grant | Source → destination | Quantity | Physical event time / recorded time | Tool receipt and next-state version | Provenance and duplicate check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

## Interpretation display

| Message set | Entity/time/quantity extraction | Correct abstention or unresolved status | Supporting tool result and source time | Provenance/freshness accepted or rejected | Operational consequence |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

An incoming claim is distinct from a successful verification. Record stale or unavailable MBTA context explicitly if the optional feed is used; it cannot supply a person's location, check-in, availability, or ETA.

## Functional checks and adapter evidence

| Check group | Implemented version | Executed cases | Passed / failed / not run | Evidence |
| --- | --- | --- | --- | --- |
| Shared authority, versioning, idempotency, hold expiry, and hidden-state isolation | | | Not run | |
| Verified-label provenance and stale optional MBTA handling | | | Not run | |
| Pantry negative/fractional/excess quantity, concurrent reserves, and consumed stock reused in a later slot | | | Not run | |
| Pantry duplicate logical request and handoff, including a new transport key | | | Not run | |
| Pantry physical receipt timing, atomic source debit, and partial receipt | | | Not run | |
| Staff-only receipt/distribution, original-target retention, and visible deficit | | | Not run | |

Record the reused components, new adapter/state/tool components, implementation effort, and remaining unsupported operations. Passing these checks supports the tested contract, not a general reliability guarantee or zero-shot domain transfer.

## One success and one failure

For each, provide the initial goal, information available at decision time, selected checks, candidate tradeoffs, actual state-changing action, final state, and the strongest competing explanation. Distinguish simulated outcomes from observed human task completion.

## Community usability record

| Role | Task attempted | Completed independently | Misunderstanding observed | Correction needed | Change to product |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
