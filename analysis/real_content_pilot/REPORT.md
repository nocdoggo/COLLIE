# Real-content pilot: report

Exploratory, and not a Gate 3 vote: the stored scripted pilot (`reports/pilot_report.md`) stays
the Gate 3 record. The plan (`PLAN.md`) was committed and pushed at `4ac16f9`, before any live
call. It logs two deviations: a logging-only change after the smoke runs, and post-hoc
supporting counts after the live results. Every number below comes from
`out/evaluation.json` (tables in `out/evaluation.md`), computed by `evaluate.py` from the committed
run outputs, unless the sentence names another source. Numbers from its `post_hoc` block, added
after the live results were seen (PLAN.md deviation 2), are marked post hoc.

## What ran

The registered 120 dev/cal episodes, nine arms, module 03's alert bank, and two live endpoints,
one run each: `gemini-3.8-flash` and `grok-4.20-0309-non-reasoning`. `scripted-bank` is the same
run with the scripted transport's one fixed payload (`demand_level / demand_up / medium`), so the
difference between a live run and `scripted-bank` is the model's answers and nothing else.

Checks that held: every run's truth is byte-identical to `reports/pilot_truth.jsonl`; the six
arms that never call the model replay `scripted-bank` exactly in both live runs; all 98 first
prompts both endpoints answered were identical; the frozen tree shows no drift.

## Bottom line

- **First proposals track the alerts.** The first proposal names the right family (and direction)
  in 61% (Gemini) and 55% (Grok) of the 96 shocked episodes, against 17% for the fixed payload; on
  the 20 early-accurate episodes that carry a bank alert, 20/20 and 18/20. Fully correct proposals
  are rare (3/96 and 2/96), and magnitude is right in only 8/96 and 7/96, fewer than any field.
  The truth is `low` in 80 of 96 episodes (`reports/pilot_truth.jsonl`), and post hoc, the models
  almost always say medium or high.
- **Family accuracy is lower under unreliable alerts, mostly through abstention.** Paired within
  seed, family accuracy is 0.60 lower (Gemini) and 0.50 lower (Grok) under unreliable than under
  early-accurate alerts (normal 95% intervals over the 20 seeds, [0.38, 0.82] and [0.28, 0.72];
  Q2 has no seed-cluster bootstrap, so this is descriptive). No seed was right only under the
  unreliable alert. Of the 12 (Gemini) and 10 (Grok) seeds lost, 11 and 7 became abstentions, and
  every distractor alert produced an abstention in both models.
- **Real content moves arm 10 on gross, not on net.** Against the fixed payload, arm 10 gains
  +198 b[15, 434] (Gemini) and +146 b[19, 319] (Grok) gross per episode; on net, which also
  charges holding, the change is -87 b[-322, 142] and -25 b[-227, 152] (`b[a, b]` is the
  seed-cluster bootstrap 95% interval). Real content also lowers arm 9 on gross (-253 and -197,
  intervals excluding zero); arm 8's gross intervals include zero. Post hoc, the 16
  lead-time-shift episodes contribute about +190 of Gemini's +198 and about +148 to Grok's +146,
  more than all of it; the other families together add about +8 and -1.5.
- **The readout does not change.** Both live runs still read `kill-or-reframe` on the same two
  triggers. `insufficient_headroom` stays 2 by construction (the oracle and arm 1 never see the
  model). `detector_indistinguishable` narrows from -558 to -360 (Gemini) and -412 (Grok) but
  stays well below zero.
- **Operations were clean.** 429 of 429 parses valid on both endpoints, no repairs, no refusals,
  no retries. Cost $1.90 (Gemini) and $0.44 (Grok), under the $3.00 cap. Rule U gave arm 10 an
  abstention in place of two Grok answers (For the team, item 1).

## Headline quantities

The Q1 rows are counts. The other rows are mean differences per episode over all 120 episodes: Q7
is the live run minus `scripted-bank` for the same arm and episode, and Q4 is the first arm minus
the second within a run (ctrl is `ctrl_cusum_to_compiler`, arm 1 `arm1_capped_base_stock`). Gross
is `total_profit`; net is `total_reward`, which also charges holding. `b[a, b]` is the
seed-cluster bootstrap 95% interval (24 clusters, 10,000 draws).

| quantity | scripted-bank | gemini-bank | grok-bank |
|---|---|---|---|
| Q1 family correct, 96 shocked | 16/96 | 59/96 | 53/96 |
| Q1 family correct, 20 early-accurate with alert | 4/20 | 20/20 | 18/20 |
| Q7 arm 10, gross | | +198.0 b[15.0, 433.8] | +146.2 b[18.5, 319.3] |
| Q7 arm 10, net | | -86.7 b[-322.2, 142.2] | -24.8 b[-227.0, 151.9] |
| Q7 arm 8, gross | | -119.0 b[-278.2, 72.3] | -48.0 b[-175.6, 117.6] |
| Q7 arm 8, net | | -216.3 b[-1,206.9, 603.1] | -291.3 b[-1,055.7, 428.0] |
| Q4 arm10-ctrl, gross | -558.4 b[-792.3, -358.1] | -360.4 b[-473.0, -244.9] | -412.2 b[-520.7, -301.3] |
| Q4 arm10-arm1, gross | +30.3 b[1.7, 68.1] | +228.3 b[38.8, 460.1] | +176.6 b[46.0, 345.1] |

## By question

**Q1, first-proposal accuracy.** Family accuracy tracks the alert: 88% (Gemini) and 79% (Grok)
for early- and late-accurate alike, 42% for both under unreliable alerts, and 29% and 21% with no
alert, where 10 of the 24 episodes never trigger a call. Family 2, which the bank cannot cover
and so never carries an alert, draws abstentions in 9/16 (Gemini) and 10/16 (Grok). Grok reads 9
of 16 temporary pulses as a demand-level rise; Gemini, 2. Onset windows are right in 20/24
early-accurate episodes for both models, all 20 that carry an alert, but the fixed payload scores
the same 20/24, so this count does not separate the models' answers from the fixed payload. In
late-accurate episodes they are right in 1/24 (Gemini, as for the fixed payload) and 4/24 (Grok):
a late alert fires two periods after onset, so the window has to reach back two periods.

**Q2, early versus unreliable.** No seed was right under the unreliable alert and wrong under the
early one, for either model. By kind: distractors drew 5/5 abstentions from both models; Gemini
abstained on all 5 ambiguous alerts, where Grok named the right family in 3; under overstated
alerts 8/10 (Gemini) and 5/10 (Grok) were right, against 10/10 and 8/10 under the early alert.
The outcome differences (arm8-arm1 and arm10-arm1, early minus unreliable, gross and net) are all
positive in point estimate. Q2 has no seed-cluster bootstrap, so none is called different from
zero; of the normal 95% intervals over the 20 per-seed differences, only arm 8's gross difference
for Gemini excludes zero (+627 [89, 1,165]).

**Q3, verification by proposal class.** Arm 10 activated 43% (Gemini) and 39% (Grok) of
right-family proposals and refuted none of them. Wrong-family proposals are few with real
content (4 and 17); arm 10 activated 1/4 and 4/17 of them. Arm 9's heuristic refuted 35% and 24%
of right-family proposals, where arm 10's e-process refuted none.

**Q4 and Q7, outcomes.** On gross, real content lifts arm 10 (+198.0 and +146.2, table above)
and lowers arm 9 (-253.4 b[-416.4, -116.7] Gemini, -197.2 b[-343.0, -78.5] Grok); arm 8's gross
bootstrap intervals include zero. On net, no LLM arm's Q7 bootstrap interval excludes zero. With
real content arms 8 and 9 hold a spec for fewer periods (post hoc; arm 8: about 21 periods per
episode, against 26 with the fixed payload; arm 9: about 15 and 14, against 20). An abstention
holds no spec, and the models abstain on 24 (Gemini) and 20 (Grok) first proposals in shocked
episodes, where the fixed payload never does.
Arm 10 moves the other way (post hoc: about 4.5 and 3.1 active periods per episode, against 1.6),
and in point estimate its gross gain comes with about 285 (Gemini) and 171 (Grok) more holding
cost per episode, the gap between its gross and net changes. Gross profit charges no holding, the
mechanism the forensics describe: on gross any delay or stand-down "gives up free over-stock",
and every holding-aware behaviour "scores as pure cost" (`analysis/kill_trigger_forensics.md`,
sections 3.5 and 5). Arm10-arm1 on net stays negative in point estimate (-146.8 with the fixed
payload; -233.5 and -171.6 live), with wider intervals that now include zero (b[-505.5, 26.1] and
b[-427.2, 57.8]).

**Q6, nulls.** Silent nulls never trigger a call. On the 12 false-alert nulls Gemini's first
proposal followed the false demand-rise alert (`demand_level / demand_up`) on all 12 and Grok
abstained on 3; arms 8 and 9 acted on 12/12 (Gemini) and 9/12 (Grok), while arm 10 activated on
1/12 in every run: post hoc, on `dev/f1/s1050001/unreliable__twin` in both live runs, the same
episode as with the fixed payload (read from the `scripted-bank` records).

**Agreement.** On the 98 shared first prompts the two models gave the same answer category 70%
of the time (Cohen's kappa 0.64). Of the 86 shocked episodes both answered, both named the right
family in 45, only Gemini in 14, only Grok in 8, neither in 19. Post hoc: in each live run, 18
prompts reached the model more than once under different episode ids. Read from the proposal
logs, 16 of the 18 are common to both runs, and in each run 17 sit on family-2 seeds: 10 from
shocked episodes, whose four conditions carry no alert and so share their prompts, and 7 from
pairs of unshocked null twins on the same family-2 seed, which carry the same false alert. The
18th is shared by a family-3 late-accurate episode, called before its late alert fired, and the
no-alert episode of the same seed. At temperature 0, Gemini returned the identical payload for
14 of its 18 and Grok for 11 of its 18; the family and direction matched for 17 and 15.

**Q5, operations.** Gemini: 174 provider calls, p50 latency 7.3 s, p95 28.7 s; 97% of its
billable output tokens are thinking, which makes it about four times Grok's cost for a similar
number of calls. Grok: 178 calls, p50 0.9 s. Rule U (PLAN.md rule 5) fired twice, both on Grok
(`duration_bin: none`).

## For the team

1. **Module 02 and module 05 disagree on legal proposals.** Module 02 accepts a shock with
   `persistence` or `duration_bin` of `none`; module 05's lifecycle raises on it and the frozen
   stack aborts the run. Grok gave such an answer to 2 of its 143 distinct prompts (post hoc;
   Gemini 0 of 138). Rule U kept this pilot running; the permanent fix (module 02 rejects the
   shape, or module 05 refuses it gracefully) is a team decision.
2. **Magnitude does not line up.** Of the first proposals that name a shock (nulls included), 68
   of 74 (Gemini) and 73 of 75 (Grok) say medium or high (post hoc); the simulator's truth is low
   in 80 of 96 shocked episodes (`reports/pilot_truth.jsonl`). The bins or the prompt's guidance
   need a look before any magnitude-sensitive claim.
3. **The dev/cal bank has no demand-down template,** so family 2's shocked episodes got no alerts
   here.
4. **The gross endpoint** charges no holding, so it credits arm 10's extra stock without its
   cost. For arm 10 against arm 1, the gross and net estimates now sit about 462 (Gemini) and 348
   (Grok) apart, against 177 with the fixed payload; the gap is arm 10's extra holding cost over
   arm 1.
5. **Gemini's thinking tokens** are 97% of its billable output and most of its cost, and its calls
   are slow (p95 28.7 s, up to 56 s for one call). A thinking budget would change the endpoint and
   needs its own registration.

## What this does not show

This is not confirmatory: the 120 episodes are the ones the registered pilot already spent, each
endpoint ran once (and, per the post-hoc check above, repeated calls do not always return the
same answer), cells hold as few as 4 episodes, and nothing is corrected for multiplicity. It does
not re-vote Gate 3, and it supports no claim about language understanding beyond the field
accuracies above. A confirmatory test needs fresh held-out seeds under a new registration.

## Reproduce

```bash
uv run python -m analysis.real_content_pilot.evaluate --runs gemini-bank grok-bank \
    --reference scripted-bank
```

The evaluation reads only committed files. Re-running the live pilots replays the local response
cache (`results/`, not committed); without it they would make new paid calls.
