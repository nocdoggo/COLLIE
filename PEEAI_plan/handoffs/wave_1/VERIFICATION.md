# Verification record

This record covers what was run, where, and with what result. Counts come from
`evidence/reports/checks.json`, `evidence/screenshots/walkthrough_report.json` and `manifest.json`.
Nothing is reported as passing unless it ran.

## 1. Clean-checkout reproduction (the M1 run)

The run used a fresh detached worktree at `afe502e`, the final implementation commit. It was
made on 2026-10-24:

```bash
git worktree add --detach <scratch>/clean_checkout afe502e
cd <scratch>/clean_checkout/apps/plan_b
uv sync --all-groups --locked                      # fresh .venv in the worktree
(cd web && npm ci)                                 # fresh node_modules (0 vulnerabilities)
uv run python scripts/collect_evidence.py --out <empty scratch dir>
# then, in the main repository (HEAD = afe502e):
uv run python scripts/write_manifest.py            # reads PEEAI_plan/handoffs/wave_1/evidence
```

`plan_b` was imported from the worktree's own `.venv`. `environment.json` records `git_head =
afe502e…` and `app_tree_clean = true`. The collector ran every check below, printed `all checks
passed` in 3 min 54 s, and left no temporary directory behind. Its output directory then
replaced `evidence/`. `write_manifest.py` printed `M1 passed_on_recorded_automated_checks`.

### Environment

| | |
| --- | --- |
| Python | CPython 3.12.11 (app `.venv`, separate from the COLLIE research environment) |
| uv | 0.9.18 |
| Node / npm | v22.19.0 / 11.15.0 |
| SQLite | 3.50.3 |
| Browser | Playwright 1.64.1, headless Chromium |
| OS | Linux 5.15.0-43-generic x86_64, glibc 2.35 |
| Lockfiles at `afe502e` | `apps/plan_b/uv.lock` `95b8337f…8803`, `apps/plan_b/web/package-lock.json` `b4f2e1e7…d7e` |
| Migrations | `0001_initial.sql` `9d22b458…ab1`, `0002_scheduled_actions.sql` `935784e8…3c5`, `0003_history_guards.sql` `4bd0ccf0…da1` |

The full hashes, including the fixtures and the 11 planning examples, are in
`evidence/reports/fixture_hashes.json` and `manifest.json`.

### Commands and results

The working directory is relative to the worktree root. A `<work>` path is the collector's
temporary directory, which it deletes at the end.

| # | Check | Working dir | Command | Exit | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | Lint | `apps/plan_b` | `uv run ruff check .` | 0 | All checks passed |
| 2 | Format | `apps/plan_b` | `uv run ruff format --check .` | 0 | 74 files already formatted |
| 3 | Types | `apps/plan_b` | `uv run mypy` | 0 | no issues in 51 source files |
| 4 | Web typecheck | `apps/plan_b/web` | `npm run typecheck` | 0 | `tsc --noEmit` clean |
| 5 | Web build | `apps/plan_b/web` | `npm run build` | 0 | JS 276.42 kB (83.43 kB gzip) |
| 6 | Python tests | `apps/plan_b` | `uv run pytest -o addopts= -q -p no:cacheprovider --junitxml=…` | 0 | **455 passed, 0 skipped, 0 failed** (1 warning: Starlette's httpx deprecation) |
| 7 | Web tests | `apps/plan_b/web` | `npm test` | 0 | **362 passed**, 0 failed |
| 8 | Web boundary lint | `apps/plan_b/web` | `npm run lint` | 0 | 21 read-only modules, 34 sources, dist bundle scanned |
| 9 | Development cases | `apps/plan_b` | `uv run plan-b run-case all --db <work>/runs.sqlite3 --out <work>/out` | 0 | 5/5 `matches_expectation=True`, `violations=0` |
| 10 | Rejections | `apps/plan_b` | `uv run plan-b demo-rejections --db <work>/demo.sqlite3 --out <work>/out` | 0 | all 20 steps got their expected result; 7 rejected receipts, 2 attempts without receipt, `violations=0` |
| 11–16 | Trace integrity | `apps/plan_b` | `uv run plan-b verify-trace <work>/out/traces/<trace>.json` | 0 | dev01, dev02, dev04, dev05, dev06 and rejected_actions are all `intact` |
| 17 | Browser walkthrough | `apps/plan_b` | `uv run python tests/e2e/walkthrough.py --out <work>/shots` | 0 | **41/41 checks passed** |
| 18 | Evidence identifier scan | `apps/plan_b` | the collector's own scan of every text file it wrote | 0 | 20 text files: no host name, user name, git email or local path |

pytest runs after the web build, so `test_browser_bundle_carries_no_private_data` scans the real
bundle. The JUnit report is `evidence/reports/pytest_junit.xml`. Its hostname is replaced with
`<host>` and its timestamp is removed. Local paths in every evidence file are written as `<repo>`,
`<evidence>`, `<work>` or `~`.

### Development case outcomes (row 9)

| Case | goal_complete | infeasibility_reported | applied plans | committed | violations | coordinator tool calls |
| --- | --- | --- | --- | --- | --- | --- |
| dev01 (genuine delay, ETA 17:25 → free swap) | true | false | 1 | $0 | 0 | 22 |
| dev02 (long delay, ETA 17:45 → hold, ask, authorize, paid backup) | true | false | 1 | $35.00 | 0 | 30 |
| dev04 (false alarm + stale P09 reminder + duplicate) | true | false | 0 | $0 | 0 | 24 |
| dev05 (cancelled, backup booked elsewhere: impossible) | **false** | **true** | 0 | $0 | 0 | 19 |
| dev06 (status service down) | true | false | 1 | $0 | 0 | 21 |

`rejected_attempts_without_receipt` is 0 in every public report. Runs no longer end with a
rejected read at the hard end (DECISIONS D9b). The tool-call column counts every coordinator call
in the episode. Each policy run is bounded to 16; there is no per-episode cap yet
(KNOWN_LIMITATIONS). The public summaries are `evidence/reports/dev0*_outcome.public.json`. The
evaluator-side reports, which hold the private predicates, are `evidence/runner_private/`.

### Rejection steps (row 10)

`evidence/reports/rejected_actions_steps.json` lists 20 steps, each with its expected and actual
result. These are the rejection steps:

| Step | Code | Receipt |
| --- | --- | --- |
| Paid booking beyond the zero committed limit | `BUDGET_EXCEEDED` | rejected receipt |
| Forged candidate and report pairing | `CANDIDATE_REPORT_MISMATCH` | rejected receipt |
| Same idempotency key, different body | `IDEMPOTENCY_CONFLICT` | none |
| Applying a candidate evaluated before the hold | `REVISION_CONFLICT` | rejected receipt |
| Converting the hold while the limit is 0 | `BUDGET_EXCEEDED` | rejected receipt |
| A participant checking in for another role | `SCOPE_VIOLATION` | rejected receipt |
| A participant changing a grant | `GRANT_REQUIRED` | none |
| A duplicate check-in | `DUPLICATE_CHECK_IN` | rejected receipt |
| Releasing a converted hold | `HOLD_CONVERTED` | rejected receipt |

Three steps succeed without widening authority or adding effects:

* A message that claims organizer authority is stored as data, and no grant changes.
* After the organizer's authorization, exactly one paid booking is made.
* An identical retry replays the original receipt (`replayed_receipt: true`).

### Browser walkthrough (row 17)

The walkthrough is Playwright with headless Chromium against `plan-b serve` on a free port, with
a fresh state directory that it deletes afterwards. It uses the built bundle from row 5. Each
check reads the live page or a fresh API request, never a screenshot. It executes the whole
minimum visible workflow of `waves/01_foundation.md`. `walkthrough_report.json` tags each check
with its workflow step.

| Step | What it shows | Checks |
| --- | --- | --- |
| 1 | Load the fixture into a clean sandbox; show goal, schedule, budget and authority | 1–4 |
| 2 | A participant submits an update through `submit_observation`; the board shows its source, times and affected entity | 17–19 |
| 3 | A scoped status query, with the actual result, including the unavailable outcome | 9, 34 |
| 4 | Alternatives and assumptions from `evaluate_candidates`; the preview reserves nothing | 10, 11 |
| 5 | Apply a checked plan and book with authorization; show the receipt and the next state read | 7, 8, 36 |
| 6 | Advance the clock: readiness, completion, and the impossible case's visible failure | 14, 15, 20, 21, 33 |
| 7 | Export, reset to a new episode, then play the visible trace under *Recorded replay* | 22–32 |

All 41 checks:

1. header shows product, sandbox and mode labels
2. scenario clock 16:40 in America/New_York
3. goal and public deadline visible
4. schedule, modeled budget and authority envelope visible (fresh API read)
5. focused control has a visible focus outline
6. keyboard Tab + Enter operated a control
7. fresh API read: swap applied at revision 4→5
8. receipt shown on the board matches the API receipt
9. status query result shown with its reported ETA
10. alternatives show feasible and rejected candidates
11. evaluating alternatives reserved nothing (fresh API read)
12. participant tab is a distinct scoped session
13. no token rendered in the page
14. moderator tab shows the facilitator without a check-in before it
15. moderator tab observes the persisted check-in by polling
16. duplicate check-in shown as rejected
17. participant update recorded through submit_observation (fresh API read)
18. participant tab confirms its update with the API receipt
19. board shows the update's source, times and affected entity
20. all required activities completed (fresh API read)
21. arrival observed before demonstrations started
22. the executed run is exported as a trace on the server
23. reset created a clean episode
24. old participant session rejected after reset
25. replay shows the persistent Recorded replay label
26. replay integrity verified in the browser
27. replay opened after the reset shows the pre-reset episode
28. replay labels recorded results as not re-queried
29. replay plays the visible trace through to its last frame
30. replayed final state shows every receipt of the executed run
31. replay issued no POST/PUT/DELETE requests
32. replay created no action in the live episode
33. impossible case stays visibly unsuccessful
34. status query shows the unavailable outcome as it is (dev06)
35. organizer sees the authorization request
36. authorized paid backup booking committed once
37. no horizontal overflow at 1920 px
38. no horizontal overflow at 1280 px
39. no page errors
40. no join code or session token in the visible text at any screenshot
41. every step of the minimum visible workflow ran with passing checks

Check 15 reads the facilitator's own Role readiness item. It reads "No check-in yet" before the
check-in (check 14) and "Checked in … (participant session)" within the polling interval after
it. Every check's recorded detail quotes the whole lines it relied on.

The 21 screenshots are in `evidence/screenshots/`. Every screenshot masks the join links
(`[data-join-link]` and any link into `#/join/`), and the panel itself shows only a 4-character
prefix of a code. The collector re-encodes the screenshots as 256-colour PNGs (median cut, no
dithering), which keeps the screenshots directory at about 7.5 MB. The evidence directory as a
whole is about 17 MB, most of it the four traces. The pass/fail results above do not depend on
the images.

## 2. M1 exit criteria → recorded outcomes

The criteria are from `PEEAI_plan/waves/01_foundation.md`. Test paths are relative to
`apps/plan_b/tests/`. All of these ran in rows 6, 7, 9, 10 or 17 above.

| M1 check | Recorded outcome | Tests and evidence |
| --- | --- | --- |
| Genuine disruption | **Pass.** dev01 applies the swap and completes every activity, with receipts matching the final state. | `test_dev_cases.py::test_dev01_genuine_disruption_swap`, `test_campus_workflow.py::test_genuine_disruption_recovers_through_state_transitions`; walkthrough 7, 8, 20, 21; `traces/dev01_trace.json` |
| Stale or duplicate update | **Pass.** dev04's stale P09 reminder and its copies change nothing. The same notices arriving after dev02's paid booking preserve the commitment, its hold and the applied plan. Duplicates cause no second mutation. | `test_dev04_stale_and_duplicate_notices_change_nothing`, `test_evidence_gaps.py::test_stale_and_duplicate_notices_after_a_paid_commitment_preserve_it`, `test_stateful_tools.py::test_duplicate_check_in_and_duplicate_source_record`, `test_older_status_does_not_revert_observed_arrival`; walkthrough 16 |
| Impossible case | **Pass.** dev05 reports infeasibility with the blocking constraints. Nothing is spent or committed, and the failures stay visible. | `test_dev05_impossible_recovery_is_visibly_unsuccessful`, `test_dev05_narration_does_not_claim_success_after_failures`, `test_scoring.py::test_infeasible_expectation_matches_without_success`; walkthrough 33; `traces/dev05_trace.json` |
| Authority boundary | **Pass.** Participant text, offers (including parsed ones) and injected instructions cannot widen a grant or impersonate the organizer. Forged identity and cross-role actions are refused. | `test_message_instructions_do_not_change_permissions`, `test_body_forged_identity_rejected`, `test_participant_cannot_change_another_role`, `test_cross_event_and_cross_actor_access`, `test_unauthorized_receipt_lookup`, `test_revoked_and_expired_grants`, `test_evidence_gaps.py::test_participant_offer_claiming_organizer_authority_is_stored_as_data`, `::test_policy_does_not_act_on_a_participant_offer`, `::test_policy_does_not_act_on_a_parsed_participant_offer`; rejection steps; `traces/rejected_actions_trace.json` |
| Transaction behavior | **Pass.** A stale revision is rejected. An identical retry returns one receipt, and a conflicting payload is rejected. Concurrent holds cannot overallocate. A late rejection inside a handler rolls back that handler's writes. | `test_stale_revision_rejected_without_mutation`, `test_identical_retry_returns_original_receipt`, `test_same_key_different_payload_rejected`, `test_competing_reservations_cannot_overallocate`, `test_concurrent_holds_cannot_exceed_reserved_limit`, `test_restart_preserves_state_receipts_and_idempotency`, `test_audit_core.py` (handler rollback); `test_receipt_consistency.py` |
| Time and holds | **Pass.** Expiry and release restore capacity and funds exactly once, and an expired hold cannot support a commit. | `test_exact_hold_expiry_boundary`, `test_release_and_expiry_never_double_refund`, `test_hold_expiring_between_evaluation_and_apply`, `test_hold_after_commitment_cutoff_rejected`, `test_conversion_charges_once_and_survives_former_cutoff`, `test_audit_core.py` (public checks before the steward) |
| Failure reconciliation | **Pass.** A response lost after commit is reconciled by its original key, with no duplicate reservation. | `test_lost_response_after_commit_is_reconciled`, `test_receipt_lookup_not_found_is_not_failure` |
| Readiness and scoring | **Pass.** An ETA alone cannot start an activity, and a start before arrival is scored as a violation. | `test_campus_workflow.py::test_eta_alone_cannot_start_demonstrations`, `test_missing_participant_readiness_prevents_execution`, `test_scoring.py::test_equipment_start_before_arrival_and_overspend_are_violations`, `test_latest_checkin_by_the_start_decides_presence`, `test_audit_domain.py` (scoring through the adapter) |
| Isolation and reset | **Pass.** Policy and planner inputs, HTTP payloads, the bundle and traces carry no private fields. Reset clears the episode's holds, memory, receipts and commitments. | `test_runner_isolation.py` (all), `test_api.py::test_http_payloads_carry_no_private_case_data`, `test_clock_and_reset_isolate_episodes`; walkthrough 13, 23, 24, 40 |
| UI and replay | **Pass.** The displayed receipts match the API. The sanitized trace replays read-only, after a reset, and the browser reports it consistent with its own (unsigned) hashes. | `test_trace_is_sanitized_intact_and_matches_the_run`, `test_replay_endpoints_perform_no_writes`, `test_trace_verifier.py`, web `tests/integrity.test.ts`, `tests/replay.test.ts`; walkthrough 8, 22–32; rows 11–16 |

The evidence the wave plan requires is present:

* fixture hashes: `reports/fixture_hashes.json`;
* successful traces: dev01, dev02;
* a rejected-action trace: `rejected_actions_trace.json`;
* an impossible-case trace: dev05;
* this completion record.

`manifest.json` computes `m1.status = passed_on_recorded_automated_checks` from them. That status
requires all of these:

* every recorded check exited 0;
* the walkthrough is among the checks and all its checks passed;
* the required evidence is present;
* the evidence came from a clean app tree;
* `apps/plan_b` is unchanged between the evidence commit and HEAD.

The status is self-assessed, and the independent audit of this final state is pending.

## 3. Review and audit history

All reviewers were independent: none had written the code under review. Each worked read-only
and reproduced its findings against the real executor and store.

| Round | Scope | Result | Disposition |
| --- | --- | --- | --- |
| Review 1 | Five areas: state and transactions, clock and execution, planner and policy, isolation and API, web honesty. Every finding was adversarially verified. | 33 findings: 14 confirmed, 17 partial, 2 refuted | Every confirmed and partial finding fixed, with tests in `test_review_fixes.py` |
| Review 1 re-check | All 33 items re-checked by a fresh verifier | 28 closed (including the 2 refuted findings, which were changed anyway), 4 partly closed, 1 accepted limitation (`planner_policy-03`); 7 regressions found | The 7 regressions fixed |
| Review 2 | Re-verification of those fixes, plus an 80-message parser corpus | 4 closed and 2 partly closed. One new regression: `/api/moderator/run` returned 500 in a reset race. The polarity cues wrongly asserted 19 of 40 non-asserted messages. | Race and date bounds fixed. The parser redesigned as strict whole-sentence forms (`rules-parser/1.2.0`). Tests in `test_review_fixes_round3.py`, `test_parser.py`, `test_policy_unit.py`. |
| Review 3 | Strict-forms parser, implemented and then independently verified | 0 of the 80 messages wrongly asserted. One high and one medium regression in verify-only handling. | Fixed. The final rule is settled in section 4. |
| Verify-only rule | Three candidate rules, two independent verifiers and a 3,131-variant scenario comparison | see section 4 | Committed as `3028cbf`; tests in `test_verify_only_end_to_end.py` |
| Wave 1 audit | Read-only audit in five areas: requirements and fixture fidelity, invariants, compliance, web and replay, documentation | 45 verified findings: 0 high, 6 confirmed medium, the rest low | All resolved in `afe502e` and in this packet (below) |
| Audit fixes | Four implementation rounds, each followed by independent verifiers who tried to break the fixes | Round 1 closed the findings. Rounds 2–4 closed what each round's verifiers found, all low or medium hardening of the boundary lint, the trace verifiers and the evidence tooling. | Each change has regression tests. The lint's remaining evasions require deliberately obfuscated code; they are documented and pinned by tests (KNOWN_LIMITATIONS). |

How the 45 audit findings were resolved:

* **Code, with tests** (commit `afe502e`):
  * M1-INV-01: the steward is consulted last;
  * M1-INV-02: handler rollback;
  * M1-INV-03: no-change receipts and the consistency rule;
  * REQ-01: loading validation;
  * REQ-03 and F3: scoring through the adapter;
  * REQ-11: status lineage;
  * REQ-12: no policy wake after close;
  * F9: history guards;
  * WEB-1: the AST boundary lint;
  * WEB-2: integrity UI;
  * WEB-3: equivalent verifiers;
  * WEB-4 and REQ-02: walkthrough coverage;
  * WEB-5: export policy id;
  * C1: join codes;
  * C3: hostname;
  * C4: walkthrough temp directory.
* **Missing tests added:** REQ-06 and F4 (alternate formats); REQ-07 (stale notices after a commitment, participant offers).
* **Documentation**, in the contract, this packet and the READMEs:
  * C2, REQ-09 and F5: lockfile hashes, now taken from the evidence;
  * C5, REQ-10 and F11: `manifest.json` and this section;
  * C6: sizes;
  * C7: neutral wording;
  * C8: the `runner_private` wording;
  * F1: logging guarantees;
  * F2: the tool budget;
  * F6: 20 steps;
  * F7: paths;
  * F8: button labels;
  * F10: cross-references;
  * F12: the round-1 counts above;
  * F13: private-input readers;
  * F14: version literals and the staff role;
  * F15: the replay directory;
  * F16: Node 22.18 and `--locked`;
  * REQ-04: grant_id and expected_revision;
  * REQ-05: the failure vocabulary;
  * REQ-08: dev02 described as a long delay.
* **Repository hygiene:**
  * C9: the `.gitignore` order, fixed in `8b7aea3`;
  * C4: the scratch worktree was removed after this run. The local Codex checkpoint ref is left in place and documented in AUDIT_GUIDE.

The accepted limitations from the review are recorded in KNOWN_LIMITATIONS.md under "Actual
defects": `planner_policy-03`, hold renewal near expiry, part of `web-2`, and authentication
failures not persisted.

## 4. Verify-only rule: measured comparison

The rule decides when the policy spends a 2-minute status query on a supplier notice in
unsupported wording. Three rules ran over the same catalogue of 3,131 scratch scenario variants:

* supplier chatter streams in eight configurations: dev01, dev04, dev05, dev06, the shipped dev02,
  and three dev02 variants with a shorter hold lifetime and a different organizer latency;
* status outages after a successful check;
* participant spam;
* genuine notices, sent alone and after chatter;
* copies and re-sends;
* long streams.

A scratch harness, which is not part of the app, ran each variant through the real runner,
executor and store. It recorded whether the goal completed and which projector queries were
made. It copies the private cases into a temporary directory and never edits the repository.

| Suite (variants) | Freshness skip (`25363fb`) | Every notice checked after the decision | Final rule (`3028cbf` = `afe502e`) |
| --- | --- | --- | --- |
| chatter (1,280) | 1,073 complete, 2,365 queries | 1,033, 4,395 | 1,074, 3,289 |
| outage after a check (1,736) | 1,440, 2,220 | 1,340, 6,334 | 1,440, 3,830 |
| participant spam (24) | 14, 63 | 15, 69 | 15, 69 |
| genuine notices (75) | 2, 151 | 59, 203 | 59, 184 |
| status service down (3) | 1, 12 | 1, 12 | 1, 12 |
| copies and re-sends (2) | 2, 4 | 2, 7 | 2, 7 |
| long streams (6) | 6, 51 | 6, 85 | 6, 81 |
| shipped cases (5) | 4, 6 | 4, 6 | 4, 6 |

Against the freshness skip, the final rule loses no variant and recovers 59: 57 genuine-notice
cases, one chatter case and one participant case. The middle rule lost 145. The shipped dev05 is
impossible by design, and many variants are made infeasible on purpose, so the counts are not
success rates. The final code at `afe502e` gives the same outcome and the same query times as
`3028cbf` on every one of the 3,131 variants: the audit fixes changed no policy behavior. A
fourth rule was rejected earlier by two independent verifiers: skip when a check completed after
the notice. It reopened the chatter failure in 40 of 160 shipped-dev02 patterns.

## 5. Not run, or not verified

* **Other browsers.** Firefox and Safari were not run; only Chromium was.
* **Screen readers.** No session was run. Keyboard operation and visible focus were checked by
  automation (walkthrough 5, 6).
* **Human comprehension and usability (product P1).** Not tested with people.
* **Python 3.11.** Declared in `requires-python`, but every check ran on 3.12.11.
* **Live services.** The application made no LLM, MBTA or other network call. No check read
  `.local/keys/`. The one OpenRouter key check is described in WAVE_2_HANDOFF.md, and it does not
  pass G-LLM.
* **Load and production hardening.** Out of scope (single process, single SQLite file).
* **Held-out evaluation cases C01–C08.** Not run. They belong to Wave 3, and the development
  cases say nothing about them.
