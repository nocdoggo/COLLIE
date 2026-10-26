# Presentation notes

Plan B: The Show Must Go On
Noctis Zhang, University of Massachusetts Boston, Paul English Applied AI Institute (PEAAII) Hackathon, October 2026

Every held-out number in this script comes from a committed run in apps/plan_b/evaluation/results/, through make_results.py. Slides 9 to 11 use wave3_heldout_20261025T1625Z, the held-out test of version 1.1 and the evaluation of record. Slide 12 uses wave3b_fresh_20261025T2327Z, the held-out test of version 1.2 on six fresh cases. The rerun of version 1.2 on the twelve spent cases (wave3b_rerun_spent_20261025T2345Z) is a post-hoc diagnostic rerun, not a held-out result, and is shown only on a backup slide. Never call it held-out. Say "held-out" only for the first two runs. Everything before slide 9 is development evidence.

Read each paragraph at a steady, clear pace, about 140 words a minute. The full script is about 930 words, about six minutes forty, which leaves about twenty seconds to point and to change slides inside the seven minutes. Time each rehearsal with rehearsal_timer.py. Pause briefly each time you advance a slide. The sentence marked "skip if late" (slide 6) can be dropped without losing the story. The bold checkpoints are the clock times of the seven-minute plan. If you are behind at a checkpoint, skip the marked sentences of the next slide.

Everything shown is a fictional local sandbox. Say "recorded" whenever you show a recorded run, and never call it live.

## Slide 1. Title
_about 10 seconds_

Hello, I am Noctis Zhang from UMass Boston. This is Plan B. It decides what to verify, what to prepare, and when to commit a change.

## Slide 2. Twenty minutes before opening, the projector may be late
_about 27 seconds_

Imagine you organize a campus showcase. It opens at five and must end by six. At four forty, a message says the projector may be twenty five minutes late. Change too much and people lose time. Wait too long and the demos fail. AI agents now act on messages like this. Would you wait, check, or prepare a backup?

**Checkpoint 0:37.**

## Slide 3. The coordinator may check, hold and make free changes, not spend
_about 30 seconds_

Plan B is a coordinator, an AI agent with written limits. It may check sources, compare options, place a hold, and make a change that costs nothing. A hold is a free reservation of a backup that expires on its own, here worth up to thirty five dollars. It cannot spend a cent without the organizer. Everything runs in a fictional local sandbox.

**Checkpoint 1:07.**

## Slide 4. A message is a claim, not a fact
_about 31 seconds_

Here is the notice, from the delivery contact. Plan B treats it as a claim, not a fact. Before changing anything, it checks the one fact that could change the decision. A status check asks the supplier's status service. The answer is delayed, with a reported arrival at five twenty five. Even that is a report, not an arrival, so the plan must still work if it slips.

## Slide 5. One checked change, one receipt
_about 44 seconds_

The planner builds the allowed repairs from fixed templates and checks each against the deadline, the people, and the budget. Sixteen are built and three pass. The best is free: swap the demonstrations with the skills exchange, so the demos start at five thirty, after the reported arrival. It is applied at four forty three, and the server writes a receipt, its own record of the change. The AI cannot write it. These frames show my rule baseline. In a recorded run, the AI coordinator made the same check and the same swap.

**Checkpoint 2:22.**

## Slide 6. Four messages, zero changes
_about 47 seconds_

Not acting is the harder skill. Here is a second practice case. First, the same delay notice, but the status check says on schedule, arriving at four fifty eight. A false alarm, so the plan stays. Then a reminder that order P nine for an October workshop was cancelled. That is another order on another date, so it does not apply. (Skip if late: It arrives again, and a volunteer forwards it. One source repeated is still one source.) In the end there is no hold, no spending and no change. Three of my twelve final test cases are quiet ones like this.

**Checkpoint 3:09.**

## Slide 7. Verify, prepare, commit
_about 26 seconds_

Verify one fact that could change the decision. Prepare a backup while a fact or an approval is pending. In another case the projector arrives too late, so Plan B holds the backup until four fifty five and asks the organizer for thirty five dollars. Commit only a plan the server checked. Or keep the plan.

## Slide 8. The model chooses, the server checks
_about 30 seconds_

A policy is the rule that picks the next step. P zero is fixed rules, which only read the messages they were written for. P one lets a model call the tools freely. P two, mine, lets the model pick from options the server built and checked. P three is P two with every relevant check run first. Every policy passes the same gate.

**Checkpoint 4:05.**

## Slide 9. Held-out test of version 1.1: zero violations, no clear winner
_about 38 seconds_

Everything so far came from practice cases I built with. Then I froze version one point one, its code, prompts, model and limits, and ran twelve held-out cases, hidden from every policy. All one hundred twenty runs were recorded. No policy executed a violation or changed a quiet event. But my P two showed no consistent advantage. P one met the expected outcome in all twenty four campus runs, at three times P two's model cost. These are descriptive counts only.

## Slide 10. One failure: a correct reading that never reached the planner
_about 26 seconds_

In one held-out case a volunteer says they will be late. P two and P three read the message correctly. But my frozen rule passes only equipment claims to the planner, so the plan was never questioned. All six of their runs stay in the count. P one met this case every time.

**Checkpoint 5:09.**

## Slide 11. Same loop, a new rule: 40 kits for a fictional pantry
_about 40 seconds_

The same loop runs a fictional pantry. Staff need forty kits by one forty. Twenty four are on the shelf. Twenty more are late, and late stock does not count. Sixteen wait in a partner pool. Plan B holds those sixteen. Only staff record the handoff and the distribution. On four held-out pantry cases, fixed rules met all four runs, and the model policies six to nine of twelve, partly because of a defect in my frozen planner. No kit was counted twice.

**Checkpoint 5:49.**

## Slide 12. Version 1.2: the fixes, then six fresh held-out cases
_about 39 seconds_

Version one point two targets those failures. A person's own delay now reaches the planner, and a pool checked as unavailable is no longer offered. The old cases were spent, so six fresh ones were written without the new code, and locked before any call. Version one point two met fifty nine of sixty runs. Fixed rules missed one late volunteer. The other policies met every run, so this small set cannot rank them. The cases differ, so this is not a before and after.

**Checkpoint 6:28.**

## Slide 13. What works today, and what is next
_about 32 seconds_

Today Plan B verifies, prepares and commits in a local sandbox. Every accepted change has a receipt, and people approve spending. In both held-out tests no policy executed a violation, and my policy showed no consistent advantage.

In real life a message is a text, a status check is a tracking page, and a hold is a refundable reservation. No community has used it yet. Next, I want to review it with community staff. Thank you.

**End 7:00.**

## Backup slides
_about 0 seconds_

_Not timed, and not read out. Use them only to answer a question: one recorded model decision, the report's per-case figures for campus and pantry, what the held-out runs cost, what the held-out numbers do not show, the post-hoc diagnostic rerun of version 1.2 on the spent cases (say "diagnostic, not held-out" whenever you show it), a development failure kept on record, a participant's own check-in, a partial pantry handoff, and the frozen configuration._
