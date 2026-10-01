# Decisions before registration (working note, 1 October 2026)

Every build session reads this file first. Each decision below is the option recommended by the
1 October review of the plan, the audit guide and the code. Decisions marked **[owner, 1 Oct]**
were confirmed by the owner on 1 October; the others are provisional until the owner confirms
them. A decision the owner changes is edited here, with the date, before any file that depends on
it is hashed. This note is not part of the registration: `PLAN.md` and `AUDIT_GUIDE.md`
carry the registered text.

## Process rules for every session

1. **Sealing.** Nobody opens, lists or computes from `external_data/sealed/`. Only the freeze step
   runs `python -m analysis.coling.corpus` (which writes the sealed files). Build sessions call
   `build_corpus` in memory and may write train-period rows and event tables only. No outcome
   value of a statement dated 2023-01-01 or later is printed, tabulated or written outside the
   sealed folder; counts of events are allowed, cross-tabulations of test outcomes are not.
2. **No paid call and no API key in the environment before the registration is pushed.** Dry runs
   and scripted clients only.
3. **One owner per file.** A session edits only the files it was given.
4. **`rules.py` is frozen now** at sha256 prefix `6a810bcb1ae277b9`. The pilot may change the
   guide and the prompts; a remaining difference from `rules.py` is disclosed, not patched.
5. **Seed 20261001** for every random draw; items are sorted by id before drawing.
6. **Sample order.** Pilot, check set and the literal-task sample are drawn first, from the events
   table and the form classifier only (no outcome field). The train-half audit sample is drawn
   next. In-context examples, dev prompt items and minimal-pair seeds exclude all of them.
7. Python: the main checkout's environment (`../COLLIE/.venv/bin/python`) with `PYTHONPATH=.`
   from the worktree root. scikit-learn, scipy, pandas and numpy are available; lightgbm, lifelines and statsmodels
   are not, and nothing is installed for this study.
8. Web requests carry `collie-research-fetch/0.1 (academic research; polite, cached)` and nothing
   personal.

## Decisions (numbering follows the review)

1. **Scope [owner, 1 Oct].** E8 is cut now (E9 was already off). **E6 is kept until its 4 October
   linker gate**, as the plan schedules it; E7 follows E6 in the plan's cut order and stays a
   "could". HeidelTime and SUTime are disclosed as not run; the HTML gap fill is disclosed as not
   done.
2. **Hold triggers [owner, 1 Oct].** Registration by 3 October 23:59 AoE and numbers frozen by
   6 October 23:59 AoE. The labellers do the pilot and the train-half audit on Friday 2 October
   and the main labelling on 3 to 5 October. One relaxation is written into the draft before
   registration, to be used only if a human gate has to be repeated: registration by 4 October
   and freeze by 7 October.
3. **Dev boundary: 2021-01-01, as a fixed date.** The rule in the draft gives 2021-10-01 with 178
   scoreable statements, 167 of them no/no, because train outcomes are censored at the split and
   captures stop for 308 days after 2021-11-30. The fixed date gives 643 scoreable dev statements
   in 73 episodes and leaves 787 for fit, on the displayed presentation (decision 5) and on the
   tables of 1 October; the corpus freeze prints the registered counts. (An earlier version of
   this note gave 661 and 799, which counted every covered presentation.) The dev outcome mix is printed in the registration, and
   the plan discloses that fit outcomes are followed past the dev boundary.
4. **Reference reading.** Eligibility for E3 and the `stated_end` shown in prompts come from the
   frozen rule reading (`rules.py`) for every form. The authors check 100 eligible statements and
   report the rule's accuracy. Author labels on the non-plain-month statements are not collected in
   October (option a).
5. **Display row.** When one statement covers several presentations, one at-risk member is drawn
   by the seeded rule and shown; the primary outcome is that presentation's bracket; the
   statement-level maximum is a secondary.
6. **Fields shown.** The entry block and the probe show Therapeutic category and Initial posting
   date, as the structured baseline uses them; Status is dropped (constant on at-risk events).
   The prompt templates are re-pinned once, together with the D1 and D3 sentences.
7. **Literal task (E2).** 120 items, double-labelled, with a 20-item pilot and a 20-item check set
   from the dated strata. One pooled exact McNemar test per primary over the forms other than
   month-and-year; per-form results are descriptive. (The owner was asked about 120 together with
   the scope cuts and did not object; 120 stands unless the owner says otherwise.)
8. **Budget scope.** `gemini-3.8-flash` runs E2 and the E3 core only; the TBD, silent and stale
   secondaries are read by the two primaries. The table is rebuilt at the real counts, with
   per-run caps that sum to the per-model caps.
9. **Availability rule and capture freeze [owner, 1 Oct].** Future, estimated and negated uses of
   "available" are not class available. The owner read the list of availability strings
   (`out/availability_strings.csv`: 233 still classed available, 647 limited, 30 moved out by the
   fix) on 1 October and rejected none, so the frozen rejection list stays empty. The capture set
   is frozen at the 110 files on disk.
10. **Alpha gate.** Computed on the 20-item check set, with the share of identical intervals
    reported beside it. Planted-error keys are scored by script after both sheets are in.
    **People [owner, 1 Oct]:** two annotators (A1 and A2) do all labelling and both outcome
    audits; the owner adjudicates and does not label. The owner may therefore read model outputs;
    A1 and A2 may not read model outputs on items they label until the gold file is hashed.
11. **Delayed entry.** Statements first captured after their stated period ended stay eligible; a
    sensitivity analysis on statements first captured on or before `t_end` is registered.
12. **Calibrator.** Form by revision when the cell has at least 100 statements, else form, else
    all dated forms; revision buckets first, second, third or later; Turnbull shares, with the
    prompt sentence reworded to match.
13. **Small rules.** Date shift of plus 4 years; the 20 samples use condition (a) and are scored
    as empirical quantiles of the sampled medians; the probe is drawn from the eligible list,
    stratified by year; H2 margin 0.02; strict parsing (the sort-and-clip sentence is deleted).
14. **Cutoffs and routes.** A session with network access collects them at source with URL and
    date; the owner reviews the two primaries.
15. **E5.** The authors' predictive readings are cut for October; the registered test is a GEE
    clustered by seed (hand-coded or via a cluster bootstrap if no library is available).
16. **Hashed at registration:** the form classifier, the calibrator and both gradient-boosted
    baselines (code). Fitted artefacts are hashed at F1. If the text model is not ready, its code
    hash moves to F1 by an edit before the push.
17. **`deepseek-v3` [owner, 1 Oct].** Its maker documents no cutoff and the route has no dated
    id: it stays a primary with its cutoff bounded by its release month, and the plan says
    "bounded", not "documented". Its endpoint is `deepinfra/fp4` (not `streamlake`). The cutoff
    table is fixed in the counts-only code at the freeze and does not change after it.
18. **Anonymity [owner, 1 Oct].** The repository stays public under the owner's handle; ARR has
    no anonymity period, and the submission does not link to it. The registration is evidenced
    by an anonymised copy of the registered plan and guide in the supplement, with their sha256
    and push time.
19. **Vague row [owner, 1 Oct].** The literal-task table's row "vague or undated" is split into
    a `vague` row and a `no_date` row, so the pilot carries a vague item (open point D1). A
    shortfall in the vague row goes to the undated row first. The four sample lists are redrawn
    before anything is handed out.
20. **Distractor rows [owner, 1 Oct].** The row "distractor date" is split into "distractor
    only" (class `distractor`, and a non-dated class that carries a distractor date) and "dated
    target beside a distractor date" (a dated class with a distractor date), half of the old
    quota each. The plan's E2 line on distractor items is reported on both rows.
21. **Guide phrases [owner, 1 Oct].** A statement that shares a wording with a phrase quoted in
    the guide may be drawn. A statement whose whole normalised text equals a quoted phrase of
    three or more words is excluded from every sample, whatever the drug or company. The number
    of drawn items that contain a quoted phrase is reported.
22. **Relative-form seeds [owner, 1 Oct].** The minimal-pair seeds of the relative form are
    taken from statements dated 2023-01-01 or later, text only, because the labelling samples
    use every train statement of that form. Calls on those seeds wait for F1. The other forms'
    seeds stay in the train period.
23. **Old archive [owner, 1 Oct].** The untracked archive of 29 September, which may hold a
    copy of the sealed outcomes, was moved unopened under the sealed folder.
24. **E6 route extension [owner, 1 Oct].** A route carried on at its stated end under a new TMI
    ID counts as extended; the same-TMI-ID reading is a registered sensitivity analysis. The
    plan discloses that the wider reading was drafted after the rate under the stricter one
    was seen.
25. **E6 gate rule [owner, 1 Oct].** At least 150 links checked, 30 per term or all of a term's
    links when it has fewer, and at least 90% of all checked links correct, with no minimum
    per term. A link on both sheets is correct only when both checkers say so, and "unclear"
    is not correct.
26. **H3 comparator (provisional until the owner confirms).** The comparator of H3 is the base
    rate by listing age, fixed at registration. The draft's contrast against the
    structured-only GBM is a registered secondary beside H3, and "value beyond the structured
    fields" is written only when the model's best condition beats both. The family stays at
    six; no predictor code changes; the H3 pair of the power code becomes the base rate
    against the text-trained GBM. The plan discloses what had been seen (item 36). If the
    freeze-run tables put the structured-only GBM below the base rate on dev, or leave the
    95% interval of their difference including zero, the choice goes back to the owner before
    registration.
