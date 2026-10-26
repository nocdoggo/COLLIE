# Failure analysis: fresh held-out check of policy 1.2, run `wave3b_fresh_20261025T2327Z`

Evaluator output, like `*/report/` and `*/runner_private/`: it names evaluator case ids and why
an episode missed its outcome class. It covers every episode of this run that did not meet its
case's outcome class: **1 of 40 campus episodes and 0 of 20 pantry episodes**. The episode stays
in its outcome-class denominator in `campus/report/`. Nothing here changes a count.

The diagnosis comes from the episode's trace (`episodes/<key>/trace.json.gz`: decisions, tool
calls, receipts, final state), its evaluator record (`runner_private/<key>.runner.json`, the
failed predicates and the actors' log) and `report/metrics.json`. The digests are in
`failure_digests/{campus,pantry}.txt`, written by `failure_digests/digest.py` (the Wave 3
script, copied unchanged) from these records. `pantry.txt` is empty because no pantry episode
missed. Trace times are UTC. The scenario clock is local time, UTC−5 (22:24Z is 17:24).

The **earliest broken stage** uses the protocol's six stages (`PEEAI_plan/08_evaluation.md`):
interpretation, evidence selection, planner input, action selection, execution and final-state
scoring.

## Summary

| Suite | Policy | Non-success / recorded | Earliest broken stage | Cases |
| --- | --- | --- | --- | --- |
| campus | P0 rules | 1 / 4 | interpretation 1 | C11 |
| campus | P1 tool use | 0 / 12 | none | none |
| campus | P2 selective | 0 / 12 | none | none |
| campus | P3 verify-all | 0 / 12 | none | none |
| pantry | P0 rules | 0 / 2 | none | none |
| pantry | P1 tool use | 0 / 6 | none | none |
| pantry | P2 selective | 0 / 6 | none | none |
| pantry | P3 verify-all | 0 / 6 | none | none |

No episode reached the model-call cap. No failure was traced to final-state scoring. The failed
predicate matches the final state in the trace.

## Provider-side errors, apart from policy failures

None. All 194 model calls of the run returned HTTP 200 with a completion
(`spend_extract.json`). Every record shows 0 failed calls, 0 retries and 0 rate-limit waits. No
episode was aborted, timed out, crashed or failed its trace check.

## C11 under P0 (`ev_w2n__P0__once`): interpretation

- **Case.** C11 (goal class) repeats the protocol's late-volunteer condition (C06). The
  facilitator holds the first slot (skills exchange, 17:40). At 17:24 the facilitator reports
  that the bus was taken out of service and that arrival will be about 17:55. The facilitator
  checks in at 17:55. The recovery is the swap (demonstrations first at 17:40, skills exchange at
  18:00), which the evaluator oracle shows reaches the goal when applied at 17:24.
- **What P0 did.** At 22:24Z (17:24) the self-report was recorded as observation `obs_0002`
  (receipt `rcpt_0001`). P0's decision `dec_0003` at the same minute reads: "Notice obs_0002 is
  outside the supported message forms, so it is not read as a claim; left unresolved. No plan
  change." The extraction label of `fac_note_2` is `abstained`. P0 kept plan v1. At 22:40Z (17:40, the
  start of the first slot) and again at 23:00Z, P0 reported that no candidate in the declared
  action space was feasible (`dec_0004`, `dec_0005`). At 23:30Z
  (`dec_0006`) the skills exchange and the closing were recorded as failed.
- **Failed predicate.** `p_required`: "skills_exchange is failed; closing is failed".
- **Earliest broken stage: interpretation.** The message that carries the only early signal
  was not read as a claim. P0's frozen parser (`rules/1.0.0`, unchanged in policy 1.2) does
  not accept this message form, and the check-in comes after the slot has started. So C11 is
  outside P0's reach by construction, as C06 was in the v1.1 run.
- **Other policies on C11.** P1, P2 and P3 met the goal in all 9 episodes, each with one applied
  plan change.
