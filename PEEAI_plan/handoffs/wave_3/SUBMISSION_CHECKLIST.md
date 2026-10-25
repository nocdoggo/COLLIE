# Submission checklist (hackathon, due 2026-10-25)

The owner listed three required items. This checklist maps each one to its file, its status
and what the owner must still do. Nothing has been submitted, pushed or hosted by the build. The
course platform's own requirements (format, size, naming, a hosted URL or video) have **not been
checked** against the platform. Confirm them there before uploading.

| # | Required item (as the owner gave it) | File | Status | What the owner must still do |
| --- | --- | --- | --- | --- |
| 1 | **Project Documentation** as a Word document, **plus the GitHub repository link** | [`submission/documentation/Plan_B_Project_Documentation.docx`](../../submission/documentation/Plan_B_Project_Documentation.docx). Repository link in the document: https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b (clickable) | The Word file is present. Its held-out numbers agree with `CLAIMS.md`. The link points at the branch, because the repository's default branch is a different project. It does **not** open yet: the branch is local | The items name the single author, Noctis Zhang. Add no team name. If the platform form requires a team field, enter the author's name. **Push the branch** `hackathon/peeaai-plan` to https://github.com/nocdoggo/COLLIE, then open the direct link and check that `apps/plan_b/README.md` renders. Check the platform's format (.docx or PDF, size). Open the document once in Word |
| 2 | **The 7-Minute Project Presentation** slide deck | [`submission/slides/slides.pdf`](../../submission/slides/slides.pdf). Spoken script [`submission/slides/pres-note.md`](../../submission/slides/pres-note.md). Runbook [`SHOWCASE.md`](SHOWCASE.md) | The PDF is present (12 timed slides plus backups), built by the `submission` worker. Its results lines match the committed run (checked against `SHOWCASE.md` slides 9 and 10). Rehearsals: 3 automated, **human rehearsals pending** | Check whether the platform wants PDF, PPTX or a video, and a file size limit. Do at least one timed human rehearsal at presentation size ([`REHEARSALS.md`](REHEARSALS.md)) |
| 3 | **The 2-Minute One-Slide** horizontal flyer or poster | [`submission/poster/poster.pdf`](../../submission/poster/poster.pdf). Spoken script [`submission/poster/poster-note.md`](../../submission/poster/poster-note.md) | The PDF is present (one horizontal 16:9 page), built by the `submission` worker | Check the platform's format and size. Rehearse the 2-minute script once |

## Before uploading

- [ ] Branch pushed: `git push origin hackathon/peeaai-plan` (owner only, this build never
      pushes). Pushing publishes the held-out case files and the evaluator records, which are
      committed on the branch. That is acceptable only because the held-out set is spent
      (`KNOWN_LIMITATIONS.md` item 15).
- [ ] The direct link https://github.com/nocdoggo/COLLIE/tree/hackathon/peeaai-plan/apps/plan_b opens, and `apps/plan_b/README.md` renders. The
      QR codes on slide 12 and the poster encode the same link.
- [ ] The platform's format and size rules checked for each item. Is a hosted URL or a video
      required? A local package is not a hosted deployment.
- [ ] The numbers on slide 9, the poster and the document are the committed ones: campus P0 6/8,
      P1 24/24, P2 18/24, P3 21/24. Pantry P0 4/4, P1 6/12, P2 9/12, P3 6/12. 0 executed
      violations ([`CLAIMS.md`](CLAIMS.md)).
- [ ] Optional: the local reviewable package, built with `uv run python scripts/build_release.py
      --out <empty dir>` from `apps/plan_b` (it includes the three items above). It is for review
      on the presentation machine, not for upload unless the platform asks for code.
