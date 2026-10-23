# Research sources and positioning

Sources were inspected during the October 23, 2026 planning conversation. The statements below distinguish public facts, author or vendor claims, and our design inferences. Public pages can change. Recheck operational rules before a real pilot.

## Program fit

The user supplied a detailed PEAAII Fall 2026 brief covering goals, constraints, tools, structured outputs, RAG, APIs, evaluation, reliability, human oversight, interdisciplinary applications, and a seven-minute presentation. The public [PEAAII program page](https://ai.umb.edu/events/) independently confirms the Agentic AI theme and lists October 25 submission, October 27 finalist notification, and October 29 symposium dates.

The public page does not establish the full judging rubric, artifact format, pre-existing-code policy, or submission timezone. Check Canvas for these items. The seven-minute presentation requirement comes from the user.

| Program objective | Proposed project evidence |
| --- | --- |
| Identify goals, constraints, tasks, tools, and actions | Structured event goal, dependency graph, resource constraints, tool contracts |
| Build an agentic workflow | Source interpretation, selective queries, planning, state-changing tools, observation loop |
| Use structured outputs and retrieval | Validated ChangeSpec and source-linked policy retrieval |
| Evaluate reliability and failure cases | Matched scenarios, strong baselines, stale/conflicting evidence, tool errors, infeasible goals |
| Apply AI to a practical problem | Organizer task and participant contributions validated with community users |
| Communicate clearly | One event story, visible plan changes, concise action record, seven-minute demonstration |

## Local primary sources

| Source | What it establishes | Design implication and boundary |
| --- | --- | --- |
| [UMass Boston Event Services](https://www.umb.edu/event-services/) | The university supports student activities, conferences, and community gatherings | A real setting for organizer workflows. It is not evidence of a partnership |
| [Student organization event workflow](https://www.umb.edu/event-services/student-organizations/) | Designated student planners use 25Live. Reservations, promotion, equipment, and catering involve dependencies and advance arrangements | Useful source material for constraints. Do not imply instant access or automatic institutional approval |
| [25Live event creation guide](https://www.umb.edu/media/umassboston/content-assets/event-services/pdf/25Live_Pro_Create_Event_Guide.pdf) | Event requests specify locations and equipment or service requirements | Supports a resource-oriented data model. No public write API was verified |
| [Boston Love Your Block 2026](https://www.boston.gov/departments/civic-organizing/love-your-block-2026) | A neighborhood cleanup operating model with volunteers, leaders, equipment pickup, and returns | A later scenario profile. Its spring 2026 event is historical context, not an upcoming event |
| [U-ACCESS](https://www.umb.edu/campus-life/current-students/u-access/) | Campus basic-needs support and a PantrySoft intake link | A possible discovery context. No operational records, endorsement, or inventory integration are available to this project |
| [U-ACCESS Food Pantry](https://www.umb.edu/campus-life/current-students/u-access/food-pantry/) and [student leadership roles](https://www.umb.edu/campus-life/current-students/u-access/u-access-student-leaders/) | Published service context includes deliveries/restocking and staff responsibilities for stock, donations, distribution and volunteers | Supports a bounded logistics discovery scenario, not inferred demand or measured impact. The synthetic kit target and stock counts are our design assumptions |
| [Campus Center dining](https://www.umb.edu/campus-center/services/dining/) and [campus Dunkin listing](https://umb.sodexomyway.com/en-us/locations/dunkin-donuts) | UMass Boston has a campus Dunkin location, and the dining operator documents its ordering channel | Coffee is a relatable future example. These pages establish neither a public operations API nor access to orders, queues or inventory |
| [Boston food resources](https://www.boston.gov/departments/food-justice/food-resources) | Public referral information and advice to confirm pantry hours | Useful referral material. It is not a live stock or donation feed |

## Optional public data

| Source | Verified capability | Appropriate use |
| --- | --- | --- |
| [MBTA V3 portal](https://api-v3.mbta.com/) and [documentation](https://api-v3.mbta.com/docs/swagger/index.html) | Schedules, predictions, alerts, stops, facilities, and other transit data. The portal permits keyless experimentation | Optional context for a delayed participant. It is not a complete journey-planning service |
| [UMass Boston shuttles](https://www.umb.edu/transportation/shuttle-bus-information/) | Posted shuttle information and a tracker link | Link or manually encode documented timetable assumptions. A supported public shuttle API was not verified |
| [National Weather Service API](https://www.weather.gov/documentation/services-web-api) | Forecasts, observations, alerts, and documented API access | Optional outdoor-event context. A weather forecast does not by itself quantify attendance or operational loss |

Live MBTA and NWS requests succeeded during the planning research. That observation establishes accessibility at that time, not a service-level guarantee. Cache source timestamps and provide a labeled fixture fallback. Do not introduce a live feed merely to satisfy a feature checklist.

## Existing products and the differentiation boundary

| Product/source | Publicly described capability | Consequence for positioning |
| --- | --- | --- |
| [Cvent CONNECT 2026 announcement](https://www.cvent.com/en/press-release/cvent-unveils-more-70-product-innovations-cvent-connect-2026-backed-1-billion) | AI event creation, venue recommendations, attendee changes, and other workflows, at differing release stages | A conversational event planner is not sufficient differentiation. Do not describe announced features as all generally available |
| [Transit GO](https://help.transitapp.com/article/549-how-to-use-go) and [service alerts](https://help.transitapp.com/article/96-get-notifications-about-disruptions-on-your-line) | Guided trips and disruption notifications | A commute assistant needs a contribution beyond alerts and route advice |
| [FoodCopia](https://foodcopia.co/food-pantries-kitchens/) | Pantry inventory and meal-planning functionality | A pantry dashboard is not a new category |
| [Food Rescue US](https://foodrescue.us/our-app/) | Food-rescue coordination tools | A future rescue application would need a specific operational contribution |

These are feature observations, not exhaustive product evaluations. We have not established that no competitor supports the proposed recovery behavior. The pitch should state what this prototype implements and measures, rather than a market-first claim.

## Technical primary sources

### ReAct

[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) established a prominent pattern of interleaved reasoning, actions, and environmental feedback. Tool use and an observation loop are inherited design ideas, not this project's novelty.

### Plan revision and commitment preservation

[Replan, Repair, or Edit?](https://arxiv.org/abs/2609.19654), submitted September 17, 2026, compares full replanning, hierarchical repair, and local revision after travel disruptions. It evaluates feasibility recovery, preservation of commitments, and computation. This supports measuring both task completion and plan disruption. Its reported results belong to its travel benchmark.

[Plan-and-Patch](https://arxiv.org/abs/2610.10786), submitted October 7, 2026, studies repairing affected regions of structured plans while retaining surrounding portions. Local repair itself is established prior art. This project does not need to implement its diffusion-model method.

### Information acquisition

[Value of Information: A Framework for Human-Agent Communication](https://arxiv.org/abs/2601.06407), submitted January 10, 2026, frames clarification as a tradeoff between expected utility and user effort. The proposed verification policy is related to that established decision-theoretic idea. Applying it to status queries, provisional holds, and event commitments is a design direction whose empirical value remains to be tested.

### Evaluating actions through state

[τ-bench](https://arxiv.org/abs/2406.12045), submitted June 17, 2024, evaluates tool-agent-user interactions using end-state checks and repeated trials. It motivates checking whether goals and domain rules are actually satisfied, rather than scoring only the quality of an explanation. Its historical model performance numbers should not be presented as current agent performance.

## Proposed contribution and evidence required

The candidate contribution is a controller that selects useful verification, prepares reversible contingencies, and commits feasible event changes under a limited budget for time, resources, and interaction.

To substantiate that contribution, compare task completion, hard-constraint violations, unnecessary changes, recovery time, and verification cost against a capable tool-using agent and a deterministic policy. A verify-all variant tests whether selective checking is useful. Record interpretation accuracy separately so language understanding is not conflated with control quality.

The public sources establish feasibility and related work. They do not establish community demand, prototype correctness, superiority, deployment readiness, or scientific novelty. Those require the discovery and evaluation work described elsewhere in this folder.

## Source maintenance

For every policy fact used by the application, retain a URL, title, retrieval date, relevant passage or identifier, and applicability scope. Treat retrieved content as evidence, not execution instructions. Retain older versions when a changed rule affects a recorded experiment. Use a small allowlisted corpus for the first demonstration so sources remain reviewable.
