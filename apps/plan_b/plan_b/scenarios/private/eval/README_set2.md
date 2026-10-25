# Fresh held-out set for version 1.2 (evaluator only)

Do not open this note or the `set2/` directories in a policy, a prompt, a retrieval index, the
browser bundle or any public report. They hold six fresh held-out cases for a small new check
of policy version 1.2: the campus cases C09 to C12 and the pantry cases T05 and T06. The twelve
Wave 3 cases (C01 to C08, T01 to T04) are spent. Their v1.1 run (`wave3_heldout_20261025T1625Z`)
stays the evaluation of record. Any later run on them is a post-hoc diagnostic rerun, never a
held-out result.

Each case is a private runner case `set2/<ref>.json` (`plan_b.private_case`) plus its evaluator
data `set2/<ref>.eval.json` (`plan_b.eval_case`, `run.EvalCase`). The agent-visible public
fixtures are in `../../public/eval/set2/`. They are opaque: no case id, condition word or
expectation appears in any identifier or text an agent can see.

## How the set was made

* **Who and when.** The Wave 3b `cases2` worker authored the set on 2026-10-25 between 18:25
  and 19:30 EDT, while the `fix2` worker built version 1.2. The `fix2` worker was told never to
  open these files.
* **Isolation.** The author changed no code and saw no version 1.2 code, diff or policy
  output. The author did read the `fix2` worker's prose brief, which lists the defects 1.2 was
  to fix (an unavailable pool kept as a handoff option, a person's delay not treated as
  material, repeated model calls, the 429 backoff, the report's id order). The audit of
  2026-10-25 (`audit2`) found this in the author's log. The case conditions were fixed in
  advance by the protocol rows below, which limits what the brief could shape.
  * The author read the frozen code at HEAD `26cf424`.
  * The author read the spent cases (to keep the format) and the Wave 3 documents.
  * Some working-tree reads were greps of files that `fix2` was already editing
    (`domain/constraints.py`, `agent/menu.py`, `agent/orchestrator.py`,
    `domain/adapters/pantry.py`). Every line those greps showed is identical to its line at
    HEAD (only line numbers had moved), so no changed line was seen.
* **Proofs.** The proofs were run on a clean `git archive` of HEAD `26cf424`, plus these files.
* **No policy run.** No compared policy (P0 to P3) was run on these cases before the lock.
* **Conditions.** Each case keeps the preregistered condition of its protocol row in
  `PEEAI_plan/08_evaluation.md`: C09 is the C01 condition, C10 is C03, C11 is C06, C12 is C08,
  T05 is T01 and T06 is T03.
* **Negative control.** C10 is the designated negative control.

| Ref | Id | Fixture | Condition | Class | What the world does |
| --- | --- | --- | --- | --- | --- |
| `ev_r4h` | C09 | `fixture_w5` | Genuine projector delivery delay | goal | Lab order desk: ETA 18:08 (delayed), its slot is 18:00. Van notice at 17:16. Checked in at 18:07. Recovery: shift the demonstrations +10 (18:10 to 18:30), or book the spare for 18:00 with approval before its 17:35 cutoff. The swap does not work |
| `ev_j8p` | C10 | `fixture_w5` | Plausible false delivery warning | goal, negative control | Front desk relays an anonymous call at 17:21 ("6:20 or later"). Order desk on schedule, ETA 17:48 (records of 17:09 and 17:29). Checked in at 17:47 |
| `ev_w2n` | C11 | `fixture_w5` | Volunteer late, with a subsequent check-in | goal | The facilitator (first slot, 17:40) self-reports a bus taken out of service at 17:24, arrival about 17:55, and checks in at 17:55. Recovery: the swap |
| `ev_s6d` | C12 | `fixture_h3` | No feasible recovery under the authorized constraints | infeasible | Order Q81 withdrawn (lamp test). The spare is free and affordable, but it must be confirmed 75 minutes before use, and the latest start (18:10) has a 16:55 cutoff, before the 17:10 opening |
| `ev_y3k` | T05 | `fixture_p6` | Primary shipment late, alternate 16 usable | target | LT62 ETA 11:35. Loft desk available. One crew handoff (4 minutes, inside 9:40 to 10:04). 40 by 10:50 |
| `ev_u5b` | T06 | `fixture_p6` | Stale or wrong-source receipt claim, authoritative arrival after the deadline | partial | Loft desk declines. LT62 ETA 11:02 (deadline 10:50). The sales rep claims delivery at 9:49. A portal proof of delivery dated 8:05 a.m. arrives at 9:57. The loading door signs for LT62 at 11:02. Limit 24, deficit 16 |

## Fixtures

The public fixtures keep the event models of the development and spent fixtures and change
everything else: date, room, people, principals, grants, sources, orders, shipment, prices,
terms and times.

* **`fixture_w5` (C09 to C11).** A Gallery room evening on 2026-12-03, from 17:30 to 18:40,
  opening at a clock of 17:10.
  * The program order is new: the skills exchange runs first (17:40 to 18:00), then the
    demonstrations (18:00 to 18:20). The closing is fixed at 18:30, so the plan has a 10-minute
    slack. That makes a shift a real recovery, which no spent case needs.
  * Shifts are +5 and +10 minutes for both middle activities.
  * The spare projector costs 3500 cents. Its free hold lasts 15 minutes and it must be
    confirmed 25 minutes before use.
  * The event budget is 9000 cents and the coordinator may reserve 3500.
  * The order desk is fresh for 15 minutes and the spare desk for 25.
  * The organizer answers in 4 minutes.
* **`fixture_h3` (C12).** The same room one week later (2026-12-10). The only change is a
  75-minute confirmation cutoff for the spare, because its cart comes from the main campus.
* **`fixture_p6` (T05, T06).** A lower hall morning on 2026-12-05.
  * The table runs from 10:10 to 10:50 (deadline inclusive) and the hard end is 11:10.
  * The handoff window is 9:40 to 10:04 and the crew answers in 4 minutes.
  * A loft hold lasts 20 minutes and a main rack hold 35.
  * The ids are new: `main_rack`, `loft_rack`, `table_crew`, `kits_morning` and shipment
    LT62.
  * It keeps the protocol's 40, 24, 20, 16 arithmetic (target 40, 24 on the rack, LT62 of 20
    expected, 16 on the loft rack), which the T01 and T03 rows name.

## Frozen staff and organizer schedules

Each case's `actor_scripts` freeze its simulated actors, the same for every policy.

* **Campus organizer rule.** `grant_coordinator_w5` (or `_h3`), at most 3500 cents, spare only,
  4 minutes.
* **Pantry crew.** One standing handoff rule answers every valid loft to main rack transfer
  hold 4 minutes after it was made, inside the window. One aggregate distribution is recorded
  at 10:50.
* **Check-ins.** C09: facilitator 17:34, presenter 17:52. C10: 17:33 and 17:51. C11: presenter
  17:31, facilitator 17:55. C12: 17:33 and 17:38. The host is checked in from the start.

## Adaptations to the frozen code (no code was changed)

* **Loader table.** The frozen loader (`run.heldout_specs`) only admits the protocol ids
  C01 to C08 and T01 to T04 (`run.CASE_CLASSES`), and only C02 to C04 as negative controls
  (`run.NEGATIVE_CONTROLS`). It refuses C09 and later. `tests/test_heldout2_cases.py` adds the
  six ids, and C10 as a negative control, inside the test process only. Then it loads the cases
  through the unchanged `heldout_specs`, which runs the full validation: schema,
  `validate_case`, opacity, development-world check and suite and class fit. The harness must
  add the same entries before `lock-heldout` or `eval run` can name these ids:
  `C09 goal`, `C10 goal`, `C11 goal`, `C12 infeasible`, `T05 target`, `T06 partial`, and C10 in
  `NEGATIVE_CONTROLS`.
* **Staging directory.** The files are staged in `set2/` subdirectories, not in
  `private/eval/` itself. In the parent directories, the frozen loader would refuse the new ids
  and fail every test that loads the spent set. `tests/test_heldout_cases.py` also pins the
  parent directories at 24 case files and three fixtures. The default loader globs
  non-recursively, so the v1.1 set still loads unchanged. The lock step may either point the
  loader at `set2/` or move the 15 files up one level. It must update those two counts in
  `tests/test_heldout_cases.py` if it moves them. `tests/test_heldout2_cases.py` finds the cases
  in either place. Any file under `scenarios/*/eval/` changes the v1.1 `heldout.json` digest, so
  that manifest verifies only at its own commit, as documented for version 1.2.
* **A loader that searches subdirectories.** By 18:50 EDT the working tree's in-progress
  version 1.2 loader found the 6 `set2/` cases, 18 in all, and admitted their ids. The author
  saw only that behavior, not the code.
  * In a run from 18:44 to 18:49, two tests in `tests/test_heldout_cases.py` that iterate every
    held-out case failed on the new cases. They were
    `test_every_protocol_case_loads_through_the_runner_loader` and
    `test_identifiers_and_agent_visible_texts_are_opaque`.
  * In a rerun from 18:50 to 18:57, all 32 passed. Another worker had changed that test module
    in the working tree by then.
  * If such a loader is kept, that module must restrict its `specs` to the twelve spent ids
    (C01 to C08, T01 to T04). The fix belongs there, not in the case data. T06's portal note
    keeps its own 8:05 a.m. `observed_at` on purpose, because it is the stale claim.
* **T06.** As in T03, the frozen simulators have no actor that records an external shipment
  receipt. So the authoritative after-deadline arrival is the dispatch ETA of 11:02 plus the
  loading door's 11:02 sign-off message, and no stock receipt of LT62 happens in the session.
  The loft desk declines the alternate, so the achievable 10:50 quantity is the 24 rack kits.
* **C11.** As in C06, a person cannot be held and a check-in cannot announce a future arrival.
  So the swap is prepared from the facilitator's own self-report and confirmed by the 17:55
  check-in. "Revise from observed availability" and "failure to release a hold" are not
  exercised. Unlike C06, the late person holds the first slot, so the swap moves the
  demonstrations earlier.
* **C12.** It differs from C08 (the event budget blocks the standby) and from the development
  infeasible case (the backup is booked elsewhere). Here the spare is free and within the
  budget and the organizer's rule, but its timing term cannot be met at any start in its
  window.

## Proofs (no policy run)

`tests/test_heldout2_cases.py` runs the scripted evaluator oracle of `tests/test_heldout_cases.py`
(`evaluator-oracle/scripted`) through the real runner, executor and clock engine. It shows:

* **C10.** Keep-only completes the original plan (`run.replay_original_plan`), and every other
  case fails under it. A status check at the warning (17:21) and after the second record (17:31)
  is fresh both times.
* **C09.** After the order desk answer, keep and the swap are infeasible, and the +10 shift
  reaches the goal (demonstrations at 18:10, closing at 18:30). A second permitted path, a spare
  hold, the organizer ask and the substitute committed at 17:26, also reaches the goal, for
  3500 cents.
* **C11.** The swap applied at 17:24 reaches the goal (demonstrations 17:40, skills exchange
  18:00).
* **T05.** One handoff and 40 committed serve 40 on time (one 16-kit receipt).
* **C12.** At 17:12 and at 17:30, the whole enumeration is infeasible: keep, swap, shifts,
  substitute and their combinations, with no truncation. Every candidate without the spare
  fails `resource_status`, every candidate with it fails `commitment_cutoff`, and none fails
  `budget`.
* **T06.** The oracle serves 24. The loft hold is refused at 9:40 and 9:55
  (`RESOURCE_UNAVAILABLE`), and the window is closed for a hold at 10:02
  (`HANDOFF_WINDOW_CLOSED`). No receipt is possible, and the coordinator grant has no
  `record_stock_receipt`.

The same file checks several more properties.

* The loader and opacity.
* The annotations of every delivered message.
* That no message text, status text, record id, resource, principal, grant or event id, and no
  world digest is shared with a development case or a spent held-out case.
* That the recovery terms differ from the spent fixtures.
* That no evaluator field reaches an observation or a tool response, in keep-and-read episodes
  that query every modeled status fact at three times, with the frozen leak check.

Message annotations (`annotations` in each `.eval.json`) describe what each delivered message's
text states (event, resource, effective time, claimed change, source, booking, the fields the
text leaves unknown), not whether it is true.

## Disclosures for the results

* **Small set.** Four campus cases and two pantry cases are a small check. With P0 once and
  P1 to P3 at three seeds, they make 40 campus and 20 pantry episodes. Report descriptive
  counts only.
* **Shift recovery is new.** C09's cheapest recovery is a shift, which no spent case needed.
  A v1.2 policy that only learned the swap would fail it. That tests generality, not a defect
  of the case.
* **Late person.** C11 again needs a policy that weighs a person's self-report (the v1.1 P2 and
  P3 weighed equipment only).
* **Frozen metrics.** The frozen metrics keep their Wave 3 properties. Extraction labels
  compare change, subject and event only. `infeasibility_reported` accepts any blocking
  constraint name, so the verdict is `metrics.class_success`.
* **Recovery delay on C09.** As on the spent C01, the actionable update is the van message
  (`van_txt_3082`, 17:16). The order desk's status already reports the delay to a check at
  17:10. A policy that queries that status and recovers before 17:16 meets the goal, but the
  recovery delay metric counts only plans applied at or after the actionable update, so it
  records that episode as unrecovered. Read C09's recovery delay together with its goal
  outcome. Found by the `audit2` audit and kept, to keep the protocol's definition.
* **Near copies of spent wording.** The fixture texts and the pantry numbers follow the spent
  templates closely (the pantry arithmetic 40, 24, 20 and 16 is fixed by the protocol rows).
  No string, id or world is shared, but a policy tuned on the spent wording sees familiar
  phrasing. Found by the `audit2` audit and disclosed, not reworded.
