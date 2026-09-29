# COLING 2027 push: working plan (not registered)

Target: ARR October 2026 cycle (submission 12 October 2026), committing to COLING 2027 (commitment
23 December 2026). Facts to confirm at their sources before relying on them: COLING 2027's route
(ARR only, or also direct), page limits, and acceptance rates (see `VENUE.md` once
verified). Owner decisions are marked **[owner]**.

## The paper in one sentence

What operational alerts say, how well language models read it, and what each reading error costs
when a certified controller acts on it: a benchmark of short supply-chain alerts with graded,
typed information content and varied phrasing, reading and calibration results across a model
ladder, a decision-weighted error measure, and a real-text check, with the UV paper's
certify-then-hedge as the instrument (cited in the third person, not a contribution).

## Scope that fits 13 days

In:
1. **Benchmark (synthetic, exact labels).** Truth first (family, direction, size, onset,
   duration; lead-time size), then text. Information levels L0 to L4; forms of expression (exact,
   verbal, range, relative, unit change, hedged, negated); reliability classes (accurate,
   overstated, understated, mis-timed, wrong entity, retracted, distractor numerals). Templates
   under `analysis/aacl/templates/`, team-reviewed. Held-out wording families for a
   generalisation split. Size: about 2,000 alerts.
2. **Reading evaluation (no simulator, cheap).** Every ladder model reads the benchmark into a
   `ShockSpec` (module 02 prompt and parser, unchanged): field accuracy, ordinal error, abstention
   on silent fields, error taxonomy, and calibration from K samples per alert. Baselines: a
   rule-based extractor and a small open model.
3. **Value of reading (simulator).** On an informative stratum (new pool), the text-reading hedge
   against the content-free hedge and arm 1, two primary models; plus the decision-weighted error
   (replace one read field with the truth, recompile, measure the change in cost) on the gate,
   whose orders use the stated size. Registered as stage E before its live runs.
4. **Real-text check.** openFDA drug-shortage notices (CC0; `https://api.fda.gov/drug/shortages.json`,
   pulled 2026-09-29: 1,599 records, of which 1,100 carry free-text `related_info`; 440 of those
   mention timing or supply terms, 135 distinct statements such as "Next Delivery: November 2026;
   Estimated Recovery: December 2026; Shortage per Manufacturer: Manufacturing Delay", "Estimated
   recovery: late September 2026", "Recovery: TBD"; `shortage_reason` gives the cause for 414).
   Only 7 records are resolved, so realised durations are not available from one snapshot: within
   the deadline, the check is reading accuracy against two human annotators (cause, expected
   recovery or next delivery, vagueness, "TBD" as abstention) and calibration; a daily snapshot
   collector started now gives realised recoveries for the camera-ready or a later version.

Out (future work): the text-informed size prior and future-onset hypotheses (method
extensions); human paraphrase sets beyond a small sample; InventoryBench instances.

## Schedule

| Days | Work | Output |
|---|---|---|
| 0 (29 Sep) | Facts verified; plan; generator and reading harness scaffold; openFDA pull | `VENUE.md`, scaffolds |
| 1 to 3 | Templates and generator; rule-based baseline; leakage and regex checks; team review of templates **[owner: who reviews]** | benchmark v1 |
| 3 to 4 | Throwaway power runs; stage E registration pushed before any live run | `PLAN.md` stage E |
| 4 to 7 | Live reading runs across the ladder (K samples for calibration); stage E decision runs, two models | outputs, evaluator |
| 6 to 8 | openFDA sample annotation **[owner: two annotators, about 200 notices]**; human ceiling on 200 benchmark alerts | agreement, ceiling |
| 8 to 12 | Analysis; ACL-format draft (8 pages long paper); limitations; Responsible NLP checklist; anonymised, third-person citation of the UV paper | draft |
| 12 (11 Oct) | Internal read; disclosure text for the UV paper | final |
| 13 (12 Oct) | ARR submission; named service contributor **[owner]** | submitted |

The UV camera-ready (due 15 October) needs only the team's author, affiliation and
acknowledgment items after today's merge.

## Owner decisions needed now

1. **Service contributor** for ARR (a qualified reviewer from the author list; required from the
   October cycle) and ORCID-linked OpenReview profiles for every author.
2. **Annotators**: two people for about 400 short items (benchmark ceiling and openFDA sample).
3. **Budget** for live runs: reading runs across about 20 models with K samples on about 2,000
   alerts, plus two-model decision runs; estimate before launch (expected tens of dollars).
4. **Templates**: team-written, or model-drafted and team-edited (then with a model family not
   among the readers).
5. **Venue risk**: accepting that 13 days is tight; the January 2027 cycle (ACL 2027) is the
   fallback, and nothing here is wasted if the October submission slips.

## Risks

- "Built so text wins": report bland and misleading levels with equal weight, and measure the
  telemetry reveal time.
- Overlap with the UV paper: no restated results; the ladder, content-free control and method
  appear only as prior work.
- Synthetic templates: held-out wordings, a regex baseline that fails on verbal forms, the
  openFDA check.
- Time: the benchmark and the reading runs are the core; the decision study can shrink to the
  two primary models and the gate's decision-weighted error if needed.
