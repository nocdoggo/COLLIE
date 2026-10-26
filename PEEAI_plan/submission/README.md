# Plan B: the three hackathon submission items

Plan B: The Show Must Go On. Noctis Zhang, University of Massachusetts Boston (single author, no
team name). Paul English Applied AI Institute (PEAAII) Hackathon, UMass Boston, October 2026.

| # | Required item | File | Rebuilt from |
| --- | --- | --- | --- |
| 1 | Project Documentation (Word) plus the repository link | `documentation/Plan_B_Project_Documentation.docx` | `documentation/build_doc.py` |
| 2 | The 7-Minute Project Presentation | `slides/slides.pdf`, spoken script `slides/pres-note.md` | `slides/slides.tex` |
| 3 | The 2-Minute, One-Slide Presentation (horizontal, 16:9) | `poster/poster.pdf`, spoken script `poster/poster-note.md` | `poster/poster.tex` |

**Repository**: https://github.com/nocdoggo/FA26-COLLIE, a clean export of the hackathon work
(the app in `apps/plan_b`, the plan, packets and these submission items in `PEEAI_plan`). The link
in the documentation and both QR codes point at it. The work was developed on the branch
`hackathon/peeaai-plan` of https://github.com/nocdoggo/COLLIE, which keeps the full history.

**Push status**: the owner pushed the branch to `origin` at `26cf424` on October 25, 2026, and
the direct link resolved (HTTP 200, 18:20 EDT). The repository's default branch is a different
project, so the bare repository link does not show the app. Use the direct link.

**Requirements**: confirmed by the owner. The documentation as a Word document plus the
repository link, the 7-minute slide deck, and the 2-minute one-slide horizontal poster. No
hosted URL or video.

## Where the numbers come from

The deck and the poster show one final system. The story and the figures follow `STORY_PLAN.md`,
which records the plan, the three critiques and the decisions. Every evaluation number comes from
committed runs in `apps/plan_b/evaluation/results/`, read by `make_results.py`. No number is typed
in by hand on the slides or the poster.

- **The final system** (the evaluation shown): `wave3b_fresh_20261025T2327Z` (commit f715dfc), six
  new held-out cases, C09 to C12, T05 and T06, written by a separate worker before the
  final freeze and locked in the same commit, before the first model call. 59 of 60 runs met. The deck and the poster read it through
  `slides/figures/results_numbers_v12.tex` (keys `fresh:`), `slides/figures/results_numbers_final.tex`
  (sums such as `final:P2:metk`) and the pgfplots charts `slides/figures/fig_result.tex` and
  `fig_result_v.tex`.
- **The earlier locked test**: `wave3_heldout_20261025T1625Z` (commit c052338), 12 cases and 120
  runs. It found the defects fixed before the final freeze, and its cases are now development
  cases. The deck names it in one line and on one backup slide. The documentation keeps its full
  record in sections 12.1 to 12.6, with the pgfplots chart `slides/figures/fig_result_record.tex`.
- **The diagnostic rerun**: `wave3b_rerun_spent_20261025T2345Z` (commit f715dfc), the final
  policies on the twelve spent cases after the fixes. It is never a held-out result. It appears
  only on one backup slide and in section 12.7 of the documentation, always with that label.

`make_results.py` never changes the earlier files: `results_numbers.tex`, `results_numbers_v12.tex`,
`fig_results.tex`, `fig_results_v.tex`, `results.json` and `results_v12.json` stay byte-identical
when it adds the new charts and `results_numbers_final.tex`.

The slides, the poster and the scripts name the four approaches in plain words: the fixed rules
(P0), the tool-calling model (P1), our coordinator (P2, the model picks from checked options) and
the check-all variant (P3). Case ids and policy codes stay in the documentation's record tables
and in file paths.

The scene (16:40, the projector, ETA 17:25, the free swap at 16:43, 16 options and 3 passing), the
quiet case and the pantry chart are development evidence from Waves 1 and 2 (development cases
dev01, dev04 and pantry_dev01) and are labelled so on the slides.

## How to rebuild

TeX Live 2026 must be on the path:

```bash
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:$PATH
cd PEEAI_plan/submission
python3 make_results.py                       # numbers and the pgfplots result charts
(cd slides/figures && for f in fig_*.tex; do pdflatex -interaction=nonstopmode $f; done)
(cd slides && latexmk -pdf slides.tex)        # pdflatex, as the ICML_pres template does
(cd poster && latexmk -pdflatex='lualatex -interaction nonstopmode' -pdf poster.tex)
(cd documentation && uv run --no-project --with python-docx==1.1.2 python build_doc.py)
python3 check_writing.py                      # no em dash, en dash, double hyphen or semicolon
python3 timing.py slides/pres-note.md         # spoken words and time at 140 words a minute
python3 timing.py poster/poster-note.md
python3 rehearsal_timer.py slides/pres-note.md  # a stopwatch for a human rehearsal: Enter per slide
```

Figures: every figure is a vector PDF from TikZ or pgfplots in `slides/figures/`, shared by the
deck, the poster and the documentation, with one style file `planb_figstyle.tex` (UMB blue
`#08457E` for the system, one warm accent for the incoming message and the clock, green only for a
receipt or a met run, greys for context). The main ones: `fig_hook` (the clock and the text),
`fig_contrast` (an agent with no gate against Plan B), `fig_story` (the scene and the program
before and after), `fig_quiet2`, `fig_design` (the hero architecture with connected and next
APIs), `fig_result` (generated), `fig_pantry_chart` and `fig_next`. The older figures the
documentation still uses load `fig_style.tex`, which maps them onto the same style.
`build_doc.py` renders `slides/figures/fig_*.pdf` to 300 dpi PNG with pdftoppm. The report's
browser-printed figures (`report_*.pdf`) and the frame crops stay in the repository but are no
longer used on the slides or the poster.

Earlier items used them: `slides/figures/crop_frames.py` remakes the crops of the Wave 2 storyboard frames. The report
figures were printed with the Playwright headless Chromium shell:
`chrome-headless-shell --headless --print-to-pdf=report_campus.pdf <page with figure.svg>` on a page
sized to the SVG. Build files are ignored by `.gitignore`. Never build inside `ICML_pres/` or
`poster_template/`.

Checked when this was written (the design step, October 26, 2026, 00:04 EDT):

- `slides.pdf`: 14 pages (the title, 9 timed slides after it and 4 backup slides), no overfull
  box. Two full-bleed blue story slides (the hook and the close). No screenshot on any slide.
- `poster.pdf`: one page, 121.92 by 68.58 cm (16:9), no overfull box. Three columns: the scene,
  the idea and the design, the evidence.
- PDF metadata: title and author (and the deck's subject). No creator, producer or embedded
  file information.
- Word metadata: title, subject and author Noctis Zhang. Figures are 300 dpi renders of the
  vector PDFs. Checked through a pandoc and headless Chromium render, since Word and LibreOffice
  were not available here.
- `pres-note.md`: identical to the slides' notes, 922 counted words, about 6:35 at 140 words a
  minute, inside 7:00.
- `poster-note.md`: 219 counted words, about 1:34.
- `check_writing.py`: 0 forbidden characters in both PDFs, the Word text, both scripts, this
  README, `DRAFT.md`, `STORY_PLAN.md` and the Wave 3 packet (16 files).

## Template credits

- **Slides**: the elegant beamer theme by Lars Spreng, licensed CC BY 4.0, copied with its
  license headers from the `ICML_pres` deck into `slides/styles/` and `slides/loadslides.tex`.
  The layout follows `ICML_pres/slides.tex` and the script follows `ICML_pres/pres-note.md`.
- **Poster**: the Gemini beamerposter theme by Anish Athalye, MIT License
  (`poster/LICENSE-gemini.md`), with the UMass Boston colour theme `beamercolorthemeumb.sty` of
  the Overleaf poster template. Made landscape 16:9 for projection.
- **Logos**: the UMass Boston logo lockups from both templates, used only to name the author's
  university.

## Checklist for the owner before submitting

- [x] Branch pushed by the owner (`origin/hackathon/peeaai-plan`). If later commits are pushed,
      open the direct link once more.
- [x] Requirements confirmed by the owner. The deck and the poster are PDFs, the documentation is
      a .docx with the repository link.
- [ ] Open the .docx in Word once. It was checked through a pandoc render, since Word and
      LibreOffice were not available here.
- [ ] Rehearse the talk aloud three times with `python3 rehearsal_timer.py slides/pres-note.md`
      and the 2-minute pitch once with `python3 rehearsal_timer.py poster/poster-note.md`. Record
      each run in `../handoffs/wave_3/REHEARSALS.md`. No human rehearsal had been recorded when
      these items were built.
- [ ] Use the recorded replay if a live model call fails during the demo. The provider allows
      20 requests a minute on this account, so run one model episode at a time.
