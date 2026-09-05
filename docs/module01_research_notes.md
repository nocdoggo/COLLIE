# Module 01 research notes

Wave 0 output (§2 of the module brief). Everything below was established by direct inspection of
the pinned benchmark (`third_party/InventoryBench`, commit `62b1f116`) or by cited public sources.
This note records findings; the registered decisions are marked **[registered]** where the module
had a choice to make.

## 1. The ten official synthetic demand patterns

No generator code ships upstream (searched all `*.py` in the submodule; `scripts/` and `docs/`
only consume data). The authoritative description is
`third_party/InventoryBench/documentation/benchmark.md`: 50 test periods, 5 train periods, the
single-changepoint patterns change at **period 16**, the AR(1) initial value is 100, and seeds are
`hash((42, pattern, variant, realization)) % 2**32`.

Layout confirmed empirically: instances exist **only** under the three `lead_time_*` subtrees (10
patterns × 4 variants × 2 realizations × 3 cost ratios = 240 per subtree, 720 total). Demand series
are **bitwise identical across the three lead-time subtrees** for the same
pattern/variant/realization (480/480 pairs equal) and identical across cost ratios within a
realization (80/80 pairs). All 1,440 synthetic CSVs are integer-valued in every demand cell —
confirms env contract §8.1. Synthetic item id is the literal string `chips(Regular)`; dates are
`Period_1…Period_50`.

Per-pattern parameters, recovered empirically from `test.csv` (pooled over r1/r2 where noted);
variant directory names proved accurate everywhere they could be checked:

| Pattern | Variant | Recovered process |
|---|---|---|
| p01 stationary_iid | v1 `normal_100_25` | N(100, 25); mean 102.4, sd 22.9 |
| | v2 `normal_100_40` | N(100, 40); sd 36.7, min 0 (clipping visible) |
| | v3 `normal_100_15` | N(100, 15); sd 15.7 |
| | v4 `uniform_50_150` | U(50, 150); range [53, 147], sd 27.7 (uniform sd 28.9) |
| p02 mean_increase | changepoint at 16 | pre ≈ N(100, 25); post means v1 200, v2 153, v3 288, v4 200 (v4 `samevar` keeps sd ≈ 25; others show sd ≈ 2.5·√mean, Poisson-like scaling — hypothesis, no generator code) |
| p03 mean_decrease | changepoint at 16 | post means v1 50, v2 73, v3 32, v4 81; same sd-scaling caveat |
| p04 increasing_trend | v1 `linear_100t` | mean = 100·t (fit 12 + 98.4·t); noise scales with level |
| | v2 `linear_50_3t` | 50 + 3·t, sd ≈ 25 |
| | v3 `exp_1_05` | 100·1.05ᵗ (fit growth 1.0508) |
| | v4 `linear_100_2t` | 100 + 2·t with heavy-tailed right-skewed multiplicative noise and exact zeros; **not** normal — caution if a Gaussian null is assumed here |
| p05 decreasing_trend | v1 `200_minus_3t` | 200 − 3·t, sd ≈ 21 |
| | v2 `exp_decay_0_97` | 200·0.97ᵗ (fit 0.9705) |
| | v3 `150_minus_2t` | 150 − 2·t, sd ≈ 18 |
| | v4 `200_div_sqrt_t` | 200/√t, sd ≈ 25 |
| p06 variance_change | changepoint at 16 | mean ≈ 100 throughout; v1 N(100,25)→U(0,200); v2 sd 25→50; v3 sd ≈60→≈15–20; v4 U(50,150)→N(100,15) |
| p07 seasonal | additive sine, base 100, phase ≈ 0 | v1 P=10 amp≈30; v2 P=5 amp≈50; v3 P=25 amp≈40; v4 `multiplicative` P=10 amp≈30 (the multiplicative claim is **not** clearly supported empirically — residual sd is if anything larger at troughs) |
| p08 multi_changepoint | changepoints at 16 and 36 | v1 means 100→150→80; v2 100→55→125; v3 mean 100, sd 23→54→18; v4 80→117→93 |
| p09 temp_spike_dip | event window periods 16–25 (10 periods) | v1 surge ≈2×, full recovery; v2 dip ≈0.5×, full recovery; v3 surge ≈2.5× then new normal ≈1.2×; v4 dip ≈0.4× then partial recovery ≈0.8× |
| p10 autocorrelated | AR(1) around mean 100, innovation sd ≈ 25, x₀ = 100 | v1 φ=0.7 (fit 0.65/0.68); v2 φ=0.5 (0.41/0.61); v3 φ=0.3 (pooled evidence weak at n=50); v4 φ=−0.3 (−0.26/−0.43) |

Train sets: 5 rows for every synthetic instance — IID samples from the first-segment distribution
for p01/p02/p03/p06/p08/p09, and sequential samples at t=1..5 for p04/p05/p07/p10. Identical across
r1/r2 within a variant.

`lead_time_stochastic` values are in `{1,2,3,inf}` with `inf` written literally, and the sequence
is shared across all instances in that subtree.

One upstream anomaly noted: a stray `perfect_score_1.txt` run-log artifact inside
`lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med/`. Harmless; the loader reads only the
named CSVs.

### Baseline processes chosen for the harness **[registered]**

Our baseline harness draws from the stationary members of the official vocabulary so a shocked
episode is a perturbation of a process the benchmark already contains, not a new distribution a
reviewer could attribute the result to. The baseline kinds mirror the five null-bank strata
(§3.8 of the brief), because the same process code serves both:

| Kind | Official anchor | Parameters |
|---|---|---|
| `stationary_iid` | p01 v1 | mean 100, sd 25, normal |
| `seasonal` | p07 v1 | mean 100, additive sine, period 10, amplitude 30, sd 25 |
| `overdispersed` | p02/p03 sd-scaling observation | negative-binomial with registered dispersion (mean 100, sd 50, i.e. variance 4× mean-level scale) |
| `dependent` | p10 v1 | AR(1) around 100, φ = 0.7, innovation sd 25, x₀ = 100 |
| censored stratum | observation model only | same demand processes, observation censored to sales+availability; handled downstream, not by the generator |

Uniform baselines (p01 v4) are deliberately excluded from the *default* harness: a normal-mean
process is what the registered verifier nulls describe, and uniform is available as an option for
robustness slices.

## 2. Integer rounding rule **[registered]**

Every demand cell in all 1,320 official instances is integer-valued (env contract §8.1), and
exact integer accounting is what makes the equivalence suite's `0.0` max-abs-diff possible. The
shock effect is multiplicative on the baseline draw, which produces non-integers, so:

> **Emitted demand is `max(0, round_half_up(x))` applied cell-by-cell, where `round_half_up(x) =
> floor(x + 0.5)`.**

Half-up rather than Python's banker's `round()`: deterministic, platform-independent, and the
obvious rule a reviewer would re-implement. Half-way cases occur only when the baseline draw
lands exactly on a `k + 0.5` boundary, which has measure zero under continuous draws; the rule
exists so the code is total, not because ties matter. Negative draws (possible in principle for
the overdispersed kind) are clipped at 0, matching the observed `min = 0` clipping in official
p01 v2.

The **twin** is constructed by applying the same rounding to the same unscaled baseline draws, so
pre-onset cells are identical by construction, not by tolerance.

## 3. Stockpyl transit-pause semantics

The spec (R3.2) names Stockpyl's transit-pausing disruption (type `'TP'`) as the semantics
reference. Verified against the Stockpyl simulation tutorial ("Supply Disruptions",
<https://stockpyl.readthedocs.io/en/latest/tutorial/tutorial_sim.html>) and the per-period
state-advance code in `src/stockpyl/sim.py` (main branch):

- During a TP disruption, the inbound shipment pipeline is **copied verbatim** into the next
  period's state instead of advancing one slot: the per-cohort transit clock freezes.
- New shipments dispatched during the pause **join the frozen pipeline** and are released with it
  (the tutorial's example: pipeline grows 21→45→67→87→104 over a 4-period pause, then 104 arrives
  in a lump at recovery+1 for lead time 1).
- A cohort whose transit completes at the first paused period **still arrives** — receipt happens
  before the freeze in the period's event order (the t=9 receipt of 20 in the tutorial example).

Our frozen semantics (env contract §8.3: "a pause freezes the transit clock of cohorts still
moving, and never holds back a cohort whose transit is already complete; a pause of length k
delays each still-moving cohort by exactly k") is **consistent** with Stockpyl's TP behaviour on
all three points. Two caveats worth recording: (a) cohorts *launched during* the pause merge into
the frozen pipeline, so their individual delay is less than k (a fact about the physics, relied on
by the conservation tests); (b) Stockpyl TP does not block *ordering* (that is type OP), so
continuing to order during a pause is our modelling choice, matching the benchmark's
always-orderable environment. No change to `collie/sim/supply.py` is indicated.

Literature grounding: the disruption-state model is from Snyder & Shen, *Fundamentals of Supply
Chain Theory* 2nd ed., Example 9.3 (referenced by the same tutorial).

## 4. Shock magnitude and duration realism (plausibility check)

Registered multipliers `m ∈ {0.6, 0.75, 1.25, 1.5, 2.0}` and durations of 2–10 periods (weekly
buckets in the real track):

- Surges: O'Connell, de Paula & Smith (CEPR DP 15371, UK scanner data, COVID first wave) — staples
  spending peaked at **+80%**, household supplies **+70%**; category spikes averaged +44% sustained
  over a 4-week window. Multipliers 1.25–2.0 over 2–10 weeks sit inside observed panic-buying
  dynamics. (<https://cepr.org/voxeu/columns/spending-dynamics-and-panic-buying-during-covid-19-first-wave>)
- Drops: US clothing-store sales fell **50.5%** in April 2020 alone; most relevant here, **H&M's
  net sales fell 50% in Q2 2020** and −18% for the full year — deeper and longer than our mildest
  registered drops (0.6–0.75). (<https://wwd.com/sourcing-journal/industry-news/h-m-sales-q2-fell-50-percent-coronavirus-stores-digital-1238753238/>)

The registered range is realistic and, if anything, conservative on the downside.

## 5. Reproducible seeding **[registered]**

Per NEP 19 (<https://numpy.org/neps/nep-0019-rng-policy.html>):

- Every generator takes an explicit `np.random.Generator` built as
  `np.random.Generator(np.random.PCG64(seed))`. No global state, no `np.random.seed`, no
  `random` module for anything that reaches a file.
- One master seed per episode; independent sub-streams for (baseline draws, onset, parameters)
  are derived with `np.random.SeedSequence(seed).spawn(...)` in a **fixed positional order** —
  never from set/dict iteration order.
- Caveat recorded: `Generator` distribution methods are *not* stream-stable across numpy feature
  releases; NEP 19's own advice is to pin the stack. Our guarantee therefore rests on the
  committed `uv.lock` numpy pin plus the byte-stability tests (regeneration must be byte-identical
  on this stack), exactly as InventoryBench itself ships generated CSVs rather than a generator.
- `hypothesis` (dev dependency, added this wave) supplies the property tests; `@example` pins any
  counterexample it finds.

## 6. Hypothesis usage notes

Current API as of hypothesis 6.167: `@given` with `st.integers`, `st.floats`, `st.lists`,
`st.composite`, `st.sampled_from`; `@settings(max_examples=..., deadline=..., suppress_health_check=...)`;
`assume()` for rejection; `HealthCheck` enum for e.g. `too_slow`. Project constraints that bite:

- `--strict-markers` is on with only `slow`, `needs_benchmark`, `needs_llm`, `equivalence`
  registered — property tests need no new marker.
- `filterwarnings = ["error::DeprecationWarning"]` escalates deprecations, so strategies must use
  current spellings (e.g. `st.integers(min_value=...)`, no deprecated `st.none()`-era idioms).
- File-writing generators get `@settings(deadline=None)`; cheap properties `max_examples=200`.
- A hypothesis database directory (`.hypothesis/`) must not be committed — covered by `.gitignore`
  check at stage time (§0.4 discipline).
