# Presentation notes

Plan B: The Show Must Go On
Noctis Zhang, University of Massachusetts Boston, Paul English Applied AI Institute (PEAAII) Hackathon, October 2026

This script is identical to the \note blocks of slides.tex. The story follows STORY_PLAN.md: one volunteer organizer (Jordan, an illustration), twenty minutes to doors open, the decision, the receipt, then the design, the evidence and what is next. Every evaluation number on the slides comes from make_results.py. The evaluation shown is the final system on six new held-out cases (wave3b_fresh_20261025T2327Z), written by a separate worker before the final freeze and locked in the same commit seven seconds after it, before the first model call. The earlier 12-case test (wave3_heldout_20261025T1625Z) is named once, as the test that found the defects fixed before the freeze. A rerun on its spent cases is a diagnostic and appears only on a backup slide. Never call it held-out.

Slide numbers here count the title as slide 1. The footer counter on the slides does not count the title, so slide 7 here shows 6/9 in its footer.

Read each paragraph at a steady, clear pace, about 140 words a minute. The script fits inside seven minutes with time to point and change slides. Pause briefly each time you advance a slide. The bold checkpoints are the clock times of the plan. Say the policies by their plain names: the fixed rules, the tool-calling model, our coordinator, the check-all variant. Say "recorded" whenever you show a recorded run, and never call it live.

## Slide 1. Title
_about 8 seconds_

Hello, I am Noctis Zhang from UMass Boston. This is Plan B. The show must go on.

**Checkpoint 0:08.**

## Slide 2. 16:40. Twenty minutes to doors open
_about 28 seconds_

Meet Jordan, a volunteer organizer. Jordan is an illustration, and the event is simulated. It is four forty. In twenty minutes the doors of a campus showcase open, and student teams are ready to demo. Then a text arrives: the projector may be twenty five minutes late. Events like this have no operations staff. Would you wait, check, or book a backup?

**Checkpoint 0:36.**

## Slide 3. An agent that acts on a text can spend money on a rumor, so Plan B checks first
_about 45 seconds_

Here is the risk. An AI agent with tools can read that text and act at once. It believes the claim, books the thirty five dollar backup, and reshuffles the whole program. That top lane is an illustration, not one of the systems I tested. Plan B works differently. First it checks the one fact that matters. Then the server builds the possible fixes and checks each one. The language model only picks one of them. And every change passes one gate that writes a receipt, the server's own record of the change. The model chooses. The server decides what is allowed.

**Checkpoint 1:21.**

## Slide 4. Plan B checked one fact, swapped two activities, and the doors opened on time
_about 56 seconds_

Here is what Plan B did. At four forty the text arrives. Plan B treats it as a claim, not a fact. It makes one status check, which means asking the supplier's tracking. The answer is delayed, with a reported arrival at five twenty five. That is still a report, not an arrival. Now the planner builds the possible fixes, sixteen of them, and checks each against the deadline, the people, and the budget. Three pass. The best one is free. The demonstrations and the skills exchange swap places, so the demos start at five thirty, after the reported arrival. At four forty three the change is made, and the server writes a receipt. The doors open on time at five, and no money is spent.

**Checkpoint 2:17.**

## Slide 5. Most messages should change nothing, so Plan B checks only what could change the decision
_about 27 seconds_

Knowing when not to act matters just as much. In another practice case four messages arrive. The first is a false alarm, because the check says on schedule. The second is about another order on another date. The last two are one source, repeated. Plan B changes nothing. Checks are selective. It verifies only what could change the decision.

**Checkpoint 2:44.**

## Slide 6. The model only picks among options the server built and checked, and one gate writes every receipt
_about 60 seconds_

Here is how it works. Think of a restaurant. The kitchen decides what can be served, the waiter picks from the menu, a manager signs off on anything that costs money, and every order gets a ticket. In Plan B the server is the kitchen. Its planner builds the options and checks each one. The language model is the waiter. Its only outputs are a checked reading of the message and one option from the server's list. It holds no tool that writes. Every change, from the model or a person, passes one gate. Is it allowed for this role? Is the plan still current? Is it within budget? Spending starts as a hold, a free reservation that expires on its own, until a person approves. The gate writes the receipt.

**Checkpoint 3:44.**

## Slide 7. On 6 new cases, 59 of 60 runs met the expected outcome, and the one miss was the fixed rules
_about 64 seconds_

Does it work? I froze the code, the prompts, the model and the limits. Then I ran six new cases, written by a separate worker before the freeze and locked with it. Fixed rules ran once per case, the model approaches three times each, all on the same model, Claude Sonnet 5.5. Fifty nine of sixty runs met the expected outcome. Our coordinator met all eighteen of its runs, and so did the other two model approaches. The one miss was the fixed rules, in a case where a volunteer runs late, because a person's own delay is a message its rules cannot read. No action ever broke a rule in these runs, because every change passes the one gate. It refused six attempts and recorded each. With six cases there is no ranking. The point is safety and reliability. An earlier, larger test is how I found and fixed real defects before this freeze.

**Checkpoint 4:48.**

## Slide 8. The same loop runs a food pantry, where food counts only once it is on the shelf
_about 39 seconds_

The same loop runs a second domain, a food pantry. Staff need forty kits by one forty. Twenty four are on the shelf. Twenty more are on a late truck, and late stock does not count. Sixteen wait in a partner pool nearby, and Plan B holds them. Only staff can record the handoff and the distribution, so the AI can never claim food that is not there. The two new pantry cases were part of the test you just saw, and no kit was counted twice in these runs.

**Checkpoint 5:27.**

## Slide 9. Plan B helps the people who run community events, runs on one laptop, and adapts to new events
_about 48 seconds_

Who does this help? Student organizers, clubs, volunteers and pantry staff, the people who run events with little time. It means fewer last-minute scrambles, no surprise spending, and a receipt for every change. It is easy to run. This is the real board on one laptop: install, then one command starts it. Without a model it needs no network at all, and any OpenAI-compatible model can plug in. And it adapts. The same core ran a campus showcase, a skills exchange and a food pantry. Next come real feeds, such as MBTA alerts as context only, and a pilot where Plan B proposes and the organizer acts. No community has used it yet.

**Checkpoint 6:15.**

## Slide 10. 16:40 again. Check first, then change
_about 30 seconds_

So, back to four forty, twenty minutes to doors open. Would you wait, check, or book a backup? Plan B checks the one fact that matters, prepares what it can undo, and commits only a change the server has checked, with a receipt. It helps a community event stay on track by deciding what to verify, what to prepare, and when to commit a change. Thank you.

**Checkpoint 6:41.**

## Backup slides
_about 0 seconds_

_Not timed, and not read out. Use them only to answer a question: what the new test cost per run, what these numbers do not show (including the earlier test and the diagnostic rerun on its spent cases), a partial pantry handoff, and the frozen configuration._
