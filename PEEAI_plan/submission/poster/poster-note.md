# Poster notes: the two-minute pitch

Plan B: The Show Must Go On
Noctis Zhang, University of Massachusetts Boston, PEAAII Hackathon, October 2026

The held-out numbers come from the committed run wave3_heldout_20261025T1625Z (apps/plan_b/evaluation/results/), through make_results.py.

Speak at a steady pace, about 140 words a minute. The script is about 260 words, so there is time to point. It works even if the listener leaves after the first twenty seconds, because the one message comes first. Point at each column as you reach it.

## Opening, the one message
_about 20 seconds_

Twenty minutes before a campus showcase opens, a message says the projector may be late. Plan B decides what to verify, what to prepare, and when to commit a change. It checks before it changes anything, and it cannot spend money without a person.

## Column 1, one recovery
_about 28 seconds_

Here the message is only a claim, so Plan B makes one status check. The supplier says delayed, arriving at five twenty five. The planner finds a free fix: two activities swap places. The server makes the change and writes a receipt, its own record of what happened. A stale reminder and its forwarded copy change nothing.

## Column 2 and column 3, how it decides and how it was tested
_about 44 seconds_

A language model reads the message and picks one option, but the server built those options and checks every action. I froze the system, then tested it on cases it never saw, against three other coordinators, from fixed rules to a model calling tools freely.

On twelve held-out cases, one hundred twenty runs in all, no policy executed a violation, and none changed a plan that needed no change. But my policy showed no consistent advantage. The model calling tools freely met every campus run, at three times my policy's model cost, and fixed rules met every pantry run.

## The pantry, in one sentence
_about 10 seconds_

The same loop runs a fictional pantry, where late stock does not count and only staff can record a handoff.

## Close
_about 18 seconds_

The limits are on the poster: twelve held-out cases, one model, one reported run, and no pilot yet. Everything is a fictional local sandbox, with no real bookings or partners. The code is on GitHub, through the QR code. Thank you.
