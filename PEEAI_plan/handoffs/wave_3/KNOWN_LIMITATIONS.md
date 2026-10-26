# Known limitations (Wave 3)

Sources: the results README and `FAILURES.md` of `wave3_heldout_20261025T1625Z`, the audit
reports summarized there, `apps/plan_b/docs/RELEASE_CHECKS.md` and this packet's rehearsals.
Items 19 to 27 come from Wave 3b: `apps/plan_b/docs/RUNTIME_CONTRACT.md` section 21, the
READMEs of `wave3b_fresh_20261025T2327Z` and `wave3b_rerun_spent_20261025T2345Z`, and
`plan_b/scenarios/private/eval/README_set2.md`. Items 1 to 18 describe v1.1 as it was run. Items
2, 3, 6 and 10 are the defects version 1.2 changes.

## Of the comparison

1. **One run, 12 cases, descriptive counts only.** The case is the unit: 8 campus and 4 pantry
   cases. Three trials per model policy are repeated runs, not independent units. Seeds were not
   sent to the provider, the temperature was the provider default, and the OpenRouter upstream
   route was not pinned or recorded per call. The trials are not reproducible.
2. **A frozen-code defect affected 6 pantry episodes.** A pool checked as `unavailable` stays a
   ranked, requestable handoff option for the planner and the P2/P3 menu, and the shared
   attention rule withholds the shortfall report while the handoff looks possible. This is the
   earliest broken stage of all six T03 P2/P3 failures. The results stand as measured. Fixing it
   needs a new freeze and new cases.
3. **The frozen P2/P3 materiality rule.** Only equipment notices reach the planner as
   hypotheses, so C06 (volunteer late) is reachable only by P1. P0's parser reads none of the
   held-out wording. Both were disclosed at the case lock, before the runs.
4. **Prompts differ by policy.** Only P2 and P3 have pantry partial-fulfilment guidance, so the
   pantry partial-class difference (P1 0/6, P2 3/6, P3 3/6) is not the controller's alone.
5. **Development-calibrated caps.** The caps are 8 model calls and 48 tool calls per episode,
   where the protocol proposed 16 tool calls. The cap was reached in 21 of 120 episodes and ended 15 of
   the 26 failures.
6. **No backoff on HTTP 429.** A provider error uses one of the 8 model calls immediately. This
   voided attempt 1 (OpenRouter limits this account to 20 requests per minute for this model)
   and affected no reported episode. Run one LLM episode at a time, live demos included.
7. **Attempt 1 was voided by an operator decision.** That departs from the frozen status rules.
   It was decided before attempt 2's first call. It is kept and disclosed.
8. **The held-out cases are spent.** Their designs are described by id in the committed results.
   Any later policy or prompt revision needs freshly authored and locked cases.
9. **Model requests are not stored verbatim.** Leak-freedom is shown from the agent view and the
   tool envelopes (post-run audit C, whose report is not a committed file).
10. **The report's "Policy identifiers" line is alphabetical**, not in P0 to P3 order. An erratum is
    in the results README. The line must not be copied.

## Of the showcase and release

11. **Rehearsals are automated only.** The three rehearsals ran the board path headless, with no
    speaking. **Human rehearsals are pending.** The forced failure is a closed local port, not a
    real network outage.
12. **The live model mode is not rehearsed by a human.** The stage plan uses the deterministic
    board and recorded replays. The only Wave 3 live-mode check is its failure path.
13. **Two submission checks need a human.** The requirements are confirmed (a Word document plus
    the repository link, the slide deck and the one-slide poster, with no hosted URL or video)
    and the branch is pushed. The .docx was checked only through a pandoc render, since Word is
    not available on the build machine, and the deck has not been opened on the presentation
    machine (`SUBMISSION_CHECKLIST.md`).
14. **The release package is local.** The build verifies it with the repository's Python
    environment (`plan_b` imported from the package, its dependencies from that
    environment), not with a fresh `uv sync` on another machine. Startup on the actual
    presentation machine still needs a check there.
15. **The release package withholds the held-out case files and evaluator records**
    (`runner_private/`). So `verify-freeze --require-heldout` cannot pass inside the package.
    The package checks freeze.json and the held-out public fixtures' hashes instead. The
    withholding is a property of the local package only. The held-out case files
    (`plan_b/scenarios/private/eval/`, 25 files) and the evaluator records (`runner_private/`)
    are committed on `hackathon/peeaai-plan` and public since the owner pushed it (`26cf424`). The
    packaged sanitized traces and `FAILURES.md` already show the held-out messages as delivered.
    The package withholds the `runner_private/` files themselves, but `failure_digests/*.txt` and
    `FAILURES.md`, both packaged, reproduce the failed predicate ids and details of every
    non-success episode.
    The held-out set is therefore spent: a later evaluation needs new cases.
16. **The identifier scan exempts three public strings by design:** the repository URL, the
    presenter's name and the LICENSE copyright line, which appear on the submission items, the
    checklist and the license. Every other occurrence of the local user or host name fails the
    scan. The package is selected by globbing the working tree, not git's tracked files. So an
    untracked or ignored file under an included directory would be packaged unless an exclude
    pattern matches it (for example a `.env.local`). Build the package from a fresh clone. At
    `8ea9d48` no such file exists under the included directories apart from the excluded caches
    and the built `web/dist`.
17. **Functional check 11 and the consumed-kits check are covered, with one limit.** Since the
    Wave 3b polish, `tests/test_release_failures.py` resolves every verify decision of P0 to P3
    runs to its successful check, source, entity and freshness, and holds consumed kits for a
    later slot (RELEASE_CHECKS.md). No run in those tests has a stale record, so staleness is
    checked only through the freshness formula. The tests cover the v1.1 code at `26cf424`.
18. **Not community validation.** No external participant, pilot or partner.

## Of version 1.2 (Wave 3b)

19. **Five limits of 1.2 were found before the freeze and frozen as they are** (A1 to A5,
    `RUNTIME_CONTRACT.md` section 21). A1: a person's delay hypothesis outlives a later check-in,
    so a person who reports a delay and then checks in on time still fails the availability check
    until the activity starts. A2: the declined-menu key holds no time, so a timed wake with the
    same acting options, the deadline watch included, gets the server's default record and no
    model call. A3: P1's declined-menu key uses the view after its turn. A4: a stale re-issue is
    recorded as a model choice with the earlier call's id. A5: a `Retry-After` above 20 s is cut
    to 20 s, and the 60 s bound counts waiting only. The auditor had seen the fresh cases, so a
    behavior change would have broken their isolation. C11 has A1's structure, and every C11 run
    of P1, P2 and P3 still met its goal.
20. **The fresh held-out set is small and its wording is close to the spent cases.** Four campus
    cases and two pantry cases, 60 runs. Their texts follow the spent templates closely (the
    `audit2` audit measured difflib ratios of 0.77 to 0.92), and the pantry arithmetic 40, 24, 20
    and 16 is fixed by the protocol. No string, id or world is shared. Descriptive counts only.
21. **Its conditions repeat the spent ones.** C09 is C01's condition, C10 C03's, C11 C06's, C12
    C08's, T05 T01's and T06 T03's. The fixes were written after reading the C06 and T03
    failures, so success on C11 and T06 tests new instances of known conditions, not new
    conditions. It is consistent with the fixes carrying over, not a measured effect.
22. **The isolation is not perfect.** The author of the fresh cases read a prose list of the
    planned fixes, but no 1.2 code, diff or output. The policy author never read the cases. The
    pre-freeze auditor saw both and changed no policy behavior. The evaluator note
    `README_set2.md` is outside the lock.
23. **The post-hoc rerun on the spent cases is diagnostic, and its harness files say
    "held-out".** Heldout.json no longer verifies (the second set added files) and heldout2.json
    refuses the spent ids. With no code change allowed, the rerun used a case lock written in
    scratch. So its `plan.json`, `metrics.json`, the report text and the lock's artifact name say
    held-out. Its README explains each one in its first line and a section. Never quote it as
    held-out.
24. **The rerun ran two episodes at a time.** It used `--jobs 2`, unlike v1.1 and the fresh run,
    and waited out 61 HTTP 429 answers on 28 calls, at most 21 s per call and at no cost. 5 of its
    10 misses had a wait. Sibling seeds suggest no effect, but `hk_f6k__P2__s101` diverged at the
    very call that waited. This is disclosed, not attributed.
25. **The report's column labels are fixed Wave 3 text.** On the fresh run the header "Goal
    completion C01 to C07" (written with a dash in the report) covers C09 to C11, and the other
    fixed headers cover C12, C10, T05 and T06. The rows, the case ids and `metrics.json` are
    correct. The report code was not changed.
26. **C09's recovery-delay metric records an early recovery as unrecovered.** A recovery from the
    17:10 desk status, before the 17:16 van message, is counted as unrecovered. This is inherited
    from C01's protocol definition. It does not affect the outcome class, which every C09 run met.
27. **The 1.2 numbers are not comparable with the v1.1 numbers.** The fresh cases differ from
    the v1.1 cases, and the rerun reruns the cases the fixes came from. P0 under the 1.2 freeze
    keeps its ids but runs on planner 1.2.0. No count difference against v1.1 is a measured
    improvement.
28. **App screenshots keep the board's own characters.** The final audit (audit3) found that
    the screenshots on two backup slides and in the documentation show the real board text, so
    time ranges appear with an en dash (`community_replanned.png`, `before_after.png`) and the
    replay summary in `live_card.png` contains one semicolon. The writing check reads only text
    layers, so it cannot see them. They are quoted UI, not prose, and the board strings live in
    `apps/plan_b/web/src`, outside the submission files (decision 14). Recapturing the frames
    after a UI change is left for after the deadline.
