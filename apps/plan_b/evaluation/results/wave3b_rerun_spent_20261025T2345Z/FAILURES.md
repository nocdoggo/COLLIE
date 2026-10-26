# Failure analysis: post-hoc diagnostic rerun of policy 1.2 on spent cases, `wave3b_rerun_spent_20261025T2345Z`

Post-hoc diagnostic rerun after fixes, on spent cases. Not a held-out result.

Evaluator output, like `*/report/` and `*/runner_private/`. It covers every episode of this
rerun that did not meet its case's outcome class: **5 of 80 campus episodes and 5 of 40 pantry
episodes**. Each stays in its outcome-class denominator in the reports. Nothing here changes a
count.

Each diagnosis comes from the episode's trace (`episodes/<key>/trace.json.gz`), its evaluator
record (`runner_private/<key>.runner.json`) and `report/metrics.json`. The digests are in
`failure_digests/{campus,pantry}.txt`, written by `failure_digests/digest.py` (the Wave 3
script, copied unchanged). Trace times are UTC. The scenario clock is local time, UTC−5.

The **earliest broken stage** uses the protocol's six stages (`PEEAI_plan/08_evaluation.md`):
interpretation, evidence selection, planner input, action selection, execution and final-state
scoring. For comparison, the v1.1 record's diagnosis of the same case and policy is in
`wave3_heldout_20261025T1625Z/FAILURES.md`.

## Summary

| Suite | Policy | Non-success / recorded | Earliest broken stage | Cases | Same pair missed in v1.1 |
| --- | --- | --- | --- | --- | --- |
| campus | P0 rules | 2 / 8 | interpretation 2 | C06, C07 | yes, same stage |
| campus | P1 tool use | 0 / 24 | none | none | |
| campus | P2 selective | 3 / 24 | action selection 3 | C07 ×3 | yes, same stage |
| campus | P3 verify-all | 0 / 24 | none | none | |
| pantry | P0 rules | 0 / 4 | none | none | |
| pantry | P1 tool use | 2 / 12 | action selection 2 | T04 ×2 | yes (3 of 3 in v1.1), same stage |
| pantry | P2 selective | 0 / 12 | none | none | |
| pantry | P3 verify-all | 3 / 12 | execution 3 | T02 ×3 | yes, same stage |

The model-call cap was reached in 8 of these 10 episodes: C07/P2 ×3, T02/P3 ×3 and T04/P1 ×2.
In each, all 8 calls returned a completion. No failure was traced to final-state scoring.

## Provider-side errors, apart from policy failures

This rerun used `--jobs 2`, and OpenRouter answered HTTP 429 61 times (README, "Concurrency and
rate limits"). Version 1.2 waited each one out inside its call. Every recorded model call of every
episode returned a completion (469 of 469), and every record shows 0 failed calls. Five of the 10
failures had a rate-limit wait on one call each: `hk_f6k__P2__s101` (call 6, 3 retries, 21 s),
`hk_f6k__P2__s303` (call 7, 2 retries, 9 s), `hp_k2e__P3__s202` (call 7, 3 retries, 21 s),
`hp_k2e__P3__s303` (call 5, 1 retry, 3 s) and `hp_g9m__P1__s303` (call 5, 1 retry, 3 s). No wait
used any of the 8 calls. The waits add wall time only, and the scenario clock is simulated. The
traces agree: `hk_f6k__P2__s303` (a wait) follows the same decisions as `hk_f6k__P2__s202` (no
wait), and the three T02/P3 seeds (two with a wait, one without) are identical. Only
`hk_f6k__P2__s101` departs from its siblings, at the very call that waited (dec_0006 chose `wait`
where the others released the hold). Model runs differ between trials anyway (no seed reaches the
provider), so that difference cannot be attributed to the wait. No failure below involves a
provider error.

## Campus (5 of 80)

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hk_q8n__P0__once` (C06) | completed | interpretation | dec_0002 23:14Z `unresolved`: the demonstrations lead's self-report (`lead_note_1`) is "outside the supported message forms" (label `abstained`). Plan v1 is kept. At 23:40Z and 00:00Z no candidate is feasible. Failed: `p_required`. As in v1.1, C06 is outside P0's reach by construction. |
| `hk_f6k__P0__once` (C07) | completed | interpretation | dec_0002 23:13Z `unresolved` (label `abstained`). The deadline watch's fresh check at 23:35Z gets `STATUS_UNAVAILABLE`, and at 23:40Z no candidate is feasible. Failed: `p_required`, `p_spend` (committed 0, expected 2800). Same as v1.1. |
| `hk_f6k__P2__s202` (C07) | capped | action selection | The reading is correct (1 `interpret` call). Then 7 `choose_action` calls: dec_0002 23:15Z and dec_0003 23:17Z check the same status twice (both `STATUS_UNAVAILABLE`), dec_0004 23:18Z holds the standby, dec_0005 23:20Z checks it (available), dec_0006 23:22Z releases that hold, dec_0007 23:23Z holds the standby again for the swap plus substitute, dec_0008 23:23Z asks the organizer to raise the committed-spend limit to 2800. That was the 8th call, and the cap stops the episode at 23:23Z. The organizer approves at 23:26Z (receipt), but the policy is never woken to apply. Failed: `p_required`, `p_spend`. The same sequence, minute for minute, as v1.1's three C07/P2 episodes. |
| `hk_f6k__P2__s303` (C07) | capped | action selection | Identical to s202, including the approval at 23:26Z that comes after the cap. |
| `hk_f6k__P2__s101` (C07) | capped | action selection | As s202 up to dec_0005 23:20Z. Then dec_0006 23:21Z `wait`, dec_0007 23:27Z releases the hold, dec_0008 23:28Z holds the standby again (8th call), and the cap stops it at 23:28Z before any ask to the organizer. Failed: `p_required`, `p_spend`. |

The 1.2 changes did not reach C07/P2. The two identical status checks, the hold, release and
re-hold, and the late ask still spend the 8 calls before an apply. P1 and P3 met C07 3/3 each.

C06 is met by P1, P2 and P3 in all 9 episodes (v1.1: P1 only). This is consistent with the fix for "a person's
delay not treated as material" working on the case it was written from.

## Pantry (5 of 40)

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hp_k2e__P3__s101` (T02, target) | capped | execution | dec_0004 20:37Z asks staff for the 16-kit handoff (hold on `neighbor_stock`). Staff record it at 20:40Z (16 moved into `shelf_stock`). dec_0008 20:42Z holds 40 shelf kits for the target. dec_0009 20:43Z: `apply_plan` is rejected as stale (`REVISION_CONFLICT`) at revision 11, and the retry needs a model call. Verify-all then reads two more notices (dec_0010 20:43Z, dec_0012 20:47Z), and the cap stops the episode at 20:47Z without a re-apply. Final state: 40 kits on the shelf, 0 distributed. Failed: `p_on_time` (0, expected 40), `p_unfulfilled`, `p_shelf_end`. The same sequence as v1.1's three T02/P3 episodes. |
| `hp_k2e__P3__s202` (T02) | capped | execution | Identical: stale apply at 20:43Z, cap at 20:47Z. |
| `hp_k2e__P3__s303` (T02) | capped | execution | Identical. |
| `hp_g9m__P1__s202` (T04, partial) | capped | action selection | The achievable on-time quantity is 34 (the crew's handoff caps out at 10 of 16). dec_0002 20:33Z asks for the handoff, and staff record 10 moved at 20:36Z. P1 then ends four turns with `wait` ("3 feasible, 0 applicable now", dec_0003 to dec_0006, 20:33Z to 20:44Z), each a model call. dec_0008 20:52Z holds the 34 kits, dec_0009 20:53Z the apply is rejected as stale (`CANDIDATE_STALE`), dec_0010 20:54Z applies the allocation (plan v2), and 34 are distributed on time. dec_0011 20:56Z checks the shipment ETA with the 8th call, and the cap stops it before any deficit report. Failed: `p_reported` only ("no infeasible decision was recorded"). |
| `hp_g9m__P1__s303` (T04) | capped | action selection | dec_0001 20:31Z asks for the handoff (10 of 16 moved at 20:34Z). Four `wait` turns (20:31Z to 20:42Z). A hold at 20:49Z is rejected (`REVISION_CONFLICT`), dec_0008 20:51Z holds the 34 kits, dec_0009 20:52Z the apply is rejected (`CANDIDATE_STALE`), dec_0010 20:53Z applies the allocation, and 34 are distributed on time. dec_0011 20:53Z ends the turn with `none`, and the cap stops it before any deficit report. Failed: `p_reported` only. |

T02/P3 is unchanged from v1.1: the stale apply and its model-call retry still end the episode.
On T04/P1 the 1.2 code reaches the 34-kit allocation and serves it on time in all three seeds
(v1.1: 0 distributed in all three). In seeds 202 and 303 the wait turns and stale retries still
spend the budget before the deficit report, so the class is missed. Seed 101 met the class.
T03 is met by every policy in every episode (v1.1: P0 only), which is consistent with the fix for "an
unavailable pool kept as a handoff option" working on the case it was written from.

## What this rerun can and cannot show

It shows that, on the cases they were built from, the C06 (P2, P3) and T03 (P1, P2, P3)
failures of the v1.1 record did not recur here, that T04/P1 met in one of three seeds (all
three served the 34 kits on time), and that no case and policy pair that met in
the v1.1 record missed here. It cannot show that 1.2 is better in general. The fixes were made
after reading these failures, and these cases are spent. The fresh held-out check
(`wave3b_fresh_20261025T2327Z`) is the only 1.2 result on unseen cases, and it is small.
