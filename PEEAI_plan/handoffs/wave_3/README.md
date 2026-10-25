# Wave 3 handoff: evidence, reliability and the seven-minute showcase

Wave 3 is the last of the three waves ([`waves/03_evidence_showcase.md`](../../waves/03_evidence_showcase.md)).
It froze the comparison, ran it once on locked held-out cases, hardened reliability, and
prepared the showcase and a local release package.

Everything is a **fictional, local sandbox**. Nothing was pushed, hosted or submitted.

## What Wave 3 delivered, and its commits

| Task | What | Where | Commit |
| --- | --- | --- | --- |
| W3.1 Freeze | freeze.json: 76 measured files, model, caps, seeds, order, prompts, runtime | `apps/plan_b/plan_b/evaluation/manifests/freeze.json`. `docs/EVALUATION.md` "Wave 3 freeze" | `3de5962` |
| W3.1 Cases | 12 held-out cases locked in heldout.json (C01 to C08, T01 to T04) | `plan_b/scenarios/private/eval/` (evaluator-only). `manifests/heldout.json` | `49e62b5` |
| W3.2 Run | `wave3_heldout_20261025T1625Z`: campus 80/80 and pantry 40/40 recorded. Reports, figure, failure analysis | `apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/` | `c052338` |
| W3.3 Reliability | failure drills, keyboard and comprehension checks, release-check mapping | `tests/test_release_failures.py`, `tests/e2e/keyboard.py`, `docs/RELEASE_CHECKS.md` | `bb2a41f` |
| W3.4 Showcase and release | script and runbook, claims ledger, rehearsals, release package, evidence collector, this packet | this directory. `tests/e2e/rehearsal.py`. `scripts/build_release.py`. `release/manifest.json`. `scripts/collect_wave3_evidence.py`. `apps/plan_b/README.md` | uncommitted at writing. The integrate step commits it |

Submission items: the deck, the poster and the Word documentation are in
[`submission/`](../../submission/), built by a concurrent worker. They are checked against this
packet in [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md).

## Headline results (from the committed run. See [`CLAIMS.md`](CLAIMS.md))

| Suite | P0 rules | P1 tool use | P2 selective | P3 verify-all |
| --- | --- | --- | --- | --- |
| Campus, met / recorded | 6/8 | 24/24 | 18/24 | 21/24 |
| Campus, cases with all trials met (of 8) | 6 | 8 | 6 | 7 |
| Pantry, met / recorded | 4/4 | 6/12 | 9/12 | 6/12 |
| Pantry, cases with all trials met (of 4) | 4 | 2 | 3 | 2 |

Across both suites:

- 0 executed violations.
- 0 unnecessary changes on the negative controls C02 to C04.
- 0 pantry conservation failures, and 0 duplicate or unauthorized credits.
- 482/482 model calls ok. Spend: $9.076770 for the reported run, and $9.642042 for the whole
  step with voided attempt 1. The ledger stands at $13.398172.

**P2 shows no consistent advantage over P1 or P0 here.**

## M3 record

The M3 criteria of `waves/03_evidence_showcase.md` ("Package and M3 exit criteria"), each with
its honest status:

| M3 criterion | Status | Evidence |
| --- | --- | --- |
| Mandatory functionality and release checks have no executed authority, stock or resource violation | **passed** | `docs/RELEASE_CHECKS.md` (every release row mapped to passing tests or N/A, the MBTA row, since MBTA was not built. Keyboard and comprehension are internal and automated only. Functional check 11 and the consumed-kits check are partly covered, and check 12 is N/A). Held-out run: 0 executed violations and 0 conservation or credit failures. Pytest and the battery in [`VERIFICATION.md`](VERIFICATION.md) |
| Evidence is frozen, scored and honestly counted | **passed** | freeze `3de5962` and lock `49e62b5` precede the first held-out call (16:22:46Z). `verify-freeze --require-heldout` passes. The reports recompute byte for byte from the raw records (`evidence/reports/results_recomputed.json`). Every failure stays in its denominator (`FAILURES.md`). The voided attempt 1 is kept and disclosed |
| All shown successes match state and receipts | **passed** | storyboard (32 checks of the page against fresh API reads) and the 3 rehearsals (identical receipts and final states, `evidence/rehearsal/rehearsal_report.json`). The results numbers are traced in `CLAIMS.md` |
| Limitations and partial protocols are visible | **passed** | [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). The results README "Disclosures". `SHOWCASE.md` "Do not claim" |
| Three rehearsals and the failure fallback work | **partial: automated passed, human pending** | 3/3 consecutive automated rehearsals from a clean reset, one with a forced provider failure and a successful switch to the labeled replay ([`REHEARSALS.md`](REHEARSALS.md)). **No human rehearsal has been done**. Three timed human rehearsals remain for the owner |
| The package meets confirmed requirements | **partial: local package built, platform requirements pending** | `scripts/build_release.py` builds the allowlisted package, then checks startup, freeze and replay from it (`evidence/release/release_report.json`). **The course platform's submission requirements have not been confirmed** (format, size, a hosted URL or video). See `SUBMISSION_CHECKLIST.md` |
| Full-study label: 80 campus episodes | **met** | 80 of 80 planned campus episodes recorded in attempt 2. 0 missing, 0 aborted. 3 capped, in the denominator |
| Full-study label: 40 pantry episodes, separately | **met** | 40 of 40 planned pantry episodes recorded. 18 capped, in the denominators. Never pooled with campus |

**M3 overall: not passed yet.** Requirements remain for the owner: the human rehearsals, the
confirmed platform requirements and the check on the presentation machine. Everything else listed
passed.

Two qualifications go with the full-study labels:

- Attempt 1 was voided for a provider rate limit, a disclosed departure from the frozen status
  rules.
- The results support descriptive counts on these 12 cases only.

## What remains (exact tasks, no new wave)

1. **Human rehearsals.** Three timed rehearsals of the whole talk, one with a forced failure if
   the live mode is used. Record them in `REHEARSALS.md`.
2. **Submission.** Push `hackathon/peeaai-plan` to https://github.com/nocdoggo/COLLIE, then open
   the direct link https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b (the repository's default branch is a different project, so the link,
   the document and the QR codes point at the branch). The items name the single
   author, Noctis Zhang, with no team name. Check each item's format against the course platform. Submit.
3. **Presentation machine.** Build or unpack the package, start `plan-b serve`, open one replay,
   and check the deck at presentation size. Open the .docx once in Word.
4. **Post-release fixes,** each needing a new freeze, new held-out cases and a separately
   versioned comparison, because these cases are spent:
   - the unavailable-pool handoff defect
   - 429 backoff
   - P2/P3 materiality of person delays
   - the report's policy-id line order

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
  storyboard and keyboard reports) and `release/`.
