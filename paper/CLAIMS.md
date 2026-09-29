# Claims audit

Every substantive claim the camera-ready draft makes, its evidence, and its status. A claim is
substantive if a reviewer could ask us to prove it: a number, a guarantee, a statement that a
property is enforced, or a statement about prior work.

Status values:

- **established**: checked against code, a committed output, or a registered evaluation.
- **registered**: a design decision recorded in the repository (a plan, a freeze, a deviation).
- **development**: measured on the spent pilot episodes during method development; reported in
  the paper only with that label and never as a claim.
- **verified externally**: a reference or public fact checked at its source.

Paths are relative to the repository root. `confirm.json` is
`analysis/commitment/out/confirm.json` (the registered stage C evaluation); `runs.<run>` below
refers to its `runs` object, and `c[...]` to `runs.<run>.contrasts[...]`.

## 1. The registered confirmation (Abstract, Section VIII-B, Table I, Fig. 2)

| Claim | Evidence | Status |
|---|---|---|
| 240 fresh episodes, 48 seed clusters, 192 shocked and 48 null | `runs.fresh-*.episodes`, `.clusters`; `analysis/commitment/episodes.py` with `--n-per-family 8` (amendment C1) | established |
| Registered before any outcome: method frozen by hash, hypotheses, tests, evaluator | `analysis/commitment/PLAN.md` stage C; commit `9d8e97f` precedes every `fresh-*` run (`out/fresh-*/invocations.jsonl` timestamps) | registered |
| Hedge minus gate +309 (Gemini), +179 (Grok), net per episode, with intervals | `c["cth-arm10\|net"]` for `fresh-gemini-3.8-flash` (309.1, [172.6, 472.1]) and `fresh-grok-4.20` (178.8, [87.4, 280.9]) | established |
| Hedge minus arm 1 +179 (Gemini), +163 (Grok) | `c["cth-arm1\|net"]`: 178.5 [54.8, 325.5]; 162.9 [47.8, 299.7] | established |
| All four primary tests reject under Holm; largest p = 0.0031 | `confirm.json` `holm_primary` | established |
| Null non-inferiority (margin -25) with both primary models; Gemini -3.2 [-8.2, -0.1], Grok +1.9 [-1.7, 8.2] | `runs.<run>.null_safety` | established |
| Gate minus arm 1 -131 [-316, 28] and -16 [-104, 75] | `c["arm10-arm1\|net"]` | established |
| Acting at once minus arm 1 -2,046 and -2,284 net; +501 gross | `c["arm8-arm1\|net"]`, `c["arm8-arm1\|gross"]` | established |
| Content-free minus arm 1 +169 [48, 312] | `c["uniform-arm1\|net"]` (identical in every run: no model call) | established |
| Hedge minus content-free +9 [-5, 24] (Gemini), -6 [-29, 11] (Grok); -43 to +1 for the four secondary models | `c["cth-uniform\|net"]` | established |
| Gross column of Table I | `c["...\|gross"]` means | established |
| Four secondary models: every hedge-vs-gate and hedge-vs-arm-1 interval excludes zero | `c["cth-arm10\|net"]`, `c["cth-arm1\|net"]` for the four secondary runs | established |
| Fig. 2 values (perception, arm 8, arm 10, hedge vs arm 1) | `paper/illustrate/data/fig2_models.csv`, written by `paper/illustrate/cth_figures.py` from `confirm.json` | established |
| Right family and direction among the 170 shocked episodes where the trigger fired | `runs.<run>.perception.arm8_spec_immediate` | established |
| Gain by family (+1,286 / +1,177 lead time; +90 / +88 demand fall; +95 / +80 pulse; -83 demand rise; about -40 compound; about -3 loss) | `runs.<run>.by_family_net_cth_minus_arm1` (generator families 4, 2, 3, 1, 6, 5) | established |
| Null commitment 0.83 (content-free), 0.45 to 0.52 (hedge), 0.04 to 0.18 (model family only) | `runs.<run>.exposure.<arm>.null_exposure_mean` | established |
| Model family only costs -16 and -83 (primary), -192 (Llama 3.1 8B) against content-free | `c["cth_llm-uniform\|net"]` | established |
| Fig. 1 episode: +198 (hedge) and -2,358 (gate); model said "medium"; true shift +1 | `paper/illustrate/data/fig1_episode.csv`; `analysis/commitment/out/fresh-gemini-3.8-flash/proposals.jsonl` and `truth.jsonl` for `dev/f4/s4100006/early_accurate`; generator params via `episodes.fresh_units` (lead 2 to 3) | established |
| Stage C cost | `out/fresh-*/spend_log.jsonl` | established |

## 2. The pilots and the gate (Section I, Section VIII-A)

| Claim | Evidence | Status |
|---|---|---|
| Gate 3 read kill-or-reframe; headroom trigger = 2 of 6; detector gap -565.53 gross | `reports/pilot_report.md`; `prereg/deviations.md` 2026-09-23 entry | registered |
| Headroom is genuine (a clairvoyant clears 5% on the same two families) | `analysis/kill_trigger_forensics.md` section 2 | established |
| The detector gap is +2,306 on net | `analysis/kill_trigger_forensics.md` sections 3 and 5 | established |
| Real-content pilot: 59/96 and 53/96 right family; fixed payload 16/96 | `analysis/real_content_pilot/out/evaluation.json` Q1 | established |
| Gate activated 43% / 39% of right-family proposals, median 10 / 11 periods | same, Q3 | established |
| Gate minus arm 1 -234 / -172 net; acting at once -2,549 / -2,624 | same, Q4 | established |
| Magnitude right 8/96 and 7/96; templates label every non-distractor shock medium | same, Q1; `collie/data/alerts/templates/{dev,cal}.yaml` alert specs | established |

## 3. Model scale (Section VIII-E)

| Claim | Evidence | Status |
|---|---|---|
| 21 models from seven developers; 18 finished at writing | `analysis/commitment/endpoints.py` `LADDER` (22 rungs, one dropped under A1); `analysis/commitment/out/ladder.json` `rungs`, `missing_or_partial` | established |
| Perception 0 to 59 of 96; Llama 3.2 1B/3B never valid; Qwen 2.5 7B mostly abstains | `ladder.json` `family_right`, `abstain_first`; `out/ladder-*/proposals.jsonl` parse flags | established |
| Acting at once 0 to -3,656; tracks commitment, not accuracy | `ladder.json` `arm8_arm1_net` with `family_right` and `abstain_first` | established (descriptive) |
| Gate between -300 and +3; at most 1 of 12 false alerts acted on | `ladder.json` `arm10_arm1_net`, `false_alert_active_arm10` | established |
| Hedge +107 to +158 on every model | `ladder.json` `cth_arm1_net_dev` (from `out/dev/ladder_dev.json`) | development |

## 4. The method and its guarantees (Section VI)

| Claim | Evidence | Status |
|---|---|---|
| Mechanism as described (hypothesis set, prior, posterior, sizing, mixture quantile) | `analysis/commitment/cth.py` (hash-frozen in stage C) | established |
| With no live hypothesis the order equals arm 1's | `tests/test_commitment.py::test_without_a_hypothesis_the_arm_orders_exactly_as_arm_1` | established |
| Live arm equals the development replay (scripted content) on 120/120 episodes | stage B check recorded in `analysis/commitment/REPORT.md` | established |
| Theorem 1 (exposure) and Theorem 2 (odds regret), proof sketches | `paper/sections/06_method_hedge.tex`; Monte Carlo check `analysis/commitment/out/mc_exposure.json` (when committed) | established (proof); pending MC |
| Gate = most-probable-hypothesis rule up to one unit of threshold | algebra in Section VI | established |
| Wrong family costs at most log(|H|/lambda) = log 16 nats | algebra in Section VI | established |

## 5. Testbed (Section II)

| Claim | Evidence | Status |
|---|---|---|
| 1,320 instances; 720 synthetic, 600 real | `docs/env_contract.md` section 1 | established |
| Max abs diff 0.0 over 648 comparisons | `reports/equivalence_report.md` | established |
| All 1,320 published order sequences reproduced; 0.4447 legacy vs 0.5208 submission path; 440 lost-shipment instances | `reports/arm1_or_baseline.md`; `docs/env_contract.md` section 8.5 | established |
| Shock families, onsets 14 to 22 of 50, demand N(100, 25), p = 4, h = 1 | `collie/data/families/`, `collie/data/splits.py`, `collie/data/writer.py` defaults | established |

## 6. Prior work (Sections VII and IX)

Maintained with the related-work rewrite; each citation is checked at its source.
