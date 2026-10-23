# Decision record

## D001: Selected direction

**Date:** October 23, 2026. **Status:** accepted by the user.

The user selected the first recommended direction, Plan B: The Show Must Go On, and requested an adaptive application and demo involving communities. The user also requested a new branch and a comprehensive `PEEAI_plan/` folder. The immediate authorized deliverable is documentation and planning artifacts.

The application helps an organizer maintain a workable event plan when updates about people, timing, or resources arrive. Its central behavior is choosing among verification, reversible preparation, and committed plan changes.

The team are PhD students. The product must be understandable to students, faculty, and company representatives while supporting a substantive technical explanation and a seven-minute presentation.

## D002: Product scope

**Status:** working implementation choice, open to refinement during discovery.

The first event model has a fixed venue, four to six activities, a few resource types, participant or volunteer roles, a delivery dependency, and a contingency budget. A finite candidate evaluator is sufficient for the first planner.

Adaptation means the same engine can load different goals, activities, roles, resources, constraints, and local policy references. It also means responding to observations during an event. It does not mean assuming the initial model represents every community's workflow.

Primary profile: `campus_showcase`. Configuration regression: `community_skills_exchange`. Second showcase: `pantry_continuity`, contingent on implementing the explicit service objectives and stock constraints in D009. Neighborhood cleanup is a later profile.

## D003: Technical contribution

**Status:** proposed mechanism, empirical value unmeasured.

Study whether selecting useful verification and preparing reversible contingencies preserves task completion while reducing unnecessary changes and verification cost.

The first mechanism uses typed changes, a small dependency graph, deterministic feasibility checks, finite candidate comparison, explicit authority, and observed tool outcomes. Advanced value-of-information estimates are optional. They require declared assumptions and sensitivity analysis, not a confidence number invented by the language model.

Plan repair, tool use, and information acquisition have established prior art. The hackathon contribution is a working, locally meaningful implementation and a transparent comparative evaluation. A paper-level originality claim requires a narrower method definition and additional literature comparison.

## D004: Community participation

**Status:** accepted product direction, specific workflow to validate.

Community involvement should change useful application state: a participant checks in, a volunteer updates availability, a resource owner offers an item, or an organizer changes a priority. The application records the scope and freshness of those contributions. Each contribution remains distinguishable from confirmed availability or authority to allocate a resource.

A participant interaction is optional in the stage demonstration. A facilitator can enter the equivalent observation if a phone, network, or accessibility barrier prevents participation.

## D005: Real and simulated boundaries

**Status:** accepted planning constraint.

The prototype's operations store, tool calls, state changes, and action receipts should be real software behavior. Delivery trajectories, resource catalogs, and disruption scenarios can be fictional or replayed, with explicit labels.

Public university policies are source material. Access to a public policy page does not establish permission or technical access to reserve rooms, purchase items, message participants, or write to institutional systems.

The application should support explicitly delegated local actions. Organizer review can authorize consequential actions outside a standing grant. A review click is not necessary for every already-authorized read or reversible local operation.

## D006: Existing project protection

**Status:** accepted implementation boundary.

The new branch starts at `867da1c276305872ab33c101c51b9d5a671fe089` on `method/graded-commitment`. Existing paper outputs, preregistrations, benchmark artifacts, and core research contracts remain historical evidence. New application schemas should live in their own namespace.

Direct reuse will be determined module by module. Importing an inventory module does not validate an event model, and changing display labels does not establish a new objective.

## D007: Schedule and team assumptions

**Status:** planning assumptions.

The public PEAAII page lists October 25, 2026 for project submission, October 27 for finalist notification, and October 29 for the symposium. The user specified a seven-minute presentation. The team's available hours, size, budget, selected model endpoint, and Canvas artifact requirements remain unconfirmed.

The user's subsequent instruction replaces the initial 24-hour and 48-hour planning options with exactly three implementation waves, defined in [the roadmap](11_implementation_roadmap.md). Wave completion is based on acceptance gates, not assumed calendar duration. Check current Canvas instructions before packaging the submission. [Program schedule](https://ai.umb.edu/events/)

## D008: Branch and artifact naming

**Status:** completed.

- Branch: `hackathon/peeaai-plan`.
- Requested folder: `PEEAI_plan/`.
- Host institute spelling in prose: PEAAII.
- Product working name: Plan B: The Show Must Go On.
- Example event date: November 5, 2026, deliberately fictional and unrelated to the actual symposium schedule.

## D009: Pantry as the second showcase

**Date:** October 23, 2026. **Status:** selected for the build plan under the user's delegated pantry-versus-coffee decision.

Use Pantry Continuity as a distinct second demonstration after the campus workflow works. It adapts the same observation, verification, contingency, authority, and receipt loop to a staff-directed distribution session. Add consumable quantities, atomic reservation and transfer, staff-confirmed receipt and distribution, and an unchanged aggregate service target. Expected stock cannot satisfy an immediate stock constraint. Reordering an event and consuming finite stock are meaningfully different domain semantics.

The development example targets 40 standardized kits. Pantry stock has 24, a separate partner stock at the same fictional venue has 16, and an expected 20-kit delivery is delayed. A partner reservation protects an option. A staff-confirmed handoff transfers stock. Only recorded distribution advances the target. No recipient eligibility, household data, dietary judgments, real inventory access, or partnership is implied. See [the detailed showcase design](15_pantry_showcase.md).

## D010: Three implementation waves

**Date:** October 23, 2026. **Status:** requested by the user.

Wave 1 completes the deterministic campus vertical slice. Wave 2 adds the tool-using agent, community participation, pantry domain extension, and optional MBTA context. Wave 3 completes separate-domain evaluation, failure handling, delivery packaging, and the seven-minute presentation. These replace earlier time-box variants. Each wave has a required demonstration and acceptance gate in [the roadmap](11_implementation_roadmap.md).

## D011: MBTA credential and integration scope

**Date:** October 23, 2026. **Status:** local credential setup completed, application adapter planned.

The supplied credential is stored in `.local/keys/mbta.key`, with owner-only permissions and an explicit Git ignore rule. A read-only route request returned HTTP 200 using the credential in an HTTP header. This establishes successful access at that time, not implemented alerts, user tracking, quotas, or production reliability. The backend adapter will use transit information only for scoped public context. It cannot infer a volunteer's location or the arrival of a donation shipment. See [API and access requirements](16_api_and_access.md).

## Change log template

For each later decision, record the date, owner, status, evidence, affected documents, and consequences for the demo or evaluation. Separate a proposed change from an accepted change. If evaluation cases or scoring change after results are inspected, preserve both versions and identify the later analysis as exploratory.
