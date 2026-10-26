# Plan B: the three hackathon submission items

Plan B: The Show Must Go On. Noctis Zhang, University of Massachusetts Boston (single author, no
team name). Paul English Applied AI Institute (PEAAII) Hackathon, UMass Boston, October 2026.

| # | Required item | File | Rebuilt from |
| --- | --- | --- | --- |
| 1 | Project Documentation (Word) plus the repository link | `documentation/Plan_B_Project_Documentation.docx` | `documentation/build_doc.py` |
| 2 | The 7-Minute Project Presentation | `slides/slides.pdf`, spoken script `slides/pres-note.md` | `slides/slides.tex` |
| 3 | The 2-Minute, One-Slide Presentation (horizontal, 16:9) | `poster/poster.pdf`, spoken script `poster/poster-note.md` | `poster/poster.tex` |

**Repository**: https://github.com/nocdoggo/COLLIE, branch `hackathon/peeaai-plan`, app in
`apps/plan_b`. The link in the documentation and both QR codes point straight at the app:
https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b

**Push status**: the owner pushed the branch to `origin` at `26cf424` on October 25, 2026, and
the direct link resolved (HTTP 200, 18:20 EDT). The repository's default branch is a different
project, so the bare repository link does not show the app. Use the direct link.

**Requirements**: confirmed by the owner. The documentation as a Word document plus the
repository link, the 7-minute slide deck, and the 2-minute one-slide horizontal poster. No
hosted URL or video.

## Where the numbers come from

Every held-out number on the slides, the poster and in section 12 of the documentation comes from
the committed run `wave3_heldout_20261025T1625Z` (commit c052338):

- `apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/{campus,pantry}/report/metrics.json`
  for the counts, read by `make_results.py`, which writes `slides/figures/results_numbers.tex`,
  `slides/figures/fig_results.tex`, `slides/figures/fig_results_v.tex` and
  `documentation/results.json`. No held-out number is typed in by hand on the slides or the poster.
- the run's `README.md` (spend, the voided first attempt, the disclosures) and `FAILURES.md` (the
  C06 failure and the other failed runs).
- the report's own figures, `{campus,pantry}/report/figure.svg`, printed to
  `slides/figures/report_{campus,pantry}.pdf` with headless Chromium in its light colours.

Wave 3b added version 1.2 and two more runs. `make_results.py` reads them as a second source and
never replaces the first: `slides/figures/results_numbers.tex`, both results figures and
`documentation/results.json` stay byte-identical, and the new numbers go to
`slides/figures/results_numbers_v12.tex` (keys `fresh:` and `rerun:`) and
`documentation/results_v12.json`.

- `wave3b_fresh_20261025T2327Z` (commit f715dfc): version 1.2 on six fresh held-out cases, C09 to
  C12, T05 and T06, locked before the first 1.2 call. 59 of 60 runs met. It is the only held-out
  result of 1.2 (slide 12, the poster band and column 3, section 12.7 of the documentation).
- `wave3b_rerun_spent_20261025T2345Z` (commit f715dfc): version 1.2 on the twelve spent cases. It
  is a post-hoc diagnostic rerun after fixes, on spent cases, not a held-out result, and appears
  only on a backup slide, in the poster's limits and in section 12.7, always with that label.

The v1.1 run stays the evaluation of record. The two 1.2 runs use other cases or spent cases, so
no item presents a difference from v1.1 as a measured improvement. Every count is descriptive.

Everything before the results is development evidence from Waves 1 and 2, and is labelled so.
The held-out results show no consistent advantage for P2 (my policy). The items say so and show
the tradeoff.

## How to rebuild

TeX Live 2026 must be on the path:

```bash
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:$PATH
cd PEEAI_plan/submission
python3 make_results.py                       # numbers and results figures from metrics.json
(cd slides/figures && for f in fig_*.tex; do pdflatex -interaction=nonstopmode $f; done)
(cd slides && latexmk -pdf slides.tex)        # pdflatex, as the ICML_pres template does
(cd poster && latexmk -pdflatex='lualatex -interaction nonstopmode' -pdf poster.tex)
(cd documentation && uv run --no-project --with python-docx==1.1.2 python build_doc.py)
python3 check_writing.py                      # no em dash, en dash, double hyphen or semicolon
python3 timing.py slides/pres-note.md         # spoken words and time at 140 words a minute
python3 timing.py poster/poster-note.md
python3 rehearsal_timer.py slides/pres-note.md  # a stopwatch for a human rehearsal: Enter per slide
```

`build_doc.py` renders `slides/figures/fig_*.pdf` and `report_*.pdf` to PNG with pdftoppm.
`slides/figures/crop_frames.py` remakes the crops of the Wave 2 storyboard frames. The report
figures were printed with the Playwright headless Chromium shell:
`chrome-headless-shell --headless --print-to-pdf=report_campus.pdf <page with figure.svg>` on a page
sized to the SVG. Build files are ignored by `.gitignore`. Never build inside `ICML_pres/` or
`poster_template/`.

Checked when this was written:

- `slides.pdf`: 23 pages (13 timed slides with the title, and 10 backup slides), no overfull box. The footer counts
  only the 12 timed slides after the title.
- PDF metadata: title and author (and the deck's subject). No creator, producer or embedded
  file information.
- Word metadata: title, subject and author Noctis Zhang. The default extended properties of
  python-docx (which name Microsoft Word and Normal.dotm) are replaced by an empty part.
- `poster.pdf`: one page, 121.92 by 68.58 cm (16:9), no overfull box. Raleway and Lato come
  from TeX Live, with Lato Regular instead of Light for projection.
- `pres-note.md`: 932 spoken words, about 6:39 at 140 words a minute, inside 7:00 (953 words before
  the Wave 3b cuts, 921 before slide 12 on version 1.2 was added).
- `poster-note.md`: 267 spoken words, about 1:54, with one sentence on version 1.2.
- `check_writing.py`: 0 forbidden characters in both PDFs, the Word text, both scripts, this
  README, `DRAFT.md` and the Wave 3 packet (15 files).

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
