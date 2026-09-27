# Kill-trigger forensics: the 2026-09-23 pilot's kill-or-reframe verdict

**Status: EXPLORATORY.** This document does not re-run or re-vote Gate 3. It does not change or
re-derive any registered threshold, criterion, endpoint, or frozen file. Anything below that points
forward is a **reframe candidate**: it carries no weight until the team gives it a new, dated
registration.

| | |
|---|---|
| Branch / base | `analysis/kill-trigger-forensics`, off `main` at `44b3f45` (module 07 merge) |
| Date | 2026-09-26 |
| Inputs | `reports/pilot_records.jsonl` (1,752 episode records: 120 episodes; 15 arms on each of the 96 shocked episodes, 13 on each of the 24 nulls) and `reports/pilot_truth.jsonl` |
| Provenance of the inputs | Scripted transport (`scripted-fake-7b` on all 18,882 call records, one fixed demand-up/medium ShockSpec answer) and demo alerts, run through the real frozen arms, parser, compiler, verifier and ledger. All 1,752 records are stamped `confirmatory` anyway (§6). |
| Counterfactuals | The pilot is regenerated deterministically through the frozen `tools/run_arms.pilot_instances`, with the arms built exactly as `run_ladder` builds them. Before any counterfactual is used, every regenerated trajectory is asserted bit-for-bit equal to its stored record (96/96 shocked episodes for arm 1 and the oracle; 120/120 for arm 10 and the control). |
| Intervals | The registered construction is shown next to a seed-cluster bootstrap (B = 10,000, seed 20260927). The bootstrap resamples whole seeds: a seed's four information conditions and its null twins form one cluster, giving 24 clusters. |
| Code | `analysis/forensics/` (exploratory package; reads no credential; writes only under `analysis/forensics/out/` and temporary directories) |

Every measured number here is printed by `analysis.forensics.tables` from
`analysis/forensics/out/*.json`. The premise corrections (§1) also quote figures from other tracked
documents, cited by path. To reproduce (each script asserts its own reproduction checks and fails
loudly on a mismatch):

```
uv run python -m analysis.forensics.facts
uv run python -m analysis.forensics.q1_clairvoyant
uv run python -m analysis.forensics.q2_decomposition
uv run python -m analysis.forensics.q3_detection      # reads out/q2_decomposition.json
uv run python -m analysis.forensics.mechanisms
uv run python -m analysis.forensics.ladder            # reads out/q2_decomposition.json
uv run python -m analysis.forensics.proposal
uv run python -m analysis.forensics.tables            # prints every table below
```

## Verdicts

| trigger | registered value | verdict | why |
|---|---|---|---|
| `insufficient_headroom` | 2 families pass; the trigger fires at `<= 3` | **GENUINE, and robust** | A mapping-free clairvoyant acting from onset passes the registered bar on the same 2 families as the oracle. Twin-differenced headroom clears 5% on at most 3 families, under either endpoint and at any warning time. The compiler bugs are real but cannot move the count. |
| `detector_indistinguishable` | -565.53 [-708.6, -422.5] | **ARTIFACT-dominated, with GENUINE components. No BUG in the trigger.** | The arithmetic is right under every interval construction. What it measures under scripted transport and a gross-profit endpoint, though, is a verifier declining an exaggerated demand-up switch that free holding would have rewarded. It does not measure whether language adds value over detection. |

Under either reading of the endpoint the recorded **kill-or-reframe** decision is unchanged,
because `insufficient_headroom` fires under both.

## 1. Premise corrections

1. **The pilot has no standalone `transit_pause` family.** The six headroom keys are
   `demand_level:demand_up`, `demand_level:demand_down`, `temporary_pulse`, `lead_time_shift`,
   `shipment_loss` and `compound`. Generator family 6 is `compound`, and its supply effect is a
   transit pause of 3 to 4 periods starting at onset. The registered compiler mapping has a
   `transit_pause` row, but no pilot episode uses it.
2. **The "-176 per episode on transit_pause" figure is not a pilot number.** It is module 04's
   fixture headroom, recorded in the 2026-09-16 deviation (`prereg/deviations.md`).
3. **The detection-power table with 0.69 / 0.77 / 0.03 is not in any tracked document.** 0.6931
   and 0.7743 do appear, but only as normalized-reward cells in `reports/final_integration_check.md`
   and `docs/module06_research_notes.md`. §4.1 measures detection power from the records instead.
4. **The pilot report is `reports/pilot_report.md`.**
5. **The pilot ran with no order cap.** `order_cap` is `inf` on 120/120 episodes because
   `pilot_instances` passes no cap and `load_instance` defaults to `inf`. The only quantity limit in
   force was the published baseline's policy-internal smoother `ceil(mean + z_0.95·std)`.
6. **The "detector" control reads the alerts.** The harness gives it the same registered
   `alert_or_detector` chain as the LLM arms. On all 98 episodes where anything fires, the control
   switches in exactly the period arm 10 first proposes, and in 84 of those 98 the first firing is
   the alert rather than the CUSUM (§4.1).
7. **The pilot covers one cost ratio.** Every generated episode has profit 4 and holding 1, which is
   the benchmark's `med` label. The `high` (19) and `low` (1) ratios (`docs/env_contract.md` §8.2)
   are untested.

## 2. `insufficient_headroom`: GENUINE, and robust

### 2.1 Clairvoyant versus the compiled oracle

The clairvoyant knows the episode's entire future demand and supply realization and chooses the
order plan by solving an exact linear program. It never goes through the compiler. Arrival periods
are read by probing the frozen `LeadTimeSupply`, so lead-time shifts, lost shipments and pauses all
follow the audited physics. The network constraint matrix makes every vertex integral, and each
optimal plan was replayed through the frozen `EpisodeRunner` and asserted to score exactly the LP
value.

Variants:
- objective: gross (registered) or net;
- orders: smoother-capped or uncapped;
- anchor: onset, onset-1, onset-2 or period 1, with orders before the anchor fixed to arm 1's.

The registered rule (raw lift >= 5% or CVaR10 lift >= 10%, using the frozen `cvar10` on the
registered 16-row shape) is applied to each bound exactly as it is applied to the oracle.

Registered endpoint (gross profit), lift over arm 1, 4 seeds per family:

| family | arm 1 | oracle | max-stock @onset (content-free) | clairvoyant @onset, smoother-capped | clairvoyant @onset, uncapped | clairvoyant @period 1, uncapped |
|---|---:|---:|---:|---:|---:|---:|
| demand_level:demand_up | 20833 | +6.11% | +6.84% | +6.84% | +6.97% | +8.79% |
| demand_level:demand_down | 15800 | -2.46% | +0.06% | +0.06% | +0.06% | +0.96% |
| temporary_pulse | 19178 | +0.48% | +1.73% | +1.73% | +2.04% | +4.40% |
| lead_time_shift | 15372 | +15.45% | +23.41% | +23.41% | +23.41% | +27.58% |
| shipment_loss | 18021 | +0.00% | +1.96% | +1.96% | +1.96% | +5.64% |
| compound | 17812 | +0.01% | +0.72% | +0.72% | +0.72% | +12.41% |

The registered rule by warning time (PASS = raw >= 5% or CVaR10 >= 10%; each cell is raw / CVaR10 lift, %):

| family | oracle | capped @onset | capped @onset-1 | capped @onset-2 | capped @period 1 | uncapped @onset | uncapped @onset-1 | uncapped @onset-2 | uncapped @period 1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| demand_level:demand_up | PASS +6.1 / +4.0 | PASS +6.8 / +4.0 | PASS +7.2 / +5.1 | PASS +7.7 / +6.5 | PASS +8.8 / +7.3 | PASS +7.0 / +4.5 | PASS +7.3 / +5.9 | PASS +7.8 / +6.9 | PASS +8.8 / +7.3 |
| demand_level:demand_down | -2.5 / -1.2 | +0.1 / +0.0 | +0.1 / +0.0 | +0.1 / +0.0 | +1.0 / +1.0 | +0.1 / +0.0 | +0.1 / +0.0 | +0.1 / +0.0 | +1.0 / +1.0 |
| temporary_pulse | +0.5 / +0.8 | +1.7 / +1.3 | +2.1 / +2.0 | +2.3 / +2.0 | +4.4 / +2.9 | +2.0 / +1.9 | +2.3 / +2.0 | +2.9 / +2.0 | +4.4 / +2.9 |
| lead_time_shift | PASS +15.5 / +21.7 | PASS +23.4 / +37.6 | PASS +24.4 / +39.1 | PASS +25.4 / +39.8 | PASS +27.5 / +41.7 | PASS +23.4 / +37.6 | PASS +26.4 / +39.8 | PASS +26.4 / +39.8 | PASS +27.6 / +42.0 |
| shipment_loss | +0.0 / +0.0 | +2.0 / +3.5 | +2.9 / +4.7 | +3.6 / +5.7 | PASS +5.6 / +6.0 | +2.0 / +3.5 | +4.7 / +5.7 | +4.7 / +5.7 | PASS +5.6 / +6.0 |
| compound | +0.0 / +0.0 | +0.7 / +0.5 | +1.2 / +1.3 | +1.9 / +2.7 | PASS +12.4 / +14.8 | +0.7 / +0.5 | +1.3 / +1.3 | PASS +12.2 / +14.2 | PASS +12.4 / +14.8 |
| **families passing** | 2 | 2 | 2 | 2 | 4 | 2 | 2 | 3 | 4 |

Clairvoyance also buys foresight of demand noise, which no shock hypothesis could convey. So each
bound is recomputed on the episode's unshocked twin, and the shock-attributable headroom is
(bound - arm 1) - (twin bound - twin arm 1), expressed as % of arm 1. Only the raw 5% bar is
applied here; a twin-differenced CVaR was not computed.

| gross (registered) | capped @onset | capped @onset-1 | capped @onset-2 | capped @period 1 | uncapped @onset | uncapped @onset-1 | uncapped @onset-2 | uncapped @period 1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| demand_level:demand_up | +5.03% | +5.16% | +5.55% | +5.64% | +5.16% | +5.34% | +5.64% | +5.64% |
| demand_level:demand_down | -2.37% | -2.37% | -2.58% | -2.58% | -2.37% | -2.37% | -2.58% | -2.58% |
| temporary_pulse | -0.30% | +0.06% | +0.26% | +0.87% | +0.01% | +0.31% | +0.87% | +0.87% |
| lead_time_shift | +21.51% | +22.44% | +23.38% | +24.41% | +21.51% | +24.41% | +24.41% | +24.41% |
| shipment_loss | -0.22% | +0.75% | +1.42% | +2.48% | -0.22% | +2.48% | +2.48% | +2.48% |
| compound | -1.58% | -1.07% | -0.49% | +9.74% | -1.58% | -0.98% | +9.74% | +9.74% |
| **families >= 5%** | 2 | 2 | 2 | 3 | 2 | 2 | 3 | 3 |

| net (NOT registered) | capped @onset | capped @onset-1 | capped @onset-2 | capped @period 1 | uncapped @onset | uncapped @onset-1 | uncapped @onset-2 | uncapped @period 1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| demand_level:demand_up | +2.69% | +2.66% | +2.99% | +2.88% | +3.19% | +3.26% | +3.52% | +3.52% |
| demand_level:demand_down | +6.28% | +6.79% | +6.67% | +6.67% | +6.09% | +6.60% | +6.48% | +6.48% |
| temporary_pulse | +1.59% | +1.61% | +1.63% | +1.82% | +1.88% | +1.86% | +2.36% | +2.35% |
| lead_time_shift | +15.47% | +15.93% | +16.04% | +15.73% | +15.47% | +17.16% | +17.16% | +17.16% |
| shipment_loss | -0.19% | +0.37% | +0.46% | +0.18% | -0.19% | +1.53% | +1.53% | +1.53% |
| compound | +0.67% | +1.12% | +1.45% | +1.73% | +0.59% | +1.08% | +6.26% | +6.26% |
| **families >= 5%** | 2 | 2 | 2 | 2 | 2 | 2 | 3 | 3 |

What the tables show:

- **At onset the ceiling equals the oracle.** Acting from onset, the time the oracle itself learns
  the truth, the clairvoyant passes the same two families as the oracle (demand_up and
  lead_time_shift), capped or uncapped. The bound already contains every response any mapping,
  magnitude binning or dispatch window could compile, so the count of 2 is not a compiler artifact.
- **Warning time barely helps.** One period of warning (onset-1, when the early alert arrives)
  still gives 2 families. Two periods, uncapped, gives 3 by adding compound. Only foresight from
  period 1 reaches 4.
- **The fourth family at period 1 is noise foresight.** shipment_loss clears +5.6% on raw lift at
  period 1, but its twin-differenced value is +2.48%. Twin-differenced headroom reaches 5% on at
  most 3 families at every anchor, on both endpoints.
- **Seeds do not rescue it.** A seed bootstrap of the oracle count puts 92.7% of mass on 2 families
  and 7.3% on 1, and never reaches 4. The demand_up seeds straddle the bar: +4.01%, +5.20%, +7.91%,
  +7.05%.

### 2.2 Why four of six is out of reach: the physics

These are per-seed mechanisms, from `out/mechanisms.json`.

- **temporary_pulse.** Pulses last 2 or 3 periods and the promised lead time is 2, so an order
  placed at onset lands 2 periods later. From onset it reaches 0, 0, 1 and 1 pulse periods across
  the four seeds; from onset-1 it reaches 1, 1, 2 and 2.
- **shipment_loss.** Orders placed during the burst (1 or 2 periods) are lost, and the first order
  after the burst lands 3 to 4 periods after the burst starts. Even the onset clairvoyant gains
  only +1.96% gross, and its twin-differenced value is -0.22%.
- **compound.** The pause starts at onset. An order placed at onset-2 lands at onset, but one placed
  at onset-1 lands only after the pause. For example, on `dev/f6/s6050000` the onset is 19, the
  pause runs 19 to 21, and an order placed at 18 lands at 23. Pre-stocking therefore needs at least
  two periods of warning: uncapped @onset-2 gives +12.2% raw and a net twin difference of +6.26%.
- **demand_down.** Holding is free under gross profit, so knowing that demand fell is worth
  nothing: the clairvoyant gains +0.06%. Its headroom exists only on net, at +6.28% twin-differenced.

### 2.3 Artifacts and bugs, none of which moves the count

- **ARTIFACT (endpoint).** On every episode and at every anchor, the capped gross clairvoyant
  scores exactly what a content-free max-stock policy scores (asserted in `q1_clairvoyant.py`).
  That policy orders the smoother cap every period from the anchor on; it knows when the shock
  happens, not what it is. So the gross headroom metric measures how much more could be sold by
  flooding the pipeline, and that is also why demand_down cannot pass on gross. The same policy
  loses 59% to 219% of arm 1's net reward (`Q1-c` in the tables).
- **BUG (oracle, frozen `collie/arms/oracle.py`).** Three defects:
  - *Supply magnitudes always bin LOW.* The docstring says "the compiler does not read it either
    way", which is false. The registered mapping reads magnitude for lead_time_shift (l_eff
    reference offset +1 / +2 / +3) and for shipment_loss (gamma 0.5 / 0 / 0). On two
    lead_time_shift seeds the true shift is 2 but the compiled offset is 1.
  - *Dispatch stops at onset + duration - 1.* On shipment_loss that window is exactly the set of
    lost-order periods, so none of the window orders land (0 per seed) and the oracle is identical
    to arm 1 on 16/16 episodes. It cannot express the pre-stock or refill response.
  - *Level double counting.* The compiled m multiplies a running mean that already absorbs the
    level shift. By the horizon, implied over true level has drifted to 1.09 to 1.23 on demand_up
    and to 0.82 to 0.89 on demand_down, which explains the oracle's -2.46% on demand_down.

  None of the three can change the count, because the onset clairvoyant already bounds every
  compiled response.
- **ARTIFACT (interval).** The registered headroom interval (2, 2) is degenerate. Arm 1 and the
  oracle each have one trajectory per seed (24/24 clusters), so each family's 16 rows are 4 seeds
  replayed 4 times. The seed bootstrap gives [1, 2]. The conclusion (`<= 3`) holds under both.

### 2.4 On net reward (not registered)

On net the oracle also passes 2 families (demand_down +10.57%, lead_time_shift +9.87%). The net
clairvoyant passes 6 on raw lift at every anchor, but its gains on the unshocked twins run from
+1509.00 to +2018.25 per episode, which is pure noise foresight. Twin-differenced, it passes 2 at
onset and 3 from onset-2 uncapped. The headroom verdict therefore does not depend on the endpoint
question.

## 3. `detector_indistinguishable`: ARTIFACT-dominated, with GENUINE components

### 3.1 What the contrast actually compares here

- **arm 8 is the control.** arm 8 is bit-identical to the control on 120/120 episodes. The scripted
  proposal is the control's payload apart from its onset window, and both arms fire on one trigger.
  So arm 10 - control equals arm 10 - arm 8: the effect of verification and lifecycle applied to
  one constant proposal.
- **The constant proposal overshoots.** It is demand-level up, MEDIUM, persistent, and it compiles
  to m = 1.5 on every family, including demand_down, lead_time_shift, shipment_loss and the nulls.
  The true-structure arms compile m = 1.25 on demand_up and 0.75 on demand_down.
- **The endpoint only counts sales.** Gross profit is 4 × units sold on every record (p = 4, h = 1,
  0 violations in 1,752), and demand does not depend on the arm. The gap is therefore exactly
  -4 × 141.38 lost units per episode, and the control buys those units with 2,871.96 more holding
  per episode, which the registered endpoint does not see.

| per-episode column | estimate | registered-style normal, n=120 | seed-cluster bootstrap, 24 seeds | seed-collapsed normal | shocked mean | null mean |
|---|---:|---:|---:|---:|---:|---:|
| total_profit (registered, gross) | -565.53 | [-708.6, -422.5] | [-799.3, -364.6] | [-852.5, -321.1] | -641.54 | -261.50 |
| total_reward (net, not registered) | +2306.43 | [+1932.9, +2679.9] | [+1625.3, +2993.1] | [+1586.9, +3098.0] | +2307.60 | +2301.71 |
| total_holding_cost | -2871.96 | [-3191.6, -2552.3] | [-3379.4, -2384.9] | [-3450.7, -2407.8] | -2949.15 | -2563.21 |
| total_lost_sales | +141.38 | [+105.6, +177.2] | [+91.1, +199.8] | [+80.3, +213.1] | +160.39 | +65.38 |

What each switching arm compiled while a spec was active (configuration × active periods):

| family | ctrl | arm 10 | keyword | AlertSpec UB | oracle |
|---|---|---|---|---|---|
| demand_level:demand_up | (1.5, 2, 1) x500 | (1.5, 2, 1) x132 | (1, 2, 0) x401 | (1.25, 2, 1) x540 | (1.25, 2, 1) x524 |
| demand_level:demand_down | (1.5, 2, 1) x467 | — | (1, 2, 0) x377 | (0.75, 2, 1) x508 | (0.75, 2, 1) x492 |
| temporary_pulse | (1.5, 2, 1) x483 | (1.5, 2, 1) x32 | (1, 2, 0) x419 | (1.5, 2, 1) x564 | (1.5, 2, 1) x40 |
| lead_time_shift | (1.5, 1, 1) x202, (1.5, 2, 1) x208 | — | (1, 1, 0) x202, (1, 2, 0) x208 | (1, 2, 1) x272, (1, 3, 1) x280 | (1, 2, 1) x264, (1, 3, 1) x272 |
| shipment_loss | (1.5, 2, 1) x386 | — | (1, 2, 0) x386 | (1, 2, 0.5) x520 | (1, 2, 0.5) x24 |
| compound | (1.5, 2, 1) x523 | (1.5, 2, 1) x29 | (1, 2, 0) x407 | (1.25, 3, 1) x548 | (1.25, 3, 1) x96 |
| null | (1.5, 2, 1) x492 | (1.5, 2, 1) x6 | (1, 2, 0) x492 | — | — |

### 3.2 The -565.53 decomposed

Each episode falls into exactly one category:
- **no fire:** the shared trigger never fires;
- **blocked:** arm 10 proposes in the control's switch period, but its e-process never activates,
  so arm 10 runs as arm 1;
- **activated:** arm 10 activates.

The activated gap is split by one counterfactual replay, D, which uses the control's
switch-and-hold seam but switches at arm 10's activation period:
- delay = D - control;
- lifecycle = arm 10 - D.

D equals arm 10 bit-for-bit wherever arm 10 never stands down (asserted). Contributions are to the
120-episode mean, with episode counts in brackets:

| stratum | no fire | blocked | activated: delay | activated: lifecycle | row total |
|---|---:|---:|---:|---:|---:|
| compound (n=16) | +0.00 [0] | -6.00 [5] | -6.07 [11] | -11.00 | -23.07 |
| demand_level:demand_down (n=16) | +0.00 [0] | -1.33 [16] | +0.00 [0] | +0.00 | -1.33 |
| demand_level:demand_up (n=16) | +0.00 [0] | -40.27 [5] | -65.67 [11] | -43.87 | -149.80 |
| lead_time_shift (n=16) | +0.00 [4] | -254.03 [12] | +0.00 [0] | +0.00 | -254.03 |
| null (n=24) | +0.00 [12] | -46.60 [11] | -1.20 [1] | -4.50 | -52.30 |
| shipment_loss (n=16) | +0.00 [4] | -47.13 [12] | +0.00 [0] | +0.00 | -47.13 |
| temporary_pulse (n=16) | +0.00 [2] | -22.53 [6] | -10.50 [8] | -4.83 | -37.87 |
| **all** | +0.00 | -417.90 | -83.43 | -64.20 | -565.53 |

**The identity:** -565.53 = 0.00 (no fire, 22 episodes) + (-417.90) (blocked, 67) + (-83.43)
(activation delay, 31) + (-64.20) (lifecycle stand-down, 31).

Seed-cluster intervals for the components: blocked [-677.9, -210.3], delay [-164.1, -17.3],
lifecycle [-124.2, -17.1], null episodes [-83.5, -23.7].

On net reward the same decomposition is +2306.43 = 0.00 + 1544.18 + 45.06 + 717.18. The delay term's
interval includes 0 ([-14.6, +131.4]), and the lifecycle term's does not ([+326.1, +1181.6]).

**Activation delay.** Measured from arm 10's first proposal, activation delays have quantiles
2 / 3 / 4 / 5 / 12 periods across the 31 activated episodes. By family:
- demand_up: 2 to 12 periods, with 5 of 11 activations coming only on the second proposal;
- compound: 3 to 5 periods;
- temporary_pulse: 2 to 3 periods;
- no activation on demand_down (0/16) or on the 24 fired lead_time_shift and shipment_loss
  episodes, and 1 of the 12 fired nulls.

### 3.3 Why arm 10 loses on the nulls at all

The nulls contribute -52.30 [-83.5, -23.7].
- On the 12 no-alert nulls nothing fires, so they contribute 0.
- On the 12 false-alert nulls (condition `unreliable`, alert at period 10 reading "demand increase
  expected"), the control switches to m = 1.5 for the remaining 41 periods. Arm 10's verifier
  blocks 11 and activates 1.
- Arm 10 does not lose to arm 1 on those nulls: 0 gross, -57.58 net.
- The control beats arm 1 by +523.0 gross, from selling 130.75 more units per episode, while paying
  +5,184 in holding (net -4,661.0).

The null deficit is the value of free over-stocking during a false alarm: on the registered
endpoint, correct abstention scores as a loss.

### 3.4 Benefit given activation

On the 31 activated episodes:
- arm 10 beats arm 1 by +116.90 gross (-590.0 net);
- the control beats arm 1 by +688.39 gross (-3,540.61 net).

On demand_up, the one family where the scripted proposal names the right family, arm 10 - arm 1 is
+304.73 gross (-900.45 net) against the control's +1,499.64 (-2,147.18 net). Activation does help
arm 10 on gross, but it comes later and ends sooner than the control's switch.

### 3.5 Verdict, by part

- **BUG: none in the trigger.** The value reproduces exactly with the frozen `paired_interval`, and
  the interval sits below 0 under all three constructions.
- **ARTIFACT (scripted inputs):**
  - arm 8 is the control;
  - early_accurate is identical to unreliable (§4.1);
  - 53.3% of the gap sits in supply-family cells where the only proposal available is the wrong
    family (§4.2);
  - the m = 1.5 overshoot sets the size of every component.
- **ARTIFACT (endpoint):**
  - Δgross = -4·Δlost exactly;
  - the sign flips on net (+2,306.43, with every interval above 0);
  - the perfect-language bound is only +18.00 gross over the control (shocked +87.88, null -261.50).
    That bound is AlertSpec parsing of the true structure at onset-1 with no verification delay on
    shocked episodes, and arm 1 on nulls. On this endpoint, beating the control means out-stocking
    it, not out-understanding it.
- **GENUINE (would survive real content):**
  - verification delay: -83.43 gross, about 0 on net;
  - lifecycle stand-down: -64.20 gross, +717.18 net.

  Both are properties of the frozen verifier and lifecycle. Their gross sign is fixed by the
  endpoint, since any delay or stand-down gives up free over-stock.
- **The sign does not rest on the supply cells.** Cells where the shock moves demand contribute
  -212.07 [-323.8, -100.0], and the nulls -52.30 [-83.5, -23.7].

## 4. The detection asymmetry

### 4.1 Who fires, and on what

The demand CUSUM alone (the no_alert rows, one per seed):

| family | seeds | fired | latency vs onset |
|---|---:|---:|---|
| compound | 4 | 4 | [3, 4, 5, 5] |
| demand_level:demand_down | 4 | 4 | [5, 5, 8, 15] |
| demand_level:demand_up | 4 | 4 | [3, 7, 8, 14] |
| lead_time_shift | 4 | 0 | [] |
| null | 4 | 0 | [] |
| shipment_loss | 4 | 0 | [] |
| temporary_pulse | 4 | 2 | [1, 3] |

- **The CUSUM cannot see supply shocks.** It has no false alarms, but it also detects no pure
  supply shock.
- **The two contrast arms share one trigger trace.** The control's switch period equals arm 10's
  first proposal period on all 98 firing episodes (asserted). By first firing source, the 120
  episodes split into 84 alert, 14 CUSUM and 22 none. In 84 of its 98 switches, then, the
  "detector" control is an alert-timed, fixed-payload control; it acts as a statistical detector
  only under no_alert. The two arms have no detection asymmetry between them. The asymmetry is
  between the demand CUSUM and supply shocks.
- **Alert content never matters in this pilot.** early_accurate and unreliable are bit-identical
  for arms 8, 9 and 10, the control and the keyword parser on 24/24 seeds. The scripted proposal
  ignores the text, and both alerts arrive at onset-1. The keyword parser compiles its arrival
  class `(1, l, 0)` on every family, because every demo alert contains "supplier". In effect the
  pilot has three information conditions (no alert, onset-1, onset), not four.

### 4.2 How much of the gap comes from cells where neither arm could act

Contribution to the 120-episode mean:

| class | episodes | gross [seed-cluster 95%] | share | net [seed-cluster 95%] |
|---|---:|---:|---:|---:|
| supply_no_alert | 8 | +0.00 [+0.0, +0.0] | 0.0% | +0.00 [+0.0, +0.0] |
| supply_alert_only | 24 | -301.17 [-580.2, -84.8] | 53.3% | +202.07 [-144.5, +590.5] |
| demand_visible | 64 | -212.07 [-323.8, -100.0] | 37.5% | +1644.01 [+1085.2, +2270.0] |
| null | 24 | -52.30 [-83.5, -23.7] | 9.2% | +460.34 [+207.3, +714.0] |

- **supply_no_alert.** lead_time_shift and shipment_loss with no alert: neither arm can fire,
  so these cells contribute exactly 0.
- **supply_alert_only.** The same families with an alert. Both arms fire on the alert alone, and
  neither can compile the right family: the control's payload is fixed demand-up, and the scripted
  proposal is the same payload. The control switches to m = 1.5, and arm 10's verifier blocks all
  24 proposals. **These cells carry 53.3% of the gap.** On net they cannot be distinguished from 0.
- **Right-content upside is largest on supply.** These are also the families where right-family
  content gains most over the alert-timed control on the registered endpoint. AlertSpec UB -
  control is +627.8 gross (+730.8 net) on lead_time_shift and +154.5 (+526.6) on shipment_loss,
  against +101.5 on temporary_pulse, +45.5 on compound, -1.0 on demand_up and -401.0 on
  demand_down.

### 4.3 Is an arrival-side detector legal under `docs/env_contract.md` §4?

**Yes, provided it is built from aggregate identities.** §4 lists as visible the previous order,
previous arrivals, the aggregate in-transit total and the promised lead time. Two identities over
exactly those quantities were evaluated on arm 1's 32 trajectories (24 seeds plus 8 null twins):

| generator family | in-transit loss identity | promised-lead arrival residual |
|---|---|---|
| f1 | [None, None, None, None] | [None, None, None, None] |
| f2 | [None, None, None, None] | [None, None, None, None] |
| f3 | [None, None, None, None] | [None, None, None, None] |
| f4 | [None, None, None, None] | [2, 3, 2, 3] |
| f5 | [1, 1, 1, 1] | [3, 3, 3, 3] |
| f6 | [None, None, None, None] | [2, 2, 2, 2] |

- **In-transit identity.** `IT_t + q_t - A_t - IT_{t+1}` equals `q_t` exactly when the order at t
  was lost, because under the authoritative `eval/` semantics a lost order never enters in-transit.
  It flagged every loss at the next decision (4/4 loss seeds). This also shows that §5's wording,
  that a lost shipment is "invisible except as an absent arrival", understates what the policy can
  observe.
- **Promised-lead residual.** `A_t - q_{t-L}` flags a lead-time shift 2 to 3 periods after onset,
  a loss after 3, and the compound pause after 2.
- **No false signals.** There were 0 identity violations and 0 false signals on the demand
  families and twins.

Three limits apply (the detector is not implemented):
1. §4 forbids using the imputed shipment-age view as evidence. These identities do not need it,
   but any rule that pins a shortfall on a specific cohort would.
2. The residual assumes deterministic lead times. That holds on COLLIE-ShockSpec episodes, but not
   on the benchmark's `lead_time_stochastic` instances, where actual lead times of {1, 2, 3, inf}
   sit against a promise of 2 (§1, §2.2). There it would fire routinely. This is inferred from the
   contract, not measured, and it matches the recorded scope restriction on the arrival-side
   anytime-valid claim.
3. Its inputs depend on the arm's own orders, so trigger traces would stop being identical across
   arms. The current trigger reads only exogenous streams, which is what lets the paired contrasts
   share firing periods.

## 5. Endpoint collinearity: a registration question for the team

**Facts:**
- `ENDPOINT_COLUMNS` maps `cumulative_undiscounted_profit` to `total_profit` = Σ p·units_sold, which
  is gross of holding (`collie/eval/intervals.py`).
- p is constant within every benchmark instance (`docs/env_contract.md` §1) and demand is
  exogenous. So for every paired contrast on every instance, Δ`total_profit` = -p·Δ`total_lost_sales`
  exactly.
- In the pilot p = 4 on every record, with 0 violations: `profit_lift` 37.75 = 4 × 9.4375, and the
  detector gap -565.53 = -4 × 141.38.
- The two registered primary endpoints are therefore one measurement up to a per-instance
  constant, and the Holm family's profit and lost-sales members duplicate each other contrast by
  contrast.
- On gross, the headroom ceiling is reached by content-free max-stock (§2.3).

**Evidence that the gross reading is a defect:**
- The benchmark's own score is `total_reward` = `total_profit` - `total_holding_cost`, normalized
  against perfect foresight (`docs/env_contract.md` §3).
- The module-06 ladder's `mean_score` is normalized reward.
- The 2026-09-16 deviation justified the oracle's hazard window by a "holding blowup", which is a
  consideration only a net measure registers.
- Under gross, every holding-aware behaviour (the verifier's blocking and stand-down) scores as
  pure cost.

**Evidence for leaving it:**
- The mapping is literal to the benchmark's column named `total_profit`, and it was frozen before
  the pilot.
- Gross profit plus lost sales is a coherent service-level framing.
- The net reading reverses the detector sign, so adopting it now would be an outcome-driven change.
- The net advantage is itself inflated by the scripted m = 1.5 payload.
- The headroom trigger fires either way.
- The gap between gross and net depends on the cost ratio, and the pilot covers only p/h = 4.

This analysis does not rule on it; it is decision 1 in §11.

## 6. Other criteria and constructions

- **`recovery_time` cannot be won as operationalised.** The threshold is `<= 4` and the estimate is
  26.58. 48 of the 96 shocked episodes (demand_up, demand_down, lead_time_shift) stay shocked to
  period 50, so no period follows the final shock-active period and they score the never-recovered
  value 51 by construction. Those 48 alone put the 96-episode mean at 25.5 for any arm. The other
  families average 1.0 (compound), 4.0 (shipment_loss) and 1.5 (temporary_pulse).
- **`fill_rate_floor` sits almost on a structural ceiling.** The floor is `>= 0.95` and arm 10
  scores 0.8876.
  - Every episode starts with nothing on hand or in transit (all 1,752 records), so the first 1 to
    2 periods sell nothing for any arm. That costs 4.18% of demand on average, putting a ceiling of
    about 0.958 on every arm.
  - The net-optimal clairvoyant at onset reaches only 0.855 to 0.948 by family. Only the full-horizon
    uncapped gross clairvoyant, which ignores holding, clears 0.95, and only on 5 of 6 families.
- **`false_activation_control`: the interval is malformed, but the verdict is not.** The registered
  Wald interval runs past 1, at [0.8767, 1.0400]. Wilson intervals give [0.7976, 0.9926] on 24
  episodes and [0.6461, 0.9851] on the 12 distinct null trajectories. The fail stands under all
  three.
- **Null construction.** The 24 null episodes are 12 distinct trajectories from 8 seeds, with
  every arm identical within each group: the no-alert twins of f1 seeds are triplicated and the
  f2 unreliable twins are duplicated.
- **Condition replication.** Arm 1 and the oracle each have 1 trajectory per seed (24/24). Arm 10
  has 1 trajectory in 14 of 24 seeds, and the control averages 2.92 distinct trajectories out of
  its 4 conditions.
- **Records stamped `confirmatory`.** All 1,752 carry the stamp because `run_pilot_artifacts` runs
  the ladder as CONFIRMATORY, while `run_ladder` hardwires `_DemoTransport`.
- **`wrong_family_activation_rate` 0.198 (19/96: pulse 8, compound 11).** It clears on its point
  estimate. All 19 are the scripted demand-up payload activated on a pulse or compound episode.
- **Already recorded by the 2026-09-26 pre-merge audit, and not re-claimed here:** the
  `cost_frontier` competitor set, the aggregation-unit tension and the scripted transport. This
  analysis adds numbers: under seed-cluster intervals both triggers still fire (detector
  [-799.3, -364.6]; headroom count interval [1, 2]).

## 7. Transport-artifact classification of every finding

The classes are:
- **(a) frozen-code property:** it would be the same with real model content.
- **(b) scripted-input property:** it comes from the scripted proposal content or the demo alert
  channel.
- **(c) undecidable:** scripted evidence cannot settle it.

| # | finding | class | basis |
|---|---|---|---|
| 1 | Headroom 2/6, with the onset clairvoyant also at 2 and twin-differenced headroom `<= 3` at every anchor | (a) | The oracle, arm 1 and the clairvoyant make no LLM call and read no alert |
| 2 | Pulse reachability, loss bursts and the compound pause limit reachable headroom | (a) | Generator plus frozen supply physics |
| 3 | The gross ceiling equals content-free max-stock, and demand_down cannot pass on gross | (a) | Endpoint mapping plus lost-sales dynamics |
| 4 | Oracle bins supply magnitudes LOW (with a false docstring), its loss window is the lost-order periods, and levels are double counted | (a) | `collie/arms/oracle.py`, `collie/control/controller.py` |
| 5 | The headroom interval (2, 2) is 4 seeds replayed 4 times | (a) | Pilot construction plus the frozen interval |
| 6 | Δgross = -p·Δlost for every contrast; the primary endpoints duplicate | (a) | `ENDPOINT_COLUMNS`, p constant per instance, exogenous demand |
| 7 | The control is alert-timed in 84/98 firing episodes | (a), with the switch periods set by (b) | Frozen `tools/run_arms.py` wiring; the timing is the demo alert channel's |
| 8 | The CUSUM is blind to supply shocks (0/8) and has no false alarms on nulls | (a) | The frozen trigger reads `prev_demand` and alerts only |
| 9 | The arrival identities flag loss at latency 1 and lead-time shift or pause at 2 to 3, with no false signals | (a) | `eval/` semantics plus §4 observables |
| 10 | Verification delay (median 4, up to 12 periods) and lifecycle stand-down | (a) mechanism, (b) magnitude | The frozen verifier; its cost depends on what it gates |
| 11 | arm 8 is identical to the control on 120/120 | (b) | The scripted answer is the control's payload |
| 12 | early_accurate is identical to unreliable on 24/24, and the keyword parser always picks the arrival class | (b) | The scripted answer ignores text; the demo texts share onset-1 timing and the word "supplier" |
| 13 | Every activated or switched spec compiles m = 1.5 demand-up, on every family | (b) | The scripted MEDIUM bin |
| 14 | 53.3% of the gap sits in supply cells where only a wrong-family proposal exists, and all 24 are blocked | (b), with the blocking itself (a) | Scripted content plus a correct verifier |
| 15 | Wrong-family activation 19/96 | (b) | Scripted content |
| 16 | The detector gap flips sign on net (+2,306.43) | (a) sign mechanism, (b) magnitude | The endpoint plus the m = 1.5 overshoot |
| 17 | The perfect-language bound is +18.00 gross | (a) with (b) | Compiler and endpoint, plus the demo alert timing (onset-1) |
| 18 | `recovery_time` is unwinnable and fill has a ceiling of about 0.958 | (a) | Criterion definitions, persistent families, empty start |
| 19 | Null duplication (12 of 24 distinct) and a Wald interval past 1 | (a) | `pilot_instances` and `build_rollouts`; the frozen interval |
| 20 | Records stamped `confirmatory` under scripted transport | (a) | `run_pilot_artifacts` |
| 21 | Whether real proposals carry information beyond alert timing | (c) | §8 |
| 22 | Whether language can identify supply shocks from alert text | (c) | §8 |
| 23 | How calibrated real magnitudes are, which sets the sign of the verifier's value | (c) | §8 |
| 24 | Real parse and repair, budget, latency, cost frontier and decoding robustness | (c) | §8 |
| 25 | Real false-proposal rates on false alerts | (c) | §8 |
| 26 | The confirmatory `arm10_vs_arm7` and `arm10_vs_arm9` contrasts | (c) | §8 |

## 8. What scripted evidence cannot decide

The scripted pilot **cannot** decide:
1. **Whether language adds value over the alert's timing.** That is the question behind
   `detector_indistinguishable`, and arm 8 is identical to the control by construction.
2. **Whether a model can read a supply disruption from alert text** and propose a lead-time-shift
   or loss spec. Every scripted proposal was demand-up.
3. **Whether alert reliability changes proposals.** early_accurate and unreliable collapse into one
   condition here.
4. **How well calibrated real magnitude bins are.** The scripted MEDIUM bin overshoots the true
   magnitude (m = 1.5 against 1.25), and the size and even the sign of the verifier's delay and
   lifecycle value depend on that.
5. **Real operating characteristics:** parse failures and repairs, budget overruns, latency, the
   realised cost frontier, and decoding-seed robustness. Gemini rejects `seed`, Grok honours it,
   and Z.ai accepts but ignores it.
6. **The false-activation rate under real false alerts.** The scripted evidence is 1 activation on
   12 distinct null trajectories.
7. **Every registered confirmatory contrast** (`arm10_vs_arm1`, `arm10_vs_arm7`, `arm10_vs_arm9`),
   as evidence about language. Each one routes LLM content.

It **can** decide:
- the headroom question (no LLM is involved);
- the endpoint identity;
- the criterion constructions (`recovery_time`, fill floor, nulls, intervals);
- the CUSUM's blindness to supply shocks;
- arrival-side observability;
- the verifier's delay and lifecycle mechanics for a given proposal.

## 9. A minimal real-content pilot (proposal only; nothing has been run)

**Purpose:** answer §8 items 1 to 6 before any reframe is registered. It would be exploratory,
registered in advance with its own dated entry, and could not revise the recorded Gate 3 decision.

- **Episodes.** The same 120 pilot episodes (dev and cal only, same seeds and conditions), so each
  real-content trajectory pairs with its scripted counterpart. No test material.
- **Arms.**
  - Include arms 1, 8, 9 and 10, the detector control, the keyword parser, the AlertSpec upper
    bound and the oracle. The non-LLM arms reproduce their stored records and act as the harness
    check.
  - Optionally add arm 7, since `arm10_vs_arm7` is a registered contrast: 147 calls, $0.46 to $0.93
    on Gemini.
  - Leave out the every-period arms 3, 5 and 11: 6,000 calls each, $14.85 to $19.97 per arm on
    Gemini even at the scripted output size.
- **Endpoints.**
  - Gemini `gemini-3.8-flash` as primary on all 120 episodes. It takes no seed, so run `det-v1`
    (temperature 0) with the cache.
  - Grok `grok-4.20-0309-non-reasoning` as confirmation on all 120 at this size. It honours seeds,
    so the robustness mode is available.
  - Z.ai `glm-5.3-flash` as an optional third. It accepts a seed but ignores it; the existing
    configuration already disables thinking.
  - Keys stay in `cloud_endpoint/` and are resolved only at run time. Nothing in this analysis
    reads them.
- **Volume and cost** (the shared arm 8/9/10 proposal call at dated list prices; mean prompt about
  1,293 tokens):

| endpoint | model | seed honoured | volume | output x1 | output x5 | output x20 |
|---|---|---|---|---:|---:|---:|
| gemini_primary | gemini-3.8-flash | False | lower_distinct_prompts | $0.25 | $0.46 | $1.23 |
| gemini_primary | gemini-3.8-flash | False | upper_all_charged_physical | $0.54 | $0.97 | $2.61 |
| gemini_primary | gemini-3.8-flash | False | upper_with_one_repair_each | $1.07 | $1.95 | $5.22 |
| grok_confirmation | grok-4.20-0309-non-reasoning | True | lower_distinct_prompts | $0.37 | $0.51 | $1.02 |
| grok_confirmation | grok-4.20-0309-non-reasoning | True | upper_all_charged_physical | $0.79 | $1.08 | $2.17 |
| grok_confirmation | grok-4.20-0309-non-reasoning | True | upper_with_one_repair_each | $1.57 | $2.15 | $4.34 |
| zai_optional | glm-5.3-flash | False | lower_distinct_prompts | $0.05 | $0.07 | $0.18 |
| zai_optional | glm-5.3-flash | False | upper_all_charged_physical | $0.10 | $0.16 | $0.38 |
| zai_optional | glm-5.3-flash | False | upper_with_one_repair_each | $0.20 | $0.32 | $0.75 |

  Volumes run from 207 distinct prompts, served once each by the cache, to 441 charged calls, or
  882 with one repair each. The output multipliers allow for real answers and billed thinking
  tokens being longer than the scripted 66 tokens.
- **Harness.** `tools/run_arms.py` is frozen and hardwires `_DemoTransport` inside `run_ladder`, and
  `run_pilot_artifacts` stamps every record CONFIRMATORY. So the run needs one of:
  - a dated deviation that adds a transport parameter to the frozen harness; or
  - an exploratory entry point outside the frozen tree. `analysis/forensics/harness.py` already
    rebuilds every arm exactly as `run_ladder` does and reproduces the stored records bit-for-bit,
    and would only need a `MeteredClient` over the real transport.

  Either way, the records must be stamped EXPLORATORY.
- **Questions to register before the run:**
  1. Proposal family and magnitude accuracy, by family and condition.
  2. Whether the unreliable alert changes proposals relative to early_accurate.
  3. The verifier's block rate for right-family versus wrong-family proposals.
  4. arm 10 - arm 8 and arm 10 - control, reported on gross and net side by side.
  5. Parse and repair, budget, and latency.
  6. Proposals on false-alert nulls.
- **Optional second factor.** Module 03's alert bank (template sampling, noise and decoys) in place
  of the demo alerts. The bank is what a language arm would actually have to read.

## 10. Reframe candidates, ranked

**Ranking criterion:** how strongly the evidence here shows that the candidate targets a measured
cause of a fired trigger. The ranking is not a recommendation. Each candidate needs a new dated
registration and fresh dev/cal seeds (the 24 used here have been analysed), sized by the registered
power rule (`collie.data.splits.required_confirmatory_seeds`, alpha 0.05, power 0.8) from the new
estimate listed with it. The real-content pilot in §9 is a measurement step, not a reframe, and
several estimates below come from it.

**1. Endpoint integrity (prereg v2).** Make the economic endpoint net of holding (`total_reward`,
the benchmark's score), or register both with a declared primary. Replace the collinear lost-sales
duplicate in the Holm family.
- **Targets:** both triggers. The detector sign comes from the endpoint, and headroom on gross is
  measured by content-free max-stock.
- **For:** an exact structural identity (0 violations out of 1,752); the ceiling equals max-stock;
  the detector contrast is +2,306.43 on net with every interval above 0; the verifier's blocked and
  lifecycle components turn from costs into benefits.
- **Against:** this is the textbook outcome-driven change. The net sign is itself partly an effect
  of the scripted m = 1.5 payload. Headroom still fails on net (oracle 2, twin-differenced 2 to 3).
  Percentage bars on a smaller net base need a new rationale.
- **Re-register:** `primary_endpoints`, `ENDPOINT_COLUMNS` (frozen code), `holm_family`, any
  threshold that names the endpoint, `threshold_rationale.md`, and a new freeze manifest.
- **New estimate:** the effect size and SD of net contrasts under real content, plus the cost-ratio
  scope (p/h of 19, 4 and 1).

**2. Honest boundary result.** Report what the task allows. Advance shock knowledge is worth 5% or
more only for persistent lead-time shifts and demand level-ups. Pulses, loss bursts and pauses are
physically unreachable from onset at a promised lead time of 1 to 2.
- **Targets:** the headroom trigger's measured cause, directly.
- **For:** the result is mapping-free, seed-robust, twin-differenced and endpoint-robust, and it
  involves no LLM.
- **Against:** it is a characterization claim, not a method claim. On gross the demand_down result
  is an endpoint artifact (+6.28% on net). The claim is scoped to synthetic ShockSpec episodes with
  deterministic lead times.
- **Re-register:** a new claim and estimand (the clairvoyant bound, the twin difference and the
  anchor), with its analysis code promoted out of `analysis/`.
- **New estimate:** clairvoyant headroom by family on fresh seeds, and at other cost ratios.

**3. Language where telemetry is blind.** Scope the method claim to supply-side disruptions.
- **Targets:** where the headroom is (lead_time_shift: +21.51% gross and +15.47% net
  twin-differenced at onset) and where 53.3% of the gap sits.
- **For:** the CUSUM sees 0 of 8 supply shocks. Right-family content gains most over the
  alert-timed control on gross in the supply families (UB - control +627.8 on lead_time_shift and
  +154.5 on shipment_loss, against at most +101.5 elsewhere).
- **Against:** an arrival-side detector sees lead-time shifts at 2 to 3 periods and losses at 1,
  with no false signals, so language's edge is at most a head start of a few periods plus
  identifying the family. shipment_loss has no headroom (at most +2.48% twin-differenced). The
  claim covers one family of six, so the 4-of-6 rule no longer applies. Whether a model can
  identify the family is unmeasured (§8 item 2).
- **Re-register:** family scope, the headroom rule, and a contrast against a detector control that
  includes an arrival-side detector, since without one the comparison is a strawman.
- **New estimate:** real-model family and magnitude accuracy on supply alerts, and the value of a
  head start of k periods on lead_time_shift (the clairvoyant rows @onset-1 and @onset-2 give its
  ceiling).

**4. Verification as downside-risk control.** Claim that verified activation bounds the harm of
unreliable language, rather than that language raises profit.
- **Targets:** the GENUINE components (delay and lifecycle) and the null deficit.
- **For:** on net, blocking contributes +1,544.18, lifecycle +717.18 and the nulls +460.34. All 24
  wrong-family supply proposals and 11 of 12 false-alert nulls were blocked.
- **Against:** on the registered endpoint every one of these components is a cost. The protection
  is measured only against one constant bad proposal. A verifier that blocks everything would also
  look protective. `false_activation_control` fails under every interval.
- **Re-register:** a downside endpoint (for example net CVaR10), arm 10 - arm 8 as the primary
  contrast (it is degenerate today), an exact or Wilson false-activation interval, and
  de-duplicated nulls.
- **New estimate:** real wrong-proposal rates by condition, especially unreliable and false-alert
  nulls.

**5. Compiler and oracle fixes** (supply magnitude binning, the loss window, level double counting).
- **Targets:** real defects, but ones measured not to move either fired trigger.
- **For:** the defects are confirmed per seed (§2.3).
- **Against:** the onset clairvoyant, which bounds every compiled response, passes the same 2
  families, and the control shares the compiler, so the fixes would shift both sides of the
  detector contrast.
- **Re-register:** a dated deviation and a freeze-manifest update for `collie/arms/oracle.py` and
  the controller or compiler.
- **New estimate:** per-family oracle lifts after the fixes, bounded above by the clairvoyant (for
  example, shipment_loss can gain at most +1.96% at onset).

**6. An arrival-side detector** in the trigger or in the detector control.
- **Targets:** the CUSUM's blindness to supply shocks.
- **For:** it is legal under §4, fast (latency 1 to 3) and produced no false signals here.
- **Against:** it helps the control at least as much as arm 10, so it would widen
  `detector_indistinguishable`. It makes trigger traces depend on the arm. It is valid only with
  deterministic lead times.
- **Re-register:** `trigger_thresholds.primary_rule`, calibration on dev/cal nulls, and the
  invariant that trigger traces are identical across arms.
- **New estimate:** latency and false-alarm rate on fresh seeds, and on `lead_time_stochastic`
  instances if those are in scope.

## 11. The three things the team must decide at Gate 3

**1. What the registered economic endpoint means: gross `total_profit` as frozen, or net
`total_reward`, and whether to settle it in a prereg v2.** The recorded decision stands under
either answer, because headroom fires both ways. The finding would go into
`prereg/deviations.md` as a dated finding, not as a threshold move.
- **The identity:** Δ`total_profit` = -p·Δ`total_lost_sales` for every contrast (0 violations in
  1,752 records). The two primary endpoints and three pairs of Holm members are duplicates.
- **The ceiling:** the capped gross clairvoyant equals content-free max-stock on every episode.
- **The sign:** the detector contrast is -565.53 on gross and +2,306.43 on net, with every interval
  construction excluding 0 on both.
- **For net:** the benchmark's own score is net; the 2026-09-16 deviation reasoned in terms of
  holding.
- **For gross:** the frozen mapping is literal to the benchmark's column name; changing it after
  seeing the flip is outcome-driven; the net advantage is inflated by the scripted overshoot.
- **Scope:** the pilot tested only one cost ratio.

**2. What the pilot is evidence of, and whether a real-content exploratory pilot runs before any
reframe is registered.**
- **What it can show.** It validates machinery, task physics and endpoint behaviour, not language.
  arm 8 is identical to the control on 120/120 episodes, early_accurate is identical to unreliable
  on 24/24 seeds, the control is alert-timed in 84 of 98 firing episodes, and every proposal is
  one constant.
- **What stands regardless.** The headroom verdict is transport-independent and holds whatever the
  pilot shows, which matches the pre-merge audit's finding 3 ("a pilot with real model content
  remains owed").
- **Cost** of the shared proposal call, from output x1 at the lower volume to output x20 at the
  upper: Gemini $0.25 to $2.61, Grok $0.37 to $2.17, Z.ai $0.05 to $0.38. The worst case with one
  repair per call is $5.22 on Gemini.
- **Sequencing risk.** On the gross endpoint the perfect-language bound is +18.00. Through this
  compiler, no real model could make the registered detector contrast meaningfully positive except
  by out-stocking the control. Running §9 before decision 1 risks a second result that cannot be
  interpreted.

**3. Which reframe candidate to register, if any, and which criterion repairs go with it.**
- **Candidates.** §10 ranks six, each with its evidence, re-registration needs and missing
  estimate.
- **Repairs owed whichever candidate is chosen:**
  - `recovery_time`: 48 of 96 shocked episodes score 51 by construction, fixing the mean at 25.5
    or more against a threshold of 4;
  - `fill_rate_floor`: the structural ceiling is about 0.958 because every episode starts empty,
    against a floor of 0.95;
  - null construction: 12 distinct trajectories among 24 nulls;
  - the false-activation interval: the Wald interval exceeds 1;
  - `cost_frontier`: the competitor set (already recorded);
  - the aggregation unit: already recorded, and both triggers survive seed-cluster intervals;
  - records stamped `confirmatory` under scripted transport.
