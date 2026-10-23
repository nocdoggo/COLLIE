# Pitch claims ledger

Status: planned claim ledger, 2026-10-23. No new event or pantry measurement is asserted. Fill this before recording or presenting. A design target becomes a result only after its evidence exists. Use [evaluation](../08_evaluation.md), [Pantry Continuity](../15_pantry_showcase.md), and the exactly three-wave [implementation roadmap](../11_implementation_roadmap.md) to check scope.

| Proposed claim | Status | Evidence/run/source | Scope and important boundary | Approved wording |
| --- | --- | --- | --- | --- |
| The agent can interpret a source-linked change | planned | | Supported message/entity types; a claim is not verification | |
| The executor preserves modeled hard constraints | planned | | Defined invariants, grants, and tested mutations | |
| The controller reduces unnecessary plan changes | unresolved | | Unmeasured hypothesis; capable comparator, cases, repetitions, and costs required | |
| Community participants can contribute observations | planned | | Supported roles and access controls; no new spending authority | |
| Campus and community event profiles reuse one event model | planned | | Configuration reuse only; list tested differences | |
| Pantry Continuity reuses the shared core through a domain adapter | planned | | New integer quantity conservation, staff receipt/distribution, and original-target deficit semantics | |
| The pantry demo can fulfill its original 40-kit target | planned | | Fictional 24 on hand plus 16 physically transferred; expected late 20 excluded until received; actual staff receipts needed | |
| A pantry reservation proves kit receipt or fulfillment | unsupported | | Holds preserve an option; receipt and distribution are separate staff actions | Omit |
| Partial pantry fulfillment is represented honestly | planned | | Original target stays 40; report actual fulfilled quantity, deadline, and remaining deficit | |
| The primary comparison covers 80 held-out episodes | planned | | Eight cases × (one P0 run + three LLM policies × three seeds); record completed counts | “We plan an 80-episode campus comparison.” |
| The pantry transfer comparison covers 40 separate episodes | planned | | Four distinct held-out cases × the same ten runs; never pooled with event metrics | “We plan a separate 40-episode pantry comparison.” |
| All compared policies have equivalent tools and options | planned | | Frozen within-suite registry, candidates, costs, model settings, and grants; no favorable case selection | |
| A verification badge has supporting provenance | planned | | Successful relevant tool result, source identity, and freshness; no inferred receipt from text | |
| Optional MBTA context predicts a participant's arrival | unsupported | | Transit data cannot establish personal location, availability, check-in, or ETA | Omit |
| This is zero-shot transfer to pantry operations | unsupported | | Pantry requires an explicitly implemented and evaluated domain extension | Omit |
| The prototype connects to live institutional bookings or pantry stock | unsupported | | No verified integration; quantities and transactions are fictional | Omit |
| U-ACCESS or another pantry is a project partner | unsupported | | Public service context does not establish participation or endorsement | Omit |
| The agent makes recipient eligibility or allergen decisions | unsupported | | These decisions and recipient identities are outside the bounded aggregate-kit workflow | Omit |
| Prior inventory guarantees apply to event or pantry recovery | unsupported | | Different transition models and assumptions; new checks and measurements required | Omit |
| An operator wants to pilot the workflow | unresolved | | Record actual consent and scope if obtained | |

Permitted statuses: planned, implemented but not evaluated, verified in a test, measured in the scenario bank, supported by external source, unresolved, unsupported.

For every numerical claim, record the metric, denominator, policy versions, model configuration, case IDs, repetitions, aggregation, and whether the analysis was planned before results were viewed.

Keep evidence categories separate: prior COLLIE inventory findings; implemented campus behavior; measured primary event results; implemented pantry adapter behavior; measured secondary transfer results; and untested deployment hypotheses. A completed trace supports that trace, not a comparative advantage. A full or partial transfer suite supports only its tested adapter and cases.

The seven-minute script assigns the pantry exactly 45 seconds at 5:40–6:25. Select its label from actual evidence: **Live model + sandbox tools**, **Recorded replay** of an actual executable pantry run, or **Planned domain extension** if incomplete. A campus replay cannot stand in for pantry implementation, and a design slide cannot be described as a measured demonstration.
