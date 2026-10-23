# Wave 3 — Evidence, reliability, and seven-minute showcase

Status: proposed implementation and release tasks, 2026-10-23. No run count, performance benefit, usability result, or release gate is claimed achieved. This is the last of the [three implementation waves](../11_implementation_roadmap.md).

Use the functioning shared core and adapters to collect comparative evidence, expose failures, improve comprehension, and prepare a reproducible demonstration. The campus case remains the primary experiment and presentation story. Pantry provides a separately scored capability test. Add no new domain capability after freezing the release comparison.

## Entry gate and ownership

M2 must pass for the full live evaluation. Harness construction, scorer review, fixture authoring, and slide structure can start earlier. A deterministic-only build can collect functional evidence, but it cannot produce fresh LLM trials or satisfy a claim of completed live comparison.

All paths below are proposed under `apps/plan_b/` except presentation artifacts explicitly linked to this planning folder. Roles E/A/U/V are defined in the [roadmap](../11_implementation_roadmap.md#work-ownership-and-proposed-files).

| Task | Owner / reviewer | Proposed files and artifacts | Dependencies | Required output |
| --- | --- | --- | --- | --- |
| W3.1 — Freeze comparison | V with A / E | `evaluation/manifest.py`, `evaluation/policies/{rules,strong_llm,selective,verify_all}.py`, `scenarios/private/eval/`, `evaluation/manifests/` | M2; development-only calibration | Scenario/prompt/tool/model/planner hashes; caps; outcome predicates; policy parity; held-out manifests |
| W3.2 — Run and report evidence | V / E and A | `evaluation/run.py`, `evaluation/scoring.py`, `evaluation/report.py`, `evaluation/results/<run_id>/`, completed [results template](../templates/evaluation_results.md) | W3.1; usable model provider for fresh trials | Primary campus comparison, separate pantry suite, actual counts and failures, per-case results, one readable figure |
| W3.3 — Reliability and UX | E with U / V | `tests/test_release_failures.py`, `tests/test_pantry_workflow.py`, `web/src/`, sanitized replay exports, walkthrough notes | M2; rerun evidence affected by fixes | Failure drills, reset/replay, authority and quantity checks, keyboard/readability/comprehension observations |
| W3.4 — Presentation and release | U with V / E and A | `README.md`, `release/manifest.json`, sanitized demo artifacts, [presentation plan](../09_seven_minute_presentation.md), completed [claim ledger](../templates/pitch_claims.md) | W3.2, W3.3; actual submission requirements | Timed script, three consecutive rehearsals, offline fallback, reproducible local package, M3 record |

W3.2 and W3.3 can run in parallel only while UI/reliability changes do not alter the measured behavior. Any change to interpretation, policy, tools, planner, stock accounting, scoring or fixtures invalidates affected frozen results. Preserve earlier runs and either rerun the matched comparison or report versions separately.

## Freeze before measuring

Use [evaluation](../08_evaluation.md) as the authoritative protocol. Record public and private fixture hashes separately; model/provider identifier and generation settings; prompt and policy versions; tool registry; candidate rules and supplies; grants; query relevance; modeled tool latency; planner/objective version; stock adapter version; staff-action schedule; cost and time caps; seeds; run ordering; and scoring predicates.

The same world, candidate options, authority, executor, planner, evidence opportunities and staff action rules apply to all four policies within each suite. P1 is a capable tool-using LLM allowed to verify and hold resources. P2 uses the selective controller. P3 checks all relevant sources under a fixed relevance rule and bounded failures. P0 uses published deterministic rules, never hidden truth. Do not make P2's input or tool menu stronger to create an advantage.

Separate two campus development cases from C01–C08. The campus stage example is development case DEV01. Author held-out wording, timings, tool outcomes and recovery choices before collecting their comparison. Confirm C01–C07 each admit a permitted successful path; prove C08 infeasible over the declared action space. Keep case names, expected outcomes, future arrivals, staff attestation schedules and truth labels out of agent-visible inputs.

Fix call caps, retry rules and timeout after development practice. Proposed starting caps remain eight model calls and sixteen tools, with every failed call consuming its cap. All policies experience the same modeled check duration; report actual provider latency separately. A run that caps out or times out stays in the denominator. Randomize policy order within each case and start each trial with fresh policy state.

## Primary campus comparison

The full protocol is **80 campus episodes**: eight cases, one P0 run per case, and three fresh trials each for P1/P2/P3: `8 × (1 + 3 + 3 + 3) = 80`. Confirm P0 is deterministic. Model-response caches cannot supply three nominally fresh trials; fixture caching is appropriate because the benchmark world is intentionally fixed.

Report C01–C07 goal completion and C08 appropriate infeasibility separately. Include rejected action attempts, executed violations, unnecessary changes on designated negative controls, plan churn, verification calls and simulated delay, recovery delay, hold cost and expiry, and actual model/tool usage. A zero executed-violation count means none were observed in these tested runs; it is not a general reliability guarantee.

Retain observations, interpretations, every proposed/rejected/accepted candidate, requests and results, receipts, final state, errors, timing, cost, and scorer output. Grade final environment state, not the agent's narration. Diagnose the first broken stage without removing the failure from its outcome denominator.

If full repetitions cannot finish, one trial per policy on all eight cases yields **32 completed campus episodes**. Report the exact case IDs, trial counts, missing repetitions and versions. Other subsets must be counted equally explicitly. The planned 80 remains visible as uncompleted scope. A reduced study can support descriptive observations for that subset; it cannot be labeled the full protocol.

## Separate pantry transfer suite

The complete secondary protocol in [evaluation](../08_evaluation.md#separate-pantry-transfer-suite) is **40 pantry episodes**: four held-out cases T01–T04, P0 once, and P1/P2/P3 three fresh trials per case: `4 × (1 + 3 + 3 + 3) = 40`. The canonical 40/24/20/16 stage trace is development material and is excluded. The two full suites total 120 planned episodes, while keeping separate metrics and denominators. Finish the campus pipeline before spending the evaluation budget on this secondary suite.

The four conditions cover successful alternate recovery, duplicate/adversarial quantity handling, stale receipt evidence with actual arrival too late, and an alternate handoff of only 10 kits leaving a six-kit deficit. The 10-of-16 transfer must preserve the residual six-unit hold until release or expiry, without a second credit. Freeze distinct wording and evidence timing; the agent cannot read the expected result from a case label. Staff-only receipt/distribution responses follow the same declared opportunities, action-relative latency, cutoff and readiness prerequisites for every policy.

Report original-target attainment on feasible T01–T02 and supported partial fulfillment on T03–T04 separately. Keep the initial target 40 visible; record timely distribution, remaining service deficit, supply gap, expected/on-hand/reserved/received/distributed quantities, source/destination conservation, duplicate credits, unreceived-stock violations, unnecessary holds, checks, cost, and staff-confirmation burden. A handoff can eliminate the supply gap while completed distribution remains zero. Do not count a committed plan as service.

The implementation acceptance trace and quantity failure checks are mandatory evidence for a pantry capability claim. The full 40 episodes are required to claim completion of the pantry comparison. If only one trial per policy on all four cases completes, report **16 pantry episodes** and the missing repetitions. If only functional traces exist, say so and make no comparative transfer claim. Never add pantry successes to the campus completion denominator or describe the adapter as zero-shot generalization.

Record which shared components stayed common, the added stock/service interfaces, and the work required to implement them. This supports a concrete statement about reuse with a domain extension. It does not establish operational suitability at a real pantry, institutional partnership, recipient benefit, or general public-resource coordination.

## Reliability and UX release checks

These checks are separate from the measured policy episodes. Rerun consequential checks after their code changes; repeated unrelated testing is not a substitute for resolving a known defect.

| Failure or interaction | Required result |
| --- | --- |
| Model outage or malformed output | Bounded failure is visible; deterministic/replay fallback is labeled; no fabricated model or tool result |
| Ambiguous mutation timeout | Reconcile original idempotency key before retry; one durable logical action |
| Stale revision, expired hold or changed goal | Reject or recompute under current state; no partially applied plan |
| Invalid authority or injected message | Tool enforcement holds even when text asks for exceptions; no privilege from message content |
| Pantry double allocation or repeated physical receipt | No second stock claim or credit, including disjoint time slots and fresh transport keys |
| Pantry partial or late handoff/distribution | Residual hold quantity retained after partial transfer; actual stock consumption and times recorded even for late service; original target and on-time deficit visible; no retroactive success |
| Pantry throughput and boundary time | Distribution does not exceed attended execution capacity; receipt/distribution/close ordering at the inclusive deadline is frozen and tested |
| Live MBTA absent or out of date | Optional evidence becomes unknown/unavailable or fixture mode is disclosed; no invented arrival confirmation |
| Episode reset and two browser views | Holds, commitments, memory, trace pointers and staff actions belong to the intended episode; both views agree on revision/receipt |
| Offline replay | Sanitized actual trace reproduces visible actions and result without provider/network access or private truth |
| Keyboard and comprehension | A viewer can identify current plan, evidence, next decision and action status; pantry view distinguishes expected stock, held stock, receipt, commitment and completed distribution |

Use a brief walkthrough with an available participant when practical and follow the [community validation plan](../10_community_validation.md). Record who was a team member versus an independent participant and what they actually understood or found confusing. Without an external participant, report an internal walkthrough. Do not fabricate feedback, pilot outcomes, or endorsement. No outreach or message sending is authorized by the documentation task.

## Seven-minute presentation and fallback

Use the [presentation plan](../09_seven_minute_presentation.md) as the timed script. Preserve most of the seven minutes for the campus goal, disruption, tool-backed decision, result, evidence and limitations. If the pantry extension passes its checks, include its tested **45-second segment inside the same seven-minute budget**, showing quantity accounting and a staff-confirmed handoff. Do not add 45 seconds after the conclusion.

The pantry slot is conditional on clear arithmetic and reliable reset. If it is incomplete, omit its live capability claim or use skills exchange as a clearly labeled configuration demonstration. A recorded pantry trace may replace the live segment only if it comes from an actual completed run and remains visibly marked as replay. Keep full transfer results as backup material if they are too dense for the main story.

Prepare one results figure directly from completed manifests, a concise per-case table, one informative failure trace, and a claim ledger linking every numerical or comparative sentence to its source run. If P2 has mixed or no consistent benefit, show that tradeoff. A useful functioning prototype remains a valid result without claiming an improvement the comparison did not find.

Complete three consecutive rehearsals of the selected scenarios from a clean reset. At least one includes a forced provider or network failure and a successful switch to offline replay. Time the complete delivery, including transitions and the pantry segment, to seven minutes. Check readability at presentation size, a non-phone path for audience participation, and the fallback recording's audio/captions if used.

## Package and M3 exit criteria

Prepare a local reviewable release package with:

- Setup and run instructions, dependency/configuration references, supported profiles, and current limitations.
- Example configuration names and sandbox/live/replay mode controls, with no credentials or private contact details.
- Public fixtures and separately controlled evaluator fixtures, plus actual sanitized traces for the stage fallback.
- Frozen run manifests, actual episode counts, per-case metrics, raw-log references, the result figure, and failure analysis.
- The seven-minute script, presentation assets, claim ledger, source/license notes, and rehearsal record.
- A requirement-by-requirement submission checklist checked against the actual course platform, including whether a hosted URL or video is required.

Build the package from an explicit artifact allowlist. Exclude local secret stores, evaluator-only content from browser bundles, and participant-identifying data. Verify startup and replay on the intended presentation machine. Hosted deployment and external submission are separate actions to perform only when authorized; a local completed package does not imply publication.

M3 passes when mandatory functionality and release checks have no executed authority/stock/resource violations; evidence is frozen, scored and honestly counted; all shown successes match state and receipts; limitations and partial protocols are visible; three rehearsals and the failure fallback work; and the package meets confirmed requirements. The full-study labels additionally require 80 campus episodes and, separately, 40 pantry episodes. A partial evaluation must remain marked partial even when the reduced package is presentation-ready.

Record unpassed requirements explicitly. If a correctness bug appears, fix it and rerun affected functional checks and matched evidence before keeping its claim. If an optional adapter or second live segment fails, remove that optional dependency and rehearse again. Do not add another wave to conceal unfinished work: retain the three-wave structure and identify the exact remaining task.
