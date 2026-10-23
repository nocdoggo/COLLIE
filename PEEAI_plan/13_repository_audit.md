# Repository audit and reuse map

Audit basis: the repository inspected on October 23, 2026 at base commit `867da1c276305872ab33c101c51b9d5a671fe089`. This is an architecture assessment, not a new experiment or execution audit.

## What the current project establishes

COLLIE separates language interpretation from numerical inventory control. A model proposes a bounded explanation of what changed. The later implementation weights a fixed set of hypotheses as evidence arrives and computes inventory actions through a deterministic controller.

The current manuscript is in [paper/](../paper/README.md). The requested [manuscript/](../manuscript/) directory contains build artifacts from an older draft. The original design documents describe successive research plans, not a complete specification of today's application.

Read the [first design](../init_design_docs/03_compile_shocks_or_always_inventory.md), [second design](../init_design_docs/03_5_compile_shocks_or_always_inventory.md), and [current claims ledger](../paper/CLAIMS.md) in that order to understand the progression from compute placement to typed hypotheses to graded influence.

## Reuse decisions

| Asset | Relevant behavior | Proposed reuse | Required work |
| --- | --- | --- | --- |
| [Core contracts](../collie/contracts.py) | Closed output vocabularies and observation isolation | Design reference | Introduce a separate event-domain schema. Preserve frozen inventory contracts |
| [Spec prompt](../collie/spec/prompt.py) and [schema](../collie/spec/schema.py) | Structured interpretation and validation | Patterns, with selected helper reuse after dependency review | New prompt, vocabulary, relevance rules, and source references |
| [LLM client](../collie/llm/client.py), [cache](../collie/llm/cache.py), [ledger](../collie/llm/ledger.py) | Metered requests and replay infrastructure | Candidate direct reuse behind an application adapter | Confirm supported provider configuration, cache isolation, and logging of user content |
| [Episode runner](../collie/sim/runner.py) | Same realization under different controllers and full records | Evaluation pattern | Event state transition engine and distinct public/private state |
| [Graded controller](../analysis/commitment/cth.py) | Evidence affects action influence | Method reference, possible supply-subsystem experiment | New transition and cost model for event recovery. No theorem transfer |
| [Inventory controller](../collie/control/controller.py) | Bounded replenishment calculations | Optional direct reuse for a genuine inventory stream | A supply objective and units that match the application |
| [Evaluation utilities](../collie/eval/) | Endpoints, traces, paired analysis | Review for generic utilities | Event completion, constraint, churn, recovery, and tool-cost metrics |
| [Real-content evaluation](../analysis/real_content_pilot/evaluate.py) | Separates interpretation and operational outcomes | Analysis design reference | A new evaluation entry point and dataset |
| [Commitment study](../analysis/commitment/PLAN.md) and [report](../analysis/commitment/REPORT.md) | Frozen protocols, comparisons, documented deviations | Research process reference | A smaller hackathon protocol with its own version and run manifest |

## Material findings for the pitch

1. The original binary activation design failed its registered pilot. The later graded design is the relevant technical starting point. [Results](../paper/sections/08_results.tex)
2. In the main simulator setting, the language-informed controller did not show a resolved incremental gain over the alert-timed no-model control. The application must retain a strong deterministic comparison. [Claims ledger](../paper/CLAIMS.md)
3. About 96% of the baseline improvement in that setting came from deterministic lead-time shifts. Improvement under noisy lead times was not confirmed. A broad claim of robust real-world event recovery would exceed this evidence. [Limitations](../paper/sections/11_limitations.tex)
4. The stated statistical bounds depend on null and arrival assumptions that the running inventory implementation does not fully satisfy. Their names must not become a product assurance label. [Limitations](../paper/sections/11_limitations.tex)
5. The live pilot identified incompatible duration/persistence interpretations and mismatched severity labels. New demo fixtures need a clean vocabulary and explicit semantic validation. [Pilot report](../analysis/real_content_pilot/REPORT.md)
6. The inspected code is research infrastructure. A browser interface, application service, event store, role model, resource holds, scheduler, and external data adapters are new work.

## New application components

The canonical proposed application tree is in [the architecture document](04_architecture.md#proposed-implementation-layout), under `apps/plan_b/`. It contains API, domain, agent, tools, store, scenarios, evaluation, web, and focused tests. Keep the finite planner and constraint evaluator in the domain boundary, with a separate planning module if its size warrants one.

This tree is a recommendation, not an assertion that these modules exist. The documentation folder remains `PEEAI_plan/`. The application should have a distinct installation and run path so demo dependencies do not silently redefine the frozen research environment.

## Implementation sequencing

Build deterministic state transitions and replay first, then the planner, then the language interface and participant view. A functioning non-LLM baseline makes the application testable before introducing model variability. Integrate existing client/cache utilities only after confirming they do not require the inventory-specific contract.

The existing runner processes complete episodes. It does not provide an incremental browser session interface. A new event service is necessary for live participant check-ins and concurrent updates.

## Data and claim provenance

The root [README](../README.md) states that the project code is MIT and warns against redistributing the pinned benchmark data. Use authored synthetic event fixtures for the public prototype. If a later operator supplies records, document access, intended use, and redaction independently from the code license.

Keep three evidence categories visible in presentation materials: prior inventory findings, newly measured event-sandbox findings, and untested deployment hypotheses. A metric from one category cannot serve as an outcome in another.
