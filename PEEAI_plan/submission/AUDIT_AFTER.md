# AUDIT_AFTER. The final audit of the Plan B deck, poster and report

Worker audit1, October 26, 2026, from 16.12 EDT. Inputs were AUDIT_BEFORE.md, REVISION_PLAN.md and the build report. COMPARISON_BRIEF.md never appeared anywhere in the repository or the scratch folders, so the "Why Plan B" claims were checked against RESEARCH_BRIEF.md (sources [1] to [37] and its "What not to claim" list) and against the code. Nothing was committed. Only files under PEEAI_plan/submission/ changed.

This note quotes old wording on purpose, so check_writing.py does not read it.

## 1. How the audit ran

1. Rebuilt all three items from source (deck figures, deck, poster figures, poster, docx) and rendered them to PNG. Slides at 60 dpi, poster at 40 and 100 dpi, the docx through pandoc and headless Chromium (an approximate page render, 34 pages, because Word and LibreOffice are not installed). Empty space was measured with tools/whitespace.py.
2. Round 1, six read-only auditors in parallel. A designer (against the owner's ICML sheet), B story and Rule of Three, C the seven questions, D accuracy against the committed results and RESEARCH_BRIEF.md, E writing rules, notes and timing, F a first-time hackathon judge who saw only the rendered pages.
3. I checked each finding myself against the files, fixed the confirmed ones, rebuilt and rechecked.
4. Round 2, three fresh auditors (designer, story and Rule of Three, writing and wording) on the fixed versions. Confirmed findings were fixed, then everything was rebuilt and rechecked again.

Scratch evidence is under the run's scratch folder, work_audit1/ (r0 is the state before this audit, r1 after round 1, r2 the final state, and build_all.sh is the rebuild and render script).

## 2. Measured state before this audit (r0)

- Deck 22 pages, 0 overfull boxes, visible words per main slide 24 to 37 (tools/wc.py), script 967 words, 414 s.
- Poster 473 words, largest empty rectangle 2.7 percent of the page.
- Docx 19 figures, 15 tables, 34 approximate pages.
- check_writing.py 16 files, 0 hits.
- Largest empty rectangles on the main slides 7 to 9 percent of the page, mostly the footer band. Backups up to 13 percent (s-21 and s-22, text-only backups).

## 3. Final measured state (r2, after both rounds)

| Item | Measure | Before (r0) | After (r2) |
| --- | --- | --- | --- |
| Deck | pages, overfull boxes | 22, 0 | 22, 0 |
| Deck | visible words per main slide (tools/wc.py, digits 1 to 3 counted) | 24 to 37 | 27 to 38 (slides 3, 5, 9, 13 at 37, slides 11 and 14 at 38) |
| Deck | largest empty rectangle, main slides | 7 to 9 percent (footer band) | 7 to 9 percent (footer band) |
| Script | spoken words, seconds at 140 a minute | 967, 414 | 976, 418 (limit 420) |
| Notes | equal to the script | yes | yes (check_writing.py rule g) |
| Poster | words (pdftotext), overfull boxes | 473, 0 | 543, 0 |
| Poster | largest empty rectangle | 2.7 percent | 2.5 percent |
| Poster pitch | words, seconds | 233, 100 | 311, 133 (short version 35 s) |
| Docx | figures, tables, approximate pages | 19, 15, 34 | 19, 15, 35 |
| check_writing.py | files, hits | 16, 0 | 17, 0 (the raw speaker notes are now checked too) |
| PDF metadata | title, author | Plan B, The Show Must Go On, Noctis Zhang | same |

The poster is about 40 words over the owner's "about 500". The extra words are the competitor comparison, the "We have not tested the other tools named here" line, the sources line and the line that defines the test, which the seven questions and the "Why Plan B" requirement need. It keeps the calm six-panel layout, the real board screenshot and the design diagram.

## 4. Round 1 findings and what was done

Six auditors returned 18 (F), 20 (B), 17 (C), 10 plus a 40-claim table (D), 22 (E) and 15 (A) findings. Each was checked against the files before it was acted on. "Fixed" means changed, rebuilt and looked at in the render.

### High

| Finding | Verdict | Action |
| --- | --- | --- |
| Report Table 12 and backup B6 said Plan B runs "with no account" (found by me first, then D1, D2, C14) | confirmed, the AI approaches need an AI service account | Fixed. "free and open source under GPL-3, with no vendor contract. It needs an account with an AI service unless the group uses the fixed rules or a model on its own computer", and on B6 "runs today on one laptop, free, with no vendor contract" |
| C1, the poster named no competitor | confirmed | Fixed. The bottom right panel is now "Why Plan B, not the tools you use" and names the group chat and shared sheet [11, 12], Zapier [7], Cvent and Bizzabo [2, 3] and the assistants [4, 6] |
| C2, the poster's three points compared with nothing | confirmed | Fixed. Each point now names what the others are built for, from RESEARCH_BRIEF.md sources, and the panel says the other tools were not tested |
| C3, no sources on the poster | confirmed | Fixed. The footer says "Sources [1] to [37] are in the documentation", and the Why panel carries the bracket numbers |
| C8, on slide 13 only Safer was compared with a competitor | confirmed | Fixed in the script. Safer against Zapier's added approval step [7], More flexible against Cvent and Bizzabo building for event teams [2, 3], More personal against assistants that ask as their makers designed [4, 6], then "We have not tested the others" |
| B2, the talk never said why a person approves money or why Plan B holds before spending | confirmed | Fixed on slide 6. "Money waits for a person's OK, because club money is a person's call", then the hold as a separate practice case (see round 2 B1 for the final wording) |
| B9, the half-minute poster pitch never named the three ideas | confirmed | Fixed. The short version now walks Jordan's evening through the three ideas in about 35 seconds |
| A1, poster figure text below 24 pt | partly confirmed (story and design labels are about 15 to 20 pt at print size) | Partly fixed. Removed "2 rehearsal minutes" and "Transit alerts not connected yet", shortened the design labels. A font bump inside both figures made labels wrap and collide, so it was reverted. Still open, see section 6 |
| F1, the hero pictures come from the fixed rules, not the AI | confirmed, and true to the records | Fixed in wording, never in substance. Slide 7 says "in a rehearsal with the fixed rules and no AI", the script says the fixed rules made the same swap and that an earlier recorded AI run made the same pick, and the poster title says "a rehearsal with no AI" |
| F2, the evaluation does not show what the AI adds | confirmed as a fair reading of the records | Not changed in substance, because the records say every AI approach met 54 of 54 and the report already says the test does not show that picking from a list improves outcomes. The script now says the fixed rules missed "the kind of message the AI is there to read". The cost difference stays on backup B7 and in the report |

### Medium and low, fixed

- Slide 5, the navy sliver in the Before row (A7, F11). The whole Demos block is now one orange-outlined box. The projector label reads "5.25 pm" (round 2 E6).
- Slide 9, the AI dot groups had no labels (A6, F3). The heads now read Fixed rules, Ours, Check-all, Tool-calling at one size on one baseline (round 2 A1), and the script names the three AI designs.
- Slide 12, direct and indirect were not named (C10). The rows read "Indirect, today" and "Direct, change plans", and the script says "Indirect competitors first" and "Direct competitors, event platforms such as Sessionboard".
- Slide 13 captions (F6, B4, C9). "The three ideas, built in", "3 kinds of event, your AI or none", "Your event, your spending limit".
- Slide 14 (C12, A15). "Next, a walk-through with staff." and "Thanks, PEAAII organizers". The code address is larger and in ink.
- Slide 8 title, "evenings" became "event days" (B19). Slide 10 title "Inside Plan B, careful with messages and money" (B7).
- Slide 11, the empty middle card and the unexplained pantry bar (F5, round 2 B7). The middle card reads "A helper runs late" (the late-volunteer test case), and the pantry card reads "20 of 20 runs met, made-up pantry days".
- Script bridges (B5). "So how does Jordan decide in twenty minutes?", "One evening is a story, not proof.", "Inside Plan B, the same ideas guard messages and money.", "So who is it for?".
- The resolution (B1). Slide 14 says doors opened at five, the projector came at five twenty four and the demonstrations started at five thirty. The poster story's last step says "projector there since 5.24 pm".
- Poster (A2, A4, A10, B11, B12, B13, C5, E14, F4, F13, C17). The left results chart no longer touches the right one. Story times are all "pm". The receipt is blue, not green. The poster subtitle says what Plan B is and who it is for. The story step at 4.43 pm says "3 of 16 changes fit". A line under the results defines the test and its limits. The pantry chart has a caption. The four approaches carry the deck's names.
- Poster pitch (B10, B11, C1, C4). It explains a test case, the practice copy, sealed and the three runs, names the other tools, says "We have not tested the others", gives the next step and the thanks.
- Report. Table 12 file paths moved to the appendices (F17). The Why section is now 10.3 inside the competitors part, with 10.1 direct and 10.2 indirect (C13), and later sections renumbered with their cross-references. "6. How we evaluated the AI agents" (C16). Sessionboard in the Safer row (C9) and the assistants sentence reworded (C15). The fourth problem of the earlier test now matches the records, a new AI call was needed and the 8-call cap sometimes came first (D3). The earlier test's costs are summed from the unrounded values, $5.56 and $1.96 (D4). Reference [25] is now cited in Table 9 (D5). The evidence index points to the Wave 2 run report for the 3 calls and $0.0366 (D9). The rerun note says two targeted cases still miss in every run and a third in two of three (D10). Three hard things instead of four (B20). The reason for a free hold (B16). The pantry under the three ideas (B15). 8.1 to 8.3 named after the ideas (B14). The case code column is gone from Table 6 (E13). The pantry log screenshot no longer ends in a half-cut line (A13).
- check_writing.py (E1, E2, E3, E4). It now checks the raw speaker notes for dashes and semicolons, catches more inflections (gating, gatekeeper, armed, orchestrate, modular), flags dotted file names on the deck, poster and scripts, and reads the cp: core properties. The script header no longer names files. timing.py runs without an argument (E22).

### Round 1, not changed, with the reason

- A5 and F15, the card layout repeats on several slides. It is the deck's visual system, and a redesign did not fit the time box. Slides 9 and 13 now say more concrete things.
- A3, the clipped "Changed" pills in the board screenshot. Fixed in round 2 by cropping that column (section 5).
- A8, A9, A12, F7, F9, F10, F16, B6, B17, B18, C6, C7, C11, D6, D7, E5 to E8, E11, E12, E15 to E17, E19 to E21 were low or are covered elsewhere. Some were done in round 2 (E12 in part, E17 spelling). C11 (model credit and sources on slide 14) does not fit the word limit, and backup slide 8 carries both. E15 (spelling out PEAAII) was not done because the expansion could not be checked in the repository.

## 5. Round 2 findings and what was done

Three fresh auditors. The designer found no high item. The writing auditor found one high, the story auditor one high.

### High, fixed

- Writing E1. The report's "How to try it" said "Section 14 has the commands" after my renumbering. It now says section 13.
- Story B1. The talk did not say why the backup is held for free, and "a second practice case" could be heard as part of Jordan's evening. Slide 6 now says "In a separate practice case, not Jordan's, the projector came too late. Plan B held the backup for free, so it was not lost while a person decided." Backup 3 is titled "A separate practice case", its duplicate grey tag is gone, and report Table 3 labels the hold as the separate 5.45 pm practice case (story D1).

### Medium, fixed

- Design A1, slide 9 headers at one size and on one baseline.
- Design A2, slide 7 now shows the board cropped before the "Change" column, whose pills the app draws over their own text. The app code is off limits, so the crop is the fix. "Everything else unchanged" and "Two activities swapped" now sit beside the screenshot, the second with an arrow to the two blue rows. The report's Figure 8 uses the same crop (screenshots/shot_campus_beforeafter_crop.png, cut from the original capture with no other change).
- Design A3, "Checks the fact" and "Lists the changes that fit" no longer read as one line in the design diagram (poster, backup 2, report Figure 7).
- Writing E2, Table 5 of the report no longer lists file paths, and points to Appendix B.
- Writing E3 and E4, the four approaches. The script names the three AI designs on slide 9, and the poster chart uses the deck's names. The slide 9 heads stay short (Ours, Check-all, Tool-calling) to keep the slide near the word limit.
- Writing E5, the tagline wording. Slide 6's title, the script on slides 3 and 14, the report's close and section 10 and backup 7 now all say "money waits for a person's OK".
- Writing E6, "5.25" became "5.25 pm" on slide 5 and in the report.
- Writing E7 and E8, plain words in the report for the OpenAI-compatible setting, OpenRouter's routing, OWASP and prompt injection, with "Prompt injection" added to the glossary.
- Story B2, the reason the AI only picks. "So the AI only chooses among changes that fit, and Plan B makes the change."
- Story B3, when the projector is due. "The projector is due at five, when doors open, and the demonstrations at ten past five need it."
- Story B4, why the AI matters. The fixed rules missed "the kind of message the AI is there to read".
- Story B5, slide 10's script now follows the ideas, then money, then privacy, then the limits.
- Story B6, the close says Jordan did not spend club money "on a maybe" (the look-up confirmed the delay, so it was not a rumor). The report's close matches and gives 5 pm, 5.24 pm and 5.30 pm (story D4).
- Story B7, the slide 11 pantry card (see section 4).
- Story P1, the poster's More flexible and More personal now compare with Cvent and Bizzabo [2, 3] and the assistants [4, 6].
- Story N1 and N2, the poster pitch says Safer, More flexible and More personal with a comparison each, and repeats the three ideas over Jordan's evening at the end.
- Story D5, report 8.2 is now Leave a receipt and 8.3 Money waits for a person's OK, in the order of the ideas.

To pay for the script additions, two sentences were cut from the talk (the earlier test's four problems, which backup 5 and the report keep, and the count of student groups, which slide 11 shows), and the look-up sentence on slide 4 was shortened. The script ends at 976 words and about 418 seconds.

### Low, fixed in round 2

Writing E10 (tabletop became "a walk-through on paper", the fingerprint and transit wording), E13 (backup 5 no longer says "Wave 3"), E14 and N3 (the pitch says "each of the three AI designs"), E15 (slide 10's limits sentence), E16 (slide 14 line shortened), E17 (color, license, misbehavior, colors). Design A9 in part (slide 12 caption is now "From their own pages."), A11, A14 and A16 (poster orphans). Story B8 (campus, community and pantry events), D2.

Design A4 (medium, round 2), the case labels on backup 1 sat a line below their row. A colour command at the start of each case cell opened an empty line, so each cell now starts with \leavevmode, and the labels line up with the row text.

## 6. What remains

No high or medium finding from either round is left open. In order of weight, these lower items remain.

1. Poster figure text. The smallest labels inside the story figure and the design diagram are about 15 to 20 pt at print size, against about 30 pt for the poster's body text (round 1 A1, round 2 A15). Making them larger needs both poster figures redrawn at poster scale. A quick size bump made labels wrap and collide, so it was reverted. Readable at arm's length, small from 2 meters.
2. Poster length. 543 words against "about 500" (section 3).
3. Slide words. tools/wc.py counts 37 on slides 3, 5, 9 and 13 and 38 on slides 11 and 14, including the panel digits 1 to 3 on slides 3 and 14. The other eight main slides are within 35.
4. The deck's card layout repeats on slides 1, 3, 8, 11, 13 and 14 (round 1 A5, F15).
5. The evaluation cannot show that the AI improves outcomes over the tool-calling model (round 1 F2). This is what the records say, and the deck and the report say so. It is not a defect to fix.
6. Text inside the real app screenshots keeps the app's colons, dashes and internal names, because the app code is off limits and check_writing.py cannot read pixels. The slide 7 and report Figure 8 crop removes the column whose labels the app draws clipped. The poster's crop already left it out.
7. Low polish left as it is. The slide 12 navy "Plan B" column has no connector (A7). The backup 6 and backup 7 tables and chart styling (A12, A13). Arrowheads touch some icons in the design diagram (A5). The poster figures use Helvetica while the poster text uses Lato and Raleway (A15). The report keeps Office's default caption colour (round 1 A14) and has no image alt text (E21). Several "X, not Y" sentences remain in the report (E11). "PEAAII" is not spelled out, because the full name is not in the repository (E15).
8. Stale figure files. slides/figures still holds old poster figure copies (fig_story_poster, fig_result_poster) and unused figures (fig_contrast, fig_architecture, fig_freeze and others), some with colons or old words. Nothing includes them, because the poster reads poster/figures first. The rebuild script compiled the stale poster copies again, so their PDFs show as modified in git.
9. The owner's Word check. The docx was checked through its text, its structure and an approximate HTML render. True Word pagination was not seen.
10. Rehearsal. The script is 418 seconds at 140 words a minute, so a spoken rehearsal should confirm it fits seven minutes with the slide changes.

## 7. Commands and results

All from PEEAI_plan/submission unless a path says otherwise, with PATH including /usr/local/texlive/2026/bin/x86_64-linux.

- Rebuild and render (work_audit1/build_all.sh r0, r1, r2). pdflatex on every figure that slides.tex, poster.tex or build_doc.py names, latexmk -g -pdf slides.tex, lualatex on poster/figures/fig_*.tex, latexmk -g -pdflatex='lualatex -interaction nonstopmode' -pdf poster.tex, uv run --no-project --with python-docx==1.1.2 python build_doc.py, pdftoppm at 60 dpi (slides) and 40 and 100 dpi (poster), pandoc plus chrome-headless-shell for the docx pages, tools/whitespace.py. The first version of the script found figures only through "figures/fig_" and missed the ones the deck names through its \visual macro, which was found and fixed in round 2.
- Final results. slides exit 0, Overfull 0, 22 pages. poster exit 0, Overfull 0. "wrote Plan_B_Project_Documentation.docx, 19 figures, 15 tables". python3 check_writing.py, "17 files checked, 0 hits". python3 timing.py slides/pres-note.md, total 976 words, 418 s. python3 timing.py poster/poster-note.md, 311 words, 133 s. python3 tools/wc.py slides/slides.pdf 14, 34 33 37 34 37 31 27 29 37 35 38 32 37 38. pdftotext poster.pdf | wc -w, 543. pdfinfo, title "Plan B, The Show Must Go On", author Noctis Zhang on both PDFs.
- One round-2 rebuild failed with "Unknown arrow tip kind 'Stealth'" after the slide 7 change. slides.tex now loads the arrows.meta library, and the rebuild passed.
- Facts checked in the repository for the new wording. dev01.json (ETA 17.25, arrival 17.24, check-ins 17.05 and 17.20), dev02.json (ETA 17.45, the backup free to hold, 3500 cents to book, the organizer's OK after 2 minutes), pantry_dev02.json (staff confirm at most 10 of the 16 partner kits, 34 distributed, 6 short), wave3_heldout README (suite costs 3.006960 plus 2.555110, 1.004722 plus 0.953090, 0.570856 plus 0.986032), wave3b_rerun README (C07 3 misses, T02 3 misses, T04 2 misses), RESEARCH_BRIEF.md [1] to [7], [11], [12], [25] and its "What not to claim" list.
- git status shows changes only under PEEAI_plan/submission, and nothing under apps/. No commit, no push, no paid API call.
