# Commitment study: report

Exploratory with respect to Gate 3: nothing here re-votes the registered pilot, and the
2026-09-23 kill-or-reframe decision stands. Within the study, stage C is a registered
confirmation: its method, hypotheses, tests and evaluator were committed and pushed
(`9d8e97f`, 2026-09-28) before its live runs; amendment C3 in `PLAN.md` discloses what touched
the fresh pool earlier (a scripted structural test computed outcomes on 6 of the 48 clusters) and
an interim look at one primary run. The plan and every amendment are in `PLAN.md`; the frozen
tree shows no drift. Numbers below come from `out/confirm.json` (stage C), `out/posthoc.json` and
`out/sensitivity.json` and `out/ablation.json` (post hoc on stage C), `out/dev/dev1.json` (stage B) and the run outputs
under `out/` (stage A), unless a sentence names another source.

## The method

**Certify-then-hedge** (`cth.py`). At each trigger firing (at most two per episode) a fixed,
action-aligned hypothesis set (demand up, demand down, lead-time shift, demand pulse) is
registered. Hypothesis `h` of firing `j` gets prior mass `a_j * w_jh`, with `a_j = 0.05 * 2^-j`
(the frozen alpha schedule) and `w_jh = lam / 4 + (1 - lam) * 1{h is the model's family}`; the
model's answer sets these weights and, for the hypothesis it names, the onset window of its
e-process, and nothing else. Each hypothesis has its own module 05
e-process, started after the proposal and fed every later period. The posterior shock mass is
proportional to `a_j w_jh E_jh`; the shock's size comes from a working likelihood of the visible
data, never from the model's magnitude bin; and the order is the `p/(p+h)` quantile of the
posterior-predictive mixture, which equals arm 1's order exactly when no hypothesis is live.
Families module 04 cannot profitably act on (compound, shipment loss, transit pause) carry no
hypothesis. `lam = 0.25` is the method, `lam = 0` trusts the model's family alone, and `lam = 1`
is a content-free control that never calls the model (it is still timed by the shared trigger,
alerts included).

Guarantees (proof sketches in `paper/sections/06_method_hedge.tex`): under a null whose baseline
is known, for every stopping time the expected shock mass is at most `A = sum a_j <= 0.0375`,
whatever the model outputs, and the one-period newsvendor regret against arm 1 is at most the
posterior odds times the value of the hypotheses. The demand e-processes as run estimate their
null from the pre-proposal prefix; the null Monte Carlo (`out/mc_exposure.md`) finds no cell
clearly above a bound with the baseline known, and 2.0 to 2.7 times `A` for the stopped exposure
with the plug-in null and a first firing at period 10. Against the content-free arm, a family the
model does not name costs exactly `log(1 / lam)` nats of evidence (log 4) and the named one saves
`log(lam + (1 - lam) |H|)` (log 3.25). With one hypothesis and `lam = 0` the gate's threshold is
a posterior-odds rule of the same form; it is an analogy, since the gate certifies the model's
full spec and the hedge a canonical one.

## Stage C: registered confirmation on fresh seeds

48 units from a reserved seed pool disjoint from every registered pool (8 per family), each under
four information conditions plus one unshocked twin: 192 shocked and 48 null episodes, 240 in
all, one cluster per unit. Eleven arms. Primary endpoints `gemini-3.8-flash` and `grok-4.20`;
secondary `gemini-2.5-flash-lite`, `llama-3.1-8b`, `deepseek-v3`, `gpt-3.5-turbo`.

**Primary hypotheses** (net reward per episode, one-sided cluster sign-flip test, Holm over the
four tests at 0.05): all four reject.

| contrast | Gemini 3.8 | Grok 4.20 |
|---|---|---|
| H1: hedge - arm 10 (gate) | +309.1 b[172.6, 472.1], p < 0.0001 | +178.8 b[87.4, 280.9], p = 0.0002 |
| H2: hedge - arm 1 | +178.5 b[54.8, 325.5], p = 0.0028 | +162.9 b[47.8, 299.7], p = 0.0031 |

`b[a, b]` is the seed-cluster bootstrap 95% interval (48 clusters, 10,000 draws).

**Secondary readouts** (net per episode against arm 1 unless stated):

| model | right family, first proposal | at once (arm 8) | gate (arm 10) | hedge | hedge - content-free | null safety (hedge - arm 1 on 48 nulls) |
|---|---|---|---|---|---|---|
| Gemini 3.8 Flash | 93/170 | -2,046 | -131 | +178 | +9 | -3.2 b[-8.2, -0.1] |
| Grok 4.20 | 84/170 | -2,284 | -16 | +163 | -6 | +1.9 b[-1.7, 8.2] |
| DeepSeek-V3 | 78/170 | -1,478 | -39 | +170 | +0 | +1.4 b[-1.6, 6.5] |
| Gemini 2.5 Flash-Lite | 102/170 | -3,181 | -81 | +154 | -16 | +0.9 b[-2.2, 5.9] |
| GPT-3.5 Turbo | 46/170 (28 parse failures) | -1,493 | -2 | +153 | -16 | +1.4 b[-2.3, 7.7] |
| Llama 3.1 8B | 29/170 (53 parse failures) | -1,838 | -109 | +126 | -43 | +1.5 b[-2.2, 7.7] |

Every model's hedge - arm 1 and hedge - arm 10 intervals exclude zero; null safety is
non-inferior (lower bound above -25) on every model. The content-free control earns +169.1
b[48.2, 312.3] against arm 1. Gross profit agrees with net for the hedge (hedge - arm 1 gross
+223 to +280) but not for immediate action, which looks best on gross (+501 on the primary
models) and worst on net.

**By family** (hedge - arm 1, net per episode, Gemini / Grok): lead-time shift +1,286 / +1,177,
demand down +90 / +88, pulse +95 / +80, demand up -83 / -83, compound -40 / -40, shipment loss
-3 / -3, null -3 / +2. The gain is where the oracle headroom is.

**Language.** The hedge is not distinguishable from the content-free control on net with the
primary models (+9.3 b[-4.9, 23.6], -6.2 b[-28.7, 10.7]) and runs from -43 to 0 against it with
the others (below zero for Llama 3.1 8B and GPT-3.5 Turbo). The model's family label mainly lowers commitment on
null episodes: mean summed shock mass on the 48 nulls is 0.83 for the content-free control,
0.45 to 0.52 for the hedge, and 0.04 to 0.18 when the model's family is trusted alone (`lam =
0`), which in turn costs net reward (-16 to -192 against content-free; Grok -82.9 b[-169.0,
-13.4]). On this simulator, at this cost ratio, the certified search timed by alerts, not the
text, carries the gain.

**Post hoc** (`out/posthoc.json`, written after the results were seen; decides nothing):

- *Where the gain comes from.* The 32 shocked lead-time episodes supply 96% of hedge - arm 1
  (Gemini 96.0%, Grok 96.3%; with their twins, 95.8% and 96.7%). Without the 8 lead-time units
  (40 clusters) hedge - arm 1 is +9.0 b[-23.9, 42.5] and +6.6 b[-24.6, 36.1]; hedge - gate stays +226.8 b[82.3, 408.1] with Gemini (+58.1
  b[-0.8, 133.6] with Grok), because the gate loses 1,057 per demand-rise episode with Gemini.
- *Without the six structural-test clusters* (units `i = 0`, 42 clusters): H1 +328.6 and +187.7,
  H2 +162.8 and +145.3; the largest one-sided p is 0.0024.
- *Null episodes.* The Gemini null loss is on the 24 false-alert twins (-6.4 b[-16.1, -0.3],
  worst -105); the 24 silent twins are -0.04 b[-0.38, 0.25] (21 never trigger). Hedge - content-free
  on the 48 nulls: -2.0 b[-8.1, 1.7] (Gemini), +3.1 b[-0.04, 8.4] (Grok).
- *Exposure.* Hedge over content-free null exposure: 0.631 b[0.429, 0.668] (Gemini) and 0.553
  b[0.392, 0.581] (Grok), cuts of 37% and 45%, almost all on false-alert twins (the silent-twin
  ratio is not estimable: only 3 clusters carry content-free exposure). Naming any family, right
  or wrong, moves prior weight off the others; the content-free control's null mass sits mostly on
  the pulse hypothesis (0.69 of 0.83).
- *Lead-time proposals.* Gemini named a lead-time shift in 17 of the 32 lead-time episodes
  (medium 8, high 3, low 6) and Grok in 11 (medium 10, high 1). Every family-4 unit moves to a
  lead of 3, so the true shift is two periods for the units with a baseline of 1 and one period
  for those with a baseline of 2 (PLAN.md, DA8; an earlier version of this report said every
  true shift was one period). Reading low, medium and high as one, two and three periods, as the
  gate compiles them, Gemini's first proposal had the right size in 10 of 17 (5 too large, 2 too
  small) and Grok's in 5 of 11 (6 too large). The gate activated a median of 11 periods after
  the proposal with both.
- *Endpoint sign.* Gross and net disagree in sign for at once - arm 1 and hedge - at once (both
  endpoints' intervals exclude zero) and for the gate - arm 1 point estimate (its net interval
  includes zero), on both primary models; every claim here is on net.

**Cost ratio** (`sensitivity.py`, `out/sensitivity.json`; exploratory replay). The 240 fresh
episodes and all eleven arms re-run at p/h = 1, 2, 9 and 19 (InventoryBench uses 1, 4 and 19),
each model-calling arm served the answer its model gave at the same (arm, episode, period) under
p/h = 4. The prompt shows the margin, the inventory position and the order and arrival history,
all of which change with the ratio, so those arms are a counterfactual with the answer held
fixed; the others are exact. At p/h = 4 the replay reproduces all 2,544 registered records of each primary run
exactly, and no call at any ratio lacked a recorded answer.

| p/h | hedge - gate (Gemini / Grok) | hedge - arm 1 | hedge - content-free |
|---|---|---|---|
| 1 | +228 b[109, 376] / +85 b[30, 151] | +16 b[-14, 47] / +10 b[-18, 40] | +1 / -5 b[-10, -0.02] |
| 2 | +259 / +114 | +67 b[8, 135] / +55 b[2, 118] | +9 / -3 |
| 4 | +309 / +179 | +178 / +163 | +9 / -6 |
| 9 | +454 / +357 | +485 b[182, 853] / +447 b[168, 785] | +47 b[6, 97] / +10 b[-34, 59] |
| 19 | +722 b[400, 1,095] / +694 b[324, 1,138] | +1,056 b[398, 1,850] / +991 b[376, 1,739] | +84 b[18, 166] / +19 b[-38, 87] |

The hedge beats the gate at every ratio. Its gain over arm 1 vanishes at p/h = 1 and grows with
the ratio; at p/h = 19 it no longer rests on lead-time shifts alone (+125 b[43, 227] and +121
b[38, 224] without the lead-time units). Every reward grows with p: as a share of arm 1's net
reward the gain is 0.5% / 0.3% at p/h = 1, 1.1% / 1.0% at 4 and 1.2% / 1.2% at 19. The text's
share over the content-free control is distinguishable from zero with Gemini at p/h = 9 and 19,
and with Grok at p/h = 1, where it is negative. All post hoc, on the confirmation's own
episodes; `sensitivity.json` holds 6 contrasts x 2 endpoints x 5 ratios x 2 models.

**Ablations** (`ablation.py`, `out/ablation.json`; post hoc, exploratory). Variants of the
method re-run on stage C's 240 fresh episodes, each served, at every decision point, the answer
text the model gave `arm12_cth` in the registered run (so the counterfactual is "the same answer
at the same decision point"; the shared trigger fixes the decision points). At p/h = 4 the
`lam = 0.25` hedge reproduces `arm12_cth`'s 240 records exactly and `lam = 1` reproduces
`ctrl_cth_uniform`'s, at p/h = 4 and 19; no variant called at a period without a recorded
answer. `lam = 0` is not `arm12b_cth_llm`, which made its own calls (their records differ on 1
and 4 episodes). Contrasts are each variant minus the method (`lam = 0.25`, hedge rule) on net
reward, with seed-cluster intervals; at p/h = 19 the comparators come from the cost-ratio replay.
The method's own null exposure is 0.523 / 0.458.

| variant | minus the method, p/h = 4 (Gemini / Grok) | p/h = 19 | null exposure (Gemini / Grok) |
|---|---|---|---|
| lam 0 (label only) | -25 b[-66, 9] / -77 b[-144, -21] | -179 b[-365, -31] / -406 b[-779, -114] | 0.184 / 0.062 |
| lam 0.1 | -4 b[-13, 3] / -14 b[-32, -1] | -23 b[-60, 3] / -57 b[-122, -7] | 0.365 / 0.275 |
| lam 0.5 | -2 b[-9, 4] / +2 b[-4, 8] | +1 b[-17, 22] / +16 b[-4, 41] | 0.672 / 0.631 |
| lam 0.75 | -4 b[-14, 6] / +5 b[-5, 18] | -25 b[-65, 14] / +11 b[-24, 48] | 0.765 / 0.739 |
| lam 1 (content-free) | -9 b[-24, 5] / +6 b[-11, 29] | -84 b[-166, -18] / -19 b[-87, 38] | 0.829 / 0.829 |
| linear rule, lam 0.25 | -3 b[-10, 2] / -9 b[-21, -0.02] | -152 b[-278, -46] / -168 b[-311, -49] | 0.523 / 0.458 |
| MAP rule, lam 0.25 | -56 b[-97, -19] / -62 b[-108, -21] | -370 b[-649, -131] / -368 b[-655, -125] | 0.523 / 0.458 |

The graded rule matters more than the prior weight. Committing to the compiled target once the
shock mass reaches 1/2 (MAP) loses about 56 and 62 per episode at p/h = 4 and about 370 at
p/h = 19, every interval below zero; interpolating the target by the shock mass (linear) costs
little at p/h = 4 and 152 and 168 at 19. At `lam = 0.5` and `0.75` the net outcome is not
distinguishable from the method's with either model, while null exposure rises with `lam`;
smaller weights on the uniform part cost with Grok (`lam = 0.1`: -14 at p/h = 4, -57 at 19), and
trusting the label alone (`lam = 0`) gives the lowest null exposure but loses with Grok at
p/h = 4 and with both models at p/h = 19.

**Cost.** Stage C provider cost $6.51: Gemini 3.8 $4.55, Grok 4.20 $1.09, GPT-3.5 $0.45,
DeepSeek-V3 $0.22, Gemini 2.5 Flash-Lite $0.13, Llama 3.1 8B $0.06.

## Stage B: development (no claim)

On the 120 spent pilot episodes, replaying arm 10's cached answers at no cost, the method scored
+141 to +156 net per episode against arm 1 on the six real-model banks available then (every
interval excluding zero) and +99 on the fixed-payload bank; +140 to +454 against arm 10 across all seven banks. The
live arm matches the replay on 120/120 episodes of the scripted bank.

## Stage A: model ladder on the pilot episodes

The registered 120 pilot episodes with every rung that has finished (`out/ladder.json`,
`out/ladder.md`; `step-5-preview`, a slow reasoning model, was still running when this was
written, and `gemini-3-flash-preview` was dropped under A1). The hedge column is the
stage B development replay (arm 10's cached answers, no calls), so it carries no claim.

| model | developer | released | size | right family / 96 | first-proposal abstain | at once - arm 1 (net) | gate - arm 1 (net) | hedge - arm 1 (net, dev) | false-alert nulls acted on (at once / gate) | cost |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen-2.5-72b | Alibaba | 2024-09 | 72B | 44/96 | 26 | -2,781 | -300 | +151 | 12/12, 1/12 | $0.14 |
| qwen-2.5-7b | Alibaba | 2024-10 | 7B | 2/96 | 63 | -61 | +0 | +107 | 0/12, 0/12 | $0.04 |
| deepseek-v3 | DeepSeek | 2024-12 | 671B-MoE | 45/96 | 37 | -1,727 | -163 | +150 | 3/12, 0/12 | $0.09 |
| gemma-3-27b | Google | 2025-03 | 27B | 51/96 | 13 | -2,212 | -55 | +158 | 12/12, 1/12 | $0.04 |
| gemini-2.5-flash | Google | 2025-06 | mid | 59/96 | 18 | -3,188 | -294 | +141 | 12/12, 1/12 | $1.34 |
| gemini-2.5-flash-lite | Google | 2025-07 | small | 55/96 | 5 | -3,656 | -300 | +154 | 12/12, 1/12 | $0.05 |
| gemini-3.1-flash-lite | Google | 2026-05 | small | 52/96 | 23 | -2,723 | -235 | +156 | 12/12, 1/12 | $0.11 |
| gemini-3.8-flash | Google | 2026-09 | mid | 59/96 | 24 | -2,549 | -234 | +154 | 12/12, 1/12 | $1.90 |
| llama-3.1-8b | Meta | 2024-07 | 8B | 19/96 | 0 | -2,267 | -174 | +120 | 12/12, 1/12 | $0.02 |
| llama-3.2-1b | Meta | 2024-09 | 1B | 0/96 | 5 | +0 | +0 | +107 | 0/12, 0/12 | $0.09 |
| llama-3.2-3b | Meta | 2024-09 | 3B | 0/96 | 0 | -28 | +0 | +107 | 2/12, 0/12 | $0.04 |
| llama-3.3-70b | Meta | 2024-12 | 70B | 24/96 | 51 | -1,641 | -158 | +136 | 2/12, 0/12 | $0.03 |
| gpt-3.5-turbo | OpenAI | 2023-05 | legacy | 26/96 | 25 | -1,821 | -60 | +148 | 11/12, 1/12 | $0.17 |
| gpt-4o-mini | OpenAI | 2024-07 | legacy | 29/96 | 0 | -1,741 | -1 | +111 | 11/12, 1/12 | $0.07 |
| gpt-oss-20b | OpenAI | 2025-08 | 21B-MoE | 49/96 | 21 | -2,626 | -176 | +149 | 6/12, 0/12 | $0.05 |
| step-3.5-flash | StepFun | 2026-01 | mid | 49/96 | 29 | -3,339 | -156 | +146 | 12/12, 1/12 | $0.37 |
| step-3.5-flash-2603 | StepFun | 2026-03 | mid | 50/96 | 26 | -3,269 | -141 | +155 | 12/12, 1/12 | $0.37 |
| step-3.7-flash | StepFun | 2026-05 | mid | 53/96 | 29 | -3,051 | -201 | +153 | 12/12, 1/12 | $1.72 |
| grok-build-0.1 | xAI | 2025-08 | small | 28/96 | 53 | -2,002 | +3 | +144 | 3/12, 0/12 | $1.28 |
| grok-4.20 | xAI | 2026-03 | mid | 53/96 | 20 | -2,624 | -172 | +154 | 9/12, 1/12 | $0.44 |

Readings. Perception ranges from 0/96 to 59/96: Llama 3.2 1B never produces a non-abstaining
`ShockSpec`, so every proposal falls back to arm 1, and 3B produces seven (all demand up), on
which acting at once loses 28 b[-54, -6]. The loss from acting at once ranges from zero to
-3,656 and, contrary to stage A's registered expectation (item 6) that it would grow as
perception falls, grows with how readily a model commits; across the rungs commitment and accuracy move
together (post hoc, `posthoc.json` `ladder`: r = 0.86; loss against either, r = -0.90), so
being right does not protect a model: Qwen 2.5 7B (2/96 right, 63 first-proposal abstentions)
loses 61, while Gemini 2.5 Flash-Lite (55/96 right, 5 abstentions) loses 3,656. The gate stays
between -300 and +3; contrary to stage A's registered expectation (item 6), its interval lies
below zero on two rungs, Gemini 2.5 Flash -294 b[-567, -45] and GPT-3.5 Turbo -60 b[-151, -1].
The hedge's development replay has point estimates of +107 to +158 on every rung (the interval
includes zero for Llama 3.1 8B); the content-free variant gains +136 on the same episodes.
Rung costs in `out/ladder.json` sum to $8.34 over the 20 finished rungs, of which $2.34 is the
real-content pilot's two banks, reused here.

## Amendments and disclosures

- A1: `gemini-3-flash-preview` dropped (projected cost over cap); `grok-build-0.1` cap raised.
- A2: StepFun (four models, shadow-priced flat-rate plan) and OpenRouter (eleven open-weight or
  legacy models) added before any call on them.
- A3: StepFun shadow caps raised to $4 so `step-3.7-flash` runs.
- C1: fresh layout reduced from 72 to 48 units before any call: the dev/cal alert bank has four
  accurate templates per family and split, and module 03's renderer refuses repeated texts.
- C2: an empty model echo is re-requested (up to three times, all attempts billed) instead of
  aborting; the `deepseek-v3` secondary run was re-run from its cache.
- C3: disclosures from an independent audit that reproduced every registered number: an interim
  look at the Grok primary run while Gemini's ran; outcomes computed (not read) on units `i = 0`
  by the pre-registration structural test; the C1 layout materialised early (no arms); the
  Gemini manifest's end-of-run SHA; Rule U applies to arm 10 only; the stage B guarantees
  restated (known null, exact prior constants, the gate as an analogy).
- Stage B tuned on the spent pilot episodes.

## What this does not show

The simulator's lead times are deterministic, which makes a lead-time shift easy to size from
receipts; at p/h = 4 the gain rests on that family. One cost ratio (p/h = 4) was confirmed; the
others are replayed with the models' answers held fixed. The exposure bound needs a known null;
the demand e-processes estimate theirs from the pre-proposal prefix, and the Monte Carlo puts
the stopped exposure at 2.0 to 2.7 times the budget at early firings in the cells matched to the
null episodes (up to 3.2 in others). The regret bound covers the one-period surrogate, not realised multi-period
cost. No claim is made about language understanding; at the registered cost ratio the text adds
no net value over the alert-timed content-free control.
