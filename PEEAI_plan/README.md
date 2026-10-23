# Plan B: The Show Must Go On

An adaptive agent for keeping a community event workable when people, resources, and plans change.

**Status:** planning package, created October 23, 2026. The application, integrations, and proposed experiments are not implemented by this package. Example data are fictional. Targets are proposed acceptance criteria, not measured results.

**Branch:** `hackathon/peeaai-plan`, created from `method/graded-commitment` at `867da1c276305872ab33c101c51b9d5a671fe089`.

**Folder naming:** `PEEAI_plan/` preserves the user's requested spelling. The host institute's abbreviation is **PEAAII**, the Paul English Applied AI Institute at UMass Boston.

## The decision

Build one agent that preserves an organizer's explicit goals by choosing whether to **verify an update, prepare a reversible contingency, or commit a feasible change**. Demonstrate it through a small campus or community event. Let community participants contribute observations and bounded resource offers through the application.

The presentation's central question is: **When a convincing update arrives, should an agent change the plan?** The audience should see a genuine disruption handled, a stale warning resolved, and actual tool actions recorded in the prototype's state.

The first implementation uses one fixed venue, a small activity graph, resource availability, participant check-ins, and a contingency budget. The campus showcase is the primary fixture. **Pantry Continuity** is the planned second showcase: the same agent loop with an explicit stock ledger and an aggregate service target. A community skills exchange remains a low-cost configuration regression and presentation fallback. Pantry support requires the new quantity and receipt semantics described below.

Implementation follows exactly **three waves**: a deterministic campus slice, agentic and community adaptation including the pantry extension, then evaluation and showcase delivery. Start with the [three-wave roadmap](11_implementation_roadmap.md). The pantry is a fictional staff workflow inspired by a relevant campus service, with no claim of U-ACCESS partnership or live stock access.

## Read in this order

| Reader or task | Start here |
| --- | --- |
| Team kickoff | [Decision record](00_decision_record.md), [product brief](01_product_brief.md) |
| Community relevance and scenario design | [Community scenarios](02_community_scenarios.md), [community validation](10_community_validation.md) |
| Interaction design | [User experience](03_user_experience.md) |
| Backend and agent implementation | [Architecture](04_architecture.md), [decision policy](05_decision_policy.md), [tool contracts](06_tool_contracts.md), [data model](07_data_model.md) |
| Research and evidence | [Evaluation protocol](08_evaluation.md), [sources and novelty](12_research_sources.md) |
| Build planning | [Implementation roadmap](11_implementation_roadmap.md), [repository reuse audit](13_repository_audit.md) |
| Seven-minute presentation | [Presentation and rehearsal plan](09_seven_minute_presentation.md) |
| Decisions still to resolve | [Risks and open decisions](14_risks_and_open_decisions.md) |
| Second showcase and transfer design | [Pantry Continuity](15_pantry_showcase.md) |
| Credentials, feeds, and access needed | [API and access plan](16_api_and_access.md) |
| Completeness, corrections, and remaining gaps | [Plan audit](17_completeness_audit.md) |

## Complete package

The numbered documents carry rationale, scope, interfaces, evaluation, and delivery decisions. Supporting artifacts make the design inspectable:

- [JSON Schema](schemas/planning.schema.json) defines illustrative contracts for the public scenario, private evaluator fixture, typed change, mutation request, and action receipt.
- [Schema notes](schemas/README.md) identify what structural validation can and cannot establish.
- [Public showcase fixture](examples/campus_showcase.public.json) contains the initial state and visible information.
- [Community skills exchange fixture](examples/community_skills_exchange.public.json) changes durations, dependencies, resource terms, priorities, and participant contributions using the same schema.
- [Pantry public fixture](examples/pantry_continuity.public.json) and [private development fixture](examples/pantry_continuity.evaluator.json) specify a 40-kit target, 24 kits in pantry stock, a delayed 20-kit delivery, and a separate 16-kit partner stock. These are planning artifacts, not executed outcomes.
- [Private evaluator fixture](examples/campus_showcase.evaluator.json) contains future events and outcome checks. It must never enter the agent's context.
- [Typed change](examples/change_spec.json), [status observation](examples/observation_after_query.json), [candidate plan](examples/candidate_plan.json), [constraint report](examples/constraint_report.json), [commit request](examples/commit_request.json), and [commit receipt](examples/commit_receipt.json) form a connected development walkthrough.
- [Example walkthrough](examples/README.md) explains the fiction, timestamps, and intermediate states.
- [Operator interview template](templates/operator_interview.md), [claims ledger](templates/pitch_claims.md), and [evaluation tables](templates/evaluation_results.md) support evidence collection.

## The finish line

A credible first build accepts a goal, interprets an update, queries the relevant state, compares a bounded set of alternatives, validates constraints, applies an authorized change to a stateful sandbox, and reacts to a later observation. It exposes a brief action record and a visible before/after plan.

The research deliverable is a matched comparison of policies on the same hidden scenarios, including false warnings and unsuccessful repairs. The presentation deliverable is a seven-minute demonstration supported by measured outcomes and a labeled replay fallback.

## Shared boundaries

- Public policy information can ground the demo. Real reservation availability, institutional writes, external messages, and partnership claims require their own verified access or evidence.
- Reuse COLLIE's separation of interpretation, control, and observation. Its inventory equations and statistical guarantees do not automatically apply to event scheduling.
- The language model's expressed confidence is not a calibrated probability. Authority, relevance, freshness, corroboration, and uncertainty have separate meanings.
- Community participants contribute scoped facts about their own role or offer. They cannot grant themselves organizer authority.
- A hard constraint failure is a failed plan, even when its explanation is persuasive.
- The schema describes structure. The proposed executor must additionally enforce authority, state revisions, resource conservation, time windows, and budget feasibility.

## Working agreement

Use this folder as a versioned planning source. Record accepted changes in [the decision record](00_decision_record.md). Update the examples, schemas, tool contracts, and evaluation protocol together when a change affects their shared meaning. Keep research outputs and frozen contracts in the existing project separate from the new application work.
