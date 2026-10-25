# Held-out evaluation cases (evaluator only)

Do not open this directory in a policy, a prompt, a retrieval index, the browser bundle or any
public report. It holds the twelve held-out cases of `PEEAI_plan/08_evaluation.md`: the
campus bank C01–C08 and the separate pantry suite T01–T04. Each case is a private runner case
`<ref>.json` (`plan_b.private_case`) plus its evaluator data `<ref>.eval.json`
(`plan_b.eval_case`, `run.EvalCase`). The agent-visible public fixtures are in
`../../public/eval/`. They are opaque: no case id, condition word or expectation appears in any
identifier or text an agent can see. The cases were authored against the frozen code (freeze
commit `3de5962`, `freeze.json` `files_sha256` `7d41fada…`), and no compared policy (P0–P3)
was run on them before the lock.

| Ref | Id | Fixture | Condition | Class | What the world does |
| --- | --- | --- | --- | --- | --- |
| `hk_m2q` | C01 | `fixture_k7` | Genuine delivery delay | goal | Order desk: ETA 18:57 (delayed). Driver notice at 18:13. Received 18:56. Lead in at 18:36. Swap before 18:40 (or the standby for 18:40, approved before 18:20) |
| `hk_7vd` | C02 | `fixture_k7` | Quiet event, ordinary updates | goal, negative control | On schedule, received 18:25. Room, driver and facilitator notes |
| `hk_d5w` | C03 | `fixture_k7` | Plausible false delivery warning | goal, negative control | Volunteer hearsay at 18:16 says "around 7:10". Order desk on schedule; received 18:33. Facilitator in at 18:33 |
| `hk_x9j` | C04 | `fixture_k7` | Stale warning, then its duplicate | goal, negative control | Courier's 11:40 update arrives at 18:12 and is re-sent word for word at 18:19 under a new id (`crr_msg_0913`). Order desk 18:05: on schedule; received 18:30 |
| `hk_b3t` | C05 | `fixture_k7` | Conflicting updates about the current booking | goal | Courier says 15 min late (18:12). A volunteer then forcefully says "already here" (18:17). Order desk: ETA 18:48 (records of 18:08 and 18:18); received 18:44. Swap (or the standby for 18:40, approved before 18:20) |
| `hk_q8n` | C06 | `fixture_k7` | Volunteer late, then a later check-in | goal | Lead self-reports a held train (18:14) and checks in at 18:54. Swap |
| `hk_f6k` | C07 | `fixture_k7` | Verification service unavailable | goal | Courier (18:13): earliest about 19:05, unverifiable. Order desk unavailable all evening; received 19:09, too late for both slots. Standby hold, organizer ask, swap + standby before the 18:40 cutoff |
| `hk_z1c` | C08 | `fixture_r2` | No feasible recovery | infeasible | Order cancelled. The standby's 4600-cent booking exceeds the 4000-cent event budget |
| `hp_4ra` | T01 | `fixture_n4` | Primary shipment late; alternate 16 usable | target | SH31 ETA 17:20. Neighbor desk available. One crew handoff; 40 by 16:40 |
| `hp_k2e` | T02 | `fixture_n4` | Duplicate request ids, repeated receipts, same stock in two slots, adversarial quantities | target | As T01, plus six adversarial messages (R-208 twice, a 4:30 second slot, 64 / −6 / 2.5, one receipt claim sent twice) |
| `hp_v7s` | T03 | `fixture_n4` | Stale or wrong-source receipt claim; authoritative arrival after the deadline | partial | Neighbor desk declines. SH31 ETA 16:50 (deadline 16:40). Neighbor steward claims receipt at 15:41; last week's receipt note forwarded at 15:47; the dock signs for SH31 at 16:50. Limit 24, deficit 16 |
| `hp_g9m` | T04 | `fixture_n4` | Alternate supplies only 10 of 16 | partial | The crew confirms at most 10 (`max_quantity`). The residual 6 stay on the transfer hold until it expires. SH31 rebooked after the session. Limit 34, deficit 6 |

## Fixtures

The public fixtures preserve the event models of the development fixtures and change
everything else.

* `fixture_k7` (C01–C07) is a Hall B evening on 2026-11-12, 18:30–19:30, opening at a clock of
  18:10.
  * Identifiers are new: event, room, people, principals, grants, sources, and order P58.
  * Recovery details are new:
    * the standby projector costs 2800 cents, with a 12-minute free hold and a 20-minute
      confirmation cutoff;
    * the event budget is 12000;
    * shifts are ±5 minutes;
    * status freshness is 20 minutes;
    * the organizer answers in 3 minutes;
    * no notice is visible at the start.
* `fixture_r2` (C08) is the same hall one week later. The standby booking costs 4600 cents
  against a 4000-cent budget.
* `fixture_n4` (T01–T04) is an annex afternoon on 2026-11-14.
  * Distribution runs 16:00–16:40, with the deadline at 16:40 inclusive and the hard end at
    17:00.
  * The handoff window is 15:30–15:52, the crew answers in 3 minutes, and a neighbor hold lasts
    18 minutes.
  * It keeps the protocol's 40/24/20/16 arithmetic: target 40, 24 on the shelf, SH31 of 20
    expected, 16 on the neighbor shelf.
  * The neighbor listing at the start does not say whether those kits can be held.

## Frozen staff and organizer schedules

Each case's `actor_scripts` freeze its simulated actors, the same for every policy:

* the campus organizer rule: `grant_coordinator_k7`, at most 2800 cents (4000 in C08), standby
  only, 3 minutes;
* the pantry crew: one standing handoff rule answering every valid neighbor→shelf transfer
  hold 3 minutes after it was made, inside the window (T04 caps it at 10 kits), and one
  aggregate distribution at 16:40.

## Adaptations to the frozen code (no code was changed)

* **T02.** "Duplicate request ids" and "repeated receipts" are separate messages, each under its
  own record id: two cite the same logical request R-208, and the re-sent receipt claim comes
  from a non-crew source. They have to be separate because the executor de-duplicates a
  repeated source record id silently, and an agent would never see one. "The same stock in two
  slots" is a message asking for the same 16 kits for a 4:30 slot. The pantry adapter has one
  service activity, so a second slot cannot be a second activity. The executor refuses a
  second transfer hold, the later-slot hold, the negative, fractional and overdraw quantities
  and an agent receipt (shown in `tests/test_heldout_cases.py`).
* **T03.** The frozen simulators have no actor that records an external-shipment receipt (the
  crew rule records only internal handoffs), and an arrival record on a stock pool is an
  untested path. So the authoritative after-deadline arrival is the supplier line's ETA of
  16:50 plus the dock's 16:50 sign-off message, and no stock receipt of SH31 happens in the
  session. The neighbor desk declines the
  alternate, so the achievable 16:40 quantity is the 24 shelf kits.
* **C06.** "Prepare a permitted reassignment and revise it from observed availability" uses the
  swap, prepared from the lead's self-report under the declared-availability assumption and
  confirmed by the 18:54 check-in. Person resources cannot be held (holds need booking terms).
  This is a departure from the protocol row: the check-in confirms the swap rather than
  revising it, and no hold is placed or released, so "revise from observed availability" and
  "failure to release a hold" are not exercised. A check-in cannot announce a future arrival
  (the executor refuses availability that starts later), so the only early signal is the
  person's own self-report.
* **C04.** The development stale-warning case concerns another order and date; this one is the
  current order's own morning update, superseded by the order desk's later record. Its
  identity check is the update's 11:40 time, not a different event or booking.
* **C08.** It differs from the development infeasible case: there, the backup was booked
  elsewhere; here, the event budget blocks it. A hold on the standby is refused at any time,
  so no pre-emptive path exists either.

## Proofs (no policy run)

`tests/test_heldout_cases.py` runs a scripted evaluator oracle (`evaluator-oracle/scripted`)
through the real runner, executor and clock engine. It shows:

* **C02–C04:** keep-only completes the original plan. That is the lock-time replay
  (`run.replay_original_plan`), and every other case fails under it.
* **C01, C05, C06:** a swap reaches the goal.
* **C07:** standby hold, ask, then swap + standby reaches the goal.
* **T01, T02:** one handoff and 40 committed serve 40 on time.
* **C08:** after the cancellation, the whole enumeration (keep, swap, shifts, substitute and
  their combinations) is infeasible, and the standby hold is refused with `BUDGET_EXCEEDED`.
* **T03:** the oracle serves 24. The neighbor hold is refused for the whole window and no
  receipt is possible.
* **T04:** the oracle serves 34. The crew confirms 10, and the residual 6-kit hold stays active
  until it expires.

The same file checks the loader, opacity, the annotations and that no evaluator field reaches
an observation or tool response.

Message annotations (`annotations` in each `.eval.json`) describe what each delivered message's
text states (event, resource, effective time, claimed change, source, booking, the fields the
text leaves unknown), not whether it is true.

## Case audit before the lock (Wave 3)

Five read-only auditors (protocol fidelity, feasibility, leakage, distinctness and fairness,
predicates and scoring) reviewed these cases before the lock; no compared policy was run. The
confirmed findings were fixed in the case data and in `tests/test_heldout_cases.py`:

* C04: the order desk's record is observed at 18:05, so a check prompted by either warning gets
  a fresh answer (it was observed at 17:52 and read stale after 18:12). C02's on-schedule record
  is observed at 18:09 for the same reason. The re-send's id is a plain serial.
* Check-in times no longer separate the negative controls from the recovery cases: the lead
  checks in before 18:40 in C01 and C05, the facilitator in C03 and C04 (C06 keeps its late
  lead, which is its condition). In C01 and C05 the standby booked for 18:40 is now a second
  permitted path.
* C05 moved away from the development swap timeline (ETA 18:48, arrival 18:44, four minutes
  early), and a fresher order-desk record (18:18) follows the forceful claim.
* C07's courier note names a time (about 19:05), so the case tests unavailable verification and
  not the reading of a notice that names none; a second standby record (18:20) stays fresh
  through the 18:40 cutoff.
* No actionable message carries a delivery lag that other messages lack (observed_at equals
  delivery except where the text dates itself earlier).
* Pantry: one neutral neighbor-desk sentence in T01, T02 and T04; T02's receipt claim is sent
  twice (15:44, 15:49) and its request id is a plain serial; T03's dock signs for SH31 at
  16:50; T04's supplier text agrees with its typed ETA.
* C08 also requires the welcome at 18:30 (the valid part of the plan is kept).
* Annotations: C06's self-reported lateness is a `delay` (the frozen readers have no
  attendance category); T02's recount claims `availability`.
* Tests: every response of every oracle episode is leak-checked at its own scenario time
  (status answers, refusals, organizer replies, crew receipts), the keep-and-read episodes read
  every modeled status fact, the negative controls' prompted checks are asserted fresh, and
  T04's cap is shown for a top-up inside the window.

Disclosures for the results (properties of the frozen code or of the protocol's mandated
numbers, not fixable in case data):

* P0's frozen parser leaves every held-out message unresolved (its grammar admits only the
  development templates). Its campus outcomes measure typed status checks (verify-only notices
  and the deadline watch), not message reading. C06 and C07 are out of P0's reach by
  construction, and its C01 recovery rests on the deadline watch.
* C06 can be recovered only by a policy that weighs a person's self-report. P0, P2 and P3 weigh
  equipment only, so their C01-C07 completion is capped at 6 of 7 by this case; report C06 per
  policy.
* T04 repeats the development partial-handoff mechanism (the protocol fixes 10 of 16 and 34/6,
  and `max_quantity` is the frozen simulator's only partial-supply mechanism); `fixture_n4`
  keeps the development pantry arithmetic and offsets (three hours later), with different
  handoff, hold and latency terms, ETAs and messages.
* The campus recoveries remain mostly the swap (C01, C05, C06; C07 swap + standby; C01 and C05
  also admit the standby for 18:40). No case needs a shift.
* Metrics (frozen): P2/P3 extraction labels compare change, subject and event only, and a
  server-chosen duplicate reading of C04's re-send is labelled incorrect against its `delay`
  annotation; `infeasibility_reported` accepts any blocking-constraint name, so the held-out
  verdict is `metrics.class_success`; churn on C06/C07 includes the repaired assignments
  (3 against 2 in C01/C05); `duplicate_attempts_blocked` counts receipt duplicates only, so
  T02's refused attempts appear under invalid attempts by code.
