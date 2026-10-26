# Poster notes: the two-minute pitch

Plan B: The Show Must Go On
Noctis Zhang, University of Massachusetts Boston, PEAAII Hackathon, October 2026

The held-out numbers come from committed runs in apps/plan_b/evaluation/results/, through make_results.py: wave3_heldout_20261025T1625Z for version 1.1, the evaluation of record, and wave3b_fresh_20261025T2327Z for version 1.2 on six fresh held-out cases. A rerun of version 1.2 on the spent cases (wave3b_rerun_spent_20261025T2345Z) is a post-hoc diagnostic rerun. If asked about it, say "diagnostic, not held-out".

Speak at a steady pace, about 140 words a minute. The script is about 265 words, so there is time to point. It works even if the listener leaves after the first twenty seconds, because the one message comes first. Point at each column as you reach it.

## Opening, the one message
_about 20 seconds_

Twenty minutes before a campus showcase opens, a message says the projector may be late. Plan B decides what to verify, what to prepare, and when to commit a change. On twelve held-out cases, no policy executed a violation, and there was no clear winner.

## Column 1, one recovery
_about 24 seconds_

Here the message is only a claim, so Plan B makes one status check. The supplier says delayed, arriving at five twenty five. The planner finds a free fix: two activities swap places. The server makes the change and writes a receipt. A stale reminder and its forwarded copy change nothing.

## Column 2 and column 3, how it decides and how it was tested
_about 48 seconds_

A language model reads the message and picks one option, but the server built those options and checks every action. Spending needs a person. I froze the system, then tested it on cases it never saw, against three other coordinators.

On the three cases that needed no change, none changed the plan. But my policy showed no consistent advantage. The model calling tools freely met all eight campus cases, at three times my policy's model cost. After fixes, version one point two met fifty nine of sixty runs on six fresh held-out cases, too few to rank the policies.

## The pantry, in one sentence
_about 10 seconds_

The same loop runs a fictional pantry, where late stock does not count and only staff can record a handoff. No kit was counted twice.

## Close
_about 18 seconds_

The limits are on the poster: twelve held-out cases and six fresh ones, one model, one reported run after a voided first attempt, and no pilot yet. Everything is a fictional local sandbox. The code is on GitHub, through the QR code. Thank you.
