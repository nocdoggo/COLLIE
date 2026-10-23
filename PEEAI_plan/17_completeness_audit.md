# Plan completeness and consistency audit

Audit date: October 23, 2026. Scope: the whole `PEEAI_plan/` package, its connection to the existing repository audit, three implementation waves, examples, schemas, external-access assumptions, and presentation. This is an audit of the plan and design artifacts. The application and comparative experiments remain to be implemented.

## Decision and readiness

**Proceed with the campus event as the main demonstration and Pantry Continuity as the second domain.** Coffee is a useful future illustration. Official campus dining pages confirm a Dunkin location, but there is no verified access to commercial stock, queue, or order systems. Pantry provides a clear additional modeling requirement: consumed stock and a fixed aggregate service goal. This is a design judgment about the proposed showcase, not a measured comparison of market demand. The detailed decision and primary sources are in [the pantry specification](15_pantry_showcase.md).

The package is sufficiently specified to begin Wave 1. It is not a completed API specification or a promise that every experiment fits an unknown team budget. The roadmap explicitly assigns remaining executable schemas, second campus development case, held-out cases, and implementation checks to their owning waves. No external account is needed to start the deterministic foundation.

## Coverage and traceability

| Requirement | Evidence in the plan | Required implementation evidence |
| --- | --- | --- |
| Clear audience and local relevance | [Product](01_product_brief.md), [scenarios](02_community_scenarios.md), [sources](12_research_sources.md) | Comprehension walkthrough and appropriately labeled community review |
| Substantive agent behavior | [Policy](05_decision_policy.md), [tools](06_tool_contracts.md) | Actual tool outcomes, persisted mutations and observe/revise behavior |
| Research depth without unsupported novelty | [Repository audit](13_repository_audit.md), [sources](12_research_sources.md), [claims ledger](templates/pitch_claims.md) | Matched baseline comparison, limitations and failures |
| Explicit goals and actions | [Data model](07_data_model.md), [schema](schemas/planning.schema.json), [examples](examples/README.md) | Validated schemas plus transactional domain checks |
| Genuine domain adaptation | [Pantry specification](15_pantry_showcase.md), [architecture](04_architecture.md) | Shared orchestrator with a separately tested stock/service adapter |
| Community participation | [User experience](03_user_experience.md), [validation](10_community_validation.md) | Role-scoped check-in, stock confirmation and staff action receipts |
| Exactly three implementation waves | [Roadmap](11_implementation_roadmap.md), [Wave 1](waves/01_foundation.md), [Wave 2](waves/02_adaptation.md), [Wave 3](waves/03_evidence_showcase.md) | Task ownership, exit gates, handoff records and explicit incomplete items |
| Complete frontend and backend path | [Architecture](04_architecture.md), [user experience](03_user_experience.md), wave task tables | API, persistent store, role views, candidate comparison and receipt visibility |
| Reliable actions and recovery | [Tools](06_tool_contracts.md), [risk register](14_risks_and_open_decisions.md) | Atomic writes, stale revision rejection, expiry, idempotency and receipt reconciliation |
| Quantity and temporal correctness | [Data model](07_data_model.md), [pantry specification](15_pantry_showcase.md) | Conservation, partial handoffs, qualified throughput, deadline scoring and late-event truth |
| Evaluation without leakage | [Evaluation](08_evaluation.md), [results template](templates/evaluation_results.md) | Separate public/private runners and frozen 80-campus/40-pantry protocol with actual counts |
| Seven-minute presentation | [Runbook](09_seven_minute_presentation.md) | 420-second rehearsals, 45-second second-domain slot and genuine replay |
| Access and cost dependencies | [API plan](16_api_and_access.md) | Existing model endpoint smoke test and bounded run budget; optional transit adapter |
| Reproducible release | [Wave 3](waves/03_evidence_showcase.md) | Clean install, sanitized artifacts, local startup, offline replay and submission requirements |
| Existing research preserved | [Decision record](00_decision_record.md), [repository audit](13_repository_audit.md) | New app namespace and no transferred inventory performance claims |

## Defects found and resolved during this audit

1. **The second domain conflicted with old scope statements.** Product, scenarios, architecture, model, roadmap, presentation and risk register now consistently select pantry. Skills exchange remains configuration regression and fallback. Coffee adds no third build obligation.
2. **Time-box variants competed with the requested waves.** Exactly three wave documents now own dependencies and completion gates. Older 24/48-hour language is only illustrative effort, never an alternative phase plan.
3. **Consumables were being treated like reusable equipment.** Stock reservations persist across time slots. Atomic handoff debits its registered source, and distribution consumes physical and reserved units together.
4. **A supply gap could be confused with unmet service.** Initially 24 on hand leaves a 16-kit supply shortfall, but zero distribution leaves a 40-kit service deficit. A handoff closes only the supply gap.
5. **Partial receipts conflicted with the proposed executor.** The contract now supports partial source transfers using remaining hold quantities. Untransferred units remain reserved until release or expiry. A partial outcome cannot reduce the original target.
6. **Physical receipt identity was weaker than retry identity.** Unique receipt/distribution references now prevent duplicate stock credit even with a fresh transport idempotency key. Receipt lookup is an explicit read operation.
7. **Staff approval and the agent's standing grant disagreed.** The agent can apply a validated plan within its grant. Staff alone attest physical handoff and distribution. The demonstration identifies those distinct sessions.
8. **A hidden fixed-time staff opportunity could bias policies.** Handoff response is now action-relative with public latency/window parameters and equal response rules across policies. It is a pending local task, not automatic success.
9. **Throughput lacked executable timing semantics.** Typed parameters and actual qualified service intervals prevent a late commitment from claiming a full earlier service window. Prior distribution is subtracted only from accumulated throughput capacity, avoiding double subtraction.
10. **Exactly-at-deadline events could be processed inconsistently.** Service completion at 13:40 is inclusive and precedes deadline closure/reconciliation at that timestamp. Provisional hold expiry remains exclusive.
11. **Late real actions could disappear or create retrospective success.** Authorized late physical distribution remains in stock/cumulative records, while on-time success uses timestamped records against the original deadline.
12. **A handoff could imply extra unmodeled staffing.** The development fixture explicitly treats the two minutes as response latency and permits confirmation during setup. Extra physical labor or transport requires a new scheduled activity.
13. **Live transit and fictional dates could be mixed.** The API plan separates current wall-clock data from the November scenario clock. Replay transformations and origin must be labeled.
14. **The existing artifacts could imply implementation.** All docs distinguish planned contracts, validated example structure, future runtime checks and unmeasured results. The schema is now 0.2.0, with the connected example request digest updated.
15. **The fallback and development-case counts were ambiguous.** The presentation may use an honest design slide or a working skills-exchange configuration fallback. Neither passes the pantry implementation gate. A second campus development trajectory is still an explicit Wave 1 task.

## Artifact checks

The final review passed the following checks across the 39-file planning package:

| Check | Result |
| --- | --- |
| Draft 2020-12 schema and examples with timestamp format checking | Schema and all 11 JSON artifacts passed |
| Local Markdown links and fenced blocks | 217 links resolved, fences balanced |
| Public fixture references, schedules, durations, dependencies, grants and budgets | All three profiles passed the artifact checks |
| Initial pantry stock, expected-shipment arithmetic and staff-only grants | Passed |
| Connected campus request/receipt digest after version update | Passed |
| Presentation timing | 420 seconds total, including a 45-second pantry insert |
| Implementation wave documents | Exactly three |
| Supplied credential | Owner-only permissions, ignored, absent from Git index and planning artifacts |
| Tracked whitespace changes | `git diff --check` passed |

These checks establish internal consistency of the planning artifacts. They do not execute `hold_resource`, `record_stock_receipt`, `record_distribution` or an LLM policy. Their runtime invariants and comparative performance must be tested during the implementation waves.

## Remaining work and decisions

| Item | Current position | Owner/wave | Blocking effect |
| --- | --- | --- | --- |
| Team roles and effort | Unconfirmed. Responsibilities are defined without assuming four people | Kickoff, Wave 1 | Assign owners before parallel coding; no need to redesign phases |
| Full executable tool contracts | Planning schema covers selected shapes. Other tool request/response models and DB migrations remain implementation work | Environment owner, Waves 1–2 | Must be completed before the corresponding action can execute |
| Second campus development case and held-out banks | Conditions defined, most executable fixtures not authored | Evaluation owner, Waves 1 and 3 | Must exist and be frozen before full evaluation claims |
| LLM endpoint, model and cost cap | Existing registry available, current app access untested | Agent owner, Wave 2 | Gates live model behavior and fresh model evaluations |
| MBTA integration | Credential stored and one route request succeeded. App adapter not implemented | Agent owner, optional Wave 2 | No mandatory gate depends on it |
| Pantry operator feedback | No confirmed review or partnership | Product owner, Waves 2–3 | Synthetic demo can proceed; operational usefulness remains unvalidated |
| Model and simulation limits | Fixed venue, small candidates, standard kits, simplified throughput | Domain owner, all waves | State these in the UI and claims; broader tasks require new semantics |
| Submission format and hosting | User/Canvas requirements still to verify | Release owner, Wave 3 | Local reviewable package can be completed first |

The next implementation action is the contract/state foundation in [Wave 1](waves/01_foundation.md). Additional APIs and broader application ideas should not delay it. The full two-domain outcome is complete only when the relevant gates pass, even if a smaller verified subset is enough for an earlier presentation.
