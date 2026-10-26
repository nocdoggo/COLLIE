# Poster notes: the two-minute pitch

Plan B: The Show Must Go On
Noctis Zhang, University of Massachusetts Boston, PEAAII Hackathon, October 2026

The evaluation numbers come from make_results.py. The test shown is the final system on six new held-out cases (wave3b_fresh_20261025T2327Z), written by a separate worker before the final freeze and locked with it, before the first model call. If asked about the earlier, larger test, say it found the defects that were fixed before the freeze, and that its cases are now development cases. If asked about the rerun on those cases, say "diagnostic, not held-out".

Speak at a steady pace, about 140 words a minute, and point at each panel as you reach it, top row first. The one message comes first, so the pitch works even if the listener leaves after twenty seconds. Say the approaches by their plain names, never by codes.

## The scene and the one message
_about 30 seconds_

It is four forty, twenty minutes before a campus showcase opens. A text says the projector may be twenty five minutes late. Plan B helps a community event stay on track by deciding what to verify, what to prepare, and when to commit a change. Jordan, the organizer, is an illustration, and the event runs in a local sandbox.

## What Plan B did
_about 25 seconds_

Plan B treats the text as a claim. It checks the supplier's tracking once: delayed, with a reported arrival at five twenty five. Then it swaps two activities, so the demos start after the reported arrival. It costs nothing, the server writes a receipt, and the doors open on time.

## How it works
_about 25 seconds_

The language model never acts on its own. The server builds the possible fixes and checks each one. The model only picks one of them. Every change passes one gate, which writes the receipt, and spending needs a person.

## Does it work
_about 22 seconds_

I froze the system and ran six new cases it had never seen, close to situations from development. Fifty nine of sixty runs met the expected outcome. The one miss was the fixed rules, when a volunteer ran late. No action broke a rule. Six cases are too few to rank anything.

## Next
_about 13 seconds_

The same loop already runs a food pantry. Next come transit alerts as context, and a pilot with real organizers. The code is behind the QR code.
