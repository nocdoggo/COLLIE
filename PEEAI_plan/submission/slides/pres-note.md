# Presentation notes

Plan B: The Show Must Go On
Noctis Zhang, University of Massachusetts Boston, Paul English Applied AI Institute (PEAAII) Hackathon, October 2026

Every held-out number in this script comes from the committed run wave3_heldout_20261025T1625Z (apps/plan_b/evaluation/results/), through make_results.py. Say "held-out" only for those numbers. Everything before slide 9 is development evidence.

Read each paragraph at a steady, clear pace, about 140 words a minute. The full script is about 950 words, which leaves room to point and to change slides inside the seven minutes. Rehearse to about six minutes fifty. Pause briefly each time you advance a slide. A sentence marked "skip if late" can be dropped without losing the story. The bold checkpoints are the clock times of the seven-minute plan. If you are behind at a checkpoint, skip the marked sentences of the next slide.

Everything shown is a fictional local sandbox. Say "recorded" whenever you show a recorded run, and never call it live.

## Slide 1. Title
_about 10 seconds_

Hello, I am Noctis Zhang from UMass Boston. This is Plan B. It decides what to verify, what to prepare, and when to commit a change.

## Slide 2. Twenty minutes before opening, the projector may be late
_about 27 seconds_

Imagine you organize a campus showcase. It opens at five and must end by six. At four forty, a message says the projector may be twenty five minutes late. Change too much and people lose time. Wait too long and the demos fail. AI agents now act on messages like this. Would you wait, check, or prepare a backup?

**Checkpoint 0:37.**

## Slide 3. The coordinator may check, hold and make free changes, not spend
_about 35 seconds_

Plan B is a coordinator, an AI agent with written limits. It may check sources, compare options, and place a hold. A hold is a free reservation of a backup that expires on its own, here worth up to thirty five dollars. It may also make a change that costs nothing. It cannot spend a cent without the organizer. Everything runs in a fictional local sandbox. (Skip if late: Participants and staff have their own narrow rights.)

**Checkpoint 1:12.**

## Slide 4. A message is a claim, not a fact
_about 35 seconds_

Here is the notice, from the delivery contact. Plan B treats it as a claim, not a fact. Before changing anything, it checks the one fact that could change the decision. A status check asks the supplier's status service. In this sandbox that takes two simulated minutes. The answer is delayed, with a reported arrival at five twenty five. Even that is a report, not an arrival, so the plan must still work if it slips.

## Slide 5. One checked change, one receipt
_about 48 seconds_

Now the planner builds the allowed repairs from fixed templates, like a swap or a ten minute shift, and checks each against the deadline, the people, and the budget. Sixteen are built and three pass. The best is free: swap the demonstrations with the skills exchange, so the demos start at five thirty, after the reported arrival. It is applied at four forty three, and the server writes a receipt, its own record of the change. The AI cannot write it. These frames show my rule baseline. In a recorded run, the AI coordinator made the same check and the same swap.

**Checkpoint 2:35.**

## Slide 6. Four messages, zero changes
_about 50 seconds_

Not acting is the harder skill. Here is a second practice case, in the order it happened. First, the same delay notice, but the status check says on schedule, arriving at four fifty eight. A false alarm, so the plan stays. Then a reminder that order P nine for an October workshop was cancelled. That is another order on another date, so it does not apply. (Skip if late: It arrives again, and a volunteer forwards it. One source repeated is still one source.) In the end there is no hold, no spending and no change. Three of my eight final test cases are quiet ones like this.

**Checkpoint 3:25.**

## Slide 7. Verify, prepare, commit
_about 28 seconds_

So the loop is simple. Verify one fact that could change the decision. Prepare a backup while a fact or an approval is pending. In another case the projector arrives too late, so Plan B holds the backup until four fifty five and asks the organizer for thirty five dollars. Commit only a plan the server checked. Or keep the plan.

## Slide 8. The model chooses, the server checks
_about 30 seconds_

A policy is the rule that picks the next step. P zero is fixed rules, which only read the messages they were written for. P one lets a model call the tools freely. P two, mine, lets the model pick from options the server built and checked. (Skip if late: P three is P two with every relevant check run first.) Every policy passes the same gate.

**Checkpoint 4:23.**

## Slide 9. Held-out test: zero violations, no clear winner
_about 50 seconds_

Everything so far came from development cases, practice cases I built with. Then I froze the code, the prompts, the model and the limits, and ran held-out cases, hidden from every policy. A first attempt hit the provider's rate limit, so I voided it and kept it on record. In the reported run all one hundred twenty runs were recorded. The server refused fifty five requests in all, and no policy executed a violation or changed a quiet event. But my P two showed no consistent advantage. P one, the model calling tools freely, met all twenty four campus runs, at three times P two's model cost. On the pantry, fixed rules met every run.

## Slide 10. One failure: a correct reading that never reached the planner
_about 26 seconds_

Here is one failure. In one held-out case a volunteer says they will be late. P two and P three read the message correctly. But my frozen rule passes only equipment claims to the planner, so the plan was never questioned. All six of their runs stay in the count. P one met this case every time.

**Checkpoint 5:39.**

## Slide 11. Same loop, a new rule: 40 kits for a fictional pantry
_about 50 seconds_

The same loop also runs a fictional pantry, with a new rule about quantities. Staff need forty kits by one forty. Twenty four are on the shelf. Twenty more are late, and late stock does not count. Sixteen wait in a partner pool at the same venue. Plan B holds those sixteen. Only staff can record the handoff, which fills the shelf to forty. And only the recorded distribution brings the kits not yet handed out to zero. On four held-out pantry cases, fixed rules met all four runs, and the model policies six to nine of twelve, partly because of a defect in my frozen planner. No kit was counted twice.

**Checkpoint 6:29.**

## Slide 12. What works today, and what is next
_about 31 seconds_

Today Plan B verifies, prepares and commits in a local sandbox. Every accepted change has a receipt, and people approve spending. On held-out cases no policy executed a violation, but my policy showed no consistent advantage over the others.

In real life a message is a text, a status check is a tracking page, and a hold is a refundable reservation. Next, I want to review these workflows with community staff. Thank you.

**End 7:00.**

## Backup slides
_about 0 seconds_

_Not timed, and not read out. Use them only to answer a question: one recorded model decision, the report's per-case figures for campus and pantry, what the held-out runs cost, what the held-out numbers do not show, a development failure kept on record, a participant's own check-in, a partial pantry handoff, and the frozen configuration._
