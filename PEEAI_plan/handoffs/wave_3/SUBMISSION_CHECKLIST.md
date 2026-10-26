# Submission checklist (hackathon, due 2026-10-25, 11:59 PM ET)

The owner **confirmed** the three required items on October 25, 2026:

1. Project Documentation as a Word document, plus the GitHub repository link.
2. The 7-Minute Project Presentation slide deck.
3. The 2-Minute One-Slide horizontal flyer or poster.

No hosted deployment or video is required. The owner pushed `hackathon/peeaai-plan` to
https://github.com/nocdoggo/COLLIE at `26cf424`, and the direct link
https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b resolved (HTTP 200,
checked by the owner at 18:20 EDT). The build has submitted nothing to Canvas.

At 23:10 EDT the owner asked for a clean export into the new repository
https://github.com/nocdoggo/FA26-COLLIE. The documentation, the deck and the poster (and both QR
codes) now link to it.

| # | Required item | File | Status | What the owner must still do |
| --- | --- | --- | --- | --- |
| 1 | **Project Documentation** as a Word document, **plus the GitHub repository link** | [`submission/documentation/Plan_B_Project_Documentation.docx`](../../submission/documentation/Plan_B_Project_Documentation.docx). Link in the document: https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b (clickable) | **Ready.** The Word file meets the confirmed format. The link points at the pushed branch, because the repository's default branch is a different project. Checked through a pandoc render, since Word is not available on the build machine | Open the .docx once in Word and page through it. Paste the same link into the platform's repository field |
| 2 | **The 7-Minute Project Presentation** slide deck | [`submission/slides/slides.pdf`](../../submission/slides/slides.pdf). Spoken script [`submission/slides/pres-note.md`](../../submission/slides/pres-note.md). Runbook [`SHOWCASE.md`](SHOWCASE.md) | **Ready.** A PDF deck: 13 timed slides with the title (slide 12 on version 1.2), then backups. The spoken script is a word-count estimate inside 420 s (`submission/timing.py`). 3 automated board rehearsals passed. **No human rehearsal yet** | Check the deck on the presentation machine at full screen. Do the three timed human rehearsals in [`REHEARSALS.md`](REHEARSALS.md) |
| 3 | **The 2-Minute One-Slide** horizontal flyer or poster | [`submission/poster/poster.pdf`](../../submission/poster/poster.pdf). Spoken script [`submission/poster/poster-note.md`](../../submission/poster/poster-note.md) | **Ready.** One horizontal 16:9 page | Rehearse the 2-minute pitch once with `python3 rehearsal_timer.py poster/poster-note.md` |

The items name the single author, Noctis Zhang, with no team name. If the platform form requires
a team field, enter the author's name.

## Before uploading

- [x] Branch first pushed by the owner at `26cf424` (October 25, 2026). Pushing
      published the held-out case files and the evaluator records committed on the branch. That
      is acceptable only because those 12 cases are spent (`KNOWN_LIMITATIONS.md` item 15).
- [x] The direct link https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b
      opens (owner check, 18:20 EDT). The QR codes on slide 12 and the poster encode the same link.
- [x] The requirements are confirmed: a Word document plus the link, a slide deck, and a
      one-slide horizontal poster. No hosted URL or video.
- [ ] If later commits are pushed before the deadline, open the link once more and check that
      `apps/plan_b/README.md` still renders.
- [ ] Presentation machine (human only): open `slides.pdf` and `poster.pdf` at full screen and
      check that the smallest text is readable from the back. If the board is shown, build or
      unpack the package, start `plan-b serve`, and open one recorded replay.
- [ ] Word (human only): open the .docx once in Microsoft Word and check the tables, the figures
      and the link.
- [ ] The Wave 3 numbers on slide 9, the poster and the document are the committed ones, labeled
      as the v1.1 evaluation of record: campus P0 6/8, P1 24/24, P2 18/24, P3 21/24. Pantry P0
      4/4, P1 6/12, P2 9/12, P3 6/12. 0 executed violations ([`CLAIMS.md`](CLAIMS.md)).
- [ ] The version 1.2 numbers on the results slides, the close, the backups, the poster and the
      document are labeled as in [`README.md`](README.md) "Wave 3b: version 1.2". The fresh
      held-out check (C09 to C12, T05, T06): campus P0 3/4, P1 12/12, P2 12/12, P3 12/12, pantry
      P0 2/2, P1 6/6, P2 6/6, P3 6/6, 59 of 60 runs. The post-hoc diagnostic rerun on the spent
      cases, never called held-out: campus P0 6/8, P1 24/24, P2 21/24, P3 24/24, pantry P0 4/4,
      P1 10/12, P2 12/12, P3 9/12. No sentence presents a 1.2 count as an improvement over 1.1.
- [x] The pytest, web and browser battery ran once more on the merged tree before the Wave 3b
      push (`VERIFICATION.md`, "Merged-tree battery before the Wave 3b push").
- [ ] The Wave 3b commits (`1ea8ea1`, `5955243`, `f715dfc` and the submission commit after them)
      are pushed, and the direct link still opens and renders `apps/plan_b/README.md`.
- [ ] Optional: the local reviewable package, built with `uv run python scripts/build_release.py
      --out <empty dir>` from `apps/plan_b`. It is for the presentation machine, not for upload.
