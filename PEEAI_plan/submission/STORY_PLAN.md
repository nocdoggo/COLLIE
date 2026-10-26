# Story plan: the 7-minute deck, the one-slide poster and the documentation

Written 2026-10-25 by the `design` step. It replaces the figure and story parts of `DRAFT.md`
(sections 3, 4 and 6), which stay as the record of the earlier waves. The decisions taken from the
three critiques are at the end.

## 1. Audiences and what each must take away

| Audience | Situation | Must take away |
| --- | --- | --- |
| Hackathon judges (7-minute talk, then questions) | Seated, many talks in a row, mixed depth | A real community problem, a clear new idea, proof it works on cases it never saw, and honest limits |
| Non-technical visitors (poster, 2 minutes) | Standing, may leave after 20 seconds | The scene (a text, twenty minutes to doors open), what Plan B did, and that a person still approves spending |
| Technical experts in agents | Skeptical of agent demos | The authority design: the model picks only among options the server built and checked, one gate writes every receipt, holds make preparation reversible, checks are selective. And a fair test: frozen system, held-out cases, every run counted |

**The one message** (kept from `09_seven_minute_presentation.md`):

> Plan B helps a community event stay on track by deciding what to verify, what to prepare, and
> when to commit a change.

**The hook and its callback**: 16:40, twenty minutes to doors open, a text says the projector may
be late. "Would you wait, check, or book a backup?" The close answers the same question.

## 2. Rules the story follows

- **One version only.** The slides and the poster show the final system. The evaluation shown is
  the final system on the 6 fresh held-out cases (C09 to C12, T05, T06), written by a separate worker
  before the final freeze and locked in the same commit before the first model call. The policy
  author never read them (the pre-freeze auditor saw both and changed no policy behavior). Development gets one line: an
  earlier 12-case test (120 runs) exposed four defects (the count in
  `handoffs/wave_3/README.md`, Wave 3b table), which were fixed before the final freeze, and
  those cases are now development cases. The post-hoc rerun on the spent cases is never called
  held-out and is not on the slides or the poster. The documentation keeps the complete record.
- **Assertion and evidence.** Every content slide has a full-sentence title that states its point,
  one visual as the evidence, and at most two short supporting lines. No list of three or more
  bullets, no nested bullets. Details go to the notes and the backup slides.
- **No decorative lines.** No frames around figures, no boxes around everything, no column
  separators. Gridlines only inside charts, light and few. Grouping by whitespace and alignment.
- **Palette.** Near-black and grey type on white. UMB blue `#08457E` is the brand and the system.
  One warm accent (orange `#E8701A`) only for tension: the incoming message and the clock. Green
  (`#2E7D32`) only for a receipt or a met run. Two full-bleed blue section slides carry the story
  beats (the hook and the close). The illustrated scene is the most colourful figure. Charts stay
  calm: P2 (my policy) in blue, the others grey.
- **Vector only.** Every figure is a standalone TikZ or pgfplots PDF. No screenshot crop on a main
  slide or on the poster. Logos only from the high-resolution sources, never upscaled. The Word
  document gets 300 dpi renders.
- **Writing.** No em dash, en dash, double hyphen or semicolon. Plain words. A term is defined in
  one short line where it first appears (status check, hold, receipt, held-out case, policy).
  "I", not "we". The persona is a fictional volunteer organizer named Jordan, labelled as an
  illustration, with no pronouns.
- **Plain names, no codes.** No case ids (C06, dev01) or policy codes (P0 to P3) in anything the
  audience reads or hears. The four policies are "fixed rules" (the baseline), "a model that
  calls tools freely", "Plan B's coordinator" (the model picks from checked options, my design)
  and "the check-everything variant". Cases are described ("a case where a volunteer runs late",
  "six new cases it had never seen"). Ids stay only in the documentation's appendix tables and
  in file paths.
- **Results say what they mean.** All three model-based policies handled every one of the six new
  cases, and only the fixed rules missed one, because a person's own delay is a message its rules
  cannot read. No executed action broke a rule, because every change passes the one gate. The
  earlier, larger test is how real defects were found and fixed before the final freeze. Six
  cases cannot rank anything, so the point is safety and reliability, not a winner.
- **Truth about APIs.** Connected today: the OpenRouter model API (`anthropic/claude-sonnet-5.5`),
  the sandbox's tool API (status checks, holds, plan changes, receipts) and the board's HTTP API.
  Designed but not connected: real feeds such as the MBTA V3 API for live transit alerts. The
  adapter was not built. Transit data could only ever be context, never a person's arrival. In
  figures: connected is solid, planned is dashed and labelled "next".

## 3. The arc (420 s, spoken target about 395 s at 140 words a minute)

| # | s | Title (the assertion) | Evidence (one visual) | Supporting lines (at most two) | Spoken gist |
| --- | --- | --- | --- | --- | --- |
| 1 | 8 | Plan B: The Show Must Go On | UMB lockup | Subtitle: deciding what to verify, what to prepare, and when to commit a change | Name, school, project |
| 2 | 30 | 16:40. Twenty minutes to doors open. (full-bleed blue) | `fig_hook`: a phone with the text "projector may be about 25 minutes late" and a clock at 20 minutes to 17:00 | Jordan, a volunteer organizer (an illustration). The demonstrations need the projector | The persona, the stakes, the question: wait, check, or book a backup? |
| 3 | 40 | A plain AI agent acts on the text. Plan B checks it first. | `fig_contrast`: two lanes from the same text. Plain agent: believes it, books the $35 backup, reshuffles the program. Plan B: checks, builds checked options, the model picks one, the gate writes a receipt | A claim is not a fact. Spending needs a person | Why naive agents are risky here, and the idea in one picture |
| 4 | 55 | Plan B checked one fact, swapped two activities, and the doors opened on time | `fig_story`: the illustrated storyboard on a clock axis 16:40 to 17:30: text, tracking check (ETA 17:25), free swap with receipt, doors open 17:00, demonstrations at 17:30 | Shown: a development run in the sandbox. The AI coordinator made the same check and swap | The vivid example, beat by beat, with the clock |
| 5 | 30 | One free swap moves the demonstrations after the projector's reported arrival | `fig_gantt`: before and after on a real time axis 16:30 to 18:00, the 17:25 ETA line | The planner built 16 options and 3 passed every check | The planner and the receipt in plain words |
| 6 | 30 | Most messages should change nothing | `fig_quiet`: three messages on a time line, each with its verdict, ending in "plan kept" | A false alarm, another order, a duplicate | Checks are selective: verify only what could change the decision |
| 7 | 65 | The model only picks among options the server built and checked | `fig_design`: the hero architecture | Every change passes one gate that writes a receipt | Inputs as claims, selective checks, the planner's menu, the model's choice, the gate, holds, receipts, the APIs connected and next |
| 8 | 55 | On 6 fresh cases it never saw, 59 of 60 runs met the expected outcome | `fig_result`: pgfplots, share of runs met per policy, one panel per suite, k of n labels | Zero executed violations. A small set, so no ranking | The fair test, the result, the one miss, the one-line development history |
| 9 | 45 | The same loop runs a food pantry, where late stock does not count | `fig_pantry`: pgfplots bars at four moments with the 40-kit target | Only staff record a handoff | Second domain in 45 s |
| 10 | 35 | Next: real feeds as context, and a pilot with community staff | `fig_next`: connected today (solid) and next (dashed): MBTA V3 alerts as context, a community pilot | Never a person's arrival from transit data | What is next, truthfully |
| 11 | 27 | (full-bleed blue) 16:40 again: Plan B checks first | the one message, the QR code | Repository link | Callback to the question, the one message, thank you |

Backup slides (untimed, no version labels): the recorded model decision (redrawn as a vector card,
no screenshot), what the evaluation cost, what the numbers do not show, the partial pantry
handoff, the frozen configuration in words.

## 4. Poster (one slide, 121.92 by 68.58 cm, Gemini with the UMB theme)

- Header: title, author, university and event, white UMB lockup at its native size or below, QR
  code on a white card.
- Band: the one message only. No results sentence, no "fictional" footer line.
- Left two thirds, top: "16:40. Twenty minutes to doors open." with `fig_story` (the hook).
- Left two thirds, bottom: "How it works" with `fig_design`.
- Right third: "Tested on 6 fresh cases" with `fig_result` (stacked variant), "A second domain"
  with a small `fig_pantry`, and "Next" with one line on MBTA alerts as context and a pilot.
- Labelled visuals, not paragraphs. Footer: the repository link only.
- Script `poster-note.md`: at most 120 s (about 250 words): the scene (30 s), the idea (30 s), the
  result (30 s), pantry and next (20 s), link (10 s).

## 5. Figures (all in `slides/figures/`, shared by the deck, the poster and the documentation)

| Figure | Kind | Design note | Numbers from |
| --- | --- | --- | --- |
| `planb_figstyle.tex` | shared preamble | Helvetica, colours `primary`, `accent`, `ok`, greys. Square corners (at most 1 pt), thin rules, no shadows or gradients | none |
| `fig_hook` | TikZ, fontawesome5 | Phone with one message bubble (accent), a clock face at 16:40 with the 20 minutes to 17:00 shaded, white on blue variant for the full-bleed slide | dev01 fixture times |
| `fig_contrast` | TikZ | Two horizontal lanes from one text. Top lane grey with three warm failure marks. Bottom lane blue, ends in a green receipt | dev02 grant ($35) |
| `fig_story` | TikZ, fontawesome5 | Clock axis 16:40 to 17:30, five beats with icons (phone, truck, exchange, receipt, users, display), the program strip before and after | dev01 (`story_04` to `story_07`) |
| `fig_gantt` | TikZ on a real time axis | 10-minute ticks, light vertical grid, before as grey outline, after in blue, the ETA line in the accent | dev01 times |
| `fig_quiet` | TikZ | One time line, three message marks, each verdict in plain words, a single "plan kept" end | dev04 |
| `fig_design` | TikZ | Left to right: inputs (claims), the server (selective checks, planner, menu), the model (picks one id), the gate, state and receipts. Holds below the gate. API strip: solid connected, dashed "next" (MBTA V3) | design facts |
| `fig_result` | pgfplots, written by `make_results.py` | Horizontal bars, x axis "share of runs met" 0 to 100 percent with light grid, labels k of n, one panel per suite, P2 blue, others grey | `results_v12.json` (fresh) |
| `fig_result_record` | pgfplots, written by `make_results.py` | The same chart for the earlier 12-case test, for the documentation's evaluation section only | `results.json` |
| `fig_pantry` | pgfplots | Grouped bars at four moments (on the shelf, partner pool, held, handed out), y axis kits 0 to 40, dashed target line at 40 | pantry_dev01 (existing figure's sources) |
| `fig_next` | TikZ | Two columns: connected today (solid) and next (dashed) | none |
| `fig_qr` | TikZ `qrcode` | Unchanged | the repository link |

The older figures the documentation still needs (`fig_roles`, `fig_freeze`, `fig_failure`,
`fig_loop`) take the new style through `fig_style.tex`, which now loads `planb_figstyle.tex`.

## 6. Documentation

Abstract, section 1 and the story sections follow the single-system framing and use the new
figures. Section 12 and the appendices keep the complete record: the earlier 12-case run, the
fresh run of the final system and the post-hoc rerun, each with its label. The browser-printed
report charts and the screenshot crops leave the document. The repository keeps them.

## 7. Critiques (three reviewers, run in parallel) and the decisions taken

**(a) A non-technical visitor.** Slide 3's "plain agent" contradicts the result slide, where the
tool-calling model also met every campus run with no violation. Too many terms (commit, held-out,
runs met, executed violations, policy, gate, hold, sandbox). The design slide needs an everyday
picture. Slide 5 repeats slide 4. Put "simulated" in the scene. Plainer words on the pantry and
next slides ("food counts only once it is on the shelf", "a late train never proves someone is
late").

**(b) A hackathon judge.** The same contradiction is the first Q&A risk. The idea must land by
1:00, not 3:13. Merge slides 4 and 5. Three bars at 100 percent look too easy: show the unit and
the refusals. Put a number on selective checks. Name the pilot concretely and what it would
measure. Prepare backups for "who wrote the cases", "zero by construction" and "what does it cost".

**(c) A technical expert in agents.** The hero figure must show the model's two strict outputs
(a reading of the message and one option id), mark the model as holding no tool that writes, put
the gate's three checks in plain words, show the spending branch (hold, then a person), and put
each API label on its own arrow, with MBTA as one dashed "next" input. "59 of 60" sums four
approaches, so say what each did. "Cases it never saw" needs care: the cases were written by a
separate worker and the author of the code changes never read them, but the pre-freeze auditor
saw both. Zero executed violations is enforced by the gate, so show the refused attempts. Say
that all four approaches share the planner and the gate. Do not hide that the coordinator scored
below the tool-calling model in the earlier test.

**Run coordinator directions received during the step** (mandatory): assertion and evidence
slides with at most two short lines, no decorative lines, one accent for tension and one colour
for the receipt, full-bleed blue story slides, vector figures only, a persona with the clock
motif and a callback at the close, plain names instead of codes, results that say what they mean.

**Decisions.**

- **E1 The idea lands on slide 3 (by 1:21).** Title: "An agent that acts on a text can spend
  money on a rumor, so Plan B checks first". The top lane of `fig_contrast` is labelled as an
  illustration of an agent with no gate, not a tested system. Slide 7 says all four approaches
  share the planner and the gate.
- **E2 Slides 4 and 5 merged.** `fig_story` carries the beats and the program before and after
  on a real time axis with the 17:25 line. "16 options built, 3 passed" is the supporting line.
  The separate Gantt slide is dropped, which leaves 10 timed slides after the title.
- **E3 The design slide** uses the restaurant picture in the script (kitchen, waiter, manager,
  ticket) and the expert's figure content. The trust sentence is spoken: the model's only
  outputs are a checked reading and one option, and it holds no tool that writes.
- **E4 The evidence slide.** Title: "On 6 new cases, 59 of 60 runs met the expected outcome, and
  the one miss was the fixed rules". The script says our coordinator met all 18 of its runs, as
  did the other two model approaches. Supporting line: no executed action broke a rule, because
  all four share the gate, which refused 6 attempts and recorded each. Six cases cannot rank. The
  caption names who wrote and locked the cases, the run counts per approach and the earlier
  locked test in one sentence. The counts 18 and 6 come from `results_numbers_final.tex` and
  `results_numbers_v12.tex`.
- **E5 The chart stays a pgfplots bar chart** with a real axis, as the owner asked, instead of the
  judge's run grid. The refusals and the unit answer "too easy".
- **E6 Selective checks get a number** on slide 5: status checks per campus run of our
  coordinator and of the check-all variant, with the same outcomes (descriptive).
- **E7 Backups** answer the judge's three questions: what the new test cost per run, what these
  numbers do not show (who wrote the cases, two repeated conditions, the unit, the earlier test
  where our coordinator met fewer campus runs than the tool-calling model, the diagnostic rerun),
  the partial pantry handoff and the frozen configuration. No version labels and no codes.
- **E8 Plain words.** "Hold" is defined on the design slide, "receipt" on slide 3, "status
  check" in the story script. "Held-out" is said as "new cases it had never seen" and the
  locking is explained. The pantry title reads "food counts only once it is on the shelf".
- **E9 The defect count.** The owner's brief and the coordinator say three defects. The Wave 3
  packet (`handoffs/wave_3/README.md`) records four. The items say "real defects" without a count,
  so neither is contradicted. Flagged in the report.
- **E10 Times stay on the 24-hour clock** (16:40), as the owner's writing rule writes them. The
  script speaks them as "four forty".
- **E11 Not taken.** The visitor's "library tech night" and the judge's named partner: inventing
  an event or a partner would overclaim. The pilot is described as a plan ("a campus event
  series") with what it would count.
- **E12 Poster.** Three columns: the scene (with one line on the pantry), the design, the
  evidence (with one line on what is next). The one message is a line of type under the header,
  followed by the visitor's plain sentence. No footer line about the sandbox and no results band.
  Block titles are assertions.
