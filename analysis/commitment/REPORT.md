# Commitment study: report

Exploratory with respect to Gate 3: nothing here re-votes the registered pilot, and the
2026-09-23 kill-or-reframe decision stands. Within the study, stage C is a registered
confirmation: its method, hypotheses, tests and evaluator were committed and pushed
(`9d8e97f`, 2026-09-28) before any fresh-seed outcome existed. The plan and every amendment are
in `PLAN.md`; the frozen tree shows no drift. Numbers below come from `out/confirm.json` (stage
C), `out/dev/dev1.json` (stage B) and the run outputs under `out/` (stage A), unless a sentence
names another source.

## The method

**Certify-then-hedge** (`cth.py`). At each trigger firing (at most two per episode) a fixed,
action-aligned hypothesis set (demand up, demand down, lead-time shift, demand pulse) is
registered. Hypothesis `h` of firing `j` gets prior mass `a_j * w_jh`, with `a_j = 0.05 * 2^-j`
(the frozen alpha schedule) and `w_jh = lam / 4 + (1 - lam) * 1{h is the model's family}`; the
model's answer sets these weights and nothing else. Each hypothesis has its own module 05
e-process, started after the proposal and fed every later period. The posterior shock mass is
proportional to `a_j w_jh E_jh`; the shock's size comes from a working likelihood of the visible
data, never from the model's magnitude bin; and the order is the `p/(p+h)` quantile of the
posterior-predictive mixture, which equals arm 1's order exactly when no hypothesis is live.
Families module 04 cannot profitably act on (compound, shipment loss, transit pause) carry no
hypothesis. `lam = 0.25` is the method, `lam = 0` trusts the model's family alone, and `lam = 1`
is a content-free control that never calls the model.

Guarantees (proof sketches in `paper/sections/06_method_hedge.tex`, conditional on module 05's
null): for every stopping time the expected shock mass under the null is at most
`A = sum a_j <= 0.0375`, whatever the model outputs; the one-period newsvendor regret against arm
1 is at most the posterior odds times the value of the hypotheses; and the registered gate is,
up to one unit of threshold, this posterior's most-probable-hypothesis rule.

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
| Gemini 3.8 Flash | 93/170 | -2,046 | -131 | +179 | +9 | -3.2 b[-8.2, -0.1] |
| Grok 4.20 | 84/170 | -2,284 | -16 | +163 | -6 | +1.9 b[-1.7, 8.2] |
| DeepSeek-V3 | 78/170 | -1,478 | -39 | +170 | +1 | +1.4 b[-1.6, 6.5] |
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

**Language.** The hedge is within about ten of the content-free control on net with the primary
models and within -43 to +1 with the others. The model's family label mainly lowers commitment on
null episodes: mean summed shock mass on the 48 nulls is 0.83 for the content-free control,
0.45 to 0.52 for the hedge, and 0.04 to 0.18 when the model's family is trusted alone (`lam =
0`), which in turn costs net reward (-16 to -192 against content-free). On this simulator the
certified search, not the language, carries the gain.

**Cost.** Stage C provider cost $6.50: Gemini 3.8 $4.55, Grok 4.20 $1.09, GPT-3.5 $0.45,
DeepSeek-V3 $0.22, Gemini 2.5 Flash-Lite $0.13, Llama 3.1 8B $0.06.

## Stage B: development (no claim)

On the 120 spent pilot episodes, replaying arm 10's cached answers at no cost, the method scored
+141 to +156 net per episode against arm 1 on the six real-model banks available then (every
interval excluding zero) and +99 on the fixed-payload bank; +140 to +454 against arm 10 across all seven banks. The
live arm matches the replay on 120/120 episodes of the scripted bank.

## Stage A: model ladder on the pilot episodes

The registered 120 pilot episodes with every rung that has finished (`out/ladder.json`,
`out/ladder.md`; `gpt-oss-20b`, `step-3.7-flash` and `step-5-preview` were still running when
this was written, and `gemini-3-flash-preview` was dropped under A1). The hedge column is the
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
| step-3.5-flash | StepFun | 2026-01 | mid | 49/96 | 29 | -3,339 | -156 | +146 | 12/12, 1/12 | $0.37 |
| step-3.5-flash-2603 | StepFun | 2026-03 | mid | 50/96 | 26 | -3,269 | -141 | +154 | 12/12, 1/12 | $0.37 |
| grok-build-0.1 | xAI | 2025-08 | small | 28/96 | 53 | -2,002 | +3 | +144 | 3/12, 0/12 | $1.28 |
| grok-4.20 | xAI | 2026-03 | mid | 53/96 | 20 | -2,624 | -172 | +154 | 9/12, 1/12 | $0.44 |

Readings. Perception ranges from 0/96 (Llama 3.2 1B and 3B never produce a valid `ShockSpec`,
so every proposal falls back to arm 1) to 59/96. The loss from acting at once ranges from zero
to -3,656 and tracks how readily a model commits rather than how often it is right: Qwen 2.5 7B
(2/96 right, 63 first-proposal abstentions) loses 61, while Gemini 2.5 Flash-Lite (55/96 right,
5 abstentions) loses 3,656. The gate stays between -300 and +3. The hedge's development replay
gains +107 to +158 on every rung; the content-free variant gains +136 on the same episodes.
Stage A cost $2.87 for the Gemini and Grok rungs plus the OpenRouter and StepFun rungs in
`out/ladder.json`.

## Amendments and disclosures

- A1: `gemini-3-flash-preview` dropped (projected cost over cap); `grok-build-0.1` cap raised.
- A2: StepFun (four models, shadow-priced flat-rate plan) and OpenRouter (eleven open-weight or
  legacy models) added before any call on them.
- A3: StepFun shadow caps raised to $4 so `step-3.7-flash` runs.
- C1: fresh layout reduced from 72 to 48 units before any call: the dev/cal alert bank has four
  accurate templates per family and split, and module 03's renderer refuses repeated texts.
- C2: an empty model echo is re-requested (up to three times, all attempts billed) instead of
  aborting; the `deepseek-v3` secondary run was re-run from its cache.
- Disclosed: a structural smoke of the fresh-layout runner (scripted, units `i = 0`) before
  registration, read for counts only; stage B tuned on the spent pilot episodes.

## What this does not show

The simulator's lead times are deterministic, which makes a lead-time shift easy to size from
receipts; the gain rests on that family. One cost ratio (p/h = 4) was confirmed. The exposure
bound is conditional on module 05's null, whose demand parameters are estimated from the
pre-proposal prefix. The regret bound covers the one-period surrogate, not realised multi-period
cost. No claim is made about language understanding, and on these data language adds no net
value over the content-free control.
