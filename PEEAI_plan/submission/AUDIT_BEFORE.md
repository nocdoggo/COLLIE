# Plan B submission, audit before revision

Audit key audit0, Monday 26 October 2026, 14.14 to 14.59 EDT. Read only. The only file this audit wrote in the repository is this one.

This file is an internal working note for the people revising the deliverables. It quotes the current slides, poster, report and scripts word for word, so it contains the colons, clock times and banned words it reports. Keep it out of `check_writing.py`.

What was audited, as committed at `000589a` on branch `hackathon/peeaai-plan`:

- the deck `slides/slides.pdf` (17 pages, 10 timed slides and 7 backups), `slides/slides.tex` and its speaker notes, and the script `slides/pres-note.md`
- the poster `poster/poster.pdf` (one page, 3456 by 1944 pt), `poster/poster.tex` and `poster/poster-note.md`
- the report `documentation/Plan_B_Project_Documentation.docx` (36 headings, 15 figures, 15 tables, about 8,800 words) and `documentation/build_doc.py`

How. Every slide and the poster were rendered to PNG and measured for empty space (section 7). The docx text, headings, tables, headers, footers and embedded figures were extracted with python-docx 1.1.2. Five auditors then ran in parallel, each read-only, each writing JSON findings with a location, a problem, evidence and a fix. A covered design and AI-slide tells, B the story and the Rule of Three, C the seven questions, D every number and claim against the committed results, E the writing rules and plain wording. Their raw JSON is listed in section 13. I checked the most severe findings myself before ranking them (the `{cases}` placeholder, the missing department line, the logo sizes, the figure resolution, the punctuation counts, the defect count in the Wave 3 packet). During the audit the run coordinator added two owner requirements, at most about 25 to 35 visible words per slide and a poster polished to the level of the Roameo poster. I measured both myself (sections 3a and 4a).

## 1. Verdict

The deliverables are honest and careful, the poster is well filled, and the headline numbers hold up (section 10). They do not yet meet the owner's brief. The gaps are structural, not cosmetic.

| Requirement | Slides | Poster | Report |
|---|---|---|---|
| 1 One story on one use case, novelty, student and community benefit | weak | weak | weak |
| 2 Rule of Three, announced, delivered, repeated | fail | fail | fail |
| 3 Seven questions | fail (Q2, Q6 missing) | fail (Q2, Q6 missing) | weak (Q2, Q6 weak) |
| 4 Design, AI-slide tells, empty gaps, UMass Boston identity | weak | weak | weak |
| 5 Writing rules (no colon, dash, semicolon, https) | fail | fail | fail |
| Plain wording (AI words, mechanical words, first-year explanations) | fail | fail | fail |
| 6 Truth | pass on all headline numbers, 4 small fixes (D5, D6, D8, D9) | pass, but 60 runs never explained | fail on the `{cases}` placeholder, plus D2 to D7, D11 to D13, D16 |
| Text density, at most about 25 to 35 words per slide (added during the audit) | fail, every slide over, timed slides average 122 words | not applicable | not applicable |
| Poster polish at Roameo level (added during the audit) | not applicable | fail on structure, good on density | not applicable |

## 2. The fixes that matter most, across all three deliverables

1. **No Rule of Three anywhere.** No slide, poster block, report section or script line names three ideas, delivers them in order and repeats them at the close. Four different triads compete: "verify, prepare, commit" (subtitle, close), "check, the model picks, the gate writes a receipt" (slide 3), "who it helps, easy to run, adaptive" (slide 9, poster, report 3.1 to 3.3, which the poster stretches to five items), and "one check, a free swap, a receipt" (slide 10). Pick one triad and use its exact words everywhere (proposal in section 9).
2. **Competitors (question 2) are missing** from the slides and the poster and only gestured at in the report (section 2 names technique families, no products, no indirect alternatives, no citations). Zero hits for "competitor" in all three.
3. **Sources and acknowledgement (question 6) are missing** from the slides and the poster. The report has no References list and no Acknowledgements section. Appendix C is an index of repository files.
4. **The report's abstract prints a raw placeholder.** "The final system was frozen and run on {cases} new cases". `documentation/build_doc.py` line 117 lacks the `f` prefix (it sits on line 115). The first paragraph a judge reads is broken.
5. **The department line is missing on every item.** No deliverable says "Department of Computer Science". Slide 1, slide 10, the poster header and the report's title table all stop at "University of Massachusetts Boston".
6. **The poster does not follow the Roameo grid.** No three ideas with icons in the header, no full-width story strip, no three idea columns with a "How we tested it" box, no bottom row with who it is for and who else, responsible use and limits, and the three ideas repeated with acknowledgements and sources. Its six panels are story, screenshot, design, results, pantry and "Why it matters".
7. **The deck has no announce slide and no close over the three ideas.** It runs hook, contrast, story, false alarm, design, results, pantry, benefits, close. All evidence sits on one results slide. The close shows the one message and a different triad, and its lower third is empty.
8. **"gate" is printed and spoken throughout** (slides 9 hits, poster 4, report 10, slide script 5, poster script 1), including the poster panel title "One gate decides." and the slide 6 title "one gate writes every receipt". Code strings reach the audience too: `cand_0001_dc26f35f`, `obs_notice_01`, `dev_fixture_01`, `rules/1.0.0` in the board screenshot on the poster and slide 9, `anthropic/claude-sonnet-5.5` on slide 6 and the poster figure, "policy" 57 times in the report.
9. **Colons everywhere, mostly clock times and labels.** Slides 73, poster 29, report 143, slide script 18, poster script 3 (raw counts, section 11). The title itself, "Plan B: The Show Must Go On", has one. Every clock time ("16:40", "17:00", "17:25") must become "16.40" or "4.40 pm". The report also shows "https://" or "http://" six times in prose and tables. Its ten "--" are all in exempt command lines. No em dash, en dash or semicolon appears in any prose.
10. **The idea "prepare" is not shown in Jordan's story.** The projector story has no hold, yet the close says Plan B "prepares what it can undo". A hold appears only in report 4.3, a different development case. The shown run of the story strip and the poster screenshot is the fixed rules with no model, so the novelty (the model picks among checked options) is a caption, not a beat.
11. **Tests are not explained at a first-year level next to the claim they support.** The results slide counts runs but does not say what a test case is, what the sandbox is, what held out means, why three runs, or what "met the expected outcome" means. See section 11 for where each is or is not explained.
12. **Empty space.** Backup slides 14 to 17 are 37 to 57 percent empty below the text, the title slide is 72 percent blank tenths, and the close slide's lower third is empty. The poster is well filled (3 blank tenths of 100).
13. **Too many words per slide.** Every slide is over the new limit of about 25 to 35 visible words. The ten timed slides average 122 words, and slide 6 has 239 (section 3a).
14. **"Three defects, fixed" is not what the records say.** The Wave 3 packet records four defects, and the diagnostic rerun shows two of the targeted failures still there. Print neither "three" nor "fixed" (section 10, D4 and D5).

The headline numbers themselves are safe. 59 of 60, 6 held-out cases, 18 of 18 for our coordinator, no executed action broke a rule, 6 refused attempts, $3.61, and every number in Jordan's story all match the committed results (section 10).

## 3. Slides, ranked findings

| # | Sev | Where | Requirement | Problem | Fix |
|---|---|---|---|---|---|
| S1 | high | whole deck and script | 2 | No three ideas announced, delivered as slide sets, or repeated. Four competing triads (fix 1 above). | Announce slide after the hook, one slide set per idea with three parts each, close repeating the three ideas over Jordan's result. |
| S2 | high | whole deck | 3 Q2 | No competitor slide or line. Only internal baselines (slide 7) and the illustrated agent with no check (slide 3). | Add a "Who it is for and who else does this" slide, direct (event and scheduling tools) and indirect (chat assistants, group chats, a run-of-show spreadsheet, a human coordinator), modest and cited. |
| S3 | high | whole deck, slide 10 | 3 Q6 | No sources and no acknowledgement. The script ends "Thank you." with no one named. | Acknowledgements and sources strip in the empty lower third of slide 10 (hosts, model and provider, open-source libraries, MBTA API documentation, cited competitor pages). |
| S4 | high | slides 1 and 10 | UMB identity | No "Department of Computer Science". | Add the department line under the name. |
| S5 | high | slides 2 to 10 order | 2, Roameo | No slide set per idea, tests not tied to an idea, all evidence lumped on slide 7. | Restructure (see section 9). |
| S6 | high | slide 4, slide 10 script | 1, 2 | "Prepare" is claimed at the close but not shown in Jordan's story. | Define idea 2 so Jordan's story shows it (16 options built, 3 passed every check, the model picked the free swap), and show the free hold only as a labelled second case. |
| S7 | medium | slide 4 caption, slide 9 screenshot | 1 | The shown story run is the fixed rules, not the AI. The novelty is a footnote. | Add the beat "the AI picks one of the 3 checked options" from the recorded coordinator run (report 4.4), and label which run is shown. |
| S8 | medium | slide 8 (pantry) and slide 5 | 1 | A second setting (40 kits by 13.40) and a second case take about 15 percent of the talk and compete with Jordan. | Move the pantry chart to backup and keep one sentence under "adapts". Frame slide 5 as "most texts Jordan gets should change nothing". |
| S9 | medium | slide 1, slides 3 to 17 | UMB identity, 4 | Title slide is plain white with a tiny logo. The lockup PNG has wide transparent margins, so at `height=1.35cm` the visible logo prints about 0.58 cm tall. No logo or dark band on content slides. Not blurred (6600 px wide). | Crop the padding or use `trim`, print it about 1.6 to 2 cm tall, add a navy title band or corner lockup as Roameo does. |
| S10 | medium | slides 14 to 17, 12 | 4 | Large empty gaps (section 7). | Merge 16 and 17 into 15 as one three-block limits slide, enlarge the cost table on 14, give the screenshots on 12 the full height. |
| S11 | medium | slide 7 | 4 | Key result chart capped at `height=4.15cm` (slides.tex line 197), labels about 5 px at 80 dpi, empty band 16 percent of height under it. | Raise to about 5.5 cm, larger bar labels, move the case list to notes. |
| S12 | medium | slides 9, 12 | 4 | Board screenshots too small to read (log text about 3 pt), so they read as decoration and show code strings. | Crop to the decision card and the 16.42 to 16.43 rows, print large, one callout each. |
| S13 | medium | slides 3, 6, 13 | 4 | Decorative rules inside figures. Grey lane separator and orange quote bar in `fig_contrast.tex` (lines 36, 16), bars and dashes in `fig_next.tex` (line 23), a `\rule` in the box in `fig_design.tex` (line 66). | Delete them, let spacing separate. |
| S14 | medium | slides 3, 6, 7 titles and labels | plain wording | "gate", "receipt" as jargon, model id string, "policy". | Say what happens. "The server checks every change against the rules before it happens and writes a receipt." |
| S15 | medium | every slide with a time | 5 | Clock times with colons in titles and figures ("16:40. Twenty minutes to doors open."), labels "The runs:", "Model:", "Limits per run:". | "16.40", label without colon. |
| S16 | medium | slide 7 and script | first-year | Tests not explained plainly. | One spoken and printed sentence each for test case, sandbox, held out, three runs, met. |
| S17 | low | timing | 2 | About 924 spoken words, about 6 min 36 s at 140 words a minute (auditor B). `timing.py` counts the bold "Checkpoint" lines as spoken (944 words, 405 s). An announce slide and a fuller close need about 50 s, which must come from cutting the pantry slide and trimming slide 7. | Budget before rewriting. Keep the spoken total near 375 s. |
| S18 | low | slides.tex comments, report section 15 | script sync | Speaker notes match `pres-note.md` word for word on all 10 timed slides. Only stale frame comments in slides.tex and the report's demo guide clock disagree. | Regenerate after the restructure. |
| S19 | low | slides 4, 6 | 4 | Green used for the receipt and its arrow, not only for a met result. | Receipt in UMB blue or navy. |
| S20 | low | slides 11, 14 | 4 | Booktabs rules on the two tables. | Optional, bold header row and light row tint instead. |

### 3a. Text density (requirement added by the run coordinator during this audit)

The new rule is one visual per slide and at most about 25 to 35 words of visible text, title included. I counted the visible words on every page with `pdftotext` per page (small-caps titles rejoined, the footer "Noctis Zhang, Plan B, n/9" removed). Words inside the TikZ figures are counted, because the audience reads them. Text inside raster screenshots is not counted, so slides 9 and 12 are undercounts.

| Slide | Content | Visible words | Over 35 by |
|---|---|---|---|
| 1 | title | 38 | 3 |
| 2 | 16:40 hook (navy) | 51 | 16 |
| 3 | problem contrast | 113 | 78 |
| 4 | projector story | 147 | 112 |
| 5 | quiet messages | 124 | 89 |
| 6 | design diagram | 239 | 204 |
| 7 | results | 207 | 172 |
| 8 | pantry | 105 | 70 |
| 9 | who it helps (plus screenshot text) | 136 | 101 |
| 10 | close (navy) | 51 | 16 |
| 11 | backup, the six cases | 267 | 232 |
| 12 | backup, pantry board (plus screenshot text) | 42 | 7 |
| 13 | backup, interfaces | 113 | 78 |
| 14 | backup, cost per run | 72 | 37 |
| 15 | backup, what the numbers do not show | 159 | 124 |
| 16 | backup, partial handoff | 62 | 27 |
| 17 | backup, frozen configuration | 81 | 46 |

**Every slide is over the limit.** The ten timed slides average 122 words, and the densest are slide 6 (239, the design diagram with all its labels), slide 7 (207, the chart plus a caption paragraph), slide 4 (147, the story strip plus the before and after program) and slide 9 (136 plus the screenshot). Several slides also carry two visuals (slide 4 has the beat strip and the program chart, slide 9 a screenshot and three text blocks, slide 7 two charts). For comparison, the Roameo deck the owner points to runs 61 to 232 words per slide by the same count, so this rule is stricter than the model and the Roameo deck cannot be copied for density.

How to get there. Move captions and the small grey "how we know" lines into the spoken script (the notes already say most of it). Give each slide one visual and a title of a full sentence of at most about 12 words. Cut figure labels to the beats a listener needs (slide 6 can lose the grey annotations "strict, schema checked", "OpenRouter model API", "sandbox tool API", the model id and the "next" box). Split the story slide into two slides if both visuals stay. Backups can stay denser, since they are not shown in the talk, but slides 14 to 17 should still lose their empty half by merging.

## 4. Poster, ranked findings

| # | Sev | Where | Requirement | Problem | Fix |
|---|---|---|---|---|---|
| P1 | high | whole layout | 2, Roameo | Six panels, no three idea columns with three parts and a "How we tested it" box, no three ideas with icons in the header, no closing block repeating the ideas. README still describes a three-column poster that no longer exists. | Re-grid as Roameo (section 9). |
| P2 | high | whole poster | 3 Q2 | No competitors at all. | "Who it is for, and who else does this" block in the bottom row. |
| P3 | high | footer band | 3 Q6 | No sources, no acknowledgement. Left two thirds of the dark footer band is empty. | One line of acknowledgements and numbered sources there, or a bottom-row block. |
| P4 | high | header | UMB identity | "University of Massachusetts Boston • PEAAII Hackathon, October 2026", no department. | "Noctis Zhang", then "Department of Computer Science, University of Massachusetts Boston", then the hackathon line. |
| P5 | medium | header title, panel titles, "Why it matters" | 5 | Colons in the title, in "16:40, twenty minutes to doors open", "The running board at 16:43", "Screenshot: ...", "target: 40 kits by 13:40", and five "Label:" leads. 29 colons in the poster text. | Rewrite without colons, times as 16.40. |
| P6 | medium | top-right panel title and figure | plain wording | "The model picks checked options. One gate decides.", "One gate", "changed only through the gate". | "The AI picks a checked option. The server checks every change and writes a receipt." |
| P7 | medium | centre screenshot | plain wording, 4 | Code strings readable as text (`cand_0001_dc26f35f`, `obs_notice_01`, `dev_fixture_01`, `rules/1.0.0`), and the shown run is the fixed rules ("Recorded at 16:43 (revision 5) by rules/1.0.0"). | Crop to the decision card, caption which run it is, or use the coordinator's recorded run. |
| P8 | medium | top-right architecture, screenshot | 4 | Figure text about 0.45 to 0.5 cm tall on a 122 cm poster, body text about 1.1 cm. `poster.tex` line 156 uses `fig_design.pdf`, although a larger-type `fig_design_poster.pdf` exists in `slides/figures/`. | Use the poster variant or drop the grey annotations. |
| P9 | medium | bottom-right "Why it matters" | 2, 3 Q5, Q7 | Five bold-lead items (Safe, Who it helps, Easy to run, Adaptive, Next) read as a bullet list and break the Rule of Three. Responsible use is one line. No sandbox, privacy or limits statement. | Split into the three Roameo bottom-row blocks. |
| P10 | medium | results panel | first-year, 3 Q5 | Chart has no "How we tested it" note (held out, locked before the freeze, three runs per AI approach, what met means). | One plain caption or the "How we tested it" box. |
| P11 | low | top-left strip | 3 Q1 | The problem is shown, not said. No sentence says why this is hard or what an agent that acts at once would do. | One problem sentence over the strip. |
| P12 | low | story strip | 4 | Green "Receipt written" is not a met result. | Blue or navy. |

### 4a. Side by side with the Roameo poster (requirement added by the run coordinator during this audit)

Both posters are 3456 by 1944 pt. I rendered Roameo's `docs/presentation/poster/poster.pdf` at the same 50 dpi and measured it the same way. Near-white share is 0.41 for Roameo and 0.64 for Plan B. Roameo sits its panels on a light blue-grey tint, so its page reads as full, while Plan B's panels float on white. Largest empty rectangle is 0.018 of the page for Roameo (a thin gutter) and 0.029 for Plan B. Visible words are 892 for Roameo and 568 for Plan B.

| Part | Roameo has | Plan B has now | What Plan B lacks |
|---|---|---|---|
| Header | Logo, title with a one-line promise, the three ideas as one line with an icon each, a one-line definition ("An agent here is an AI helper with one job."), the names, the department line, the hackathon's full name top right, two labelled QR codes ("Try it", "Code") | Logo, title with a colon, name, "University of Massachusetts Boston • PEAAII Hackathon, October 2026", one unlabelled QR code. The promise sits in a white band below the header. | The three ideas with icons, the department line, the hackathon's full name ("PEAAII AI Applications Hackathon 2026"), a label on the QR code, a colon-free title |
| Story strip | Eight beats across the full width, each with an icon, a two-word head and one line, a tension beat in orange, the resolution beat in green, and a navy box with the one-sentence promise at the end | One panel in the top-left third: five beats with icons, plus the before and after program chart | A full-width strip that walks Jordan's evening beat by beat to "doors open on time", the tension beat in orange, the resolution in green, the promise box at the end |
| Three idea columns | Three columns, one per idea, each titled with the idea's icon and name, three blue sub-heads (the three parts), one visual per part, and a "How we tested it" box with a green check that says in plain words what a test is, how many runs and why | Two rows of three unrelated panels (story, screenshot, design, results, pantry, why it matters) | All of it. No idea columns, no sub-heads naming parts, no "How we tested it" box anywhere. The single results chart has no plain explanation. |
| Bottom row | "Who it is for, and who else helps plan trips" (audience, then named competitors with numbered sources and "We have not tested the others"), "Responsible use and limits" (a small data-flow diagram and the limits in plain words), "Three ideas, one trip" (the ideas repeated over the use case, thanks to the organizers, the model and data sources, numbered sources, where to try it) | "Why it matters" with five bold-lead lines, and a dark footer with the repository address | Competitors with sources, a responsible use and limits block, the three ideas repeated over Jordan's result, thanks, numbered sources |
| Readability | Smallest text in figures about the size of body text. Sub-heads in UMB blue, body near black, numbers large ("8 flights 18 hotels 59 events") | Figure annotations about 0.45 to 0.5 cm tall against body text about 1.1 cm. The screenshot's log text is unreadable at poster distance. `poster.tex` uses the slide figure `fig_design.pdf`, not the larger-type `fig_design_poster.pdf`. | Figure text at body size, a cropped screenshot, big numbers for the headline result |
| Colour | Navy header, UMB blue heads, orange only for the over-budget beat and bar, green only for the OK beat and the tested boxes | Mostly calm. Green also used for the receipt, orange for the 16:40 beat (right) and the late kits (right) | Green kept for met results and the resolution only |
| Gaps | Panels touch through thin gutters on a tinted ground | White gaps between rows and under the screenshot caption (8 percent of the height at the right, between the architecture figure and "Why it matters") | Tinted ground or panels sized to fill |

The Plan B poster is already dense and its figures are good. The lift is a re-grid, not new content. The story strip, the design figure, the 59 of 60 chart and the screenshot each have a natural place in the Roameo grid (strip on top, design figure in idea 2 or 3, chart split into per-idea "How we tested it" lines, screenshot cropped into idea 3).

## 5. Report, ranked findings

| # | Sev | Where | Requirement | Problem | Fix |
|---|---|---|---|---|---|
| R1 | high | Abstract | 6, polish | Raw `{cases}` placeholder (build_doc.py line 117, missing `f`). | Add `f`, rebuild, grep the extracted text for `{`. |
| R2 | high | whole report | 2 | No three ideas stated, delivered or repeated. Section 3 opens with five outcomes (Verify, Prepare, Commit, Keep, Report infeasible), then switches to the benefit triad. No conclusion at all. The report ends with Future work and three appendices. | Add "Plan B in one page" (Jordan's evening in beats, a 3 by 3 table of the ideas and their parts, the headline result), open section 3 with the three ideas, add a closing section "Three ideas, one evening". |
| R3 | high | after section 17 | 3 Q6 | No References and no Acknowledgements. Uncited outside claims, for example "Plan repair and information gathering are well studied in planning research" (section 2) and "inspired by the public context of campus food services" (section 16). | Add "Acknowledgements and sources" with numbered, verified references, and cite them in sections 2, 16 and 17. |
| R4 | high | title block | UMB identity | Opens with an "Item, Value" form table, no logo, no department, repository shown with "https://". | Title block with the UMB lockup at native size, title, promise, name, department line, hackathon line, address without https. |
| R5 | medium | section 2 | 3 Q2 | "What is different here" is a novelty statement, not a competitor answer. No named product, no indirect alternative, no citation. Tone is appropriately modest ("It does not claim to be the first of its kind"). | Add "Competitors and what is different", a table of alternative, what it does well, what it does not do, each statement cited. |
| R6 | medium | 4.2, 4.3, 8, 9, 12.4 | 1 | Several stories with equal weight. "Jordan" appears once (section 1). | Make 4.1 "Jordan's evening" the spine, label 4.2 and 4.3 as other ways the same evening could go under ideas 1 and 3, keep the skills exchange and pantry short as evidence for "adapts". |
| R7 | medium | sections 10, 16, ordering | 3 Q5, signposting | Responsible use is split between section 10 and section 16, which sits after the demo guide. None of the seven questions is signposted. | A "seven questions at a glance" table after the abstract, and headings a judge expects ("Who it is for", "Competitors", "Responsible use of AI", "Acknowledgements and sources", "Anything else"). |
| R8 | medium | whole report | plain wording | "gate" 10 times, "harness" 4 times, "policy" 57 times, "grant", "executor", code paths in prose, about 100 case ids. 140 colons in visible text outside command lines (47 of them clock times), 6 "https://" or "http://". | See section 11. Command lines in monospace stay as code. |
| R9 | medium | whole report | 1 | The second test record (12 cases, 120 runs, sections 12.1 to 12.6) is longer than the final test (12.7) and reads as a second headline. | Lead with the final six-case test, move the 12-case record behind it as "the earlier test that found three defects". |
| R10 | low | Figure 7 (image9.png) | 4 | The only figure under 300 ppi, 918 px at 5.0 in, about 184 ppi. All others 240 to 338 ppi. Its app text shows an en dash, an arrow and colons. | Re-capture at scale 2 or print at 3.5 in, crop to the changed rows. |
| R11 | low | Figure 11 (fig_freeze), Figures 1, 7 | 4 | Green used for a process step ("3. Test once") and the receipt. | Blue or navy. |
| R12 | low | section 15 demo guide | script sync | Demo guide clock ("5:27 to 6:11, What is next") disagrees with the script (slide 9 ends at 6:15). | Regenerate from the new script. |

Report figures were checked for resolution, not rendered as Word pages. LibreOffice is not installed here, so page breaks, empty page space and table widths in Word were not measured. The owner's Word check is still needed.

## 6. Scripts

- `pres-note.md` matches the `\note` blocks of `slides.tex` word for word on all 10 timed slides (auditor B). It never announces three ideas. Its opening is "Hello, I am Noctis Zhang from UMass Boston. This is Plan B. The show must go on." Its close repeats "checks the one fact that matters, prepares what it can undo, and commits only a change the server has checked", a triad never announced. It says "gate" 5 times.
- `poster-note.md` has five sections (scene, what it did, how it works, does it work, who it helps) and no three ideas.
- Neither script names a competitor or thanks anyone.

## 7. Empty space, measured

Method. Each page was rendered with `pdftoppm` (slides at 80 dpi, 630 by 410 px; poster at 50 dpi, 2400 by 1350 px). A pixel is near white when its grey value is at least 245 of 255. "Blank tenths" splits the page into a 10 by 10 grid and counts cells that are at least 99.5 percent near white. "Largest empty rectangle" is the largest axis-aligned all-white rectangle on a 200 px wide downsample, as a share of the page, with its position as x, y, width, height in percent of the page. The dark slides 2 and 10 read as 0 because they are navy, not white. Their empty navy space is noted in the text.

| Page | Content | Near-white share | Blank tenths (of 100) | Fully blank row bands (tenths from top) | Largest empty rectangle (share of page) | Rectangle x, y, w, h (% of page) |
|---|---|---|---|---|---|---|
| s-01 | title | 0.98 | 72 | 1, 2, 3, 9, 10 | 0.30 | 0, 0, 100, 30 |
| s-02 | 16:40 hook (navy) | 0.01 | 0 | none | 0.00 | navy page |
| s-03 | problem contrast | 0.95 | 36 | 1, 3 | 0.15 | 23, 13, 77, 20 |
| s-04 | projector story | 0.89 | 32 | 1 | 0.12 | 34, 13, 66, 18 |
| s-05 | quiet messages | 0.94 | 29 | none | 0.11 | 0, 18, 100, 11 |
| s-06 | design diagram | 0.86 | 29 | 1 | 0.10 | 86, 13, 14, 69 |
| s-07 | results | 0.90 | 46 | 1, 9 | 0.16 | 0, 78, 100, 16 |
| s-08 | pantry | 0.92 | 30 | 1 | 0.12 | 84, 13, 16, 81 |
| s-09 | who it helps | 0.84 | 33 | 1 | 0.09 | 0, 0, 100, 9 |
| s-10 | close (navy) | 0.07 | 0 | none | 0.01 | navy page, lower third empty navy |
| s-11 | backup 1, the six cases | 0.90 | 27 | 1 | 0.12 | 0, 82, 100, 12 |
| s-12 | backup 2, pantry board | 0.85 | 23 | 1 | 0.09 | 57, 0, 43, 22 |
| s-13 | backup 3, interfaces | 0.94 | 47 | 1, 7 | 0.17 | 0, 58, 100, 17 |
| s-14 | backup 4, cost per run | 0.96 | 57 | 1, 7, 8, 9 | 0.38 | 0, 56, 100, 38 |
| s-15 | backup 5, what the numbers do not show | 0.93 | 51 | 1, 7, 8, 9 | 0.37 | 0, 57, 100, 37 |
| s-16 | backup 6, partial handoff | 0.97 | 71 | 1, 5, 6, 7, 8, 9 | 0.57 | 0, 37, 100, 57 |
| s-17 | backup 7, frozen configuration | 0.96 | 61 | 1, 6, 7, 8, 9 | 0.48 | 0, 46, 100, 48 |
| poster | poster | 0.64 | 3 | none | 0.03 | 64, 61, 36, 8 |

Worst areas, in order.

1. **s-16** (backup, partial handoff). Two short paragraphs, then 57 percent of the page empty from 37 percent down.
2. **s-17** (backup, frozen configuration). 48 percent empty from 46 percent down.
3. **s-14** (backup, cost table). 38 percent empty under a small table.
4. **s-15** (backup, limits). 37 percent empty under three paragraphs.
5. **s-01** (title). 72 of 100 tenths blank, the top 30 percent and the bottom 20 percent empty. The logo prints about 0.58 cm tall.
6. **s-10** (close). The lower third of the navy page is empty under the logo and QR (auditor A measured rows 264 to 381 of 410).
7. **s-13** (backup, interfaces). 17 percent band empty across the lower half.
8. **s-07** (results). 16 percent band empty under the chart, which is capped at 4.15 cm.
9. **s-03** (contrast). 15 percent block empty right of the 16:40 quote, above the lanes.
10. **Every white content slide** has its top tenth blank (row band 1). The title sits below a blank strip and there is no header band. A navy title band, as in Roameo, would use it.
11. **Poster**. Only 3 blank tenths. The largest gap is 8 percent of the height between the architecture figure and "Why it matters" (x 64 to 100 percent, y 61 to 69 percent), and the band under the screenshot caption. The poster's problem is small type inside figures, not empty space.

The raw measurements are in `whitespace.json` and `grid.txt` (section 13).

## 8. The seven questions, coverage now

From auditor C, checked against the extracted text.

| Question | Slides | Poster | Report |
|---|---|---|---|
| Q1 Problem | covered (slides 2 and 3) | weak (shown in the 16:40 strip, never said in a sentence) | covered (section 1 and the abstract) |
| Q2 Competitors | **missing** | **missing** | **weak** (section 2, technique families only, nothing named or cited) |
| Q3 Target market | covered (slide 9, "Student organizers, clubs, volunteers and pantry staff") | covered ("Why it matters") | covered (3.1, adds "campus offices", so the three lists differ) |
| Q4 How it works | covered (slides 4 and 6) | covered (architecture panel and screenshot) | covered (sections 3 to 9) |
| Q5 Evaluation and responsible AI | weak (evaluation on slide 7, responsible use scattered over slides 3, 6, 8, 9, limits on an unread backup, privacy never said) | weak (chart and one "Safe" line, no sandbox, privacy or limits) | covered (sections 10, 11, 12, 13, 16, but split, and 16 sits after the demo guide) |
| Q6 Sources and acknowledgement | **missing** | **missing** | **weak** (Appendix C is an internal evidence index, no References, no Acknowledgements) |
| Q7 Anything else | weak (one footnote on slide 9, the address on slide 10) | weak (one "Next" line, the address) | covered (sections 13, 14, 15, 17) |

Student and community benefit is stated as a list ("fewer last-minute scrambles, no surprise spending, a receipt for every change") rather than through the story. The story ends on the schedule ("doors open on time", "demonstrations start after the reported arrival"), not on the people. The fixture names the activity "Community demonstrations" and mentions no students, so "student teams are ready to demo" in the script is narrative, which is acceptable for an illustration but should stay labelled as one.

## 9. The Rule of Three, as found and as proposed

As found (auditor B). Slides, poster, report and scripts use four different triads and never call any of them the three ideas.

- Subtitle, slide 10, poster band, report subtitle and abstract: "what to verify, what to prepare, and when to commit a change". Parts never given. "Prepare" never shown in Jordan's story.
- Slide 3 and its script: "checks the one fact that matters", "the model picks one option the server checked", "the gate writes a receipt".
- Slide 9, poster "Why it matters" (plus Safe and Next, five items), report 3.1 to 3.3 ("Easy to deploy" there, "Easy to run" elsewhere, and "Easy to deploy" has four parts): "Who it helps", "Easy to run", "Adaptive".
- Slide 10: "one check, a free swap, and a receipt".

Proposed, for the reviser to confirm. It keeps the one message the deliverables already carry ("deciding what to verify, what to prepare, and when to commit a change"), avoids "gate", and lets Jordan's story show each part.

1. **Check first.** A text is a claim, not a fact. Plan B checks only the one fact that could change the decision (one status check, "delayed, reported arrival 17.25"). Most messages should change nothing (the false alarm, the other order, the duplicate). How we tested it, in plain words: the believable false alarm among the new cases.
2. **Prepare checked options, and let the AI only pick.** The server builds the possible fixes and checks each against the deadline, the people and the budget (16 built, 3 passed every check). The AI picks one and holds no tool that changes anything (the free swap). A backup can be held for free while a fact or a person's OK is pending (shown in a second, labelled development case, since Jordan's story has no hold). How we tested it: the real projector delay among the new cases.
3. **Change only what the server checked, and keep a person in charge of money.** The server checks every change against the rules before it happens (the right role, the plan still current, within budget) and writes a receipt. Any spending waits for a person's OK. Every change has a receipt Jordan can show the club. How we tested it: no executed action broke a rule, and the refused attempts.

Benefits ("who it helps", "easy to run", "adapts to new events") then answer question 3 in the bottom row, with the same three labels in every deliverable, and are not presented as headline ideas.

Truth constraint for the reviser. Do not put a hold into Jordan's projector story unless a committed run shows one. Report 4.3 is a separate development case. Every count in the proposal above must be re-checked against section 10 before it is printed.

## 10. Numbers and claims

From auditor D, who recomputed every number from the committed `metrics.json` and `spend_extract.json` files, the results READMEs, the Wave 1 to 3 packets, the scenario files and the app code. 32 claims checked: 16 verified, 9 inconsistent, 4 unsupported, 3 wrong. I re-checked the defect count myself (item D4).

**Safe to print (verified).**

- **59 of 60 runs met the expected outcome on 6 new cases.** `apps/plan_b/evaluation/results/wave3b_fresh_20261025T2327Z/{campus,pantry}/report/metrics.json`. Campus, the fixed rules 3 of 4 (the miss is the late volunteer case), each AI approach 12 of 12. Pantry, the fixed rules 2 of 2, each AI approach 6 of 6. 60 runs = 6 cases times 10 runs. Each case ran the fixed rules once (no AI) and each of the three AI approaches 3 times (seeds 101, 202 and 303 recorded, not sent). So "3 runs" applies to the AI approaches only. The poster never says where 60 comes from.
- **Our coordinator met 18 of 18**, and so did the tool-calling model and the check-all variant. Name mapping is consistent everywhere (our coordinator P2, tool-calling model P1, check-all variant P3, fixed rules P0).
- **The cases were held out.** Cases C09 to C12, T05, T06. Frozen at 23.23.47 UTC, locked 7 seconds later in the same commit `5955243`, first AI call at 23.27.31 UTC (3 min 38 s later). The author of the code changes never opened them.
- **No executed action broke a rule.** Executed violations 0 for every approach in both suites. The server refused 6 attempts (1 plan-changed-meanwhile, 5 resource-unavailable).
- **Cost.** The new test cost $3.61 for 60 runs (3.60815 USD), 194 AI calls, per-run costs as on backup slide 14. Limits per run 48 tool calls, 8 AI calls, $0.50, 900 seconds.
- **The earlier 12-case test.** Campus 8 cases and 80 runs, pantry 4 cases and 40 runs, and every table value in report 12.1 to 12.6 (`wave3_heldout_20261025T1625Z`).
- **Jordan's story numbers.** Text at 16.40, about 25 minutes late, one status check of 2 simulated minutes, delayed with reported arrival 17.25, 16 options built and 3 passed, free swap at 16.43, plan version 1 to 2, $35 backup not booked, demonstrations at 17.30 (`plan_b/scenarios/private/dev01.json`, `handoffs/wave_2/evidence/storyboard/storyboard_report.json`).
- **The pantry numbers.** 40 kits by 13.40, 24 on the shelf, 20 late and not counted, 16 in the partner pool, partial handoff 10 of 16, 34 handed out, 6 short, no kit counted twice.
- **Slide 5's check rate.** Our coordinator 0.8 status checks per campus run (10 in 12), the check-all variant 1.5 (18 in 12).
- **What the app does.** One server path checks every change (role, current plan, budget) and writes a receipt (`plan_b/tools/executor.py`), spending starts as a free hold, and a person approves money.

**Wrong or inconsistent, fix before printing.**

| # | Sev | Where | Claim now | What the records say | Fix |
|---|---|---|---|---|---|
| D1 | high | report abstract | "run on {cases} new cases" | 6 (the placeholder is unfilled) | Fill it, rebuild, grep for `{` |
| D2 | medium | report section 14 | `uv run plan-b eval verify-freeze --require-heldout` "should print verified" | That command checks the version 1.1 freeze by default, and 14 app files changed since, so it would most likely fail. Not run in this audit. | Use the version 1.2 command from `apps/plan_b/docs/EVALUATION.md` line 425 (`--freeze freeze_v1_2.json --heldout heldout2.json --require-heldout`) and confirm once. |
| D3 | medium | report 12.6 | "Python tests, 896 passed" at commit `3442874` | `3442874` predates version 1.2. The final tree's record is 951 passed (`handoffs/wave_3/VERIFICATION.md` line 105, an earlier audit run 950). | Lead with 951 on the final version, label 896 as version 1.1. |
| D4 | medium | owner brief, all items | "the earlier 12-case test found three defects that were fixed" | `handoffs/wave_3/README.md` line 78 records **four** defects (plus a rate-limit change and a report-order erratum). The deliverables give no count ("real defects"), so nothing printed contradicts the records. `STORY_PLAN.md` E9 says the disagreement is "flagged in the report", but the report does not mention it (0 hits for a count next to "defect"). | Never print "three". If a count is wanted, print four, cite the Wave 3 packet, and record the brief's "three" in one sentence of report 12.7. |
| D5 | medium | slide 7 caption, script slide 7, report abstract and 12 | "found real defects, fixed before the freeze" | The diagnostic rerun on the spent cases (`wave3b_rerun_spent_20261025T2345Z`) shows our coordinator still missing C07 in 0 of 3 runs and the check-all variant still missing T02 in 0 of 3. Report 12.7 says so itself. | "found real defects, and I changed the code to address them before the freeze". Do not say all were fixed. |
| D6 | medium | slide 9 "Adaptive" | "A new event is a configuration file." | Report section 9 says the pantry needed a stock extension (`store/migrations/0004_consumable_stock.sql`, `domain/stock.py`, `tools/stock.py`), "reuse with an explicit extension, not zero-shot transfer". | "A new event of a known kind is a configuration file. The pantry needed one small stock extension." |
| D7 | medium | report sections 1 and 2 | Statements about tool-calling agents, rule systems, planning research | No citation, no References section | Cite each (section 5, R3) |
| D8 | low | backup slide 11, row "Campus, late volunteer" | "The leader of the first activity reports a late bus" | C11 (`ev_w2n.json`) is the skills exchange leader, a middle activity | "The skills exchange leader reports a late bus, then checks in" |
| D9 | low | slide 4 caption, report 4.4 | "In a recorded run, our coordinator made the same check and the same swap at 16:43" | True, but that recorded run is version `live/1.0.0` (Wave 2), not the tested 1.2 | "an earlier version of our coordinator" |
| D10 | low | both scripts | "No action ever broke a rule" | The record measures executed actions. 6 attempts were refused. | "No executed action broke a rule", as printed |
| D11 | low | report 12.7 and 13 | Two of the new cases repeat spent conditions | The fresh results README says all six repeat a development condition (backup slide 15 already says so) | "All six repeat conditions seen in development" |
| D12 | low | report 15 demo guide | "5:27 to 6:11, What is next" | Script slide 9 ends at 6.15 | Regenerate from the script |
| D13 | low | report 12.6 | "922 counted words" citing `REHEARSALS.md` | 922 is right for the current script, but `REHEARSALS.md` line 152 timed an earlier 932-word script | Cite `submission/README.md` or the script |
| D14 | low | script slide 2 | "Events like this have no operations staff." | No record or source | "This event has no operations staff" or "often run without" |
| D15 | low | poster-note | "with any model or none" | The provider is OpenAI-compatible only | "any OpenAI-compatible model, or none" |
| D16 | low | report 17 | MBTA "a key exists" | Only a local, uncommitted key file supports it | Drop "and a key exists" |

The owner's keep list also says "59 of 60 runs met the expected outcome" and "no executed action broke a rule". Both are verified. "The earlier 12-case test found three defects that were fixed" is the one item on the keep list that the records do not support as worded (D4, D5).

## 11. Writing rules and plain wording

From auditor E, who counted over the extracted visible text of each item and both scripts. Report command lines in monospace were counted separately as exempt.

| Rule | Slides | Poster | Report | pres-note | poster-note |
|---|---|---|---|---|---|
| em dash, en dash, "---", "--", semicolon | 0 | 0 | 0 in prose (10 "--" in exempt command lines) | 0 | 0 |
| colon, clock times | 34 | 15 | 47 (plus about 34 inside figure images) | 12 | 0 |
| colon, other | 39 | 14 | 84 | 6 | 3 |
| "https://" or "http://" shown | 0 | 0 | 6 (2 more in exempt command lines) | 0 | 0 |
| AI-sounding words | 0 | 0 | 4 ("harness") | 0 | 0 |
| "gate" | 9 | 4 | 10 (plus 4 inside figures) | 5 | 1 |
| "checkpoint" | 0 | 0 | 0 | 11 | 0 |
| "fallback" | 0 | 0 | 1 | 0 | 0 |
| model id string `anthropic/claude-sonnet-5.5` | 4 | 1 | 2 | 0 | 0 |
| "option id", "schema", "API" | 16 | 7 | 7 | 0 | 0 |
| snake_case identifiers | 0 | 1 | 68 | 1 | 1 |
| file names or paths | 0 | 1 | 107 | 3 | 1 |
| case codes (C01 to C12, T01 to T06, dev01 and so on) | 0 | 0 | 100 | 0 | 0 |
| policy codes (P0 to P3), receipt ids (`rcpt_0001`) | 0 | 0 | 4 and 3 | 0 | 0 |

My own raw count of every ":" character agrees (slides 73, poster 29, report 143 including exempt lines, pres-note 18, poster-note 3). The slides' count includes text inside the TikZ figures, which pdftotext reads. The board screenshots are images and carry more colons and code strings that no text count sees.

Findings, ranked.

1. **Critical. The `{cases}` placeholder** in the report abstract (section 5, R1).
2. **High. The title has a colon on every item** and in the PDF metadata. "Plan B: The Show Must Go On" becomes "Plan B, The Show Must Go On" in `\title`, `pdftitle`, the poster header, the docx title and core properties, and both scripts.
3. **High. Clock times with colons**, two of them in slide titles ("16:40. Twenty minutes to doors open.", "16:40 again. Check first, then change.") and two in poster block titles. Use "4.40 pm" in titles and speech, "16.40" on figure axes, "23.23 UTC" for time stamps, "36 s" in the demo guide.
4. **High. Lead-in and label colons.** Backup titles "Backup: ..." (7), "Campus event: 4 cases, 40 runs", "Our coordinator: picks checked options", "The runs: ...", "Model:", "Limits per run:", the poster's five "Safe:", "Who it helps:" leads, "Screenshot: ...", "target: 40 kits by 13:40", and 84 in the report ("Three facts make this hard:", "a narrow question: can an agent ...").
5. **High. "gate" in titles, figures, captions and both scripts** (29 in text, 4 more in report figures). Replacement text to use: "the server checks every change against the rules before it happens and writes a receipt". The figure box "One gate" becomes "The server checks every change". "An AI agent with no gate" becomes "an AI agent that acts without checks".
6. **High. Tests are not explained at a first-year level** on the poster or in either script. Slides partly (sandbox named, not explained, "3 times" with no reason except on a backup, "met" defined only on backup 15). The report does best (section 3 explains the sandbox, section 11 explains held out, the Glossary defines "met") but has no plain definition of a test case and no reason for repeated runs.
7. **Medium. The report body is full of codes.** About 100 case codes, a receipt id, an order id ("order P17"), policy codes, version strings, run ids, and 120 inline-code runs. Name cases by what happens ("the late volunteer case"), keep codes in one table column and the appendices.
8. **Medium. Engineering words on screen.** "option id", "strict, schema checked", "OpenRouter model API", "board HTTP API", "sandbox tool API", "approve, report, attest", "policy" (57 in the report), "executor", "episode", "negative control", "post-hoc", "denominator".
9. **Medium. "https://" and "http://" shown** six times in report prose and tables.
10. **Medium. "checkpoint"** 11 times in `pres-note.md` ("**Checkpoint 0:08.**"), each with a colon time. The `\note` markers in slides.tex read "(8s, ends 0:08)" instead, so the two are not character-identical in these lines.
11. **Medium. "harness"** 4 times in the report, "fallback" once.
12. **Low. Provenance in the scripts.** File names and run ids (`STORY_PLAN.md`, `make_results.py`, `wave3b_fresh_20261025T2327Z`) in the presenter directions. Move them to README.

Passes. No em dash, en dash, "---", "--" or semicolon in any prose. No AI-sounding word on the slides, the poster or in the scripts. Only Noctis Zhang is named as author, never with a gendered pronoun, and the report uses "I".

First-year explanations, where they are now.

| Explanation | Slides | Poster | Report | Scripts |
|---|---|---|---|---|
| What a test case is | missing (only the list of six situations) | missing | missing as a definition | missing |
| What the sandbox is | named ("a simulated event in a local sandbox"), not explained | missing ("2 simulated minutes", "sandbox tool API") | explained in section 3 ("No university booking, purchase, delivery or message is made") | "the event is simulated" only |
| What held out means | half ("Written and locked before the first model call") | missing ("6 new cases") | explained in section 11 and the abstract | half ("written by a separate worker before the freeze") |
| What 3 runs means and why | number only, reason on backup 15 | missing | "repeated trials, not independent units", no reason | number only (slides), missing (poster) |
| What "met the expected outcome" means | backup 15 only | missing | Glossary | missing |
| Why the AI only picks among checked options | slide 6, well done in the script | stated as a rule | sections 5 to 7 | slide 6 script, well done |
| Why a hold before spending | slide 6, one line | missing | section 4.3 and 10 | slide 6 script |
| Why a person approves money | slide 3, slide 6 | stated as a rule | sections 1 and 10 ("Changes have owners") | slide 3 script |

`check_writing.py` gaps. It looks only for U+2012 to U+2015, U+2212, "--" and ";". It misses every colon, "https://" in visible text, every banned AI or mechanical word, code identifiers, text inside the report's figure images, the slides.tex speaker notes, unrendered placeholders such as `{cases}`, and author names. It also skips every inline-code run in the docx (120 runs), so identifiers placed there are never seen. It scans README, DRAFT, STORY_PLAN and the Wave 3 handoffs, which are not deliverables. Run read-only, it printed "16 files checked, 0 lines with a forbidden character" and exited 0.

## 12. Things the reviser should keep

- The Jordan projector story, its beats and its resolution at 17.00 (slide 4, poster top left, report Figure 1).
- The one final system on the slides and the poster (6 new held-out cases, 59 of 60 runs met the expected outcome, no executed action broke a rule). For the earlier 12-case test, say it "found real defects that I changed the code to address", or "four defects" with the Wave 3 packet as the source, never "three defects that were fixed" (section 10, D4 and D5).
- The plain names for the four approaches (the fixed rules, the tool-calling model, the check-all variant, our coordinator).
- The honest limits (six cases cannot rank the approaches, everything is fictional and local, no community pilot).
- The board screenshots, cropped larger.
- The poster's density. It already fills its page.
- No slide is a bullet list. Slides use figures and short sentences.
- Logos are high resolution (blue lockup 6600 by 5100 px, white lockup 2289 by 1094 px, text logo 2222 by 1132 px). The fault is size and padding, not blur.
- Report figures are sharp (240 to 338 ppi), except Figure 7.

## 13. Evidence files and commands

Scratch folder `/tmp/claude-1002/-data-noctis-GitHub-Data-COLLIE/73b311fe-2b64-4d29-96d1-2bd778af21aa/scratchpad/w8/work_audit0/`.

- `slides/s-01.png` to `s-17.png`, `poster/p-1.png`, `sheet.png` (contact sheet), `slides/slides.txt`, `poster/poster.txt`
- `doc/doc.txt` (report text with figure and table markers), `doc/doc_headings.txt`, `doc/media/` (the 15 embedded figures)
- `whitespace.json`, `grid.txt`, `ws_table.md` (empty-space measurements), `counts.txt` (punctuation and key-word counts)
- `wordcount.txt` and `wc.py` (visible words per slide), `roameo/rp-1.png` and `roameo/rposter.txt` (the Roameo poster at the same 50 dpi)
- `findings_A.json` to `findings_E.json` (the five auditors), `E/` (auditor E's count scripts), `REQUIREMENTS.md` (the brief they were given)

Commands run, all read-only on the repository.

```
pdftoppm -r 80 -png slides/slides.pdf .../slides/s
pdftoppm -r 50 -png poster/poster.pdf .../poster/p
pdftotext -layout slides/slides.pdf .../slides/slides.txt
pdftotext -layout poster/poster.pdf .../poster/poster.txt
cd documentation && uv run --no-project --with python-docx==1.1.2 python .../docx_extract.py Plan_B_Project_Documentation.docx .../doc/doc.txt
  -> figures 15 tables 15 headings 36 media 15
python3 .../whitespace.py .../slides/s-*.png .../poster/p-1.png > .../whitespace.json
python3 .../counts.py ... > .../counts.txt
montage s-*.png -tile 4x5 -geometry 480x312+6+6 .../sheet.png
python3 .../wc.py slides/slides.pdf 17 > .../wordcount.txt
pdftoppm -r 50 -png /data/noctis/GitHub-Data/Travel_Agent/docs/presentation/poster/poster.pdf .../roameo/rp
cd PEEAI_plan/submission && python3 check_writing.py   (auditor E, read-only)
  -> 16 files checked, 0 lines with a forbidden character, exit 0
```

`soffice` is not installed, so the docx was not rendered to pages.
