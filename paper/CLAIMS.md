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
`sensitivity.json`'s `results.<run>.<ratio>`; `abl.<run>.<ratio>` to `ablation.json`'s
`results.<run>.<ratio>` (`ablation.py`, post hoc). `confirm_d.json` is the registered stage D
evaluation (`confirm_d.py`) and `readout_d.json` its registered secondaries (`readout_d.py`);
`d.<family>` refers to `confirm_d.json`'s `families.<family>` and `rd.<run>` to
`readout_d.json`'s `runs.<run>`. All of them store unrounded values; every integer in the
paper is rounded once from them or from `confirm.json` (never from a rounded value).

## 1. The fresh-seed confirmation (Abstract, Section VIII-B, Table I, Fig. 3)

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
| Fig. 3 values (perception, arm 8, arm 10, hedge vs arm 1, content-free band) | `paper/illustrate/data/fig3_models.csv`, written by `paper/illustrate/cth_figures.py` from `confirm.json` | established |
| Right family and direction among the 170 shocked episodes where the trigger fired | `runs.<run>.perception.arm8_spec_immediate` | established |

## 1b. Where the gain comes from, and the language (Section VIII-C, VIII-D)

| Claim | Evidence | Status |
|---|---|---|
| Gain by family (+1,286 / +1,177 lead time; +90 / +88 demand fall; +95 / +80 pulse; about -40 compound; about -3 loss) | `runs.<run>.by_family_net_cth_minus_arm1` (generator families 4, 2, 3, 6, 5) | established |
| Post hoc, every shocked family's interval excludes zero except the demand rise: -83 [-200, 21] (Gemini), -83 [-204, 26] (Grok) | `ph.<run>.gain_source["by_family_cth-arm1\|net"]["1"]` (-83.38 [-200.00, 21.09]; -83.44 [-203.88, 25.60]); families 2 to 6 exclude zero | post hoc |
| The 32 shocked lead-time episodes supply 96% of hedge - arm 1 | arithmetic on the registered per-family readout: 32 x 1285.53 / (240 x 178.47) = 0.960, Grok 0.963; `ph.<run>.gain_source.lead_time_episodes_share` | established |
| Without the lead-time units (episodes and twins): hedge - arm 1 +9 [-24, 43] and +7 [-25, 36]; hedge - gate +227 [82, 408] (Gemini), +58 [-1, 134] (Grok, not distinguishable from zero) | `ph.<run>.gain_source["cth-arm1\|net\|without_lead_time_units"]` (9.04 [-23.88, 42.52], 6.55 [-24.55, 36.08]), `["cth-arm10\|net\|without_lead_time_units"]` (226.81 [82.28, 408.13]; 58.09 [-0.76, 133.59]) | post hoc |
| The gate loses 1,057 per demand-rise episode with Gemini | `ph.fresh-gemini-3.8-flash.gain_source.by_family_net["arm10-arm1"]["1"]` (-1056.59) | post hoc |
| The stated lead-time size was wrong in 7 of 17 Gemini proposals (5 too large, 2 too small) and 6 of 11 Grok (all too large); true shifts were one or two periods (every family-4 unit moves to a lead of 3 from 1 or 2) | `ph.<run>.lead_time_proposals.first_proposal_vs_true_shift` ({right 10, too_large 5, too_small 2}; {5, 6, 0}); `collie/data/splits.py` `COMBO_A[4]`; PLAN.md DA8 | post hoc |
| The gate compiles medium as two periods | `collie/control/mapping.py` (medium: effective lead 3 against a reference of 1) | established |
| The gate commits a median of 11 periods after the lead-time proposal | `ph.<run>.lead_time_proposals.gate_delay_median` (11 and 11) | post hoc |
| Null commitment 0.83 (content-free), 0.52 and 0.46 (hedge), 0.18 and 0.06 (model family only) | `runs.<run>.exposure.<arm>.null_exposure_mean` | established |
| Cuts of 37% and 45%, intervals [33, 57]% and [42, 61]%, almost all on false-alert twins | `ph.<run>.null_exposure.all_twins` (ratio 0.631 [0.429, 0.668], 0.553 [0.392, 0.581], 10,000 valid draws); `false_alert_twins` vs `silent_twins` (the silent-twin ratio is not estimable: 3 clusters) | post hoc |
| No detectable change in null reward: -2 [-8, 2], +3 [-0.04, 8.4] | `ph.<run>.null_cth_minus_uniform` (-1.98 [-8.08, 1.71]; 3.15 [-0.042, 8.40]) | post hoc |
| Model family only (lambda = 0) costs net reward against content-free with four of the six models, from -83 [-169, -13] (Grok) to -192 (Llama 3.1 8B); not distinguishable with Gemini (-16 [-66, 27]) | `c["cth_llm-uniform\|net"]` (Grok -82.89 [-169.01, -13.43]; Gemini 2.5 Flash-Lite -115.48 [-240.75, -17.25]; GPT-3.5 Turbo -93.37 [-165.64, -32.14]; Llama 3.1 8B -191.94) | established |
| Post hoc, answers held fixed: lambda 0.5 and 0.75 not distinguishable from 0.25; committing at shock mass 1/2 (MAP) changes net reward by -56 [-97, -19] and -62 [-108, -21] at p/h = 4, -370 and -368 at 19 | `abl.<run>.<ratio>.variants.<vid>["minus_cth\|net"]` (lam0.5: -2.45 [-9.07, 4.19], +1.87 [-3.60, 8.49]; lam0.75: -4.25 [-13.71, 5.80], +4.79 [-5.14, 17.56]; map: -55.90 [-97.42, -19.03], -61.68 [-108.18, -21.21]; at 19: -370.23, -368.48); the method's own variant reproduces its registered records exactly (`checks`) | post hoc |
| Fig. 1 (overview): the alert text, six of the nine ShockSpec fields, the true offset (+1 period from period 14), the gate's switch at period 24 (eleven periods after the alert) and its compiled offset (+2), the hedge's estimated offset (+1, all posterior mass from period 18), +198 (hedge) and -2,358 (gate) | `paper/illustrate/data/fig1_episode.csv` and `fig1_episode_meta.json`, both written by `paper/illustrate/cth_figures.py` from `fresh-gemini-3.8-flash/` (`alerts.jsonl`, `proposals.jsonl`, `truth.jsonl`, `records.jsonl.gz`; true offset from the episode's realised lead times; compiled offset = `control_config.l_eff` minus the promised lead of 2); the hedge's offset posterior by a replay of the frozen arm that must reproduce its recorded total reward (16,601) exactly; `illustrate/overview.py` asserts every value it draws against these files | established |
| Fig. 1 (overview) episode was chosen post hoc: of the 32 lead-time episodes, the gate's third-worst and the hedge's tenth-lowest; the gate's family average +414 (post hoc in the caption; the hedge's +1,286 is the registered per-family readout) | arm 10 - arm 1 and arm 12 - arm 1 sorted over the 32 lead-time episodes in `records.jsonl.gz`; `ph.fresh-gemini-3.8-flash.gain_source.by_family_net["arm10-arm1"]["4"]` (414.31) | post hoc |

## 2. The pilots and the gate (Section I, Section VIII-A)

| Claim | Evidence | Status |
|---|---|---|
| Gate 3 read kill-or-reframe; headroom trigger = 2 of 6; detector gap -565.53 gross | `reports/pilot_report.md`; `prereg/deviations.md` 2026-09-23 entry | registered |
| Headroom is genuine (a clairvoyant clears 5% on the same two families); pulses, loss bursts and compound transit pauses end before an onset order lands | `analysis/kill_trigger_forensics.md` sections 1-2 | established |
| The detector gap is +2,306 on net | `analysis/kill_trigger_forensics.md` sections 3 and 5 | established |
| Real-content pilot: 59/96 and 53/96 right family | `analysis/real_content_pilot/out/evaluation.json` Q1 | established |
| Gate rarely acted on a false alarm with live models: 1 of 12 false-alert nulls each | same, Q6 `false_alert.arm10.any_active` | established |
| Gate activated 43% / 39% of right-family proposals, median 10 / 11 periods; refuted none of them (0 of 67, 0 of 74) | same, Q3 (`q3.arm10.right.refuted`) | established |
| Gate minus arm 1 -234 / -172 net; acting at once -2,549 / -2,624 | same, Q4 | established |
| Magnitude matched the truth bin in 8/96 and 7/96, a label mismatch rather than calibration: the provisional truth binning puts 80 of 96 shocks in low; the hidden alert-spec label of every non-distractor template is medium; no alert text states a size | same, Q1; `collie/data/alerts/templates/{dev,cal}.yaml` alert specs; `prereg/deviations.md` 2026-09-28 finding 2 | established |
| Excluded families: an onset clairvoyant gains under 1% on loss bursts or compound shocks once its foresight of demand noise is removed (gross -0.22% / -1.58%; net -0.19% / +0.67%) | `analysis/kill_trigger_forensics.md` sections 2.1-2.2 (clairvoyant at onset gross +1.96% / +0.72%, twin-differenced -0.22% / -1.58%; `analysis/forensics/out/q1_clairvoyant.json`); the compiled oracle's +0.00% on loss bursts is not evidence (dispatch-window bug, section 2.3) | established |

## 3. Model scale (Section VIII-F)

| Claim | Evidence | Status |
|---|---|---|
| 21 models from seven developers, all run | `analysis/commitment/endpoints.py` `LADDER` (22 rungs, one dropped under A1); `analysis/commitment/out/ladder.json` `rungs` (21), `missing_or_partial` (only the dropped rung) | established |
| Perception 0 to 65 of 96 (Step 5 Preview the highest; it finished under a 900 s request timeout (from about 11:03 UTC; 82 of its 179 answers) instead of the registered 180 s, a logged deviation that admitted 13 answers slower than 180 s on their first attempt; without it 0 to 59); Llama 3.2 1B never non-abstaining; Qwen 2.5 7B mostly abstains | `ladder.json` `family_right`, `abstain_first`, `arm8_arm1_net`; `out/ladder-*/proposals.jsonl` | established |
| Acting at once 0 (Llama 3.2 1B) to -3,656 (Gemini 2.5 Flash-Lite) | `ladder.json` `arm8_arm1_net` | established |
| Loss grows with commitment, contrary to stage A's registered expectation that it would grow as perception falls; commitment and accuracy move together (r = 0.86); the most accurate models lose among the most | `posthoc.json` `ladder.pearson` (committed_vs_family_right 0.862; loss vs committed -0.909, vs family_right -0.906) | post hoc |
| Gate between -300 and +3; at most 1 of 12 false alerts acted on | `ladder.json` `arm10_arm1_net`, `false_alert_active_arm10` | established |
| Gate's interval below zero on Gemini 2.5 Flash -294 [-567, -45] and GPT-3.5 Turbo -60 [-151, -1], contrary to stage A's registered expectation | `posthoc.json` `ladder.gate_interval_below_zero`; `PLAN.md` stage A item 6 | established |
| Hedge point estimates +107 to +158 on every model; content-free +136 | `ladder.json` `cth_arm1_net_dev`, `cth_uniform_arm1_net_dev` (from `out/dev/ladder_dev.json`) | development |

## 3b. Cost ratios and noisy lead times: stage D (Abstract, Section I, VII, VIII-E, X, XI)

Registered at `fae3714` with pre-run amendments DA1 to DA12 (`PLAN.md`); all six runs complete at
`a38eb64`. Here `d.` is the root of `confirm_d.json` (`d.families.<family>.tests["<contrast>|<model>"]`,
`d.families.<family>.holm`, `d.runs.<run>`) and `rd.` the root of `readout_d.json` (`rd.runs.<run>`,
`rd.across_ratios.<model>`).

| Claim | Evidence | Status |
|---|---|---|
| InventoryBench uses p/h = 1, 4 and 19 | `docs/env_contract.md` section 8.2 | established |
| New pool of 48 units at p/h = 19 and 1; eight lead-time units at p/h = 4 with the registered arrival law's noise, clipped at four periods; Holm within each family | `PLAN.md` stage D, DA10; `stage_d.py` `LEAD_RULE`; `out/<run>/stage_d.json` | registered |
| Before any stage D call, an independent audit of the registration led to dated amendments that changed no hypothesis, pool or cap | `PLAN.md` "Stage D amendments" (DA1 to DA12) | registered |
| p/h = 19: hedge - gate +597 [323, 917], +631 [265, 1,085]; hedge - arm 1 +979 [364, 1,703], +896 [322, 1,569]; hedge - content-free +82 [35, 138] (Gemini), -2 [-75, 59] (Grok); five of six tests reject | `d.families.high_margin.tests` (596.57 [322.85, 917.04]; 631.36 [265.01, 1084.56]; 979.26 [364.41, 1702.74]; 895.79 [322.32, 1568.97]; 81.53 [35.12, 138.10]; -1.95 [-74.61, 58.69]); `d.families.high_margin.holm` | established |
| p/h = 19 null episodes: -22 [-65, 5] with each model (not distinguishable from zero), so non-inferiority at -25 is not established (the p/4-scaled margin is reported in REPORT.md only, at both ratios) | `d.runs.d19-<model>.null_safety` (-21.96 [-64.65, 4.79]; -21.56 [-64.59, 5.35]); `rd.runs.d19-<model>.null_safety_scaled` (margin -118.75); `PLAN.md` DA4 | established |
| p/h = 1: hedge - gate +189 [103, 288], +45 [10, 86], both reject (the gate itself loses to arm 1: -178.5 [-288.9, -78.8], -40.8 [-81.9, -5.6]); hedge - arm 1 not distinguishable (+10 [-24.5, 51.8], just non-inferior at -25; +4 [-27.6, 43.3], not non-inferior); text two-sided not distinguishable; null episodes -3.5 [-7.0, -0.8], -3.3 [-6.7, -0.7] | `d.families.low_margin.tests`, `.holm`; `d.runs.d1-<model>.overall_non_inferiority` (10.06 [-24.53, 51.81], true; 4.41 [-27.59, 43.25], false), `.contrasts["cth-uniform\|net"]` (5.63 [-0.72, 13.31]; -0.03 [-5.47, 5.23]), `.contrasts["arm10-arm1\|net"]`, `.null_safety` (-3.48 [-6.96, -0.83]; -3.31 [-6.73, -0.69]) | established |
| Table II marks: registered tests reject (check) or not (cross) after Holm within each setting (D1, D2, D3 Gemini, D4 reject; D3 Grok, D5 do not); non-inferiority at -25 established over all p/h = 1 episodes with Gemini only, and not on p/h = 19 null episodes with either model | `d.families.<family>.holm`; `d.runs.d1-<model>.overall_non_inferiority.non_inferior` (true, false); `d.runs.d19-<model>.null_safety.non_inferior` (false, false) | established |
| Per unit of price, hedge - arm 1 rises from p/h = 1 to 19 with Grok, +43 [2, 80] (c19/19 - c1); with Gemini +41 [-1, 79], not distinguishable (per-unit gain about 10 and 4 at p/h = 1, 52 and 47 at 19) | `rd.across_ratios.<model>["cth-arm1"].per_unit_of_p` (41.48 [-0.83, 78.98]; 42.73 [2.21, 79.88]) | established |
| Noisy lead: hedge - arm 1 +254, +187, not confirmed (exact p 0.14, 0.15); descriptive 8-cluster intervals [-141, 629], [-149, 469]; six of eight unit gains positive with each model | `d.families.noisy_lead.tests` (253.65 [-141.48, 628.71], p_exact 0.13672; 187.20 [-149.33, 469.15], p_exact 0.14844) | established |
| Descriptively, the noisy-lead gain came from the four two-period units, while the one-period units lost on average (-155.0, -166.75 per shocked episode); shift size is confounded with the baseline lead (DA11) | `rd.runs.dsl-<model>.stratum.by_unit` (units 14 and 18 negative with both models) and `.by_shift` | established (descriptive, untested) |
| The post-hoc replay of stage C's episodes had the text's gain with Gemini at p/h = 19 at +84 [18, 166] | `sens.fresh-gemini-3.8-flash.19["cth-uniform\|net"]` (84.18 [17.57, 166.11]) | post hoc |
| Abstract and contributions (Section I): a second registered, exploratory stage; gains over the gate confirmed at the two other ratios, over the baseline at the higher one; the answer added 82 with Gemini, not detectably with Grok; non-inferiority on no-shock episodes not established at the higher ratio; noisy-lead gain not confirmed | the rows above | established |
| Conclusion: beat the gate at all three ratios and the baseline at the middle and highest | `confirm.json` holm_primary; `d.families.high_margin.holm`, `d.low_margin.holm` | established |

## 4. The method and its guarantees (Section VI)

| Claim | Evidence | Status |
|---|---|---|
| Mechanism as described (hypothesis set, prior, posterior, sizing with five pseudo-observations and a Gaussian lead-time likelihood, mixture quantile) | `analysis/commitment/cth.py` (hash-frozen in stage C) | established |
| h-hat is none on abstention, a parse failure after one repair, or a family and direction outside H; the pulse hypothesis is upward only | `cth.py` `hypothesis_key`, `_ask` | established |
| Only hypotheses whose e-process cannot be built or meets an impossible observation are dropped; closed windows are kept | `cth.py` `_build`, `_feed`, `_components` | established |
| With no live hypothesis the order equals arm 1's | `tests/test_commitment.py::test_without_a_hypothesis_the_arm_orders_exactly_as_arm_1` | established |
| Live arm equals the development replay (scripted content) on 120/120 episodes | stage B check recorded in `analysis/commitment/REPORT.md` | established |
| Theorem 1 (gate activation: Ville's inequality and a union bound under the registered no-change null) | `paper/sections/06_method_verify.tex` | established (proof) |
| Theorem 2 (exposure, stopping times of the decision filtration) and Theorem 3 (odds regret), proof sketches via the augmented budget process, under a known null and the registered arrival law | `paper/sections/06_method_hedge.tex` | established (proof) |
| Where the premise holds no simulated cell is clearly above a bound; with deterministic delays a named lead-time hypothesis reaches 1.24 times its per-decision budget; with the plug-in null, in the matched cells at period 10, E[Pi_sigma] is 2.0 to 2.7 times A and P(sup >= 1/2) 2.3 to 3.7 times its bound, up to 3.2 and 4.7 in other cells | `analysis/commitment/out/mc_exposure.md` and `.json` (`mc_exposure.py`) | established (simulation) |
| With one hypothesis and lambda = 0 the gate's threshold is a posterior-odds rule of the same form (an analogy, not an identity: for a named demand or pulse hypothesis the e-process is the same, and for a lead-time shift the magnitude only selects the delay tilt; the gate acts all at once on the compiled stated magnitude, the hedge sizes the shock from the data) | algebra in Section VI; `collie/verify/demand.py` (`from_spec`, `for_level_change` mix over `MAGNITUDE_SETS`), `collie/verify/arrival.py` (`_changed_laws_for`: low and medium one tilt, high another); `cth.py` canonical specs | established |
| Against the content-free arm a wrong or missing family costs exactly log(1/lambda) = log 4 nats; the named one saves log(lambda + (1 - lambda)|H|) = log 3.25 | algebra in Section VI; weights in `cth.py` | established |
| The model's answer sets the prior weights and the named hypothesis's onset window, nothing else | `cth.py` (`_build`, `_maybe_propose`) | established |
| Crediting each period's shock mass to its leading hypothesis, pulse-led periods carry 0.69 of the content-free control's 0.83 and 0.32 / 0.38 of the hedge's 0.52 / 0.46, so most of the label's cut is that mass | `ph.<run>.null_exposure.by_top_hypothesis.<arm>.pulse_up` (0.6944; 0.3235, 0.3767), `runs.<run>.exposure.<arm>.null_exposure_mean` (0.8285; 0.5231, 0.4583); `posthoc.py` `exposure_by_hypothesis` | post hoc |

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
