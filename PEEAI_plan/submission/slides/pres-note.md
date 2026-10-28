# Plan B, The Show Must Go On. The seven-minute script

> Noctis Zhang and Zhen Lu, Department of Computer Science, University of Massachusetts Boston. Yinzhi Jin, Department of Management Information Systems, Carnegie Mellon University. PEAAII AI Applications Hackathon 2026, October 2026.
> Fourteen slides, at most 420 seconds at 140 words a minute (the timing tool prints the count). The italic line under each heading is a stage direction (the planned seconds and the clock at the end of the slide). It is not spoken, and the timing tool skips it.
> The speaker notes in the deck source say exactly what this file says. The sync tool in the tools folder copies them, and the writing check compares them.
> Three ideas carry the talk. Check the fact. Pick only what fits. Leave a receipt, and money waits for a person's OK. Slide 3 announces them, slides 4 to 6 deliver them on Jordan's evening, slide 7 shows the real board, and slide 14 repeats them.

## Slide 1. Plan B, The Show Must Go On

_about 13 seconds, ends 0.13_

Hello, I am Noctis Zhang, from the Department of Computer Science at UMass Boston. This is Plan B. The show must go on. Plan B checks before it changes anything.

## Slide 2. Twenty minutes before doors open, Jordan gets a text

_about 33 seconds, ends 0.46_

Meet Jordan, a volunteer organizer we made up. Jordan runs a small campus showcase. The projector is due at five, when doors open, and the demonstrations at ten past five need it. At four forty, a text arrives. The projector may be twenty five minutes late. Wait and hope? Spend thirty five dollars of club money on a maybe? Reshuffle the evening alone? Small events change by text, and a wrong move costs money or the evening.

## Slide 3. Plan B rests on three simple ideas

_about 18 seconds, ends 1.04_

So how does Jordan decide in twenty minutes? Plan B rests on three simple ideas. Check the fact. Pick only what fits. Leave a receipt. And money waits for a person's OK. Let me show you each one on Jordan's evening.

## Slide 4. First, Plan B checks the one fact that matters

_about 25 seconds, ends 1.29_

First, check the fact. A message is a claim, not a fact. So Plan B changes nothing yet. It looks up the one fact that could change the plan, the delivery. In our rehearsal, the answer is delayed, expected about five twenty five. Most messages, like a false alarm, should change nothing, and then Plan B keeps the plan.

## Slide 5. Then the AI picks only from changes that fit

_about 39 seconds, ends 2.08_

Second, pick only what fits. Plan B lists every allowed change, sixteen in all. It throws out every change that breaks the time, the people or the budget. Three fit. The AI picks one of the three, the free swap. The demonstrations move to five thirty, after the projector should arrive. Why only pick? The AI reads messy messages well, but can answer differently each time. So the AI only chooses among changes that fit, and Plan B makes the change. In an earlier recorded run, the AI made this same pick.

## Slide 6. Every change leaves a receipt, and money waits for a person's OK

_about 43 seconds, ends 2.51_

Third, leave a receipt. Plan B checks every change against the rules before it happens, and if a check fails, it keeps the plan. Then it writes a receipt, a record of what changed, when, and what it cost. At four forty three, version one became version two, for zero dollars, and the thirty five dollar backup was never booked. Money waits for a person's OK, because club money is a person's call. In a separate practice case, not Jordan's, the projector came too late. Plan B held the backup for free, so it was not lost while a person decided.

## Slide 7. This is the real board after the swap

_about 12 seconds, ends 3.03_

Here is the real board after the swap. In this rehearsal the fixed rules, with no AI, made the same swap. Jordan shares this plan with the group chat.

## Slide 8. We tested Plan B on event days it had never seen

_about 37 seconds, ends 3.40_

One evening is a story, not proof. A test case is a small made-up event day, written in advance, with messages that arrive at set times. We run it in a rehearsal on a computer, with a clock we can speed up, where nothing real is booked or bought. At the end, code checks the final state. Did every activity happen, and was no rule broken? The six final cases were sealed, written and locked before the test and never seen by whoever changed the code.

## Slide 9. 59 of 60 runs met the expected outcome

_about 38 seconds, ends 4.18_

Each case ran once with the fixed rules, and three times with each of three AI designs, ours, a check-all variant and a tool-calling model, because the AI can answer differently each time. Fifty nine of sixty met the expected outcome, meaning every final check passed. Every AI run met it. The fixed rules missed one, a late volunteer's own text, the kind of message the AI is there to read. No executed action broke a rule. Six cases are a small check, not a ranking.

## Slide 10. Inside Plan B, careful with messages and money

_about 34 seconds, ends 4.52_

Inside Plan B, the same ideas guard messages and money. In our coordinator the AI only picks a change from the list, so a misleading message can at most lead to a choice that already fits. Money needs a person's OK, and if nobody answers, nothing is bought. Every message goes to an outside AI service, so keep names and health details out of messages. Not shown yet. Only six test cases, made-up events, one AI model, no trial.

## Slide 11. Built for student clubs and volunteer groups

_about 25 seconds, ends 5.17_

So who is it for? Student club officers come first. Then volunteer coordinators and pantry staff. Two of the six test cases were days at a made-up food pantry, and all twenty runs met. For a student it is simple. It checks the text before you spend club money, and leaves the treasurer a record of why.

## Slide 12. Other tools help, and Plan B works beside them

_about 28 seconds, ends 5.45_

Indirect competitors first. Today the text lands in a group chat, a shared sheet, a sign-up sheet or a campus portal. Direct competitors, event platforms such as Sessionboard, check agenda changes, and Cvent and Bizzabo have announced agents. AI assistants ask before they buy. These pieces are not new. Plan B puts them together for a small group on the day of an event.

## Slide 13. Plan B is safer, more flexible and more personal

_about 35 seconds, ends 6.20_

So why Plan B? Safer, because the three ideas are built in, where in Zapier the user adds the approval step. More flexible, because Cvent and Bizzabo build for event teams, and Plan B ran campus, community and pantry events on one laptop, with your AI model or none. More personal, because ChatGPT and Gemini ask before buying the way their makers designed, and here your group writes its own event and its own spending limit. We have not tested the others.

## Slide 14. Check the fact, pick only what fits, leave a receipt

_about 37 seconds, ends 6.57_

So, three ideas. Plan B checked the fact, so Jordan did not spend club money on a maybe. The AI picked only from changes that fit. And every change left a receipt, and money waited for a person's OK. Doors opened at five, the projector came at five twenty four, and the demonstrations started at five thirty. The code is free. Next is a walk-through on paper with community staff, so please tell me where it goes wrong. Thanks to the PEAAII organizers, and to you.
