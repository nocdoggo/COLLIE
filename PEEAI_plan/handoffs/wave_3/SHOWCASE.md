# Showcase: the seven-minute Plan B presentation (Wave 3, final)

This is the final script and runbook for the 420-second talk. It follows the slide order of the
submission deck ([`submission/slides/slides.pdf`](../../submission/slides/slides.pdf), spoken
script [`submission/slides/pres-note.md`](../../submission/slides/pres-note.md)). It builds on
the Wave 2 runbook [`../wave_2/DEMO.md`](../wave_2/DEMO.md) and on
[`09_seven_minute_presentation.md`](../../09_seven_minute_presentation.md).

Everything shown is a **fictional, local sandbox**. Every Wave 3 number comes from one committed
run, `wave3_heldout_20261025T1625Z`
([README](../../../apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/README.md),
committed in `c052338`), the evaluation of record of version 1.1. Wave 3b adds version 1.2 and two
labelled runs (commit `f715dfc`): the held-out run on six fresh cases,
[`wave3b_fresh_20261025T2327Z`](../../../apps/plan_b/evaluation/results/wave3b_fresh_20261025T2327Z/README.md)
(slide 12), and a post-hoc diagnostic rerun on the twelve spent cases,
[`wave3b_rerun_spent_20261025T2345Z`](../../../apps/plan_b/evaluation/results/wave3b_rerun_spent_20261025T2345Z/README.md),
which is not a held-out result and appears only on a backup slide. Every row of
[`CLAIMS.md`](CLAIMS.md) names its source.

## 1. The message, and what the judges should retell

**One sentence:** *Plan B helps a community event stay on track by deciding what to verify, what
to prepare, and when to commit a change.*

The audience should be able to retell four things:

1. **One recovery.** The projector is late. The notice is checked, then one free change is
   applied, and the server writes a receipt.
2. **One avoided change.** Four messages lead to zero changes.
3. **One measured result.** The frozen comparison ran on held-out cases, and every planned run
   was recorded.
4. **One failure on record, and the honest tradeoff.** My selective controller (P2) showed no
   consistent advantage ("no clear winner"). It was cheaper per run, but it met fewer cases than
   the tool-use agent (P1) on campus. One held-out failure: a correct reading that never reached
   the planner. Version 1.2 then met 59 of 60 runs on six fresh held-out cases, too few to rank
   the model policies.

## 2. Operating mode: say it before you start

| Part | Default mode | Label on screen | Evidence the mode works |
| --- | --- | --- | --- |
| Slides 1 to 13 | The deck alone (PDF). It needs no server | none | the deck file |
| Optional board, slides 3 to 7 | **Deterministic policy** acting on the sandbox (`rules/1.0.0`), no model call | Header badge "Deterministic policy" | 3 automated rehearsals ([REHEARSALS.md](REHEARSALS.md)) |
| Optional board, slide 8 | **Recorded replay** of a real paid development run (`live_p2-live_dev02_trace.json`, `live/1.0.0`) | Purple "Recorded replay" banner. "Integrity check passed" | rehearsals, and the storyboard check |
| Optional board, slide 11 (pantry cameo) | **Live sandbox tools with the deterministic pantry policy** (`pantry-rules/1.1.0`), no model call | "Fictional pantry sandbox". Header "Deterministic policy" | rehearsals (40 of 40 on time in all three) |

**Pantry cameo label, chosen from the evidence.** The cameo is an executable run of the
implemented pantry adapter, so the "Planned domain extension" label does not apply. No model
runs in it, so "Live model + sandbox tools" does not apply either. Say: "This is the
deterministic pantry policy acting live in the sandbox." If the board is not used, slide 11's
figure is shown as frames of a real development run. If the board fails, switch to **Recorded
replay** `pantry_dev01_trace.json` (section 6).

**Live model mode is not planned for the stage.** It has never been rehearsed by a human. The
automated rehearsals test only its failure path. If it is used anyway, the per-run cap is
$0.50 and the ledger caps stay in force. OpenRouter allows this account 20 requests per minute
for this model, so run no other paid job at the same time.

## 3. Setup from a clean state (stage machine, before the projector is on)

```bash
cd apps/plan_b
unset VIRTUAL_ENV
uv sync --all-groups --locked
(cd web && npm ci && npm run build)
uv run python scripts/demo_prep.py          # var/demo: an empty state dir + verified recorded traces
PLAN_B_MODERATOR_CODE='<choose one, never project it>' \
  uv run plan-b serve --port 8790 --var var/demo/state --replay-dir var/demo/replays
```

Use Chromium or Chrome at 1920×1080 with **zoom 125 %**. Open the deck in a PDF viewer in
presentation mode. Optional board tabs, as in DEMO.md section 3:

- T1: the moderator board, `http://127.0.0.1:8790/`. Sign in **before** projecting.
- T2: `#/replay/live_p2-live_dev02_trace.json`. Click **Final recorded state**.
- T4: `#/replay/pantry_dev01_trace.json`, as the fallback.

Have the results figure open in a browser tab:
`apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/campus/report/figure.svg` (the
backup slide "the report's per-case figure, campus" shows the same figure).

## 4. Run of show (420 seconds, slide by slide)

**Clicks** are deck advances or board actions. Board actions are optional. The deck alone tells
the story. **Point at** is what to show. **Say** follows `pres-note.md`, about 140 words per
minute. The spoken script is 932 words, an estimated 399 s against the 420 s plan, so board
actions are spoken over and never paused for. If the board is used, drop the "skip if late"
sentence of slide 6.

Slide numbers here follow `pres-note.md` and the PDF pages. The deck's footer counts only the 12
slides after the title, so slide 9 here shows "8 / 12" in the footer. Slide 12 (version 1.2) was
added in Wave 3b.

### Slide 1 · 0:00 to 0:10 · Title (10 s)

- **Point at:** the title, "Plan B: The Show Must Go On".
- **Say:** the presenter's name and school, then "This is Plan B. It decides what to verify,
  what to prepare, and when to commit a change." (as in `pres-note.md` slide 1).

### Slide 2 · 0:10 to 0:37 · Twenty minutes before opening, the projector may be late (27 s)

- **Point at:** the timeline. The showcase opens at 17:00 and must end by 18:00, and the
  demonstrations need the projector.
- **Say:** the hook, then the question: "Would you wait, check, or prepare a backup?" Wait for
  a show of hands. Nobody needs a phone.

### Slide 3 · 0:37 to 1:07 · The coordinator may check, hold and make free changes, not spend (30 s)

- **Point at:** the roles figure, and the hold limit of $35.
- **Optional board (T1):** load case `dev01`. Show the `agent_demo` grant: "Committed $0.00 of
  $0.00 · held $0.00 of $35.00".
- **Say:** "It cannot spend a cent without the organizer."

### Slide 4 · 1:07 to 1:38 · A message is a claim, not a fact (31 s)

- **Optional board:** **Run deterministic policy**, once.
- **Point at:** the notice from `delivery_contact`. Then the status check: delayed, reported
  ETA 17:25, and the board's note that a reported ETA is not an arrival.
- **Say:** "Before changing anything, it checks the one fact that could change the decision."

### Slide 5 · 1:38 to 2:22 · One checked change, one receipt (44 s)

- **Point at:** the swap figure. "16 built, 3 pass". The receipt line "Plan version 1 → 2,
  applied at 16:43 by receipt `rcpt_0001`".
- **Say:** "The server writes a receipt, its own record of the change. The AI cannot write it."
  Then: "These frames show my rule baseline. In a recorded run, the AI coordinator made the same
  check and the same swap." (as in `pres-note.md` slide 5)

### Slide 6 · 2:22 to 3:09 · Four messages, zero changes (47 s)

- **Optional board:** load `dev04` → **Run deterministic policy** → *Minutes* `8` → **Run 8
  minutes with policy**. This fast-forwards the scenario clock. Say "fast-forward".
- **Point at:** "does not apply" (order P09, another date), "duplicate" (one source repeated),
  and "Plan version 1 kept: no hold, no spending, no change".
- **Say:** "Three of my twelve final test cases are quiet ones like this." Results tie-in, from the committed run: **no policy made an unnecessary change on
  those three quiet cases** (0 committed changes over 3, 9, 9 and 9 episodes).

### Slide 7 · 3:09 to 3:35 · Verify, prepare, commit (26 s)

- **Optional board:** load `dev02` → **Run deterministic policy**. Point at "Held `hold_0001`,
  Hold expires 16:55" and the ask for $35.
- **Say:** walk the loop once. "Prepare" is the paid backup case: the backup is held until 16:55
  and the organizer is asked to approve $35.

### Slide 8 · 3:35 to 4:05 · The model chooses, the server checks (30 s)

- **Optional board (T2, Recorded replay):** the **Commit** card shows `live/1.0.0 · chosen by a
  model call`, latency 3.75 s, cost $0.0135, receipt `rcpt_0003`. The rationale is labeled
  "untrusted model text".
- **Say:** contrast P1 (the model calls the tools itself) with P2 (the model picks from options
  the server built and checked). "Every policy passes the same gate." Say "recorded" whenever a
  replay is on screen.

### Slide 9 · 4:05 to 4:43 · Held-out test of version 1.1: zero violations, no clear winner (38 s), the results of record

What to point at:

- the "Held-out cases" bullet (cases locked and code frozen before the test: the freeze at
  14:51:31Z, commit `3de5962`, then the case lock at 16:16:24Z, `49e62b5`).
- the two bar charts, campus then pantry, and the P2 bars in dark blue.
- the cost bullet: P1 24 of 24 for $3.01, P3 21 for $0.57, P2 18 for $1.00.
- for questions, the results figure (the backup slides, or the `figure.svg` tab).

**The figure.** `campus/report/figure.svg`, "Outcome met and status checks, per case and
policy": one bar per policy and case, labeled met/recorded, with the mean status checks per run.
The pantry figure is `pantry/report/figure.svg`.

**Compact readout.** Episodes meeting their case's outcome class, over recorded episodes. Then
cases where every trial met. Planned 80 campus and 40 pantry. All 120 were recorded.

| Suite | P0 rules | P1 tool use | P2 selective | P3 verify-all |
| --- | --- | --- | --- | --- |
| Campus episodes (C01 to C08) | 6/8 | 24/24 | 18/24 | 21/24 |
| Campus cases, all trials met | 6/8 | 8/8 | 6/8 | 7/8 |
| Pantry episodes (T01 to T04) | 4/4 | 6/12 | 9/12 | 6/12 |
| Pantry cases, all trials met | 4/4 | 2/4 | 3/4 | 2/4 |
| Executed violations | 0 | 0 | 0 | 0 |
| Unnecessary changes, C02 to C04 | 0 (n 3) | 0 (n 9) | 0 (n 9) | 0 (n 9) |
| Campus provider-reported USD | 0 | 3.006960 | 1.004722 | 0.570856 |

Per case, campus:

- C01 to C05 and C08: every policy met every trial.
- C06 (volunteer late): P1 met 3/3. P0, P2 and P3 met none.
- C07 (verification service unavailable): P1 3/3, P3 3/3, P2 0/3, P0 0/1.

Per case, pantry:

- T01: every policy met every trial.
- T02: P3 met 0/3. The others met theirs.
- T03: only P0 met (1/1).
- T04: P1 met 0/3. The others met theirs.

**Say** (the deck's line, `pres-note.md` slide 9):

> "Everything so far came from practice cases I built with. Then I froze version one point one,
> its code, prompts, model and limits, and ran twelve held-out cases, hidden from every policy.
> All one hundred twenty runs were recorded. No policy executed a violation or changed a quiet
> event. But my P two showed no consistent advantage. P one met the expected outcome in all
> twenty four campus runs, at three times P two's model cost. These are descriptive counts
> only."

The voided first attempt and the 55 refused requests are no longer spoken. They stay on the
slide (refusals) and on the backup slide "what the held-out runs cost" (the void).

"Three times" checks out: P1's provider-reported campus cost is $3.006960 against P2's
$1.004722, about 2.99 times.

**The honest tradeoff, for questions:**

- **On campus, P2 is cheaper per run than P1, not than P3.** It cost $1.00 against P1's $3.01,
  with 84 model calls against 90. P3 met 21 of 24 campus runs for $0.57.
- **P2 met fewer campus cases.** Its six campus misses have two causes:
  - C06, ×3: a frozen rule that treats only equipment notices as material, so a correctly read
    "volunteer late" never reached the planner. P3 has the same limit. Both were disclosed
    before the runs.
  - C07, ×3: action selection. A repeated check and a released, re-made hold used up the 8
    model calls before the approved change could be applied.
- **Refused requests on campus.** P1 made 5, P2 made 0 and P3 made 6. The
  executor turned them all away, with 0 executed violations.
- **On the two pantry partial cases,** P1 met 0 of 6 runs, P2 3 of 6 and P3 3 of 6.
  Two causes:
  - Only P2 and P3 have pantry-specific prompt guidance, a confound.
  - A frozen-code defect: a pool checked as unavailable stays a requestable handoff. It was the
    earliest broken stage of all six P2 and P3 T03 failures. The results stand as measured.

### Slide 10 · 4:43 to 5:09 · One failure: a correct reading that never reached the planner (26 s)

**The failure trace (the deck's choice):** `hk_q8n__P2__s101`, case C06, the protocol
condition "volunteer late, with a subsequent check-in". Its earliest broken stage is planner
input. Status completed, goal not met.

What happened:

- The one `interpret` call read the person's self-report correctly: extraction label `correct`,
  a `delay` change spec for the demonstrations lead.
- The server then judged the notice "not material for the current plan" and recorded `keep`.
- No hypothesis reached `evaluate_candidates`. The swap stayed evaluated and applicable at every
  wake, but nothing put the plan in question.
- Infeasibility was reported once the demonstrations could no longer start.

The same happens in all six P2 and P3 runs, and P0's parser abstains. P1 met C06 3/3.

Sources: [`FAILURES.md`](../../../apps/plan_b/evaluation/results/wave3_heldout_20261025T1625Z/FAILURES.md),
"C06". Trace `campus/episodes/hk_q8n__P2__s101/trace.json.gz`. This limit was disclosed at the
case lock, before the runs.

- **Point at:** the slide's four steps: message, read correctly, stopped here, plan kept. Then
  "in the count".
- **Say** (the deck's line):

> "In one held-out case a volunteer says they will be late. P two and P
> three read the message correctly. But my frozen rule passes only equipment claims to the
> planner, so the plan was never questioned. All six of their runs stay in the count. P one met
> this case every time."

**A second failure, for questions only:** `hk_f6k__P2__s101`, case C07, "relevant verification
service unavailable". Its stage is action selection, and the episode is capped. All three P2
trials repeat it.

| Model call | What P2 did |
| --- | --- |
| 1 | read the notice correctly |
| 2 and 3 | checked the same unavailable status service twice |
| 4 and 5 | held the standby, then checked it (available) |
| 6 and 7 | released the hold, then held the standby again for another slot |
| 8 | asked the organizer to approve the spend. The 8-call cap then stopped the episode |
| none | the organizer approved, but the stopped policy was never woken to apply the change |

There was no violation and no invented confirmation.

### Slide 11 · 5:09 to 5:49 · Same loop, a new rule: 40 kits for a fictional pantry (40 s)

**Clicks (optional board, as in DEMO.md's pantry segment):**

1. Load `pantry_dev01`. The clock reads 12:30.
2. **Role sessions** → `fictional_staff` → **Issue join code** → **Open in new tab**.
3. T1: **Run deterministic policy**.
4. Staff tab: wait for the hold, then **Record stock receipt**, once.
5. T1: **Run deterministic policy**.
6. *Minutes* = 13:40 minus the header clock → **Run N minutes with policy**. Say "fast-forward".
7. Staff tab: **Record distribution**.

**Point at:** "Fictional pantry sandbox". Target 40. The counters move from supply shortfall
16 / service deficit 40, to 0/40 after the staff handoff, to 0/0 after the distribution ("40 of
40 on time").

**Say:** the narration of `pres-note.md` slide 11. Its results sentence reads: "On four
held-out pantry cases, fixed rules met all four runs, and the model policies six to nine of
twelve, partly because of a defect in my frozen planner. No kit was counted twice." That matches `pantry/report`: P0 4/4. P1 6/12, P2 9/12,
P3 6/12. 0 duplicate or unauthorized credits. 0 conservation failures.

### Slide 12 · 5:49 to 6:28 · Version 1.2: the fixes, then six fresh held-out cases (39 s)

Added in Wave 3b. Sources: `apps/plan_b/evaluation/results/wave3b_fresh_20261025T2327Z/`
(README.md, FAILURES.md, `{campus,pantry}/report/metrics.json`), read by `make_results.py` into
`slides/figures/results_numbers_v12.tex`.

- **Point at:** the two-row table. Row 1 is the v1.1 record (12 cases). Row 2 is version 1.2 on
  six fresh held-out cases (C09 to C12, T05, T06), locked at 23:23:54Z, before the first 1.2
  call at 23:27:31Z. Then "59 of 60 fresh runs met" and the caption "not a before and after".

| Version 1.2, fresh held-out (60 runs) | P0 rules | P1 tool use | P2 selective | P3 verify-all |
| --- | --- | --- | --- | --- |
| Campus episodes (C09 to C12) | 3/4 | 12/12 | 12/12 | 12/12 |
| Pantry episodes (T05, T06) | 2/2 | 6/6 | 6/6 | 6/6 |
| Executed violations | 0 | 0 | 0 | 0 |

The miss is C11 under P0 (`ev_w2n__P0__once`, interpretation: P0's frozen parser does not read
a person's own delay report). C10, the negative control, had 0 unnecessary changes in 10 of 10
runs. The fresh run cost 3.608150 USD.

- **Say** (the deck's line, `pres-note.md` slide 12):

> "Version one point two targets those failures. A person's own delay now reaches the planner,
> and a pool checked as unavailable is no longer offered. The old cases were spent, so six fresh
> ones were written without the new code, and locked before any call. Version one point two met
> fifty nine of sixty runs. Fixed rules missed one late volunteer. The other policies met every
> run, so this small set cannot rank them. The cases differ, so this is not a before and after."

**For questions only:**

- The fresh cases repeat known conditions (C11 is the C06 condition, T06 is T03), with near
  copies of the spent wording, so they test new instances of known conditions. The cases' author
  saw a prose list of the planned fixes but no 1.2 code. The policy author never read the cases.
- Five limits of 1.2 found by the audit before the freeze (A1 to A5, `RUNTIME_CONTRACT.md`
  section 21) stayed frozen, because the auditor had seen the fresh cases.
- **The rerun on the spent cases** (`wave3b_rerun_spent_20261025T2345Z`, backup slide "version
  1.2 on the spent cases, a diagnostic rerun"): always say "post-hoc diagnostic rerun after
  fixes, on spent cases, not held-out". Campus P0 6/8, P1 24/24, P2 21/24, P3 24/24. Pantry P0
  4/4, P1 10/12, P2 12/12, P3 9/12. The C06 misses of P2 and P3 and the T03 misses did not
  recur, consistent with the fixes. C07 under P2, T02 under P3, T04 under P1 (2 of 3) and P0 on
  C06 and C07 still miss. It ran two jobs at a time and waited out 61 HTTP 429 answers at no
  cost. Its generated files say held-out only because of the harness path (its README explains).
- P2 still shows no consistent advantage.

### Slide 13 · 6:28 to 7:00 · What works today, and what is next (32 s)

- **Point at:** the QR code (it opens `apps/plan_b` on the pushed branch) and "12 held-out
  cases (120 runs), then version 1.2 on 6 fresh ones (60 runs)".
- **Say** (the deck's line): "Today Plan B verifies, prepares and commits in a local sandbox.
  Every accepted change has a receipt, and people approve spending. In both held-out tests no
  policy executed a violation, and my policy showed no consistent advantage." Then the
  real-life mapping, "No community has used it yet." and "Next, I want to review it with
  community staff. Thank you."

## 5. Forced-failure fallback (the live model, if it is ever used on stage)

The automated rehearsal checks one failure path, an endpoint that refuses the connection
(rehearsal 2, [REHEARSALS.md](REHEARSALS.md)). It shows a **Wait** card "Failure `provider_error`: the model provider
failed or could not be reached. Nothing was invented in its place." The plan, holds,
commitments, budget and receipts are unchanged, and no successful call or cost is recorded.
A hanging endpoint (no card until the provider's 90 s timeout) and a rate-limit error were not
rehearsed. If live mode is used, run it only on `dev01`, the case the fallback replay recorded,
and only in slide 8's board time. The whole switch takes about 25 s, which replaces slide 8's
board time. Keep a tab T3 open on `#/replay/live_p2-live_dev01_trace.json` with **Final
recorded state** clicked. This section replaces DEMO.md section 5, which switched to T2.

1. Switch if nothing visible changes **20 s** after **Run live agent**. In the rehearsal the
   failure card appeared after 0.2 s.
2. Say: **"We are switching to a recorded run of the same scenario."**
3. Open `#/replay/live_p2-live_dev01_trace.json` → **Final recorded state**. The purple
   "Recorded replay" banner and "Integrity check passed" stay on screen, with receipts
   `rcpt_0001` to `rcpt_0003`. The rehearsal had the replay ready 0.8 s after the switch.
4. Never leave the live badge over a replay, never call a replay live, and never retry until it
   works. Continue with the deck, and load a clean episode before using the board again.

If the board misbehaves but the server runs, open `#/replay/pantry_dev01_trace.json`, labeled
"Recorded replay". A replay needs the server. If the server fails, continue with the deck alone.
It tells the whole story.

## 6. Do not claim

- **No comparative advantage for P2.** Do not say or imply that P2 beats P1, P3 or P0. Do not
  say P2 is "more efficient" without its denominator: it cost less per run, and it also met
  fewer campus cases.
- **No significance, no rate beyond the counts.** The case is the unit (8 campus, 4 pantry).
  Three trials are repeated runs of one case, not three cases, and seeds were not sent to the
  provider.
- **Never pool campus and pantry.** Never say "120 episodes met …".
- **Zero violations is enforced by design.** Say it next to the refused requests, which show
  the gate working. It means none were observed in these runs, not a guarantee.
- **Never hide the voided attempt 1.** The first attempt hit the provider's rate limit and was
  voided before any reported result existed. That departs from the frozen status rules. The
  results README discloses it.
- **The held-out cases are spent.** Name a case only by its id and the protocol condition in
  `08_evaluation.md`. Never show its messages, timings, predicates or expected outcome on a
  slide.
- **Which policy acted.** Board frames are the rule baseline (no model). Model decisions come
  from recorded runs: Wave 2 development runs at `1.0.0`, Wave 3 held-out runs at the frozen
  `1.1.0` ids.
- **Fictional sandbox.** No real bookings, rooms, purchases, messages, people or stock. The
  November 2026 dates are fictional.
- **No real pantry and no U-ACCESS involvement.** U-ACCESS is public context only. There are no
  recipient identities and no eligibility, allergen or medical decisions.
- **Not zero-shot transfer.** The pantry needed an explicit adapter.
- **Rehearsals.** The rehearsals were automated internal ones. Human rehearsals are pending.
  Do not say "rehearsed live" or "tested with users".
- **No community validation, no pilot, no partner.**
- The model's rationale is untrusted text, never an explanation.
- Never say "always safe", "proven reliable", "optimal", "first ever" or "guarantee".

## 7. Reset checklist between rehearsals

Follow DEMO.md section 8: stop the server. Run `demo_prep.py`. Start the server. Sign in. Close
old role tabs. Reload the replay tabs. Then add:

- Reopen the deck at slide 1.
- Keep the `figure.svg` tab open.
- `uv run plan-b eval verify-freeze --require-heldout` prints "verified" for both manifests.
