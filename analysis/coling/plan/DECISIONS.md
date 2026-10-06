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
26. **H3 comparator [owner, 3 Oct].** The comparator of H3 is the base
    rate by listing age, fixed at registration. The draft's contrast against the
    structured-only GBM is a registered secondary beside H3, and "value beyond the structured
    fields" is written only when the model's best condition beats both. The family stays at
    six; no predictor code changes; the H3 pair of the power code becomes the base rate
    against the text-trained GBM. The plan discloses what had been seen (item 36). If the
    freeze-run tables put the structured-only GBM below the base rate on dev, or leave the
    95% interval of their difference including zero, the choice goes back to the owner before
    registration.
27. **Owner, 3 October.** A1 and A2 started on Saturday 3 October with the pilot and the
    train-half outcome audit, to be returned by the end of that day. The registration deadline
    stays as written, Saturday 3 October 23:59 AoE (the relaxation is for a repeated human gate
    only). E6 is kept to its linker gate. The remaining provisional rules of the plan, and the
    items of its change list, item 36 included, are confirmed as written. The worktree reaches
    the API keys through links to the main checkout's key files (`cloud_endpoint/`, ignored by
    git; the files themselves are never read).
28. **Owner, 5 October: the hold.** A1 and A2 returned the pilot and the train-half outcome
    audit on 5 October. The registration deadline of 3 October and its relaxation had passed,
    so the hold trigger fired: the paper goes to the ARR cycle of January 2027 and not to
    COLING 2027. The plan's Plan B (section 12) describes the January version; its scope and
    its schedule are to be settled with the owner before registration. E6 is cut from the
    October study by its own gate rule (no link was checked by 4 October) and returns under
    Plan B.
29. **Pilot and train-half audit, 5 October.** Both pilot sheets are valid: alpha 1.0 on start
    and end month offsets, identical intervals on the 13 notices where both gave one, one
    disagreement on statement type in 20 notices. The sitting times on the sheets (120 and 300
    minutes) include reading the guide (owner, 5 October), so the labelling rate is measured on
    the check set. Train-half outcome audit: both sheets valid; all six planted errors caught;
    definition B, no confirmed error in 50 items; definition A, one confirmed error in 50 (item
    Q7d21bfff, code O1: the product's NDC was renumbered and the thread was not re-linked;
    adjudicated by the owner on 5 October); pass, no rule fix required. The returned workbooks
    are under `external_data/annotation/returned/`, their converted sheets under
    `external_data/annotation/pilot/` and `outcome_train/`.
30. **Owner, 5 October, evening: the October cycle after all.** The paper is registered with
    ARR for the October cycle, and the owner reversed the hold of decision 28 the same day:
    submission on 12 October. New dates, with no relaxation: registration by Tuesday 6 October
    23:59 AoE, numbers frozen by Friday 9 October 23:59 AoE. E6 stays cut.
31. **Pilot points [owner, 5 Oct].** Settled from the pilot itself, without a meeting, and
    told to A1 and A2 with guide v1: D1 as the guide has it (an abstaining target with no
    unknown marker is `estimated` when vague and `undetermined` when undated or TBD); D3 as C11
    ("until X" and "through X" are the period X); D13 as C17 (seasons); "temporarily on
    backorder" and "Sporadic availability expected" are not statements about timing; "Partial
    shipments on allocation April-July 2021" beside "No current supply" is a next delivery (a
    recovery needs wording that the shortage state ends). D14: the prompt is not extended; ADJ
    marks the gold items whose reading rests on a convention the prompt does not state, and
    E2 is reported with and without them. The pilot sentences D1 and D3 and the sentence on a
    median of 365 are in `read.py` (commit `29b10a4`).
32. **Registered test [owner, 5 Oct: option 1, the larger-of test with H1 one-sided].** Two simulations and a third
    that reconciled them (`size_check.py`, `out/size_check.json`) show that the draft's
    percentile p-values over-reject at the study's episode sizes (Holm 5.5% to 9.2% against
    5%). The plan now registers the larger of the bootstrap-t and the studentised sign-flip
    p-values, with the intervals of that test and H2's equivalence read from it; the draft's
    procedures become sensitivity analyses (PLAN section 6; change-list item 38). Cost: power
    at the plan's detectable differences falls from 75% to 61% (H1), 80-82% to 69-73% (H2)
    and 78-84% to 66-73% (H3). The alternatives put to the owner: the same test with H1
    two-sided; or the percentile p-values kept and their size disclosed. On 5 October the
    owner chose the test as the plan has it (H1 one-sided), with both sets of power figures
    before them. In the
    evaluator the choice is the constant `P_VALUE_SOURCE`. At `f57a91d` it is still
    `percentile` and every interval is a percentile interval; both change before F1 hashes
    the file. The power figures above are those of the random-effects generator; with whole
    dev episodes the registered test has 44% (H1), 43-49% (H2) and 70-71% (H3) at the plan's
    detectable differences, and the percentile p-values 54%, 44-55% and 77-85%. An
    independent check of the new plan text (5 Oct) found every figure of "Why this test"
    in the committed output and four statements that rested on runs outside it; the plan now
    says so where it cites them.
33. **What the evaluator computes, and who reads sealed outcomes [owner, 5 Oct: as written].** `evaluate.py` computes the six tests, Holm, the
    secondaries of section 6, the probe rule and the E3 analyses listed in section 6,
    "Evaluator". Eleven registered analyses are not in it (its own list `NOT_COMPUTED_HERE`);
    they are computed by secondary scorers, each named with its hash in F1 or in a dated
    amendment pushed before the script first reads a sealed file, and never before the
    evaluator has written its result file (so after the test-half outcome audit too); this
    widens the draft's sealing rule; the owner confirmed it on 5 October (change-list item
    39). E2, E5
    and the rule accuracy beside H2 read no sealed
    outcome. What is not computed by the freeze of numbers is named in the paper as not run.
    The twelve points on which the evaluator had to decide where the plan was silent are now
    in the plan (change-list item 39). `sealed_counts.py` is not edited (it is hashed in the
    freeze record): the plan's standing rule says that the evaluator calls its checked reader.
    `power.py` holds the secondary pair as (structured GBM, base rate) and the evaluator as
    (base rate, structured GBM), which is the plan's wording; the paper states the direction.
34. **Task E tool (5 Oct, late).** `audit_reference.py` is built and checked twice. Two points
    the guide left open are settled as the tool has them and written into the guide: an error
    may carry several codes (K1 with K3 or K4 can occur together); and two shares are reported,
    the one without a confirmed error (guide 8.4) and the one whose rule reading is confirmed
    (an item ADJ leaves unresolved is not), which is the list E7 uses. The blanks are in
    `analysis/coling/out/audit_reference/`. The guide's text on task E made its hash move to
    `ce58129993b31d33`; the literal, minimal-pair and task E sheets were written again under it
    (only their guide line changed), the freeze record was refreshed, and the check sheets,
    already with A1 and A2, keep the text `449c8e049be6cab1`. One statement of the task E
    sample has the same text as a literal-sample statement of another drug; the registered
    rule allows it, and the guide's changelog says so.
35. **E5 test and E2 reports (6 Oct).** The scorer `literal_scores.py` was reviewed by three
    readers; 26 of 28 findings were confirmed by a second reader each. Plan side, taken as
    recommended and listed for the owner's read: the unedited seed item is held to the
    criterion of the factor it is compared with (the registered contrast compared two
    definitions of error); the GEE's fallback is called by a primary's own cells only and
    takes the centred bootstrap p-value (the percentile one gave a Holm familywise error up to
    about 10% at low error rates in a simulation on the item file's layout; the centred one at
    most 5.8%); "by form" in the literal task is by stratum; the two weights are described for
    what they are; the convention items are a file fixed with the gold. Code side: 20 findings
    fixed with tests; the like-for-like error and the centred p-value are still to be put into
    the scorer, which is hashed in F1 or in an amendment before it runs on model readings.
36. **Intervals, after the review of the evaluator change (6 Oct).** 18 findings, all
    confirmed. Plan side: the search ends on a change of verdict, which is the last value not
    rejected only where the p-value falls steadily; an end is called unbounded on the value 50
    standard errors away alone, so equivalence can be declared beside a 90% interval with no
    end; the six secondary models' H1 to H3 carry the registered-test interval too. No number
    and no rule changed. An outage of about ten hours (5 Oct 21:56 to 6 Oct 08:20 EDT) stopped
    the fixer of that review partway; it was started again on the files as it left them.
37. **Result rules (6 Oct; points a and b wait for the owner).** A review of the paper draft
    found five places where the plan did not fix what the paper may write. Three proposals, one
    merged text and two attacks on it gave the wording now in the plan (change-list item 41):
    (a) a registered pattern decides the sentence "models read the letter of a notice but not
    its pragmatics" for a primary: a letter part (letter accuracy on the gold letter items not
    more than 0.10 below the rule reader's, by the 90% interval; no E5 test on a letter factor
    holding) and a standing part (an E5 test on a standing factor holding under Holm, at least
    0.10 above the seeds and above the letter edits, and the factor's own error on at least 0.10
    of its items); (b) the overconfidence criterion has two parts over every statement of the
    item set, against the largest frequency the captures allow and against the base rate's
    mean probability; (c) the two settings of the undetermined events are scenarios, not bounds
    (the panel's wider proposal of limits over all settings was not taken, to keep the
    evaluator as reviewed); (d) the anonymised copies are made by a script from a fixed list,
    their hashes recorded in F1 (the panel's version with a hash file in the registration
    commit was not taken, for time); (e) a secondary analysis by statement type, computed by a
    secondary scorer (the panel assigned it to the evaluator). Code that follows: the two-part
    criterion in `evaluate.py` before F1; letter accuracy, the floors and a `pattern` command
    in `literal_scores.py` before it runs on model readings; the analysis by type and the
    criterion's quantities in `secondary_scores.py` before its first sealed read.
38. **Overconfidence criterion in the evaluator; withholding (6 Oct).** The two-part criterion
    of section 13 is built into `evaluate.py` and was checked by an independent recomputation
    and by a regression, mutation and sealing check. Points the plan now states because the
    code had to decide them: a primary without an item set has no reading; an end on zero does
    not exclude zero; with one episode there is no interval. One sealing point found on the
    way, in code that was already committed: with one failed answer, the contrast "on the
    statements both sides parsed" stood beside the contrast on every scoreable statement and
    gave back that one statement's loss difference by subtraction. Both that contrast and the
    criterion's parsed-only figures are now withheld when 1 to 4 statements are left out or
    remain (plan sections 4 and 13). The criterion's code follows the recommended option of
    change-list item 41(b), which still waits for the owner.
39. **Last read of the plan, and what the review of the secondary scorer asked of it (6 Oct).**
    Three sentences came from the review of `secondary_scores.py` (the rule of the Date
    Discontinued cell analysis; a failed sample is left out of the sampled quantiles; where the
    two scenarios are reported, with figures over every statement withheld where 1 to 4
    statements of a set are not scoreable). A last independent read of the whole plan against
    itself, the guide and the frozen files then gave twelve corrections, all applied: the
    change list gains item 42 for the rules added on 6 October; section 16 records the counts
    the freeze run printed; the E5 negative result, Gate 2 and E1 no longer contradict section
    13, section 6 and the standing rules; the frame count of E2 is 685 (688 counts statements
    outside the frame); section 10 says that no pilot meeting was held and gives the dates as
    they fell; the anonymising script is committed by F1, not at registration; a cut of E5
    keeps the first 50 seeds in draw order; task E checks what the guide says; section 13
    words all four outcomes of H2. The sample lists, the sample manifest and the minimal-pair
    items, whose hashes the plan registers, are committed with it; the submitted sheets are
    fixed by their hashes and stay out of the repository for now. To do in `evaluate.py`
    before F1: the withholding of figures over every statement where 1 to 4 statements are
    not scoreable. The secondary scorer's 29 confirmed findings are still being applied.
40. **Owner, 6 October, evening.** (a) The headline rule: the registered pattern of section 13,
    with a margin of 0.10 against the rule reader in its letter part (the alternatives put to
    the owner: 0.15, or no switch at all). (b) The overconfidence criterion in two parts over
    every statement (the alternative: on the scoreable statements only). (c) The check-set zips
    went to A1 and A2 on 6 October; the sheets are expected the same evening. (d) If the check
    sheets are not back in time for the deadline of Wednesday 7 October 11:59 UTC, the plan is
    registered on time without the check-set result: the gate moves to amendment F1 and must
    pass before the literal task is handed out and before any confirmatory call, and the plan
    says so openly.
