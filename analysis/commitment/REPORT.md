# Commitment study: report

Exploratory with respect to Gate 3: nothing here re-votes the registered pilot, and the
2026-09-23 kill-or-reframe decision stands. Within the study, stage C is a registered
confirmation: its method, hypotheses, tests and evaluator were committed and pushed
(`9d8e97f`, 2026-09-28) before its live runs, and stage D likewise (`fae3714`, with pre-run
amendments at `33f77b4`, 2026-09-29); amendment C3 in `PLAN.md` discloses what touched
the fresh pool earlier (a scripted structural test computed outcomes on 6 of the 48 clusters) and
an interim look at one primary run. The plan and every amendment are in `PLAN.md`; the frozen
tree shows no drift. Numbers below come from `out/confirm.json` (stage C), `out/posthoc.json` and
`out/sensitivity.json` and `out/ablation.json` (post hoc on stage C), `out/confirm_d.json` and
`out/readout_d.json` (stage D), `out/dev/dev1.json` (stage B) and the run outputs
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
a posterior-odds rule of the same form; it is an analogy, not an identity: for a named demand
or pulse hypothesis the two e-processes coincide (the gate's mixes over the registered
multipliers whatever magnitude is stated), for a lead-time shift the magnitude only selects the
delay tilt, and the gate then acts all at once on the compiled stated magnitude while the hedge
sizes the shock from the data.

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
  (40 clusters) hedge - arm 1 is +9.0 b[-23.9, 42.5] and +6.6 b[-24.6, 36.1]; hedge - gate stays +226.8 b[82.3, 408.1] with Gemini, because the gate loses 1,057 per demand-rise episode;
  with Grok, +58.1 b[-0.8, 133.6] is not distinguishable from zero. Per family, every shocked
  family's interval excludes zero except the demand rise (-83.4 b[-200.0, 21.1] and -83.4
  b[-203.9, 25.6]; `gain_source["by_family_cth-arm1|net"]`).
- *Without the six structural-test clusters* (units `i = 0`, 42 clusters): H1 +328.6 and +187.7,
  H2 +162.8 and +145.3; the largest one-sided p is 0.0024.
- *Null episodes.* The Gemini null loss is on the 24 false-alert twins (-6.4 b[-16.1, -0.3],
  worst -105); the 24 silent twins are -0.04 b[-0.38, 0.25] (21 never trigger). Hedge - content-free
  on the 48 nulls: -2.0 b[-8.1, 1.7] (Gemini), +3.1 b[-0.04, 8.4] (Grok).
- *Exposure.* Hedge over content-free null exposure: 0.631 b[0.429, 0.668] (Gemini) and 0.553
  b[0.392, 0.581] (Grok), cuts of 37% and 45%, almost all on false-alert twins (the silent-twin
  ratio is not estimable: only 3 clusters carry content-free exposure). Naming any family, right
  or wrong, moves prior weight off the others. Crediting each period's mass to its leading
  hypothesis, pulse-led periods carry 0.69 of the content-free control's 0.83 and 0.32 and 0.38
  of the hedge's 0.52 and 0.46, so most of the label's cut is that mass.
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

## Stage D: cost ratios and noisy lead times (registered)

Registered at `fae3714` before any stage D call, with pre-run amendments DA1 to DA12 at `33f77b4`
(from an independent audit of the registration and a fact-check; none changed a hypothesis, a
family, a pool or a cap). The six runs (`d19-`, `d1-` and `dsl-` for Gemini 3.8 and Grok 4.20)
completed at `a38eb64` (which differs from `33f77b4` in no stage C or D code file; the hashes
match), with nothing dirty but the owner's `.gitignore` edit, the runs' own output directories
and the still-running `ladder-step-5-preview` output; nothing was evaluated before all six had
finished. Rounding: one decimal, half away from zero; p-values at the Monte Carlo floor
(1/100,001) are written p < 0.0001. Evaluation:
`confirm_d.py` (`out/confirm_d.json`); registered secondaries: `readout_d.py`
(`out/readout_d.json`). Stage D pool: seeds `family * 1e6 + 200000 + i`, `i = 0..7`, 240 episodes,
48 clusters, run at p/h = 19 and 1. Stratum: family 4, `i = 12..19` of base 100000, 40 episodes,
8 clusters, p/h = 4, each order's lead `min(4, max(0, L_t + xi_t))` (DA10); after onset every unit
has lead 3 plus noise, on leads 1 to 4 with probabilities (2, 27, 48, 22) / 99.

| Family (Holm within) | Test | Gemini 3.8 | Grok 4.20 |
|---|---|---|---|
| High margin, p/h = 19 | D1 hedge - gate | +596.6 b[322.8, 917.0], p < 0.0001, reject | +631.4 b[265.0, 1,084.6], p 0.00009, reject |
| | D2 hedge - arm 1 | +979.3 b[364.4, 1,702.7], p 0.00019, reject | +895.8 b[322.3, 1,569.0], p 0.00060, reject |
| | D3 hedge - content-free | +81.5 b[35.1, 138.1], p 0.00003, reject | -1.9 b[-74.6, 58.7], p 0.52, no |
| Low margin, p/h = 1 | D4 hedge - gate | +188.5 b[103.0, 287.5], p < 0.0001, reject | +45.2 b[10.1, 85.7], p 0.010, reject |
| Noisy lead, p/h = 4 | D5 hedge - arm 1 | +253.7 b[-141.5, 628.7], exact p 0.137, no | +187.2 b[-149.3, 469.2], exact p 0.148, no |

Readings (every contrast is net reward per episode; b[...] is the 95% seed-cluster interval):

- *High margin.* Five of the six tests reject. The text's value (D3) rejects with Gemini only.
  By the registered per-family readout the lead-time family supplies 95.6% and 97.2% of hedge -
  arm 1 (32 x 7,023.4 / (240 x 979.3); 32 x 6,532.6 / (240 x 895.8)), so at this ratio too the
  gain rests on lead-time shifts; this contradicts the post-hoc replay's reading (stage C, above)
  that at p/h = 19 it no longer does. Secondary: the gate is above arm 1 with Grok (+264.4
  b[1.9, 591.8]) and not distinguishable with Gemini (+382.7 b[-36.5, 866.5]); trusting the label
  alone (`lam = 0`) loses to the content-free control with Grok (-394.2 b[-852.9, -89.1]); acting
  at once loses 1,298.6 and 1,450.4 net (gross +1,496.1 and +1,586.1).
- *Null safety at p/h = 19* (registered secondary, margin -25 in currency, DA4): -22.0
  b[-64.6, 4.8] and -21.6 b[-64.6, 5.4]; non-inferiority is **not** established with either
  model. At the margin scaled by p/4 (-118.75; descriptive) it holds.
- *Low margin.* D4 rejects with both; it reflects the gate's own loss to arm 1 at this ratio
  (-178.5 b[-288.9, -78.8] and -40.8 b[-81.9, -5.6]); on gross, hedge - gate is -3.2 b[-20.4, 15.4]
  with Gemini and +24.6 b[7.7, 44.7] with Grok. Hedge - arm 1 over all 240 episodes: +10.1 b[-24.5, 51.8]
  (non-inferior at -25, barely) and +4.4 b[-27.6, 43.3] (not non-inferior); the text, read
  two-sided, is not distinguishable from zero (+5.6 b[-0.7, 13.3], -0.0 b[-5.5, 5.2]). Null
  safety holds at -25 (-3.5 b[-7.0, -0.8], -3.3 b[-6.7, -0.7]); at the scaled margin (-6.25)
  it does not (descriptive).
- *Across ratios* (registered secondary, per unit of p, `c19 / 19 - c1 / 1`, paired by episode):
  hedge - arm 1 +41.5 b[-0.8, 79.0] and +42.7 b[2.2, 79.9] (the per-unit gain rises from about
  10 and 4 at p/h = 1 to about 52 and 47 at p/h = 19; the rise is distinguishable with Grok only);
  hedge - gate -157.1 b[-253.9, -75.1] (falls, Gemini) and -12.0 b[-51.8, 25.5]; hedge -
  content-free -1.3 b[-7.7, 4.0] and -0.1 b[-4.9, 4.9]. In currency (dominated by the 19x scale):
  hedge - arm 1 +969.2 b[370.6, 1,677.0] and +891.4 b[328.5, 1,547.8]; hedge - gate +408.0
  b[148.0, 716.2] and +586.1 b[227.8, 1,029.3]; hedge - content-free +75.9 b[33.2, 127.9] and
  -1.9 b[-72.6, 56.2]. As a
  share of arm 1's net reward, hedge - arm 1 is 1.16% b[0.42, 2.05] and 1.06% b[0.38, 1.89] at
  p/h = 19, 0.34% and 0.15% (intervals include zero) at p/h = 1.
- *Noisy lead times.* D5 does not reject; the 8-cluster intervals are descriptive (DA11), and
  six of the eight unit gains are positive with each model. The plan expected D5 to reject if the
  content-free development gain carried over (DA12: +1,115 per shocked episode on the same
  throwaway units with deterministic leads, +506 with noisy leads before the clip). Descriptively
  (DA11, untested), the gain comes from the four two-period units (per shocked episode +788.9 and
  +634.1; share of the total gain above one, 1.24 and 1.36), while the one-period units lose on
  average (-155.0 and -166.8), units 14 and 18 losing (-1,038.25 and -144.5 with Gemini, -980.5
  and -154.5 with Grok); shift size is confounded with the baseline lead and with the null's fit.
  By condition (hedge - arm 1 per shocked episode): early +492.1 and +254.0, late +468.1 and
  +356.1, unreliable +321.6 and +338.6, no alert -14.0 and -14.0. Null exposure by baseline lead
  (4 twins each): 0.04 and 0.03 (lead 1), 0.65 and 0.65 (lead 2), against 0.08 and 1.59 for the
  content-free control. The hedge still beats the gate here: +251.3 b[16.6, 439.9] and +273.7
  b[50.9, 451.7] (secondary). Null safety holds (+0.4 and +1.3).
- *Cost:* $12.49 (Gemini 3.8 $4.78, $5.00, $0.49; Grok 4.20 $1.07, $1.07, $0.08).

Post hoc: the cost-ratio replay on stage C's episodes (above) had the same sign as most stage D
main-pool results, including the text's value with Gemini at p/h = 19 (+84 b[18, 166] there,
+81.5 registered), but not all: with Grok it had +19 where stage D registered -1.9, and it read
the p/h = 19 gain as no longer resting on lead-time shifts, which stage D contradicts. The replay
held stage C's answers fixed (DA5), so it was never a prediction.

## Stage B: development (no claim)

On the 120 spent pilot episodes, replaying arm 10's cached answers at no cost, the method scored
+141 to +156 net per episode against arm 1 on the six real-model banks available then (every
interval excluding zero) and +99 on the fixed-payload bank; +140 to +454 against arm 10 across all seven banks. The
live arm matches the replay on 120/120 episodes of the scripted bank.

## Stage A: model ladder on the pilot episodes

The registered 120 pilot episodes with all 21 rungs (`out/ladder.json`, `out/ladder.md`;
`gemini-3-flash-preview` was dropped under A1; `step-5-preview`, a slow reasoning model, finished
on 2026-09-29 at 13:41 UTC after the restarts recorded in A4). The hedge column is the
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
| step-3.5-flash | StepFun | 2026-01 | mid | 49/96 | 29 | -3,339 | -157 | +146 | 12/12, 1/12 | $0.37 |
| step-3.5-flash-2603 | StepFun | 2026-03 | mid | 50/96 | 26 | -3,269 | -141 | +155 | 12/12, 1/12 | $0.37 |
| step-3.7-flash | StepFun | 2026-05 | mid | 53/96 | 29 | -3,051 | -201 | +153 | 12/12, 1/12 | $1.72 |
| step-5-preview | StepFun | 2026-09 | large | 65/96 | 17 | -3,350 | -167 | +158 | 12/12, 1/12 | $1.71 |
| grok-build-0.1 | xAI | 2025-08 | small | 28/96 | 53 | -2,002 | +3 | +144 | 3/12, 0/12 | $1.28 |
| grok-4.20 | xAI | 2026-03 | mid | 53/96 | 20 | -2,624 | -172 | +154 | 9/12, 1/12 | $0.44 |

Readings. Perception ranges from 0/96 to 65/96 (`step-5-preview`): Llama 3.2 1B never produces a non-abstaining
`ShockSpec`, so every proposal falls back to arm 1, and 3B produces seven (all demand up), on
which acting at once loses 28 b[-54, -6]. The loss from acting at once ranges from zero to
-3,656 and, contrary to stage A's registered expectation (item 6) that it would grow as
perception falls, grows with how readily a model commits; across the rungs commitment and accuracy move
together (post hoc, `posthoc.json` `ladder`: r = 0.86; loss against either, r = -0.91), so
being right does not protect a model: Qwen 2.5 7B (2/96 right, 63 first-proposal abstentions)
loses 61, while Gemini 2.5 Flash-Lite (55/96 right, 5 abstentions) loses 3,656 and the most
accurate rung, `step-5-preview` (65/96), loses 3,350. The gate stays
between -300 and +3; contrary to stage A's registered expectation (item 6), its interval lies
below zero on two rungs, Gemini 2.5 Flash -294 b[-567, -45] and GPT-3.5 Turbo -60 b[-151, -1].
The hedge's development replay has point estimates of +107 to +158 on every rung (the interval
includes zero for Llama 3.1 8B); the content-free variant gains +136 on the same episodes.
Rung costs in `out/ladder.json` sum to $10.05 over the 21 rungs (StepFun's four, $4.17, are
shadow prices on a flat-rate plan), of which $2.34 is the real-content pilot's two banks, reused
here.

## Amendments and disclosures

- A1: `gemini-3-flash-preview` dropped (projected cost over cap); `grok-build-0.1` cap raised.
- A2: StepFun (four models, shadow-priced flat-rate plan) and OpenRouter (eleven open-weight or
  legacy models) added before any call on them.
- A3: StepFun shadow caps raised to $4 so `step-3.7-flash` runs.
- A4: the `step-5-preview` full run stopped on provider timeouts several times and was resumed
  from its cache under the same name and cap. From about 11:03 UTC its request timeout was 900 s,
  not the 180 s of the transport rules stage A adopts (a logged deviation; `runner.py`, frozen by
  hash in stages C and D, gained a `--timeout-s` flag defaulting to 180 s). No prompt, decoding or
  cached answer changed, but 13 of its 179 answers took 184 to 372 s on their first attempt and
  were accepted only because of the longer timeout. It finished at 13:41 UTC for $1.71 (shadow).
- C1: fresh layout reduced from 72 to 48 units before any call: the dev/cal alert bank has four
  accurate templates per family and split, and module 03's renderer refuses repeated texts.
- C2: an empty model echo is re-requested (up to three times, all attempts billed) instead of
  aborting; the `deepseek-v3` secondary run was re-run from its cache.
- C3: disclosures from an independent audit that reproduced every registered number: an interim
  look at the Grok primary run while Gemini's ran; outcomes computed (not read) on units `i = 0`
  by the pre-registration structural test; the C1 layout materialised early (no arms); the
  Gemini manifest's end-of-run SHA; Rule U applies to arm 10 only; the stage B guarantees
  restated (known null, exact prior constants, the gate as an analogy).
- C3 erratum (dated): arm 10's e-process does not certify the model's full spec; the evidence is
  largely shared with the hedge's, and what differs is its use.
- DA1 to DA12 (stage D, before any call): DA1 and DA7, the evaluator refuses any run but the
  registered one (pool, base, seeds, completeness); DA2, a relative tie tolerance, and the exact
  flip test decides D5; DA3, the two secondaries defined (`readout_d.py`); DA4, across-ratio
  changes read per unit of p, the -25 margin kept in currency; DA5, the replay-based
  expectations are not like-for-like; DA6, only the two-model evaluation is confirmatory; DA8,
  the true lead-time shift sizes (two periods from a baseline of 1, one from 2); DA9, handling of
  stopped runs; DA10, the stratum's leads clipped at 4 (a lead of 5 made arm 10's e-process
  raise); DA11, D5 read by sign consistency, with descriptive per-unit, per-shift, per-condition
  and per-baseline readouts; DA12, a comparator's provenance and the launch commands.
- Stage B tuned on the spent pilot episodes.

## What this does not show

The simulator's lead times are deterministic outside stage D's stratum, which makes a
lead-time shift easy to size from receipts; at p/h = 4 the gain rests on that family, and on
noisy lead times (8 units) the gain over arm 1 was not confirmed. Null safety at p/h = 19 is not
established at the registered margin. The exposure bound needs a known null; the demand e-processes estimate theirs from the pre-proposal prefix, and the Monte Carlo puts
the stopped exposure at 2.0 to 2.7 times the budget at early firings in the cells matched to the
null episodes (up to 3.2 in others). The regret bound covers the one-period surrogate, not realised multi-period
cost. No claim is made about language understanding; at p/h = 4 the text's net value over the
alert-timed content-free control is not distinguishable from zero, and at p/h = 19 it is
distinguishable with Gemini only.
