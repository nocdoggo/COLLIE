# Submission draft plan: the three hackathon items

Status: plan and draft, written 2026-10-25 while the Wave 3 held-out evaluation was still
running. The final step (section 13) filled every placeholder from the committed run and revised
the plan where the results changed the story. Sections 1 to 12 are kept as written. Wave 3b later
added version 1.2 and slide 12 on its fresh held-out cases (see `README.md`, "Where the numbers
come from").
Nothing in sections 1 to 12 is a Wave 3 result. Every Wave 3 number is a named placeholder with the
file it must come from. A later worker (`submission`) fills the placeholders from the committed
results and finishes the items. This is the revised plan: the three critiques of the first
version and the decisions taken from them are in sections 11 and 12, and the build status in section 10.

The three required items:

1. **Project Documentation**: a Word document (`documentation/Plan_B_Project_Documentation.docx`)
   plus the GitHub repository link: https://github.com/nocdoggo/COLLIE, branch
   `hackathon/peeaai-plan`, app path `apps/plan_b`. The owner pushed the branch at `26cf424`, and
   the direct link opens the app.
2. **The 7-Minute Project Presentation**: the slide deck `slides/slides.pdf` with speaker notes
   and the spoken script `slides/pres-note.md`.
3. **The 2-Minute One-Slide Presentation**: a horizontal (16:9) poster `poster/poster.pdf` and its
   spoken script `poster/poster-note.md`.

Author on every item: **Noctis Zhang**, the only member, no team name, University of
Massachusetts Boston. The presenter is named or called "the presenter", never with a gendered
pronoun. The scripts say "I", not "we".

## 1. Audiences and the one message

| Audience | Situation | What they need | What they should take away |
| --- | --- | --- | --- |
| Hackathon judges, 7-minute talk | Seated, one pass, then questions. Mixed technical depth. Many talks in a row | The stakes in the first 30 seconds, proof that the system really acts and that the AI really decides, an honest result, why it matters for a community | One recovery, one avoided change, one measured result and its limit |
| People walking past the poster, 2 minutes | Standing, may leave after 20 seconds | The problem and the idea readable from two meters, one picture of one recovery, one result | The one message, and that it was tested on cases it never saw |
| A reader of the documentation | At a desk, may try the code | Complete, checkable explanation: what it does, how, how it was tested, the exact counts, the limits, how to run it | Enough to reproduce the demo and audit every number |

**The one message to remember** (from `09_seven_minute_presentation.md`):

> **Plan B helps a community event stay on track by deciding what to verify, what to prepare,
> and when to commit a change.**

The hook that carries it (from the judge's critique): *when a last-minute message threatens an
event, Plan B checks before it changes anything, and it cannot spend money without a person.*
The stakes: AI agents are starting to book and buy things for people, and acting on a wrong or
stale message is the failure that matters.

## 2. Story arc and why each part earns its time

1. **The human problem (0:00 to 0:35).** You are the volunteer organizer of a campus showcase,
   and an hour before it opens a message says the projector may be late. Everyone has felt this.
   The rest of the talk is about this one event.
2. **What the coordinator may and may not do (0:35 to 1:10).** Authority before intelligence.
   Judges trust an agent that cannot spend money on its own. One new term: a **hold**.
3. **The recovery (1:10 to 2:40).** The proof that the system acts: the message is a claim, one
   status check confirms it, the planner checks the options, one free change is made official
   with a **receipt**. The most important 90 seconds. It also says plainly that these frames are
   the rule baseline and that the AI coordinator made the same moves in a recorded run.
4. **Three messages, zero changes (2:40 to 3:35).** Doing nothing on purpose is the less obvious
   skill, and three of the eight test cases measure exactly that.
5. **The mechanism (3:35 to 4:30).** One loop picture with this event's real examples on each
   branch (so "prepare" is shown, not told), then "the model chooses, the server checks": the
   four policies P0 to P3 behind one gate, and one real model decision from a recorded run. This
   answers "why AI" and "what is different".
6. **The evidence (4:30 to 5:40).** How the test was kept fair (practice cases, then a freeze,
   then held-out cases run once), the headline counts, and one failure kept on record. This is
   what makes the project more than a demo.
7. **The second domain (5:40 to 6:25).** The pantry cameo: the same loop with a quantity rule a
   schedule cannot fake. Late stock is not stock, and only distribution serves anyone.
8. **Close (6:25 to 7:00).** What works today, what the sandbox stands for in real life, what
   was not shown, the next step with community staff. Repeat the one message.

## 3. Deck plan, slide by slide (12 slides, 420 seconds)

The deck uses the ICML_pres elegant beamer theme (`style=gray`, primary colour `#08457E`), its
page size (200 mm by 130 mm) and its writing style: a short title that states the point, two to
four bullets with **bold** key terms and `\emphasize` highlights, a figure on every content
slide, and `\note{...}` speaker notes that hold the same text as `pres-note.md`.

Pace: about 140 spoken words per minute, budget about 85 percent of `seconds × 140 / 60` so
there is time to point and switch. Whole script about 830 words, rehearsed to about 6:40.

| # | Clock | s | Words | Title (the claim) | Points on the slide | Figure | What the presenter says (gist) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0:00 to 0:06 | 6 | 12 | Plan B: The Show Must Go On | Subtitle "Deciding what to verify, what to prepare, and when to commit a change". Noctis Zhang, University of Massachusetts Boston. "Paul English Applied AI Institute (PEAAII) Hackathon, UMass Boston, October 2026" | UMB logo lockup | Name, school, project. The hook starts while the title is up |
| 2 | 0:06 to 0:35 | 29 | 58 | An hour before the show, the projector may be late | **Fictional campus showcase**: five activities, opens 17:00, must finish by 18:00. At 16:40 a message: the projector may be about 25 minutes late. Change too much and people lose time. Wait too long and the demos fail. AI agents are starting to act for people, and acting on a wrong message is the failure that matters | `fig_timeline` (Gantt 16:30 to 18:00, demonstrations need the projector) | "You are the volunteer organizer…" then ask: "Would you wait, check, or prepare a backup?" |
| 3 | 0:35 to 1:10 | 35 | 69 | The coordinator may check, hold and make free changes, not spend | The **coordinator** (the AI agent) may check sources, compare options, place a **hold** (a free, expiring reservation of a backup, here up to $35) and apply a checked change that costs nothing. **Spending** needs the organizer. Participants and staff have their own narrow rights. Everything runs in a **fictional local sandbox** | `fig_roles` (who may do what, one gate under all of them) | "It cannot spend a cent without the organizer." [skip if late: the participant and staff boxes] |
| 4 | 1:10 to 1:50 | 40 | 79 | A message is a claim, not a fact | The notice comes from the delivery contact at 16:40. One **status check** (asking the supplier's status service, two simulated minutes): delayed, reported ETA 17:25. A reported time is still not an arrival | Two tight real crops joined by a TikZ arrow: the notice (`story_04`) and the status check line (`story_05`), arrow label "1 status check, 2 simulated minutes" | "Before changing anything, it checks the one fact that could change the decision." |
| 5 | 1:50 to 2:40 | 50 | 99 | One checked change, one receipt | The **planner** builds the allowed repairs from fixed templates (keep, swap, shift by ten minutes, the approved backup) and checks each against the deadline, people and budget: 16 built, 3 pass. Best: swap demonstrations and skills exchange, cost $0. Made official at 16:43 with a **receipt** (the server's record of an accepted change), plan version 1 to 2. Shown here: the rule baseline. The AI coordinator made the same check and the same swap at 16:43 in a recorded development run | `fig_swap` (Gantt before and after with the 17:25 ETA line) and the real receipt line crop from `story_07` | "The receipt is the evidence. The server writes it, the AI cannot." |
| 6 | 2:40 to 3:35 | 55 | 109 | Three messages, zero changes | Case dev04, in the order it happened: (1) the same delay notice, but the status check says on schedule, ETA 16:58: a false alarm, keep the plan. (2) A reminder that order P09 for an October 29 workshop was cancelled: another order, another date, so it **does not apply**. (3) The reminder again, then a volunteer's forwarded copy: one source repeated is one source, a **duplicate**. Plan version 1 kept, no hold, no spending | `fig_quiet` (TikZ: three message cards in time order, each with its verdict, ending in "plan version 1 kept") | "Three of the eight test cases are quiet ones like this. Changing nothing is the right answer." [skip if late: the re-delivery] |
| 7 | 3:35 to 4:05 | 30 | 60 | Verify, prepare, commit | **Verify** one fact that could change the decision. **Prepare** a backup while a fact or an approval is pending. **Commit** only a plan the server checked. **Keep** the plan when nothing should change. Every step returns to the next decision with what actually happened | `fig_loop` with this event's examples on each branch (verify: delayed, 17:25. Prepare: with a 17:45 ETA the backup is held until 16:55 and the organizer is asked to approve $35. Commit: the swap at 16:43. Keep: the stale reminder) | Walk the loop once. "Prepare" is the paid backup case in one sentence |
| 8 | 4:05 to 4:30 | 25 | 50 | The model chooses, the server checks | A **policy** is the rule that picks the next step. **P0** fixed rules. **P1** a language model that calls the tools itself. **P2** (ours) a model that picks one of the options the server built. **P3** P2 with every relevant status check run first. Same tools, same rights, same gate. Why a model: rules only read message forms they were written for. One real decision from a recorded development run | `fig_architecture` (four policies, one gate, state and receipts, the planner feeding the options) and a small TikZ callout of the recorded card (`story_12`): "model chose: apply the backup projector, 3.75 s, $0.0135. Server checked it, receipt rcpt_0003" | Contrast only P1 and P2 aloud. "Whatever the model says, only checked actions reach the state." [skip if late: P3] |
| 9 | 4:30 to 5:15 | 45 | 89 | [Result headline, set from the counts] | Fair test strip: practice on **development cases** (cases I built with) → **freeze** code, prompts, model and limits → run **held-out cases** (written and locked before the test, never seen in development, hidden from every policy) once, three trials per model policy. Planned 80 campus and 40 pantry runs, completed [R_CAMPUS_COMPLETED] and [R_PANTRY_COMPLETED]. Four-row table in words: goal completion on C01 to C07, unnecessary changes on the quiet cases C02 to C04, refused requests and executed violations | `fig_freeze` strip on top, the four-row k/n table below (placeholders) | Read two numbers and the tradeoff in plain words. No claim beyond the counts |
| 10 | 5:15 to 5:40 | 25 | 50 | One failure, on record | One held-out run that missed its goal or added cost: what the policy did, where it first went wrong, what the receipts show. Kept in the denominator | A short step list drawn from the public trace, no case contents ([R_FAILURE]) | "We keep failures in the count." |
| 11 | 5:40 to 6:25 | 45 | 89 | Same loop, a new rule: 40 kits for a fictional pantry | **Fictional pantry sandbox**. Staff need 40 kits by 13:40. 24 on the shelf, 20 more are late and **do not count**, 16 wait in a partner pool at the same venue. The coordinator holds the 16. Only **staff** record the handoff (24 + 16 = 40 on the shelf) and the distribution (40 handed out). Two counters: **supply shortfall** (kits still missing from the shelf) and **service deficit** (kits not yet handed out). Pantry suite: [R_PANTRY_HEADLINE] | `fig_pantry` (four moments: start, hold, handoff, distribution) | The 45-second cameo from 09, read from the counters. [skip if late: the counter names] |
| 12 | 6:25 to 7:00 | 35 | 69 | What works today, and what is next | Works: verify, prepare, commit in a local sandbox. Every accepted change has a receipt, people approve spending and attest physical events. Tested: [R_HEADLINE_SHORT]. In real life a message is a text, a status check is a tracking page, a hold is a refundable reservation. Not shown: real bookings, real stock, community validation. Next: review the workflows with community staff | `fig_qr` (repository) and the UMB logo | Repeat the one message. "Thank you." |
| | | **420** | **830** | | | | |

**Backup slides** after the close, not timed, for questions:

- B1 The recorded decision card (`story_12` crop, labelled "Recorded replay of a Wave 2
  development run, policy live/1.0.0"). Defines a **replay**: it re-shows a recorded run and never
  calls a tool.
- B2 The report's figure (`<run>/report/figure.svg`, printed with the light colour scheme).
- B3 The per-case table.
- B4 The Wave 2 development failure kept on record (P1's first pantry run: a defect in my P1
  harness, fixed, rerun 40 of 40).
- B5 A participant's own check-in changes the plan (`story_16`, `story_17`, development case
  skills_dev01).
- B6 The pantry partial handoff (development case pantry_dev02: 10 of 16, 34 distributed, a
  6-kit deficit). Labelled development so it is not read as a held-out case.
- B7 The frozen configuration (policy ids, model, limits, seeds).

## 4. Poster plan (one horizontal slide, 2 minutes)

Format: the Overleaf Gemini beamerposter with the `umb` colour theme, landscape
`size=custom,width=121.92,height=68.58` (48 by 27 inches, exactly 16:9). It must work as one
projected slide, so: three columns, `scale` about 2.2 (body near 55 pt, about 1/35 of the page
height), Lato Regular instead of Light for projection, at most about 170 words of body text, and
no screenshot or report figure as a main figure. Fonts: Raleway and Lato are in TeX Live 2026
(checked with `luaotfload-tool`), so the template's font families are kept.

- **Header**: title "Plan B: The Show Must Go On", author Noctis Zhang, University of
  Massachusetts Boston. Left: the white UMB lockup. Right: a QR code of the repository link on a
  white card (a standalone `qrcode` figure, no network).
- **Band** (at most 20 words): the one message, then the headline result ([R_POSTER_HEADLINE]).
- **Column 1, "One late projector"**: the four-step strip (message, checked, changed, receipt),
  drawn vertically, then one line: "A stale reminder and its forwarded copy change nothing."
- **Column 2, "How it decides"**: the loop with its examples, then "The model chooses, the server
  checks", one line on P0 to P3 in words, one line on the pantry rule.
- **Column 3, "Tested on cases it never saw"**: the freeze in one line, the four-row result
  table (placeholders), one limit, the repository link.
- **Footer**: "Fictional local sandbox: no real bookings, purchases, stock or messages. No
  partnership is claimed." and the link with the branch and app path.

**The 2-minute script** (`poster/poster-note.md`, about 235 words, so there is time to point):
0:00 to 0:20 hook and the one message (about 40 words), 0:20 to 0:55 the recovery with its
receipt and the copy that changed nothing (70), 0:55 to 1:30 the held-out counts and one limit
(70), 1:30 to 1:45 the pantry in one sentence (30), 1:45 to 2:00 sandbox and link (25). Opening
line: "An hour before a campus showcase, a message says the projector may be late. Plan B
decides what to verify, what to prepare, and when to commit a change." No P0 to P3 names in the
pitch ("three other policies, from fixed rules to a model calling tools freely"), no ids, caps or
seeds.

## 5. Documentation outline (Word, US Letter)

Built by `documentation/build_doc.py` with python-docx 1.1.2 (`uv run --no-project --with
python-docx==1.1.2 python build_doc.py`). Built-in Heading 1 to 3 styles, real Word bullet and
numbered lists (List Bullet, List Number with restarts), tables with explicit column widths,
embedded PNG figures with captions, core properties title "Plan B: The Show Must Go On, Project
Documentation" and author "Noctis Zhang". About 12 to 16 pages.

| Section | What goes in it |
| --- | --- |
| Title block | Title, subtitle, Noctis Zhang, University of Massachusetts Boston, the repository link, branch and app path |
| Abstract | Five sentences: problem, idea, what was built, how it was tested (held-out placeholders), the main limit |
| 1. Problem and motivation | Small community events run on volunteers and fixed rooms. Messages are claims of mixed quality. Changing too much costs people time, waiting too long breaks the event. Why an agent that acts needs bounded authority |
| 2. What is different here | Related approaches in plain words (ordinary tool-calling agents, rule systems, plan repair) and what Plan B does differently: the model picks only among options the server built and checked, holds make preparation reversible, and every accepted change has a receipt. No claim of being first |
| 3. What Plan B does | The three moves and the two quiet outcomes (keep the plan, report that no recovery exists). The fictional sandbox. The roles and their rights |
| 4. A recovery, step by step | dev01 from the notice to the receipt, dev04 (three messages, zero changes), dev02 (hold until 16:55, organizer approves $35, commit). Which runs were rule baseline and which were the AI coordinator |
| 5. Architecture | Figure. FastAPI server, SQLite store, the executor, the planner, the scenario runner and clock, the policies, the provider, the browser board, trace export and replay. Runtime dependencies FastAPI, uvicorn and Pydantic only |
| 6. The decision policy | The loop. When a check is worth it, what a hold buys, when to commit. When the model is called (a new notice the server cannot resolve, or a menu that offers an action). The server builds the options, the model returns one option id, the server validates |
| 7. The agent and the comparison policies | P0 to P3 with ids and prompt versions, the model and provider, the limits, why P1 is a serious baseline, why P3 is an ablation, P3's checks run by the server |
| 8. Community participation | Role sessions with one-time join codes, a participant's own check-in, the kit steward's offer in the skills exchange (campus offers are refused), organizer approval in its own session |
| 9. The pantry extension | Consumable stock, quantity holds, staff-only receipt and distribution, the two counters, the 24 + 16 = 40 sequence, the partial handoff (development case pantry_dev02). A shared core with a domain extension, not zero-shot transfer |
| 10. Safety and authority boundaries | Grants enforced by the executor, plan versions (revisions) checked on every change, repeat keys (idempotency), hold expiry, message text treated as data, model rationale shown as untrusted, the public and evaluator-only split, spend caps and the ledger, the key read by the server at call time (and the audit scripts' disclosed reads) |
| 11. Evaluation protocol | Development cases versus held-out cases, the public C01 to C08 and T01 to T04 conditions, 80 + 40 planned runs, the freeze (commit 3de5962), seeds recorded but not sent, the limits, metric definitions, what counts as a failure, caveats (P2 versus P0 does not isolate the decision policy from language reading, P3's fewer model calls are not less checking) |
| 12. Results | Placeholders: completed counts and denominators per suite, the campus table, the pantry table, the figure, one success and one failure, the honest tradeoff, spend. Then the functional evidence (tests, walkthroughs, storyboard, rehearsals) |
| 13. Limitations and what was not done | Section 8 of this plan, in full |
| 14. How to run it | Dash-free exact commands (decision D7), the moderator code, the replay, where the evaluation commands are documented |
| 15. Demo guide | The talk's segments with the case to load and what to point at, the fallback to replay |
| 16. Ethics and the fictional sandbox | No real people, rooms, bookings, purchases, stock or messages. U-ACCESS only as public context. No recipient identities or eligibility decisions. Paid model calls only under caps |
| 17. Future work | Workflow review with community staff, explicit authorization state, the MBTA adapter, more cases and models, human rehearsals |
| Appendix A. Glossary | One line per term: hold, receipt, revision (plan version), status check, grant, policy, P0 to P3, held-out case, development run, replay, executor, planner, supply shortfall, service deficit |
| Appendix B. File map | The main paths under `apps/plan_b` and `PEEAI_plan/` |
| Appendix C. Evidence index | Every number in the document with its source file |

## 6. Figures

| Figure | Status | Source and method | Used in |
| --- | --- | --- | --- |
| `fig_timeline` program 16:30 to 18:00 and the 16:40 message | drawn | TikZ standalone, times from the dev01 fixture | slide 2, doc 4 |
| `fig_roles` who may do what, one gate | drawn | TikZ, grants from `story_03` and RUNTIME_CONTRACT sections 2 and 15 | slide 3, doc 3 and 10 |
| `fig_claim` the notice and the status check | drawn | TikZ around two real crops (`notice`, `status_line`) | slide 4 |
| `fig_swap` before and after the swap with the 17:25 ETA line | drawn | TikZ, dev01 times from `story_07` | slide 5, doc 4 |
| receipt line crop | cropped | `story_07`, the line "Plan version 1 → 2 … receipt rcpt_0001" | slide 5 |
| `fig_quiet` three messages, zero changes | drawn | TikZ, notice texts from `scenarios/private/dev04.json`, verdicts from `story_08` | slide 6, doc 4 |
| `fig_loop` verify, prepare, commit, keep, with examples | drawn | TikZ | slide 7, poster, doc 6 |
| `fig_architecture` four policies, one gate | drawn, with the recorded decision card inside | TikZ from the README and RUNTIME_CONTRACT | slide 8, doc 5 |
| `fig_freeze` practice, freeze, held-out | drawn | TikZ | slide 9, doc 11 |
| `fig_pantry` four moments and two counters | drawn | TikZ, DEMO.md section 4 and `pantry_accounting.json` | slide 11, poster, doc 9 |
| `fig_strip` one recovery in four steps | drawn | TikZ | poster (vertical variant), doc abstract |
| `fig_qr` repository QR code | drawn | TikZ `qrcode` package | slide 12, poster |
| Frame crops (`crop_frames.py`) | cropped | Pillow from `handoffs/wave_2/evidence/storyboard/` | slides 4, 5, backup, doc |
| Results figure | to come | `<run>/report/figure.svg`, printed to PDF with the light scheme through the app's Playwright Chromium | backup B2, doc 12 |

All TikZ figures are standalone files in `slides/figures/`, compiled with pdflatex, and
rendered to PNG at 200 dpi with pdftoppm for the Word document. The poster includes the same
PDFs. Time ranges in figures are written "17:10 to 17:30", never with a dash.

## 7. Every number the items will cite

### Wave 1 and Wave 2 (development evidence, labelled so)

| Number | Value | Source |
| --- | --- | --- |
| Development cases at Wave 1, all matched | 5 (dev01, dev02, dev04, dev05, dev06) | `handoffs/wave_1/README.md` |
| dev01 program | five activities, 16:30 to 18:00, opens 17:00, only the demonstrations need the projector, budget $150 | `scenarios/public/campus_showcase.json`, `story_01` |
| dev01 notice | from the delivery contact, observed 16:39, received 16:40, "about 25 minutes later" | `story_04` |
| dev01 check | one status check of 2 simulated minutes, delayed, reported ETA 17:25 | `story_05`, `storyboard_report.json` steps 5 to 7, RUNTIME_CONTRACT section 4 |
| dev01 options | 16 generated, 3 feasible, 13 rejected | `story_06`, `story_07` |
| dev01 commit | swap at 16:43, `rcpt_0001`, plan version 1 to 2 (state revision 4 to 5), $0 | `story_07`, DEMO.md lines 164 to 174 |
| AI coordinator on dev01 | P2 made the same check and swap at 16:43 (`rcpt_0001`, revision 4 to 5), 3 model calls, $0.0366 | `evaluation/development/README.md`, `live_p2-live_dev01_run.json` |
| dev02 paid backup | ETA 17:45, `hold_0001` until 16:55, organizer raises the limit to $35.00, committed once | `story_09` to `story_11`, DEMO.md |
| dev04 three messages | false alarm (on schedule, ETA 16:58), P09 for an October 29 workshop (not P17, not 5 November), re-delivered and forwarded copy, plan version 1 kept, no hold or spend | `scenarios/private/dev04.json`, `story_08` |
| Agent grant | holds up to $35.00, $0.00 committed, may apply free plan changes | `story_03`, RUNTIME_CONTRACT section 2 |
| Rejection demo (Wave 1) | 20 steps, all expected | wave_1 README |
| Model | `anthropic/claude-sonnet-5.5` through OpenRouter | wave_2 README |
| Recorded decision card (B1, slide 8 callout) | a model call chose, 3.75 s, $0.0135, 6 of 8 model calls, `rcpt_0003`, policy `live/1.0.0` | `story_12`, DEMO.md section 4 lines 238 to 242 |
| Development runs of P1 to P3 | 20 recorded, 15 current all matching, 5 superseded | `evaluation/development/README.md` |
| Pantry canonical (pantry_dev01) | target 40 by 13:40, 24 on hand, 20 expected, 16 partner, 24/16 to 40/0, 40 of 40 on time | DEMO.md section 4, `pantry_accounting.json` |
| Pantry partial (pantry_dev02) | 10 of 16 handed off, 34 distributed, 6-kit deficit | wave_2 README |
| P1 development failure | 6 refused holds, 0 of 40, a defect in my P1 harness, rerun 40 of 40 | `evaluation/development/README.md` |
| Paid spend through Wave 2 | 2.91545 USD in 136 calls | `evidence/reports/model_spend_summary.json` |
| Wave 2 test counts (superseded by R_TESTS) | 766 Python, 392 web, 41/41, 30/30, storyboard 32/32 | wave_2 README |

### Wave 3 frozen configuration (committed in 3de5962)

Policies P0 `rules/1.0.0` and `pantry-rules/1.1.0`, P1 `tool-use/1.1.0` (prompt `tool_use.v3`),
P2 `live/1.1.0`, P3 `verify-all/1.1.0` (relevance rule `verify-all-relevance/1.0.0`). Model
`anthropic/claude-sonnet-5.5` through OpenRouter. Limits: 48 tool calls and 8 model calls per
episode, 0.50 USD per episode, 900 s wall time. Seeds 101, 202, 303 recorded but not sent (the
model's endpoints refuse a seed), so the three trials are repeated runs within a case, not independent units. Policy order seed
20261025. Sources: `apps/plan_b/plan_b/evaluation/manifests/freeze.json` and
RUNTIME_CONTRACT section 20. The Wave 2 frames and the recorded card show the pre-freeze
versions (`live/1.0.0` and so on), and are labelled Wave 2 development.

### Wave 3 held-out results (placeholders, never filled from memory)

`<run>` is each suite's results directory. The protocol names
`apps/plan_b/plan_b/evaluation/results/<run_id>/`, but the code writes wherever `--out` points,
so the real paths come from the Wave 3 packet and the `audit_eval` report. `M` is
`<run>/report/metrics.json`, `E` is `<run>/report/evaluation_results.md`.

| Placeholder | Meaning | Exact source |
| --- | --- | --- |
| R_RUN_IDS | the campus and pantry results directories | the Wave 3 packet, `<run>/plan.json` |
| R_CAMPUS_COMPLETED, R_PANTRY_COMPLETED | runs recorded of 80 and of 40 planned, and the missing or aborted ones | `M` `by_policy[P].recorded` summed, `M.missing`, `M.aborted` |
| R_GOAL_P0 to R_GOAL_P3 | goal completion on C01 to C07, `k/n` | `M` `by_policy[P].goal_completion` |
| R_INFEAS_P0 to R_INFEAS_P3 | appropriate infeasibility on C08, `k/n`, and who decided | `M` `by_policy[P].appropriate_infeasibility`, and `M.episodes[*].decided_by` filtered to C08 |
| R_UNNEC_P0 to R_UNNEC_P3 | unnecessary committed changes on C02 to C04 | `M` `by_policy[P].unnecessary_changes` (`committed_changes`, `episodes_with_change`, `n`) |
| R_INVALID_P*, R_VIOL_P* | refused requests and executed violations (scored runs only) | `M` `by_policy[P].invalid_attempts`, `executed_violations`, with `scored` |
| R_CHECKS_P* | status checks per run | `M` `by_policy[P].verification` divided by `scored`, or `by_case[*].policies[P].status_checks_mean` |
| R_RECOVERY_P* | recovery delay median and unrecovered count | `M` `by_policy[P].recovery` |
| R_CALLS_P*, R_USD_P* | model calls and provider-reported USD | `M` `by_policy[P].computation` |
| R_TARGET_P*, R_PARTIAL_P* | pantry target met on T01 and T02, supported partial on T03 and T04 | pantry `M` `by_policy[P].target_attainment`, `supported_partial` |
| R_KITS_P*, R_CONSERV_P*, R_DUPCREDIT_P* | kits on time, conservation failures, duplicate credits | pantry `M` `by_policy[P].pantry` |
| R_FIGURE | the per-case figure | `<run>/report/figure.svg` |
| R_PER_CASE | the per-case table | `E`, "Per-case display" |
| R_FAILURE | one failed or costly held-out run, its key and first broken stage | `E` per-case notes, `<run>/episodes/<key>/record.json` and `trace.json.gz` |
| R_HEADLINE, R_HEADLINE_SHORT, R_POSTER_HEADLINE, R_PANTRY_HEADLINE | the result sentences, from the counts only | the rows above, wording checked against the Wave 3 claims ledger |
| R_SPEND_TOTAL | ledger total after Wave 3 | the Wave 3 packet's spend summary |
| R_TESTS | Python tests, web tests, walkthroughs, storyboard at the final commit | the Wave 3 packet's VERIFICATION file |
| R_REHEARSALS | automated rehearsals and their timings, human rehearsals pending | the Wave 3 packet's rehearsal record |

## 8. What not to claim, and the caveats to state

- **No comparative claim beyond the descriptive counts.** No "P2 beats P1", no "more reliable",
  no rate without its denominator, no significance. The case is the unit, and three trials are
  not three worlds. If P2 shows no consistent advantage, say so and describe the tradeoff seen.
- **Zero executed violations is enforced by design**, so it is shown next to the number of
  refused requests, which shows the gate at work. A zero means none were observed in these runs.
- **A P2 versus P0 difference** does not separate the decision policy from language reading.
  **P3's fewer model calls** are not less checking: the server runs its checks.
- **Which policy acted.** The campus, community and pantry frames are the rule baseline P0
  acting in the sandbox, with no model call. Say so. The AI coordinator's moves come from
  recorded runs (pre-freeze `live/1.0.0` in Wave 2, the frozen versions in Wave 3).
- **Fictional sandbox.** No real bookings, rooms, purchases, messages, people or stock. The
  November 2026 date is fictional. In the browser the presenter plays staff, and the modeled
  2-minute handoff latency is not enforced there.
- **No real pantry and no U-ACCESS involvement.** U-ACCESS is public context only. No recipient
  identities, eligibility, allergen or medical decisions. The 40-kit numbers are scenario
  assumptions.
- **Development versus held-out.** Every Wave 1 and Wave 2 number is development evidence. Only
  the Wave 3 held-out numbers are evaluation results, and only with their completed counts. A
  reduced run is never called the 80-run study.
- **Automated versus human rehearsals.** Storyboard and rehearsal scripts are automated runs.
  Human rehearsals are pending unless recorded. Most failure paths were tested with scripted
  model replies, and the model was driven from a browser only once, by hand.
- **Replay versus live.** A replay re-shows a recorded run. It is never a new trial and never
  called live. Trace hashes are checked but not signed.
- **Receipts.** Every accepted change has a receipt. Refused requests are recorded too, some as
  attempts without a receipt. Read-only tools have no receipt.
- **No zero-shot transfer.** The pantry needed an explicit adapter.
- **No community validation, no pilot, no partner.**
- Never "always safe", "proven reliable", "optimal", "first ever", "guarantee".
- The model's rationale is untrusted text, never an explanation.
- **Held-out case contents stay evaluator-only.** The items may name a case id (C01) with the
  protocol's public condition from `08_evaluation.md` and its counts, never its messages,
  timings, predicates or expected outcome.

## 9. Open decisions for the final step

1. The result headline (slide 9 title, poster band, abstract), written only after the counts
   are known and checked against the Wave 3 claims ledger.
2. Which failure to show on slide 10: the first held-out run that missed its class with an
   informative first broken stage, or C08's infeasibility report if every policy met its class.
   It must be describable without case contents.
3. Whether the pantry suite gets more than one line on slide 11.
4. Resolved by the run coordinator: the title slide reads "Paul English Applied AI Institute
   (PEAAII) Hackathon, UMass Boston, October 2026" (`00_decision_record.md` D007 lists
   2026-10-25 as the submission date).
5. Resolved by the run coordinator: the deck must work alone. A live switch to the board stays
   optional in the Wave 3 runbook.
6. Resolved: the owner pushed the branch at `26cf424`. The QR codes encode the direct link
   `https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b`, which resolves.
7. Resolved by the run coordinator: PDF for the deck and the poster, .docx for the
   documentation, unless the owner says otherwise.
8. Whether to keep real app crops at all on slides 4 and 5 (they prove the app is real) or redraw
   them. The crops chosen contain no dash characters.

## 10. Build status of this draft (2026-10-25)

This table is the state of the first draft and is kept as it was. The final items are described
in `README.md` (the deck has 23 pages with 10 backup slides, and the document has 15 figures).

| Item | File | State |
| --- | --- | --- |
| Deck | `slides/slides.pdf` from `slides/slides.tex` (latexmk, pdflatex) | 12 timed slides and 7 backup slides, notes in `\note{}`, results as marked placeholders |
| Spoken script | `slides/pres-note.md` | 820 spoken words before the result lines (`timing.py`: about 351 s), checkpoints at the 09 boundaries |
| Poster | `poster/poster.pdf` from `poster/poster.tex` (latexmk, lualatex) | 121.92 by 68.58 cm, scale 1.75, Raleway and Lato from TeX Live, three columns, placeholders in the band and the result table |
| Poster script | `poster/poster-note.md` | about 200 words before the result line (`timing.py`: about 85 s) |
| Documentation | `documentation/Plan_B_Project_Documentation.docx` from `build_doc.py` and `docx_helpers.py` | 17 sections and 3 appendices, 11 figures, placeholders marked "[Wave 3 result: ... pending]" and "[R_...]" |
| Figures | `slides/figures/fig_*.tex` (standalone TikZ), `crop_frames.py` (frame crops), `documentation/figures/` (PNG renders) | results-independent figures done. The results figure is a placeholder |
| Checks | `check_writing.py`, `timing.py` | 0 forbidden characters in both PDFs, the docx prose and both scripts |

Scale differs from the plan in section 4 (2.2): at 2.2 the three columns overflowed the page,
so the poster uses 1.75 with Lato Regular, about 150 words of body text and figures drawn for
the poster column (`fig_strip_v`, `fig_loop_poster`). Body text projects at about 22 px on a
1080p screen. The pantry figure and the report figure are left off the poster.

## 11. Critique of the first version (three reviewers, run in parallel)

**(a) A first-time hackathon judge.**
- It was not clear whether the AI made the decisions: the main frames are the rule baseline,
  and the only model decision was in the backup slides.
- "Plan version" and "revision" would confuse.
- Slide 3 defined four terms before anything happened.
- P0 to P3 would be forgotten by the results slide.
- Missing: why AI at all, what is new, who the user is and the stakes, the real-world mapping.
  "Prepare" was told, not shown.
- Too long: 55 s on a non-event with ids. The 8 by 10 grid carries no information. The results
  slide had five metrics in 30 s. The pantry slide was dense.
- Unconvincing: "0 executed violations" is guaranteed by design, so show the refused requests.
  Dense screenshots.
- Single best change: show the AI making a decision in the main story.
- Poster: fails the 20-second test. Open with the stakes line and a four-step recovery strip,
  thin the columns.

**(b) A presentation coach.**
- 13 slides was too many. The coach proposed the 12-slide timing now used, keeping the 09
  boundaries.
- Overloaded: the results slide (five metrics), slide 8 (six terms), slide 9, slide 7 (a new
  scenario with four numbers), the close.
- One idea per slide: move "receipt" to the slide where it first appears. Use only "plan
  version" in the talk. Narrate dev04 in trace order as "three messages, zero changes". Define
  "development case" by contrast at the results.
- Legibility rule: a crop's pixel width should be at most 5 times its printed width in mm. Full
  panels beside bullets come out near 6 pt. So use tight crops or TikZ redraws. The crops also
  carry dash characters.
- The report SVG is too dense for a slide (64 bars, 11 px labels): move it to backup and draw a
  four-row k/n summary.
- Poster: three columns, body about 55 pt, at most 170 words, no screenshot. Pitch about 235
  words with the given structure and opening line.
- pres-note.md: the ICML shape, a time line per slide, checkpoints at the 09 boundaries,
  "[skip if late]" marks, one number per sentence spelled as spoken, "I" not "we", notes equal
  to the script, rehearse to about 6:40.

**(c) An accuracy checker.**
- No cited number was wrong.
- Two sources were mis-cited: the dev01 check and receipt are not in the wave_1 README, and the
  live card figures are in DEMO.md section 4, not 7.
- Overstated:
  - the dev04 status check answered the false alarm, not the P09 reminder, and the reminder is
    about a cancelled order for an October 29 workshop.
  - the coordinator may also apply free changes.
  - "every action has a receipt" is false for reads and some refusals.
  - the planner builds a bounded template set, not "every allowed repair".
  - P3's checks are run by the server under a relevance rule.
  - the model-call rule wording was wrong.
  - only the skills exchange's kit steward can offer a resource.
  - "prepare while unsure" should read "while a fact or an approval is pending".
  - the key-read statement needs the audit disclosure.
- Placeholder paths: the results path is a convention. `decided_by` must be filtered to C08.
  `verification` holds totals. The pantry keys are `target_attainment` and `supported_partial`.
- Missing caveats: the frames are P0, the Wave 2 live runs used pre-freeze versions, P3's call
  counts, P2 versus P0, unsigned hashes and a single hand-run browser model check, the browser's
  staff latency, scripted failure paths, and B5 (now B6) must be labelled development.
- It confirmed the freeze values against `freeze.json` (committed in 3de5962).

## 12. Decisions taken from the critique and the run coordinator

- **D1 Twelve slides on the coach's timing** (section 3), keeping the 09 segment boundaries
  0:35, 1:10, 2:40, 3:35, 4:30, 5:40 and 6:25. The protocol grid is dropped. The fair-test strip
  and the result share slide 9.
- **D2 The AI is shown deciding in the main story.** Slide 5 says the frames are the rule
  baseline and that the recorded P2 run made the same check and swap at 16:43 (verified in the
  development README). Slide 8 carries one real recorded model decision as a TikZ callout, with
  the full card on backup B1.
- **D3 Terms where they first appear.** Hold on slide 3, status check on 4, receipt on 5, policy
  and P0 to P3 on 8, development and held-out cases on 9, replay on B1. The talk says only "plan
  version". Revision is defined in the documentation glossary as the state's version number.
- **D4 Tight crops and TikZ redraws.** Slides 4 and 5 use one-line real crops that contain no
  dash characters. Slide 6 and the pantry slide are redrawn in TikZ. Full panels move to backup
  and the documentation.
- **D5 Results as a four-row table in words**, with refused requests next to executed
  violations. The report's SVG goes to backup B2 and the documentation.
- **D6 Poster: three columns, about 170 words, scale about 2.2, Lato Regular**, the hook and the
  four-step strip first, no screenshot, pitch about 235 words.
- **D7 Commands are code, not prose** (revised by the run coordinator). The Word document
  gives the exact command lines with the flags they need, in the monospace paragraph style
  "Code" (and identifiers in the character style "Inline Code"). `check_writing.py` skips text
  in those two styles and nothing else. All prose stays free of dashes and semicolons. The
  slides and the poster contain no command lines.
- **D8 Every accuracy fix is applied** to the wording in sections 3 to 8. The accuracy caveats
  are in section 8.
- **D9 Not taken:** the judge's "cut slide 6 to 30 s". The 09 plan gives that segment 55 s, and
  the coach's trace-order narration uses it to set up the negative-control metric. "Prepare" is
  shown on slide 7 instead.
- **D10 Not taken:** recapturing the frames at a 2x device scale. That needs a new storyboard
  run, which belongs to the `story` worker. The tight crops keep the text legible at 1x.
- **D11 Run coordinator decisions** (received during the draft): the title-slide event name,
  commands as code in the docx (D7), PDF and .docx formats, and a deck that works alone.

## 13. Final step: what the results changed (submission worker, 2026-10-25)

The committed run `wave3_heldout_20261025T1625Z` (commit c052338) gave a mixed comparison. P1 met
24 of 24 campus runs, P2 18 of 24, P3 21 of 24 and P0 6 of 8. On the pantry P0 met 4 of 4, P2 9 of
12, and P1 and P3 6 of 12 each. No policy executed a violation or changed a quiet case. P2 shows
no consistent advantage, so the plan was revised as follows.

- **F1 Numbers are generated, not typed.** `make_results.py` reads both `metrics.json` files and
  writes `results_numbers.tex` (macros `\res{suite:policy:key}`), `fig_results.tex`,
  `fig_results_v.tex` and `documentation/results.json`.
- **F2 Slide 9** became "Held-out test: zero violations, no clear winner". The freeze strip moved
  out of the slide (a one-line definition replaces it) to make room for the results figure in
  large type. It states "No consistent advantage for P2" and the cost tradeoff.
- **F3 Slide 10 shows C06**, a P2 and P3 failure told with the protocol's public condition only
  (a volunteer will be late). The earliest broken stage is planner input, from `FAILURES.md`.
- **F4 Pantry and close** carry one held-out line each. The close says plainly that my policy showed
  no consistent advantage over the others.
- **F5 Backups**: the report's two per-case figures (printed from `figure.svg`), the cost table
  with the voided first attempt, and a slide of what the numbers do not show (unit of analysis,
  C06, the pantry prompt difference and planner defect, the call limit, spent cases). The
  per-case table backup was replaced by the report figures.
- **F6 Poster in four columns** so the stacked results figure fits with its counts, plus a
  "What I built" block. The repository link sits in the footer and the QR code.
- **F7 Documentation section 12** was rewritten around the counts, with the tradeoff, the spend,
  the voided attempt, the disclosures and the other failures.
- **F8 Slides PDF title** now reads "Plan B: The Show Must Go On" (class option
  `usepdftitle=false`).

