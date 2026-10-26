# Rehearsal record (Wave 3)

## Human rehearsals: the one-page checklist (pending)

**No human rehearsal has been done or is claimed.** This page is for the owner. Do three timed
runs of the full 7-minute talk and one of the 2-minute poster pitch, then fill in the tables.

**Before each run**

- [ ] Deck `submission/slides/slides.pdf` at full screen on the presentation machine (or the
      same resolution), slide 1 showing. Script `submission/slides/pres-note.md` on paper or a
      second screen.
- [ ] If the board is shown: a clean reset first (`SHOWCASE.md` section 7), `plan-b serve`
      running, case `dev01` loaded, the replay tab open as the fallback.
- [ ] Timer: `cd PEEAI_plan/submission && python3 rehearsal_timer.py slides/pres-note.md`.
      Press Enter to start, then Enter at every slide change. It prints the budget and the
      "be done by" time of each slide, and at the end one row for the table below.

**During the run**

- [ ] Speak, do not read. Pause briefly at each slide change.
- [ ] Behind at a checkpoint? Drop the "skip if late" sentence of the next slide (slide 6).
- [ ] Run 2 only, if the live mode will be used on stage: force a failure (Wi-Fi off) and
      switch to the recorded replay (`SHOWCASE.md` section 5). Otherwise rehearse the switch once.

**Slide budget (the 420 s plan) and the spoken estimate** (`timing.py`, 140 words a minute)

| Slide | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Budget, s | 10 | 27 | 30 | 31 | 44 | 47 | 26 | 30 | 38 | 26 | 40 | 39 | 32 | 420 |
| Be done by | 0:10 | 0:37 | 1:07 | 1:38 | 2:22 | 3:09 | 3:35 | 4:05 | 4:43 | 5:09 | 5:49 | 6:28 | 7:00 | |
| Spoken estimate, s | 11 | 26 | 28 | 29 | 41 | 45 | 24 | 28 | 35 | 24 | 37 | 37 | 34 | 399 |

The script is 932 words, about 399 s, so about 21 s are left for pointing and slide changes.
Slide 12 (version 1.2, six fresh held-out cases) was added in Wave 3b, and other slides were cut
to make room.

**Pass criteria**: the total is at most 7:00, no checkpoint is more than 15 s late, every
honesty line is said (fictional and local, "recorded", no consistent advantage for P2, no
community pilot), and nothing is claimed that is not on a slide.

**Human runs of the 7-minute talk** (paste the timer's row, then fill in the rest)

| Run | Date and time | Place, machine | Total | Slides reached | Slowest slide vs budget | Forced failure | What went wrong, what to change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | /13 | | no | |
| 2 | | | | /13 | | yes or not used | |
| 3 | | | | /13 | | no | |

**Human run of the 2-minute poster pitch** (`python3 rehearsal_timer.py poster/poster-note.md`,
budget 120 s, script 267 words, about 114 s)

| Run | Date and time | Total | What went wrong, what to change |
| --- | --- | --- | --- |
| 1 | | | |

**After the runs**: check readability from the back of the room, keyboard operation of the board
(`tests/e2e/keyboard.py` covers only the automated part) and the audio if a recording is used.
Then update the M3 row "Three rehearsals and the failure fallback work" in `README.md`.

## Automated rehearsals (Wave 3, done)

### What was rehearsed, and how

**These are AUTOMATED internal rehearsals, not human ones.** `apps/plan_b/tests/e2e/rehearsal.py`
ran the showcase's board path three times in a row in headless Chromium on the development
machine, each from a clean reset. Nobody spoke, and there was no projector. The rehearsals do not
measure the talk track.

Each rehearsal:

1. ran `scripts/demo_prep.py` for an empty state directory and the verified recorded traces.
2. started its own `plan-b serve` on a free 127.0.0.1 port.
3. clicked through the Wave 2 storyboard (`tests/e2e/storyboard.py`, the segments of DEMO.md),
   which covers every optional board action of [`SHOWCASE.md`](SHOWCASE.md) plus extra steps:
   `dev01` verify and commit. `dev04` stale and duplicate. `dev02` hold, organizer approval and
   commit. The recorded P2 decision card and the P3 and P1 replays. The `skills_dev01` check-in
   (backup slide). The `pantry_dev01` cameo. The fallback list.
4. opened the committed results figure.
5. read every episode's receipts and final state from the API.

The story steps are `tests/e2e/storyboard.py`'s, reused unchanged with its 32 page-against-API
checks.

**Rehearsal 2 forced a provider failure first.** Its server pointed the provider at
`http://127.0.0.1:<a closed port>/api/v1`, with a placeholder key file and a temporary ledger, so
no request left the machine, no key was read and the real ledger was untouched. It selected
**Live agent** on `dev01` and pressed **Run live agent**. It checked the visible failure and the
unchanged state, then switched to the labeled offline replay `live_p2-live_dev01_trace.json`.
After that it reset and ran the story like the others.

### Results (the collector's run, `evidence/rehearsal/rehearsal_report.json`)

Command: `uv run python tests/e2e/rehearsal.py --out evidence/rehearsal`, run by
`scripts/collect_wave3_evidence.py` from a clean checkout of `3442874` (the integrate step).
Exit 0: **3/3 rehearsals passed**, 133.4 s
in all. The receipts and final states, now including the pantry pool balances, allocations,
distributions and handoff tasks, were **identical across all three**, every expected outcome
held, and the repository ledger was unchanged (its sha256 before and after). The file is
authoritative.

| Rehearsal | Forced failure | Checks | App time (s) | Notes |
| --- | --- | --- | --- | --- |
| 1 | no | 34/34 | 40.4 | 32 story checks and 2 results-figure checks |
| 2 | **yes** | 42/42 | 45.2 | 8 forced-failure checks, plus the story |
| 3 | no | 34/34 | 40.5 | |

Earlier runs into scratch gave the same check counts: 40.8 / 43.4 / 40.4 s, then
40.5 / 43.9 / 42.0 s (the first before a fix to how the script keys its signatures by case), and
the story audit's runs of the hardened script 40.3 / 43.7 / 38.8 s and 42.2 / 43.8 / 40.8 s. The audit made three checks
real: the results figure is now compared with the committed blob at `c052338` (it was only
hashed), the work ledger must hold exactly the failed call as a `transport` failure (an absent
ledger used to pass), and the rehearsals that do not force a failure get a key path that does not
exist, so no misclick can reach the provider.

Forced failure (rehearsal 2):

- A `provider_error` card was visible **0.2 s** after the press (the switch threshold is 20 s).
- Plan, holds, commitments, budget and receipts were unchanged.
- The failed run was recorded under `live/1.1.0` as a wait.
- The temporary ledger held 1 call with outcome `transport` and $0.
- The replay was ready **0.8 s** after the switch: "Recorded replay" banner, integrity
  "passed", receipts `rcpt_0001` to `rcpt_0003` on its final state, no request other than GET.

Expected outcomes, identical in all three rehearsals:

- `dev01`: plan version 2 by one `apply_plan` receipt (`rcpt_0001`).
- `dev04`: plan version 1 kept, no receipt, no hold, no spend.
- `dev02`: `hold_resource`, `update_grant` and `apply_plan` receipts, and one commitment of
  $35.00.
- `skills_dev01`: the check-in, then the swap (plan version 2).
- `pantry_dev01`: target 40, 40 distributed on time.

Automated segment time per rehearsal, in seconds, from `segments_seconds` in
`evidence/rehearsal/rehearsal_report.json` (an earlier version of this table did not match that
file). App work only, no speaking:

| Segment | Rehearsal 1 | Rehearsal 2 | Rehearsal 3 |
| --- | --- | --- | --- |
| showcase | 1.9 | 1.9 | 1.9 |
| commitments | 1.0 | 1.0 | 1.0 |
| delay | 2.3 | 2.3 | 2.3 |
| stale | 5.9 | 5.9 | 6.0 |
| backup | 10.1 | 10.0 | 9.9 |
| live (replay card, plus the forced failure in rehearsal 2) | 3.1 | 6.3 | 3.2 |
| community | 7.8 | 7.8 | 7.8 |
| pantry | 7.8 | 9.7 | 7.9 |
| close, with the results figure step | 0.3 | 0.3 | 0.3 |

### Timing against the 420 seconds

The deck's spoken script is 932 words, an estimated 399 s (about 6:39) at 140 words per minute
against the 420 s plan (`submission/slides/pres-note.md`, counted by `submission/timing.py`). It
was 953 words (about 408 s) until the Wave 3b polish cut 32 words, then 921. The results2 step
added slide 12 on version 1.2 and cut other slides, for 932. This is a word-count estimate,
not a timed human rehearsal. The app's busiest segment takes at most about 11 s of clicks and
waits. The time goes to talking and switching tabs, as in Wave 2.
