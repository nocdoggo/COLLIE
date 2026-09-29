# Claims audit

Every substantive claim the camera-ready draft makes, its evidence, and its status. A claim is
substantive if a reviewer could ask us to prove it: a number, a guarantee, a statement that a
property is enforced, or a statement about prior work.

Status values:

- **established**: checked against code, a committed output, or a registered evaluation.
- **registered**: a design decision recorded in the repository (a plan, a freeze, a deviation).
- **post hoc**: computed after the stage C results were seen, on its episodes; the paper labels
  it post hoc and never presents it as a confirmed result.
- **development**: measured on the spent pilot episodes during method development; reported in
  the paper only with that label and never as a claim.
- **verified externally**: a reference or public fact checked at its source.

Paths are relative to the repository root. `confirm.json` is
`analysis/commitment/out/confirm.json` (the registered stage C evaluation); `runs.<run>` below
refers to its `runs` object, and `c[...]` to `runs.<run>.contrasts[...]`. `posthoc.json` and
`sensitivity.json` are the post-hoc readouts in the same directory (`posthoc.py`,
`sensitivity.py`); `ph.<run>` refers to `posthoc.json`'s `runs.<run>`, and `sens.<run>.<ratio>` to
`sensitivity.json`'s `results.<run>.<ratio>`. Both store unrounded values; every integer in the
paper is rounded once from them or from `confirm.json` (never from a rounded value).

## 1. The fresh-seed confirmation (Abstract, Section VIII-B, Table I, Fig. 2)

| Claim | Evidence | Status |
|---|---|---|
| 240 fresh episodes, 48 seed clusters, 192 shocked and 48 null | `runs.fresh-*.episodes`, `.clusters`; `analysis/commitment/episodes.py` with `--n-per-family 8` (amendment C1) | established |
| Registered before its live runs; exploratory relative to the project's preregistration | `analysis/commitment/PLAN.md` stage C; `9d8e97f` precedes every live `fresh-*` invocation (`out/fresh-*/invocations.jsonl`); `confirm.json` `analysis_class` | registered |
| Disclosed: structural test computed outcomes on 6 of 48 clusters beforehand; both primary tests evaluated on one model's run while the other ran; further departures, none changing a run, rule or number | `PLAN.md` amendment C3 | registered |
| Without the six structural-test clusters: +329, +188, +163, +145; largest p 0.0024 | `ph.<run>.without_structural_test_clusters` (328.59, 187.75, 162.81, 145.33; p 0.00242) | post hoc |
| Hedge minus gate +309 (Gemini), +179 (Grok) | `c["cth-arm10\|net"]`: 309.12 [172.57, 472.10]; 178.76 [87.39, 280.91] | established |
| Hedge minus arm 1 +178 (Gemini), +163 (Grok) | `c["cth-arm1\|net"]`: 178.47 [54.82, 325.53]; 162.88 [47.75, 299.73] | established |
| All four primary tests reject under Holm; largest p = 0.0031 | `confirm.json` `holm_primary` | established |
| Null non-inferiority (margin -25) with both primary models; Gemini -3.2 [-8.2, -0.1], Grok +1.9 [-1.7, 8.2] | `runs.<run>.null_safety` (its `p_one_sided` tests superiority, not non-inferiority) | established |
| Gemini null loss from the 24 false-alert twins: -6.4 [-16.1, -0.3], worst -105; silent twins rarely trigger | `ph.fresh-gemini-3.8-flash.null_safety_split`; `null_exposure.silent_twins.episodes_uniform_zero` (21 of 24) | post hoc |
| Among Table I's arms, acting at once is best on gross and worst on net; hedge - at once changes sign | `c["arm8-arm1\|*"]`, `c["cth-arm8\|*"]` (both endpoints' intervals exclude zero); the detector control has higher gross than arm 8 (`records.jsonl.gz`), hence "among Table I's arms" | established |
| Gate minus arm 1 -131 [-316, 28] and -16 [-104, 75] | `c["arm10-arm1\|net"]` | established |
| Acting at once minus arm 1 -2,046 [-2,612, -1,478] and -2,284 [-2,849, -1,710] net; +501 gross | `c["arm8-arm1\|net"]` (-2045.80, -2283.53), `c["arm8-arm1\|gross"]` (500.75, 501.25) | established |
| Acting at once lost 1,478 to 3,181 across six models | `c["arm8-arm1\|net"]` over the six runs (-1477.70 DeepSeek to -3180.87 Flash-Lite) | established |
| Content-free minus arm 1 +169 [48, 312] | `c["uniform-arm1\|net"]` (identical in every run: no model call) | established |
| Hedge minus content-free +9 [-5, 24] (Gemini), -6 [-29, 11] (Grok); -43 to 0 for the four secondary models, intervals below zero for Llama 3.1 8B [-78, -15] and GPT-3.5 Turbo [-35, -0.4] | `c["cth-uniform\|net"]` (DeepSeek 0.47, Llama -43.43) | established |
| The content-free control is timed by the same alerts (no model call) | `analysis/commitment/arms.py` (same `alert_or_detector` trigger); no `ctrl_cth_uniform` row in any ledger | established |
| Gross column of Table I | `c["...\|gross"]` means (85.05, 138.95, 279.95, 261.75, 194.9, 122.8, 500.75, 501.25, 270.18, 9.77, -8.43) | established |
| Four secondary models: every hedge-vs-gate and hedge-vs-arm-1 interval excludes zero | `c["cth-arm10\|net"]`, `c["cth-arm1\|net"]` for the four secondary runs | established |
| Fig. 2 values (perception, arm 8, arm 10, hedge vs arm 1, content-free band) | `paper/illustrate/data/fig2_models.csv`, written by `paper/illustrate/cth_figures.py` from `confirm.json` | established |
| Right family and direction among the 170 shocked episodes where the trigger fired | `runs.<run>.perception.arm8_spec_immediate` | established |

## 1b. Where the gain comes from, and the language (Section VIII-C, VIII-D)

| Claim | Evidence | Status |
|---|---|---|
| Gain by family (+1,286 / +1,177 lead time; +90 / +88 demand fall; +95 / +80 pulse; -83 demand rise; about -40 compound; about -3 loss) | `runs.<run>.by_family_net_cth_minus_arm1` (generator families 4, 2, 3, 1, 6, 5) | established |
| The 32 shocked lead-time episodes supply 96% of hedge - arm 1 | arithmetic on the registered per-family readout: 32 x 1285.53 / (240 x 178.47) = 0.960, Grok 0.963; `ph.<run>.gain_source.lead_time_episodes_share` | established |
| Without the lead-time units (episodes and twins): hedge - arm 1 +9 [-24, 43] and +7 [-25, 36]; hedge - gate +227 [82, 408] (Gemini), +58 [-1, 134] (Grok) | `ph.<run>.gain_source["cth-arm1\|net\|without_lead_time_units"]` (9.04 [-23.88, 42.52], 6.55 [-24.55, 36.08]), `["cth-arm10\|net\|without_lead_time_units"]` | post hoc |
| The gate loses 1,057 per demand-rise episode with Gemini | `ph.fresh-gemini-3.8-flash.gain_source.by_family_net["arm10-arm1"]["1"]` (-1056.59) | post hoc |
| Models oversized lead-time shifts: medium or high in 11 of 17 Gemini proposals and 11 of 11 Grok; every true shift one period (low) | `ph.<run>.lead_time_proposals.first_proposal_magnitude`, `true_magnitudes` | post hoc |
| The gate compiles medium as two periods | `collie/control/mapping.py` (medium: effective lead 3 against a reference of 1) | established |
| The gate commits a median of 11 periods after the lead-time proposal | `ph.<run>.lead_time_proposals.gate_delay_median` (11 and 11) | post hoc |
| Null commitment 0.83 (content-free), 0.52 and 0.46 (hedge), 0.18 and 0.06 (model family only) | `runs.<run>.exposure.<arm>.null_exposure_mean` | established |
| Cuts of 37% and 45%, intervals [33, 57]% and [42, 61]%, almost all on false-alert twins | `ph.<run>.null_exposure.all_twins` (ratio 0.631 [0.429, 0.668], 0.553 [0.392, 0.581], 10,000 valid draws); `false_alert_twins` vs `silent_twins` (the silent-twin ratio is not estimable: 3 clusters) | post hoc |
| No detectable change in null reward: -2 [-8, 2], +3 [-0.04, 8.4] | `ph.<run>.null_cth_minus_uniform` (-1.98 [-8.08, 1.71]; 3.15 [-0.042, 8.40]) | post hoc |
| Model family only: -83 [-169, -13] (Grok), -192 (Llama 3.1 8B) against content-free; -16 [-66, 27] (Gemini) | `c["cth_llm-uniform\|net"]` | established |
| Fig. 1 episode: +198 (hedge) and -2,358 (gate); model said "medium"; true shift one period; onset 14 | `paper/illustrate/data/fig1_episode.csv` (onset read from `truth.jsonl`); `fresh-gemini-3.8-flash/proposals.jsonl` for `dev/f4/s4100006/early_accurate` | established |
| Fig. 1 episode was chosen: the gate's third-worst of the 32 lead-time episodes; family averages +1,286 (hedge) and +414 (gate) | arm 10 - arm 1 sorted over family 4 in `records.jsonl.gz`; `ph.fresh-gemini-3.8-flash.gain_source.by_family_net["arm10-arm1"]["4"]` (414.31) | post hoc |

## 2. The pilots and the gate (Section I, Section VIII-A)

| Claim | Evidence | Status |
|---|---|---|
| Gate 3 read kill-or-reframe; headroom trigger = 2 of 6; detector gap -565.53 gross | `reports/pilot_report.md`; `prereg/deviations.md` 2026-09-23 entry | registered |
| Headroom is genuine (a clairvoyant clears 5% on the same two families); pulses, loss bursts and compound transit pauses end before an onset order lands | `analysis/kill_trigger_forensics.md` sections 1-2 | established |
| The detector gap is +2,306 on net | `analysis/kill_trigger_forensics.md` sections 3 and 5 | established |
| Real-content pilot: 59/96 and 53/96 right family | `analysis/real_content_pilot/out/evaluation.json` Q1 | established |
| Gate rarely acted on a false alarm with live models: 1 of 12 false-alert nulls each | same, Q6 `false_alert.arm10.any_active` | established |
| Gate activated 43% / 39% of right-family proposals, median 10 / 11 periods | same, Q3 | established |
| Gate minus arm 1 -234 / -172 net; acting at once -2,549 / -2,624 | same, Q4 | established |
| Magnitude right 8/96 and 7/96; templates label every non-distractor shock medium | same, Q1; `collie/data/alerts/templates/{dev,cal}.yaml` alert specs | established |
| Excluded families: the compiled oracle gained nothing on loss bursts or compound shocks in the pilot | `analysis/kill_trigger_forensics.md` section 2 (compiled oracle gross +0.00%, +0.01%) | established |

## 3. Model scale (Section VIII-F)

| Claim | Evidence | Status |
|---|---|---|
| 21 models from seven developers; 20 finished at writing | `analysis/commitment/endpoints.py` `LADDER` (22 rungs, one dropped under A1); `analysis/commitment/out/ladder.json` `rungs`, `missing_or_partial` | established |
| Perception 0 to 59 of 96; Llama 3.2 1B never non-abstaining; 3B seven demand-up specs, arm 8 -28 [-54, -6]; Qwen 2.5 7B mostly abstains | `ladder.json` `family_right`, `abstain_first`, `arm8_arm1_net`; `out/ladder-*/proposals.jsonl` | established |
| Acting at once 0 (Llama 3.2 1B) to -3,656 (Gemini 2.5 Flash-Lite) | `ladder.json` `arm8_arm1_net` | established |
| Loss grows with commitment; commitment and accuracy move together (r = 0.86); the most accurate models lose among the most | `posthoc.json` `ladder.pearson` (committed_vs_family_right 0.859; loss vs committed -0.905, vs family_right -0.901) | post hoc |
| Gate between -300 and +3; at most 1 of 12 false alerts acted on | `ladder.json` `arm10_arm1_net`, `false_alert_active_arm10` | established |
| Gate's interval below zero on Gemini 2.5 Flash -294 [-567, -45] and GPT-3.5 Turbo -60 [-151, -1], contrary to stage A's registered expectation | `posthoc.json` `ladder.gate_interval_below_zero`; `PLAN.md` stage A item 6 | established |
| Hedge point estimates +107 to +158 on every model; content-free +136 | `ladder.json` `cth_arm1_net_dev`, `cth_uniform_arm1_net_dev` (from `out/dev/ladder_dev.json`) | development |

## 3b. Cost ratio (Section VIII-E)

| Claim | Evidence | Status |
|---|---|---|
| InventoryBench uses p/h = 1, 4 and 19 | `docs/env_contract.md` section 8.2 | established |
| The replay ran p/h = 1, 2, 9 and 19; it reproduces every registered record at p/h = 4; no call at any ratio lacked a recorded answer | `sensitivity.json` `reproduction_at_registered_ratio`, `replay` | established |
| The prompt shows margin, inventory position and order and arrival history | `collie/spec/prompt.py` `build_prompt` | established |
| Hedge - gate +85 to +722 over ratios and models, every interval above zero | `sens.<run>.<ratio>["cth-arm10\|net"]` (min 85.46 Grok p/h 1, max 722.34 Gemini p/h 19) | post hoc |
| Hedge - arm 1 at 1: +16 [-14, 47], +10 [-18, 40]; at 19: +1,056 [398, 1,850], +991 [376, 1,739]; without the lead-time units at 19: +125 [43, 227], +121 [38, 224] | `sens.<run>.<ratio>["cth-arm1\|net"]`, `["cth-arm1\|net\|without_lead_time_units"]` | post hoc |
| As a share of arm 1's net: 0.5% and 0.3% at 1, 1.1% and 1.0% at 4, 1.2% at 19 | `sens.<run>.<ratio>["cth-arm1\|net\|share_of_arm1_net"]` (0.00532, 0.00343; 0.01128, 0.01029; 0.01250, 0.01173) | post hoc |
| Hedge - content-free with Gemini: +47 [6, 97] at 9, +84 [18, 166] at 19; with Grok -5 [-10, -0.02] at 1, intervals including zero elsewhere | `sens.<run>.<ratio>["cth-uniform\|net"]` | post hoc |

## 4. The method and its guarantees (Section VI)

| Claim | Evidence | Status |
|---|---|---|
| Mechanism as described (hypothesis set, prior, posterior, sizing with five pseudo-observations and a Gaussian lead-time likelihood, mixture quantile) | `analysis/commitment/cth.py` (hash-frozen in stage C) | established |
| h-hat is none on abstention, a parse failure after one repair, or a family and direction outside H; the pulse hypothesis is upward only | `cth.py` `hypothesis_key`, `_ask` | established |
| Only hypotheses whose e-process cannot be built or meets an impossible observation are dropped; closed windows are kept | `cth.py` `_build`, `_feed`, `_components` | established |
| With no live hypothesis the order equals arm 1's | `tests/test_commitment.py::test_without_a_hypothesis_the_arm_orders_exactly_as_arm_1` | established |
| Live arm equals the development replay (scripted content) on 120/120 episodes | stage B check recorded in `analysis/commitment/REPORT.md` | established |
| Theorem 1 (exposure, stopping times of the decision filtration) and Theorem 2 (odds regret), proof sketches via the augmented budget process, under a known null and the registered arrival law | `paper/sections/06_method_hedge.tex` | established (proof) |
| Where the premise holds no simulated cell is clearly above a bound; with deterministic delays a named lead-time hypothesis reaches 1.24 times its per-decision budget; with the plug-in null, in the matched cells at period 10, E[Pi_sigma] is 2.0 to 2.7 times A and P(sup >= 1/2) 2.3 to 3.7 times its bound, up to 3.2 and 4.7 in other cells | `analysis/commitment/out/mc_exposure.md` and `.json` (`mc_exposure.py`) | established (simulation) |
| With one hypothesis and lambda = 0 the gate's threshold is a posterior-odds rule of the same form (an analogy: the gate certifies the full spec, the hedge a canonical one) | algebra in Section VI; `cth.py` canonical specs vs `collie/verify/arrival.py` alternatives | established |
| Against the content-free arm a wrong or missing family costs exactly log(1/lambda) = log 4 nats; the named one saves log(lambda + (1 - lambda)|H|) = log 3.25 | algebra in Section VI; weights in `cth.py` | established |
| The model's answer sets the prior weights and the named hypothesis's onset window, nothing else | `cth.py` (`_build`, `_maybe_propose`) | established |
| The content-free control's null mass sits mostly on the pulse hypothesis (0.69 of 0.83) | `ph.<run>.null_exposure.by_top_hypothesis.ctrl_cth_uniform.pulse_up` | post hoc |

## 5. Testbed (Section II)

| Claim | Evidence | Status |
|---|---|---|
| 1,320 instances; 720 synthetic, 600 real | `docs/env_contract.md` section 1 | established |
| Max abs diff 0.0 over 648 comparisons | `reports/equivalence_report.md` | established |
| All 1,320 published order sequences reproduced; 0.4447 legacy vs 0.5208 submission path; 440 lost-shipment instances | `reports/arm1_or_baseline.md`; `docs/env_contract.md` section 8.5 | established |
| Shock families, onsets 14 to 22 of 50, demand N(100, 25), p = 4, h = 1 | `collie/data/families/`, `collie/data/splits.py`, `collie/data/writer.py` defaults | established |

## 6. Prior work (Sections I and IX)

Rewritten with Section IX (branch `method/cth-support`); each of the 14 new entries was checked
against arXiv, Crossref or PMLR at its source. Section I no longer claims that retailers use
language models; it says they are being proposed, citing InventoryBench.
