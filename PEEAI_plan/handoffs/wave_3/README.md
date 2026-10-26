# Wave 3 handoff: evidence, reliability and the seven-minute showcase

Wave 3 is the last of the three waves ([`waves/03_evidence_showcase.md`](../../waves/03_evidence_showcase.md)).
It froze the comparison, ran it once on locked held-out cases, hardened reliability, and
prepared the showcase and a local release package.

Everything is a **fictional, local sandbox**. Nothing is hosted. The owner pushed the branch at
`26cf424`, and the build itself submitted nothing. The Wave 3b commits `1ea8ea1`, `5955243` and
`f715dfc` (policy 1.2, its freeze and lock, and its results) sit on top of `26cf424`. As of October 25, 2026, when this addendum was written, they were not
yet pushed. See "Wave 3b: version 1.2" below.

## What Wave 3 delivered, and its commits

| Task | What | Where | Commit |
| --- | --- | --- | --- |
| W3.1 Freeze | freeze.json: 76 measured files, model, caps, seeds, order, prompts, runtime | `apps/plan_b/plan_b/evaluation/manifests/freeze.json`. `docs/EVALUATION.md` "Wave 3 freeze" | `3de5962` |
| W3.1 Cases | 12 held-out cases locked in heldout.json (C01 to C08, T01 to T04) | `plan_b/scenarios/private/eval/` (evaluator-only). `manifests/heldout.json` | `49e62b5` |
| W3.2 Run | `wave3_heldout_20261025T1625Z`: campus 80/80 and pantry 40/40 recorded. Reports, figure, failure analysis | `apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/` | `c052338` |
| W3.3 Reliability | failure drills, keyboard and comprehension checks, release-check mapping | `tests/test_release_failures.py`, `tests/e2e/keyboard.py`, `docs/RELEASE_CHECKS.md` | `bb2a41f` |
| W3.4 Showcase and release | script and runbook, claims ledger, rehearsals, release package, evidence collector, this packet | this directory. `tests/e2e/rehearsal.py`. `scripts/build_release.py`. `release/manifest.json`. `scripts/collect_wave3_evidence.py`. `apps/plan_b/README.md` | `aed860c` (the app files) and `da8e7e3` (this packet). `evidence/` regenerated from a clean checkout of `3442874` |

Submission items: the deck, the poster and the Word documentation are in
[`submission/`](../../submission/), built by a concurrent worker. They are checked against this
packet in [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md). They are committed in `3442874`.

## Headline results (v1.1, the evaluation of record, from the committed run. See [`CLAIMS.md`](CLAIMS.md))

| Suite | P0 rules | P1 tool use | P2 selective | P3 verify-all |
| --- | --- | --- | --- | --- |
| Campus, met / recorded | 6/8 | 24/24 | 18/24 | 21/24 |
| Campus, cases with all trials met (of 8) | 6 | 8 | 6 | 7 |
| Pantry, met / recorded | 4/4 | 6/12 | 9/12 | 6/12 |
| Pantry, cases with all trials met (of 4) | 4 | 2 | 3 | 2 |

Across both suites:

- 0 executed violations.
- 0 unnecessary changes on the campus negative controls C02 to C04. The pantry suite has no
  negative control.
- 0 pantry conservation failures, and 0 duplicate or unauthorized credits.
- 482/482 model calls ok. Spend: $9.076770 for the reported run, and $9.642042 for the whole
  step with voided attempt 1. The ledger stands at $13.398172.

**P2 shows no consistent advantage over P1 or P0 here.**

## M3 record

The M3 criteria of `waves/03_evidence_showcase.md` ("Package and M3 exit criteria"), each with
its honest status:

| M3 criterion | Status | Evidence |
| --- | --- | --- |
| Mandatory functionality and release checks have no executed authority, stock or resource violation | **passed** | `docs/RELEASE_CHECKS.md` (every release row mapped to passing tests or N/A, the MBTA row, since MBTA was not built. Keyboard and comprehension are internal and automated only. Functional check 11 and the consumed-kits check, partly covered at the Wave 3 commit, are covered by tests added in the Wave 3b polish, and check 12 is N/A). Held-out run: 0 executed violations and 0 conservation or credit failures. Pytest and the battery in [`VERIFICATION.md`](VERIFICATION.md). Wave 3b: both version 1.2 runs also have 0 executed violations |
| Evidence is frozen, scored and honestly counted | **passed** | freeze `3de5962` and lock `49e62b5` precede the first held-out call (16:22:46Z). `verify-freeze --require-heldout` passes. The reports recompute byte for byte from the raw records (`evidence/reports/results_recomputed.json`). Every failure stays in its denominator (`FAILURES.md`). The voided attempt 1 is kept and disclosed. Wave 3b: `freeze_v1_2.json` (23:23:47Z) and `heldout2.json` (23:23:54Z) precede the first version 1.2 call (23:27:31Z), and the v1.1 record is unchanged ("Wave 3b: version 1.2" below) |
| All shown successes match state and receipts | **passed** | storyboard (32 checks of the page against fresh API reads) and the 3 rehearsals (identical receipts and final states, `evidence/rehearsal/rehearsal_report.json`). The results numbers are traced in `CLAIMS.md` |
| Limitations and partial protocols are visible | **passed** | [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). The results README "Disclosures". `SHOWCASE.md` "Do not claim" |
| Three rehearsals and the failure fallback work | **partial: automated passed, human pending** | 3/3 consecutive automated rehearsals from a clean reset, one with a forced provider failure and a successful switch to the labeled replay ([`REHEARSALS.md`](REHEARSALS.md)). **No human rehearsal has been done**. REHEARSALS.md now opens with a one-page checklist and an empty timing table for the three human runs, and `submission/rehearsal_timer.py` prints each slide's budget as the speaker presses Enter |
| The package meets confirmed requirements | **partial: requirements confirmed and met, two human checks pending** | The owner confirmed the requirements: the Project Documentation as a Word document plus the GitHub repository link, the 7-minute slide deck, and the 2-minute one-slide horizontal poster. No hosted URL or video. All three are in `submission/` and the link is in the document. The owner pushed the branch at `26cf424`, and the direct link resolved (HTTP 200, 18:20 EDT). `scripts/build_release.py` builds the allowlisted local package and checks startup, freeze and replay from it (`evidence/release/release_report.json`). **Pending, human only**: the check on the presentation machine and opening the .docx in Word. See `SUBMISSION_CHECKLIST.md` |
| Full-study label: 80 campus episodes | **met** | 80 of 80 planned campus episodes recorded in attempt 2. 0 missing, 0 aborted. 3 capped, in the denominator |
| Full-study label: 40 pantry episodes, separately | **met** | 40 of 40 planned pantry episodes recorded. 18 capped, in the denominators. Never pooled with campus |

**M3 overall: not passed yet.** What remains needs a human: the three timed rehearsals, the
check on the presentation machine and opening the .docx in Word. Everything else listed passed.

Two qualifications go with the full-study labels:

- Attempt 1 was voided for a provider rate limit, a disclosed departure from the frozen status
  rules.
- The results support descriptive counts on these 12 cases only.

## Wave 3b: version 1.2 (addendum, October 25, 2026)

This addendum adds results. It changes nothing above: the v1.1 run stays the evaluation of
record, and its 12 cases are spent.

### What changed between 1.1 and 1.2, and why

The v1.1 held-out run exposed four defects (its `FAILURES.md` and items 2, 3, 6 and 10 of
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md)). Version 1.2 (P1 `tool-use/1.2.0`, P2
`live/1.2.0`, P3 `verify-all/1.2.0`, planner `plan_b.planner/1.2.0`) changes the following.
[`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md) section
21 has each fix, its file and its test.

| v1.1 defect | What it caused in v1.1 | Version 1.2 |
| --- | --- | --- |
| A pool checked unavailable stayed a handoff option | the earliest broken stage of all six T03 P2/P3 failures | the planner fails that handoff, so the shortfall report is no longer withheld |
| Only equipment notices were material | C06 (a volunteer running late) was reachable by P1 only | a notice about a person a not-started activity needs reaches the planner as a hypothesis |
| Repeated calls on a menu already passed on | model calls spent on repeated waits, as in T04 under P1, until the 8-call cap stopped the run | the model is not called again on the same acting options in the same state |
| A choice rejected only as stale cost a new call | in T02 under P3 the retry of a stale apply needed a model call, and the cap came first | P2 and P3 re-issue the same option without a model call |
| An HTTP 429 used one of the 8 model calls | voided attempt 1 | the provider waits it out inside the call (3 s doubling to 20 s, at most 60 s) |
| The report's policy-id line was alphabetical | an erratum in the results README | P0 to P3 order |

P0's own code and ids (`rules/1.0.0`, `pantry-rules/1.1.0`) are unchanged, but P0 shares the
planner, so a P0 result under the v1.2 freeze is P0 on planner 1.2.0. The caps, the model and the
output limit are the same as in 1.1. The pre-freeze audit found five limits of 1.2 (A1 to A5,
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) item 19) and froze them as they are, because the
auditor had seen the fresh cases.

### Order of events

| Time (UTC) | Event | Commit or file |
| --- | --- | --- |
| before 23:23 | the 1.2 code and six fresh cases (C09 to C12, T05, T06), written by separate workers | `1ea8ea1` |
| 23:23:47Z | freeze of 1.2: 76 files, the same model and caps | `freeze_v1_2.json` in `5955243` |
| 23:23:54Z | lock of the fresh cases: 15 files, C10 the negative control | `heldout2.json` in `5955243` |
| 23:27:31Z | first 1.2 model call on the fresh cases. The last paid call before it was a development smoke at 22:38:39Z | the ledger |
| 23:45 to 00:09 | the post-hoc diagnostic rerun on the spent cases | `f715dfc` |

### Three result layers, always labeled

All counts are runs that met the case's outcome class over recorded runs. They are descriptive
counts, with no rate, score or significance test.

| Layer | Run | Campus P0 / P1 / P2 / P3 | Pantry P0 / P1 / P2 / P3 |
| --- | --- | --- | --- |
| (i) **v1.1 held-out, the evaluation of record** (C01 to C08, T01 to T04, 120 runs) | `wave3_heldout_20261025T1625Z` | 6/8, 24/24, 18/24, 21/24 | 4/4, 6/12, 9/12, 6/12 |
| (ii) **v1.2 on the fresh held-out set** (C09 to C12, T05, T06, 60 runs) | `wave3b_fresh_20261025T2327Z` | 3/4, 12/12, 12/12, 12/12 | 2/2, 6/6, 6/6, 6/6 |
| (iii) **v1.2 post-hoc diagnostic rerun on the spent cases, not held-out** (120 runs) | `wave3b_rerun_spent_20261025T2345Z` | 6/8, 24/24, 21/24, 24/24 | 4/4, 10/12, 12/12, 9/12 |

Layer (ii), the only held-out result of 1.2: 59 of 60 runs met their outcome. The one miss is
C11 under P0, whose frozen parser cannot read the facilitator's self-report (the same gap as C06
in v1.1). The negative control C10 had 0 unnecessary changes in 10 of 10 runs. There were 0
executed violations, 0 capped runs and 0 rate-limit waits, and every one of the 194 model calls
was answered.

Layer (iii) is diagnostic. Its 10 misses are C06 P0, C07 P0, C07 P2 in all three trials, T02 P3
in all three trials and T04 P1 in two trials. Each sits in a case and policy pair that also
missed in v1.1. The C06 failures of P2 and P3 and all nine T03 failures of v1.1 (P1, P2 and P3)
did not recur, which is consistent with the fixes, but these are the cases the fixes were written
from. C06 under P0 still misses, because P0's parser is unchanged. The rerun used `--jobs 2` and waited
out 61 HTTP 429 answers on 28 calls at no cost. 19 runs were capped, all at 8 calls. The harness
files of this run say "held-out" because a scratch case lock was the only way to run spent ids
without a code change. Its README explains every such label.

### What the numbers show and do not show

- They show that 1.2 ran the fresh cases with no executed violation and met the outcome in 59 of
  60 runs. The executor refused each of the 6 invalid pantry requests (all on T05 and T06).
- They do not show that 1.2 is better than 1.1. Layers (i) and (ii) use different cases, and
  layer (iii) reruns cases the fixes were made from.
- The fresh set is small (four campus cases and two pantry cases) and repeats the spent
  conditions: C09 is C01's, C10 is C03's, C11 is C06's, C12 is C08's, T05 is T01's and T06 is
  T03's. It tests new instances of known conditions, not new conditions. Its wording is close to
  the spent templates.
- **P2 still shows no consistent advantage.** On the fresh set P1, P2 and P3 all met every run.
  On the diagnostic rerun P2 missed C07 in three trials and P1 and P3 did not, while on the pantry
  P2 met 12 of 12 and P1 and P3 did not.
- Isolation was not perfect. The author of the fresh cases read a prose list of the planned fixes,
  but no 1.2 code. The policy author never read the cases. The pre-freeze auditor saw both, and
  therefore changed no policy behavior.

### Spend

The fresh run cost 3.608150 USD and the rerun 8.944586 USD (provider-reported). The ledger
stands at 26.433970 USD with no open reservation, under the 40 USD cap. The deliverables were
updated with no paid call.

### Where the v1.2 numbers are cited

`submission/make_results.py` reads a second and a third source and writes them under the prefixed
keys `fresh:` and `rerun:` to `slides/figures/results_numbers_v12.tex` and
`documentation/results_v12.json`. The v1.1 files it writes stay byte-identical. The claims are in
[`CLAIMS.md`](CLAIMS.md) ("Wave 3b"), the checks in [`VERIFICATION.md`](VERIFICATION.md) ("Wave
3b: version 1.2") and the decisions in [`DECISIONS.md`](DECISIONS.md) items 18 to 22.

## What remains (exact tasks, no new wave)

1. **Human rehearsals.** Three timed rehearsals of the whole talk, one with a forced failure if
   the live mode is used. Record them in `REHEARSALS.md`.
2. **Submission.** The owner first pushed the branch at `26cf424` (October 25, 2026) and the
   direct link https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b resolves (the
   repository's default branch is a different project, so the link, the document and the QR codes
   point at the branch). The requirements are confirmed (`SUBMISSION_CHECKLIST.md`). The items name
   the single author, Noctis Zhang, with no team name. Submit the three items and the link.
3. **Presentation machine.** Build or unpack the package, start `plan-b serve`, open one replay,
   and check the deck at presentation size. Open the .docx once in Word.
4. **Post-release fixes.** These four were made in Wave 3b as policy version 1.2, with a new
   freeze, six fresh held-out cases and a separately versioned result ("Wave 3b: version 1.2"
   above):
   - the unavailable-pool handoff defect
   - 429 backoff
   - P2/P3 materiality of person delays
   - the report's policy-id line order
5. **Push the Wave 3b commits.** As of October 25, 2026, before the integrate step, `1ea8ea1`, `5955243`,
   `f715dfc` and the submission commit that follows them were local. The integrate step ran the test
   battery once more on the merged tree first (`VERIFICATION.md`, "Merged-tree battery before the Wave 3b push"). After the push, open the direct link once more.

## Packet contents

- [`SHOWCASE.md`](SHOWCASE.md): the 420-second script and runbook.
- [`CLAIMS.md`](CLAIMS.md): the claims ledger.
- [`REHEARSALS.md`](REHEARSALS.md): the rehearsal record.
- [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md): the three required items.
- [`VERIFICATION.md`](VERIFICATION.md): commands and results.
- [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
- [`DECISIONS.md`](DECISIONS.md).
- `evidence/`: regenerated by `uv run python scripts/collect_wave3_evidence.py --out <empty dir>`
  from `apps/plan_b`, with no paid call. It holds `reports/` (checks, Wave 1 parity, the results
  recomputation and summary, the environment), `rehearsal/`, `browser/` (walkthrough,
  storyboard and keyboard reports) and `release/`. The copy here comes from a clean checkout of
  `3442874` (a fresh `git worktree`, `uv sync --all-groups --locked`, `npm ci`), so
  `reports/environment.json` records `app_tree_clean: true` and that git head.
