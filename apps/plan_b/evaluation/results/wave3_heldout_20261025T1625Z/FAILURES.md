# Failure analysis: Wave 3 held-out evaluation `wave3_heldout_20261025T1625Z`

Evaluator output, like `*/report/` and `*/runner_private/`: it names evaluator case ids and why
an episode missed its outcome class. It covers every episode of the reported run (attempt 2) that
did not meet its case's outcome class: **11 of 80 campus episodes and 15 of 40 pantry
episodes**. Every one of them stays in its outcome-class denominator in `campus/report/` and
`pantry/report/`. Nothing here changes a count.

Each diagnosis comes from the episode's trace (`episodes/<key>/trace.json.gz`: decisions, tool
calls, receipts, final state), its public record, its evaluator record
(`runner_private/<key>.runner.json`, the failed predicates) and `report/metrics.json`. The
per-episode digests these tables were read from are in `failure_digests/{campus,pantry}.txt`,
written by `failure_digests/digest.py` from the copied records. Trace times are UTC; the scenario
clock is local time, UTC−5 (23:40Z is 18:40).

The **earliest broken stage** uses the protocol's six stages (`PEEAI_plan/08_evaluation.md`):

- **interpretation**: the message was not read as the claim it makes;
- **evidence selection**: the wrong source was checked, or a needed one was not;
- **planner input**: a correct reading did not reach the planner as a hypothesis or constraint;
- **action selection**: the policy chose an action that cannot reach the class, or spent its
  budget so that it could not;
- **execution**: a correct action failed when it was carried out;
- **final-state scoring**: the scorer misjudged a final state.

No failure was traced to final-state scoring. Every failed predicate matches the final state in
its trace.

## Summary

| Suite | Policy | Non-success / recorded | Earliest broken stage | Cases |
| --- | --- | --- | --- | --- |
| campus | P0 rules | 2 / 8 | interpretation 2 | C06, C07 |
| campus | P1 tool use | 0 / 24 | — | — |
| campus | P2 selective | 6 / 24 | planner input 3, action selection 3 | C06 ×3, C07 ×3 |
| campus | P3 verify-all | 3 / 24 | planner input 3 | C06 ×3 |
| pantry | P0 rules | 0 / 4 | — | — |
| pantry | P1 tool use | 6 / 12 | action selection 6 | T03 ×3, T04 ×3 |
| pantry | P2 selective | 3 / 12 | planner input 3 (borderline: action selection) | T03 ×3 |
| pantry | P3 verify-all | 6 / 12 | execution 3, planner input 3 | T02 ×3, T03 ×3 |

The model-call cap was reached in 15 of these 26 episodes: campus C07/P2 ×3; pantry T02/P3 ×3,
T03/P2 ×3, T03/P3 ×3 and T04/P1 ×3. In each, every one of the 8 calls returned a valid
completion (none failed, none retried). The cap is the frozen episode cap, the same for every
policy. Where it ended an episode, the table names the earliest broken stage, not the cap
itself: the stage that spent the budget, or, for T02/P3, the stale apply whose retry needed a
call.

The T03 P2/P3 stages were revised by the post-run audit (audit_eval, findings D1–D2). The first
version of this file labelled them action selection. The traces show an earlier break in frozen
code; see "Findings in frozen code" below.

## Provider-side errors, apart from policy failures

- **Reported run (attempt 2): none.** All 482 model calls returned HTTP 200 with a completion
  (`spend_extract.json` → `attempt2_reported`). The records show 0 failed calls and 0 retries in
  every episode, and the returned model was `anthropic/claude-sonnet-5.5` on every call. No
  episode was aborted, timed out, crashed or failed its trace check. None of the 26 failures
  below involves a provider error.
- **Voided attempt 1** (`attempt1_rate_limited/`, see `README.md`): from 16:22:57Z OpenRouter
  answered HTTP 429, "new accounts are limited to 20 requests per minute for this model". That
  happened on 692 of 732 calls. The harness records a provider error as a visible wait that uses
  one of the episode's 8 model calls, so 429s capped the LLM episodes within seconds.

  | Suite | Policy | Planned | Recorded | Episodes with a 429 | 429 calls in records |
  | --- | --- | --- | --- | --- | --- |
  | campus | P0 | 8 | 6 | 0 | 0 |
  | campus | P1 | 24 | 17 | 17 | 129 |
  | campus | P2 | 24 | 18 | 17 | 119 |
  | campus | P3 | 24 | 18 | 15 | 114 |
  | pantry | P0 | 4 | 4 | 0 | 0 |
  | pantry | P1 | 12 | 12 | 12 | 96 |
  | pantry | P2 | 12 | 12 | 12 | 96 |
  | pantry | P3 | 12 | 12 | 12 | 96 |

  The campus run was stopped by PID after 59 of its 80 episodes were recorded. The ledger's 692
  429s include calls of episodes the stop cut short; those episodes have no records. These are
  provider-side failures, not policy failures, and attempt 1 is not part of any reported count.

## Campus (11 of 80)

### C06: P0 once; P2 and P3, all three seeds (7 episodes)

All 7 fail only `p_required` ("demonstrations is failed; closing is failed"). None has a
violation or an invalid attempt. Each reports infeasibility at 23:40Z, when demonstrations can no
longer start. The case's actionable update is a person's self-report (`lead_note_1`, 23:14Z) that
the demonstrations lead will arrive late.

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hk_q8n__P0__once` | completed | interpretation | dec_0002 23:14Z `unresolved`: "outside the supported message forms" (extraction label `abstained`). The kept plan passes at 23:23Z; infeasible at 23:40Z and 00:00Z. |
| `hk_q8n__P2__s101` | completed | planner input | The one `interpret` call reads the notice correctly (label `correct`: a `delay` change spec for `demo_lead`, ETA about 18:55). dec_0002 23:14Z `keep`, by the server: "notice obs_0001 not material for the current plan". No hypothesis reaches `evaluate_candidates` (every call has `hypotheses: []`). The swap is evaluated and applicable at every wake from 23:10Z to 23:30Z. With no hypothesis the keep plan passes and the notice is not material, so the plan is never in question, no `choose_action` call is made, and the server records `keep`. |
| `hk_q8n__P2__s202` | completed | planner input | Identical decision sequence to s101 (keep 23:10, keep 23:14 "not material", keep 23:23, infeasible 23:40/00:00). |
| `hk_q8n__P2__s303` | completed | planner input | Identical to s101. |
| `hk_q8n__P3__s101` | completed | planner input | Identical to P2: a correct reading ("expects to arrive at Hall B around 18:55"), judged not material, so no hypothesis reaches the planner. |
| `hk_q8n__P3__s202` | completed | planner input | Identical. |
| `hk_q8n__P3__s303` | completed | planner input | Identical. |

This is the structural limit disclosed before the runs (`scenarios/private/eval/README.md`, "Case
audit before the lock"; audit_cases G17). P0's frozen parser does not read this wording. The
frozen P2/P3 controller forms planner hypotheses from equipment claims only, so a correct reading
of a person's delay stops before the planner. P1 met C06 3/3.

### C07: P0 once; P2, all three seeds (4 episodes)

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hk_f6k__P0__once` | completed | interpretation | dec_0002 23:13Z `unresolved`: the notice is "outside the supported message forms" (label `abstained`). The deadline watch's fresh check at 23:35Z gets `STATUS_UNAVAILABLE`; infeasible at 23:40Z. Failed: `p_required`, `p_spend` (committed 0; expected 2800). C07 is out of P0's reach by construction (disclosed). |
| `hk_f6k__P2__s101` | capped | action selection | The reading is correct (1 `interpret` call). Then 7 `choose_action` calls: dec_0002 23:15Z and dec_0003 23:17Z check the same status twice (both `STATUS_UNAVAILABLE`); dec_0004 23:18Z holds the standby; dec_0005 23:20Z checks it (available); dec_0006 23:22Z releases that hold (the only non-wait option the frozen menu offers once its 18:40 candidate has lapsed); dec_0007 23:23Z holds the standby again, for the 19:00–19:20 slot of the swap plus substitute, a hold the menu had offered since dec_0002; dec_0008 23:23Z asks the organizer to raise the committed-spend limit to 2800. That was the 8th call: dec_0009 23:23Z `stop` (model-call cap). The organizer approved at 23:26Z (receipt), but the policy was never woken to apply the swap plus substitute. Failed: `p_required`, `p_spend`. Borderline with the budget: the approval at 23:26Z came while hold_0002 was live (to 23:35Z), so one more model call would have applied it. |
| `hk_f6k__P2__s202` | capped | action selection | Identical decision sequence and receipts to s101. |
| `hk_f6k__P2__s303` | capped | action selection | Identical to s101. |

P1 and P3 met C07 3/3 each.

## Pantry (15 of 40)

### T02: P3, all three seeds (3 episodes, class target)

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hp_k2e__P3__s101` | capped | execution | dec_0004 20:37Z asks staff for the 16-kit handoff (hold on `neighbor_stock`); staff record the handoff at 20:40Z (16 moved into `shelf_stock`). dec_0008 20:42Z holds 40 shelf kits for the target. dec_0009 20:43Z: `apply_plan` is **rejected as stale (`REVISION_CONFLICT`)** at revision 11. The retry needs a model call. Verify-all then reads two more notices (dec_0010 20:43Z, dec_0012 20:47Z; 4 `interpret` calls in all), and the 8-call cap stops the episode at 20:47Z without a re-apply. Final state: 40 kits on the shelf, 0 distributed. Failed: `p_on_time` (0; expected 40), `p_unfulfilled`, `p_shelf_end`. |
| `hp_k2e__P3__s202` | capped | execution | Identical decision sequence: stale apply at 20:43Z, cap at 20:47Z. |
| `hp_k2e__P3__s303` | capped | execution | Identical. |

P1 and P2 met T02 3/3 each.

### T03: P1, P2 and P3, all three seeds (9 episodes, class partial)

The achievable on-time quantity is 24 kits; the partner pool is booked elsewhere.

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hp_v7s__P1__s101` | completed | action selection | The handoff hold is rejected (`RESOURCE_UNAVAILABLE`, 20:30Z). Its checks find `neighbor_stock` booked elsewhere (20:33Z) and the shipment delayed to 16:50 (20:35Z). It ends turns with `infeasible` (dec_0004 20:35Z, dec_0008 21:50Z; decided by the model), `keep` and `inapplicable`, each noting "3 feasible, 0 applicable now". It never holds or commits the 24 kits on hand, so staff distribute nothing. Failed: `p_on_time` (0; expected 24), `p_unfulfilled` (40; expected 16), `p_shelf_end`. The deficit report itself passed. |
| `hp_v7s__P1__s202` | completed | action selection | Same pattern (verify, wait, verify, infeasible 20:35Z, …, infeasible 21:50Z); 24 kits never committed. |
| `hp_v7s__P1__s303` | completed | action selection | Same as s202. |
| `hp_v7s__P2__s101` | capped | planner input (borderline: action selection) | dec_0001 20:31Z: the handoff request is rejected (`RESOURCE_UNAVAILABLE`); dec_0002 20:33Z: the check finds the pool booked elsewhere. At 20:35Z (dec_0004) the model chooses `wait` over the offered 24-kit hold. The planner still ranks the 40-kit handoff candidate first (`feasible_under_assumptions`), although the pool has been `unavailable` since 20:33Z. The frozen menu re-offers the handoff, which the model takes twice: 20:40Z rejected as stale (`REVISION_CONFLICT`), 20:42Z rejected `RESOURCE_UNAVAILABLE`. dec_0007 20:43Z holds the 24 shelf kits with the last of 8 calls; the cap (20:43Z) comes before an apply or a deficit report. Failed: `p_on_time` (0; expected 24), `p_unfulfilled`, `p_shelf_end`, `p_reported` (no infeasible decision). |
| `hp_v7s__P2__s202` | capped | planner input (borderline: action selection) | Identical sequence. |
| `hp_v7s__P2__s303` | capped | planner input (borderline: action selection) | Identical. |
| `hp_v7s__P3__s101` | capped | planner input | The check at 20:34Z finds the pool booked elsewhere. dec_0003 20:35Z still requests the handoff (rejected `RESOURCE_UNAVAILABLE`), and it is requested again at 20:40Z (stale) and 20:42Z (rejected). dec_0009 20:43Z commits the 24-kit allocation, and 24 are distributed on time (that part met). The cap at 20:47Z comes before any infeasible decision. In P2/P3's T04 successes the server's shared narration reports the deficit in the same wake as the commit (20:37Z–20:42Z). Here the commit wake records a server `keep` (dec_0010 20:43Z). `neighbor_stock` has been `unavailable` (status observation) since 20:34Z, yet every evaluation still ranks the 40-kit handoff candidate first (`feasible_under_assumptions`), and the frozen menu counts the pool's units as requestable. So the menu re-offers the handoff (20:41Z, 20:42Z), and the call-free shortfall report is withheld while a handoff could still be requested (until about 20:48Z). The cap at 20:47Z stops the policy first, including that narration. Borderline with action selection: at 20:36Z the model chose `wait` over the offered apply. Failed: `p_reported` only. |
| `hp_v7s__P3__s202` | capped | planner input | Same (commit at 20:44Z, then a server `keep`; 24 on time; cap 20:47Z; no infeasible decision). |
| `hp_v7s__P3__s303` | capped | planner input | Same as s202. |

P0 met T03 (24 on time, infeasible reported by the policy at 20:37Z).

### T04: P1, all three seeds (3 episodes, class partial)

The achievable on-time quantity is 34 kits: the crew's handoff caps out at 10 of the 16.

| Episode | Status | Earliest broken stage | Evidence in the trace |
| --- | --- | --- | --- |
| `hp_g9m__P1__s101` | capped | action selection | dec_0001 20:31Z asks for the 16-kit handoff; staff record 10 moved at 20:34Z. Then P1 ends five turns with `wait` and a short self-requested wake (dec_0002–dec_0006, 20:31Z–20:46Z, "0 applicable now"), each a model call, without holding the 34 kits now on hand. Its holds at 20:48Z and 20:49Z are rejected as stale (`REVISION_CONFLICT`), and the 8-call cap stops it at 20:50Z. Failed: `p_on_time` (0; expected 34), `p_unfulfilled`, `p_shelf_end`, `p_reported`. |
| `hp_g9m__P1__s202` | capped | action selection | Same pattern (ask, verify 20:33Z, waits to 20:49Z, stale holds, cap 20:50Z). |
| `hp_g9m__P1__s303` | capped | action selection | Same as s202. |

P0, P2 and P3 met T04 (P2/P3 3/3 each, with the deficit reported by the server's shared
narration).

## What the failures share

- **Model-call budget.** In 15 of the 26 failures the episode used its 8 calls before the action
  that completed the class. In most, the calls went first to repeated or menu-offered steps: a
  second check of an unavailable status, a hold released and re-made for another slot, handoff
  requests to a pool already checked as booked elsewhere, and short waits. In T02/P3 the apply
  was made in time and failed stale, and the remaining calls went to verify-all readings of new
  notices. All policies share the
  frozen cap; it is development-calibrated (the protocol's proposed 16 tool calls were not used;
  `freeze.json` records 48 tool / 8 model calls).
- **Frozen hypothesis rule (C06).** P2 and P3 read the self-report correctly but do not pass a
  person's delay to the planner. This is a design limit of the frozen controller, disclosed
  before the runs, not a reading error.
- **P0's parser (C06, C07).** It abstains on the held-out wording, as disclosed at the lock.
- **Stale rejections.** `REVISION_CONFLICT` is retryable by design. Each one here came from a
  state change during a one-minute tool call. In T02/P3, obs_0005 arrived at 20:43Z during the
  apply. In T03/P2–P3, obs_0003 arrived at 20:41Z during a handoff request. In T04/P1, hold_0001
  expired at 20:49Z and activities changed at 20:50Z, during two holds. Only in T02/P3 was a
  correct apply left unretried for want of a model call. In T03 the retried handoff was rejected
  again (`RESOURCE_UNAVAILABLE`), and in T04/P1 the second stale hold was itself the retry.
- **An unavailable pool kept as a handoff option (T03, P2 and P3).** This is a finding in frozen
  code; see below.
- **No violations and no unsafe credit.** Across all 26 failures there are 0 executed
  violations. The 15 pantry failures also have 0 conservation failures and 0 duplicate or
  unauthorized credits, and every receipt passed the integrity check.

## Findings in frozen code (post-run audit)

These are results of the evaluation, not corrections to it. The frozen code was not changed,
no episode was rerun, and no count above changes.

1. **An `unavailable` stock pool stays a requestable handoff (affects measured episodes).** A
   typed status check that finds a pool `unavailable` does not reach the planner or the menu as
   a constraint. Evaluations keep the handoff candidate `feasible_under_assumptions` and ranked
   first. `agent/menu.py` `handoff_quantity` counts the pool's available units, not its status,
   so the menu re-offers the handoff and `stock_improvable` keeps the plan in question. The shared
   attention rule then withholds the call-free shortfall report while a handoff could still be
   requested (`agent/attention.py`). In T03 this is the earliest broken stage of all six P2 and P3
   failures: P2 never committed the 24 achievable kits, and P3 committed them but its deficit
   report came too late for its call budget. P1 does not use the menu. It reads the same
   planner's evaluations, but its T03 failure is its own action selection: it never held the 24
   kits on hand. Severity: a correctness defect of the frozen controller and planner input,
   material to 6 of the 40 pantry episodes. To fix after release, then rerun as a new, separately
   versioned comparison.
2. **No wall-clock backoff on HTTP 429 (affects no measured episode).** A provider error,
   including a rate-limit 429, counts as one of the episode's 8 model calls, and the retry fires
   at the next scenario wake with no wall-clock wait. This is what voided attempt 1. In the
   reported run, all 482 calls were `ok`, with 0 retries. Severity: reliability, for live use
   and any later paid run. To fix after release; until then, run one LLM episode at a time.
