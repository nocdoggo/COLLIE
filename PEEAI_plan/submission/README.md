# Plan B, the three hackathon submission items

Plan B, The Show Must Go On. Noctis Zhang, Department of Computer Science, University of
Massachusetts Boston. PEAAII AI Applications Hackathon 2026, October 2026. Single author.

| # | Required item | File | Rebuilt from |
| --- | --- | --- | --- |
| 1 | Project documentation (Word) plus the repository link | `documentation/Plan_B_Project_Documentation.docx` | `documentation/build_doc.py` |
| 2 | The 7-minute project presentation | `slides/slides.pdf`, spoken script `slides/pres-note.md` | `slides/slides.tex` |
| 3 | The 2-minute, one-slide presentation (landscape, 16 by 9) | `poster/poster.pdf`, spoken script `poster/poster-note.md` | `poster/poster.tex` |

**Repository**, github.com/nocdoggo/FA26-COLLIE, a clean copy with the app in `apps/plan_b` and
the five final files of this folder. The work is developed on the branch `hackathon/peeaai-plan` of
github.com/nocdoggo/COLLIE, which keeps the full history. The QR codes and the documentation point
at FA26-COLLIE.

## The story and the three ideas

All three items tell one story, built on one made-up use case. Jordan, a volunteer organizer we
made up, gets a text twenty minutes before doors open. The projector may be 25 minutes late. Plan B
checks the delivery first, keeps only the changes that fit, the AI picks the free swap, and Plan B
leaves a receipt. Doors open on time and no club money is spent.

Three ideas carry every item (the Rule of Three), each in three parts.

1. **Check the fact.** A message is a claim, not a fact. Look up only the fact that could change
   the plan. Most messages should change nothing.
2. **Pick only what fits.** Plan B lists every allowed change. It throws out any that break the
   time, the people or the budget. The AI picks one, but cannot change the plan itself.
3. **Leave a receipt.** Plan B checks every change against the rules before it happens. Every
   accepted change leaves a receipt. Money waits for a person's OK.

The deck announces them on slide 3, gives each its slide (4 to 6), shows the real board after the
swap (slide 7) and repeats them on slide 14. The poster keeps the calm six-panel layout of the
earlier poster, which the owner preferred to a denser Roameo-style version, with the three ideas
in its sub-heading line, the design diagram and a screenshot of the running board. The
documentation is organised around the three ideas and answers the hackathon's seven questions,
each in its own section, with a table that says where.

The plan for this revision is `REVISION_PLAN.md`. The audit before it is `AUDIT_BEFORE.md`, and
the cited outside facts are in `RESEARCH_BRIEF.md`. These three are working notes. They quote the
old wording on purpose and the writing check never reads them.

## Where the numbers come from

Every number comes from the committed records in this repository, as listed in
`REVISION_PLAN.md` section 9.

- **The final test**, `apps/plan_b/evaluation/results/wave3b_fresh_20261025T2327Z`, six cases
  sealed before the test (C09 to C12 campus, T05 and T06 pantry), 60 runs. 59 of 60 met the
  expected outcome, every AI run met it, the fixed rules missed one (C11), no executed action broke
  a rule, 6 attempts were refused, $3.61 for 194 AI calls. The deck reads it through
  `slides/figures/results_numbers_v12.tex`, written by `make_results.py`.
- **The earlier 12-case test**, `wave3_heldout_20261025T1625Z`, 120 runs. It found four problems
  (`PEEAI_plan/handoffs/wave_3/README.md`), which were worked on before the final test. A later
  diagnostic rerun on those spent cases still misses two of the targeted cases. The deck shows it
  on backup slide B5 and the documentation in section 7.2. An earlier planning brief said three
  problems, and the records say four, so every item says four.
- **Jordan's evening** is the practice case `apps/plan_b/plan_b/scenarios/private/dev01.json`. The
  pictures are a rehearsal with the fixed rules, and in an earlier recorded run (version 1.0) the
  AI made the same look-up and the same swap. The 5.45 pm "what if" is a separate practice case
  (`dev02.json`), and the made-up pantry is `pantry_dev02.json`.
- **Why Plan B** (safer, more flexible, more personal) rests on the release checks in
  `apps/plan_b/docs/RELEASE_CHECKS.md`, the settings in `apps/plan_b/plan_b/agent/config.py` and
  the cited competitor pages of `RESEARCH_BRIEF.md`. The $0.50 a run and $20 total defaults cap the
  AI service's own bill, not event money. The licence is GPL-3 (the owner's decision of
  October 26, 2026).

## How to rebuild

TeX Live 2026 must be on the path.

```bash
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:$PATH
cd PEEAI_plan/submission
python3 make_results.py                          # numbers for the result charts
(cd slides/figures && for f in fig_*.tex; do pdflatex -interaction=nonstopmode $f; done)
python3 timing.py --update slides/pres-note.md   # stage directions follow the spoken words
python3 tools/sync_notes.py                      # the speaker notes copy the script
(cd slides && latexmk -pdf slides.tex)
(cd poster/figures && for f in fig_*.tex; do lualatex -interaction=nonstopmode $f; done)
(cd poster && latexmk -pdflatex='lualatex -interaction nonstopmode' -pdf poster.tex)
(cd documentation && uv run --no-project --with python-docx==1.1.2 python build_doc.py)
python3 check_writing.py                         # must end at 0 hits
python3 timing.py slides/pres-note.md            # at most 420 seconds
python3 timing.py poster/poster-note.md          # at most 120 seconds
python3 tools/wc.py slides/slides.pdf 14         # visible words per main slide
pdftoppm -r 60 -png slides/slides.pdf /tmp/s && python3 tools/whitespace.py /tmp/s-*.png
```

Tools in this folder.

- `check_writing.py` has two rule sets. The first, on everything it has always read (both PDFs,
  the Word text, both scripts, this README, `DRAFT.md`, `STORY_PLAN.md` and the Wave 3 packet),
  forbids em and en dashes, a double hyphen and semicolons. The second, on the deliverables only (the
  rendered deck and poster with their PDF metadata, the speaker notes, both scripts and the Word
  document's visible text), also forbids colons, "https://", the owner's banned AI-sounding words,
  the mechanical words that name code instead of saying what happens (gate, pipeline, policy and
  the like), code identifiers and case codes on the deck, the poster and the scripts, unfilled
  placeholders, any author but Noctis Zhang, and speaker notes that differ from `pres-note.md`.
  Whole monospace command paragraphs in the Word document are exempt.
- `timing.py` estimates the spoken time at 140 words a minute, and with `--update` rewrites the
  stage directions to match.
- `tools/sync_notes.py` copies `slides/pres-note.md` into the deck's speaker notes.
- `tools/wc.py` counts the visible words on each slide (the owner's limit is about 25 to 35).
- `tools/whitespace.py` measures the largest empty rectangle on a rendered page.

Figures are vector PDFs from TikZ and pgfplots. The deck's are in `slides/figures/` and share
`planb_figstyle.tex` (the calm UMass Boston palette, UMB blue #005A8B, navy #132245, primary
#08457E, orange #FF791F only for tension, green #2E7D32 only for a met result, and the three idea
marks, a magnifier, a funnel and a receipt). The poster uses the deck's `fig_design_poster` and
`fig_qr`, and its own `poster/figures/` (the story, the results and the pantry chart at poster
size, and a crop of the board screenshot). `build_doc.py` renders the deck's figure PDFs to 300 dpi PNG for the Word
document. The screenshots in `screenshots/` are the real board in a rehearsal with the fixed rules
(no AI call), used at native resolution and only scaled down. As raster images of the app's own
screen they keep its clock format, which the writing check cannot read. Build files are ignored by
`.gitignore`.

## Checked when this was built

Measured on October 26, 2026, about 16.40 EDT, after the final audit (AUDIT_AFTER.md) and a full
rebuild from source.

- `slides.pdf`, 22 pages, fourteen timed slides and eight backups, 0 overfull boxes. Visible words
  per main slide (tools/wc.py, the panel numbers 1 to 3 included) 34, 33, 37, 34, 37, 31, 27, 29,
  37, 35, 38, 32, 37 and 38. The largest empty area on a main slide is the footer band (at most
  9 percent of the page, tools/whitespace.py at 60 dpi), and at most 13 percent on a backup.
- `pres-note.md`, 976 spoken words, about 418 seconds at 140 words a minute, under 420. The speaker
  notes are identical (checked by check_writing.py).
- `poster.pdf`, one page, 121.92 by 68.58 cm (16 by 9), 0 overfull boxes, 543 words
  (pdftotext), largest empty area 2.5 percent of the page. `poster-note.md`, 311 words, about 133
  seconds, with a short version of about 35 seconds.
- `Plan_B_Project_Documentation.docx`, 19 figures and 15 tables. Title and author set in the core
  properties. Checked through its text, its structure and an approximate HTML render (35 pages),
  since Word and LibreOffice are not available here.
- PDF metadata, title "Plan B, The Show Must Go On" and author Noctis Zhang, with no creator or
  producer.
- `check_writing.py`, 17 files checked (the speaker notes now count as one), 0 hits.

## Template credits

- **Slides**, the elegant beamer theme by Lars Spreng, CC BY 4.0, in `slides/styles/` and
  `slides/loadslides.tex`.
- **Poster**, the Gemini beamerposter theme by Anish Athalye, MIT License
  (`poster/LICENSE-gemini.md`), with the UMass Boston colour theme `beamercolorthemeumb.sty`.
- **Logos**, the UMass Boston logo lockups, used at native resolution and only scaled down, to name
  the author's university.

## Before submitting

- [ ] Open the .docx in Word once. Word and LibreOffice are not available here, so the document
      was checked through its text, its structure and an approximate HTML render.
- [ ] Rehearse the talk aloud with `python3 rehearsal_timer.py slides/pres-note.md`, and the pitch
      with `python3 rehearsal_timer.py poster/poster-note.md`.
