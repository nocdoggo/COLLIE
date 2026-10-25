# Known limitations (Wave 3)

Sources: the results README and `FAILURES.md` of `wave3_heldout_20261025T1625Z`, the audit
reports summarized there, `apps/plan_b/docs/RELEASE_CHECKS.md` and this packet's rehearsals.

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
13. **The course platform's requirements are unconfirmed:** format, size, a hosted URL or
    video, and team names (`SUBMISSION_CHECKLIST.md`).
14. **The release package is local.** The build verifies it with the repository's Python
    environment (`plan_b` imported from the package, its dependencies from that
    environment), not with a fresh `uv sync` on another machine. Startup on the actual
    presentation machine still needs a check there.
15. **The release package withholds the held-out case files and evaluator records**
    (`runner_private/`). So `verify-freeze --require-heldout` cannot pass inside the package.
    The package checks freeze.json and the held-out public fixtures' hashes instead. The
    withholding is a property of the local package only. The held-out case files
    (`plan_b/scenarios/private/eval/`, 25 files) and the evaluator records (`runner_private/`)
    are committed on `hackathon/peeaai-plan` and become public when the branch is pushed. The
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
17. **Functional check 11 is partly covered.** No runtime test resolves every verify decision to
    a matching successful check. The consumed-kits-in-a-later-slot check is partly covered too
    (RELEASE_CHECKS.md).
18. **Not community validation.** No external participant, pilot or partner.
