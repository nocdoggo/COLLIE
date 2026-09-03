# 01. Shock generator, splits, and the null bank

| | |
|---|---|
| **Owner** | P2 |
| **Checkpoint 1** | Day 3 |
| **Checkpoint 2** | Day 8 |
| **Depends on** | `00-foundation.md` only. You are unblocked on day 1. |
| **Consumed by** | 03 alert bank, 05 verifier, 07 evaluation, and the pilot |

You are the most upstream module. Four other modules read your output, so your Checkpoint 1 is
scheduled first and a slip here propagates. If you are going to miss, say so on day 2.

## What you are building

COLLIE-ShockSpec: a dataset of episodes in which a named, typed exogenous shock happens at a hidden
onset period, each paired with a **baseline twin** that shares every pre-onset random draw and then
continues unshocked. The twin is what makes the comparison a comparison rather than an anecdote.

Six families, three perturbing demand and three perturbing supply. Plus the splits that keep test
data untouchable, and a bank of well-specified null episodes that measures how often the whole
pipeline fires when nothing happened.

Two properties matter more than anything else you write:

1. **Onset is invisible.** Nothing in the observable stream before onset may differ between a shocked
   episode and its twin. If it does, every downstream measurement of detection is contaminated.
2. **The same seed gives byte-identical output.** Not statistically similar. Identical files.

## Where the code goes

```
collie/data/
  families/
    __init__.py
    base.py           baseline demand process, twin construction, shared plumbing
    demand.py         families 1-3
    supply.py         families 4-6
  writer.py           instance directory writer, official format plus sidecars
  splits.py           seed registry, split construction, integrity assertions
  nullbank.py         the well-specified null and fragility episodes
tools/
  build_shockspec.py  CLI, emits manifests/shockspec_v1.json
tests/
  test_families.py
  test_generator_invariance.py
  test_splits.py
  test_nullbank.py
```

## The file format you must emit

The loader already exists and is frozen. Write files it can read; do not change it.

```
<instance>/
  train.csv       official format: exact_dates_<item>, demand_<item>
  test.csv        official format: exact_dates_<item>, demand_<item>,
                  lead_time_<item>, profit_<item>, holding_cost_<item>
  supply.csv      PROJECT-OWNED, optional
  incident.json   PROJECT-OWNED, hidden truth, emitted for EVERY shocked episode
```

**`test.csv` carries more than the original plan assumed.** It has a per-period
`lead_time_<item>` column, and `lead_time = inf` already encodes a lost shipment. So:

| Family | Mechanism | Needs `supply.csv`? |
|---|---|---|
| 1-3 demand shocks | the `demand` column | no |
| 4 lead-time shift | the `lead_time` column, per period | no |
| 5 lost-shipment burst | `lead_time = inf` on affected order periods | no |
| 6 compound, with transit pause | pause must freeze cohorts already in transit | **yes** |

Only the pause needs a sidecar, because both harnesses fix an arrival date at order time and a pause
must defer one already set. This is a better outcome than assumed: most of the dataset rides on the
unmodified instance format, which is what makes the neutral-sidecar equivalence argument hold.

**`supply.csv` schema, exactly as the loader parses it:**

```csv
period,lead_time,pause_active
1,2,false
2,2,true
```

- `period` is required, 1-based, and must cover `1..horizon` for **every column you declare**. A
  partial sidecar raises. There is no `lost` column: a loss is `inf` in `lead_time`.
- Declaring `pause_active` only is legal and normal for family 6; lead times then come from
  `test.csv`.
- A sidecar that merely restates `test.csv` must produce a byte-identical episode. There is already a
  test for this; do not break it.

**`incident.json` schema, exactly as the loader parses it.** Field names differ from early drafts;
these are the ones that work:

```json
{
  "family": "compound",
  "onset_period": 17,
  "magnitude": 1.5,
  "duration": 8,
  "conditional_independence": false,
  "supply_effect": {
    "kind": "transit_pause",
    "start_period": 17,
    "length": 4,
    "disrupted_lead_time": null
  },
  "baseline_twin_id": "<relpath of the twin>",
  "seed": 40117,
  "held_out_combo": true
}
```

`family` and `supply_effect.kind` must be members of `ShockFamily` and `SupplyEffectKind`. Unknown
values raise at load.

## Family parameters — use these exact values

Onset is drawn `U{14..22}` for every family and recorded **only** in `incident.json`.

| # | Family | `ShockFamily` | Parameters |
|---|---|---|---|
| 1 | persistent increase | `demand_level` | `m in {1.25, 1.5}`, persists to horizon |
| 2 | persistent decrease | `demand_level` | `m in {0.6, 0.75}`, persists to horizon |
| 3 | temporary spike | `temporary_pulse` | `m in {1.5, 2.0}`, duration 2-4 periods |
| 4 | lead-time shift | `lead_time_shift` | baseline `{1,2}` to disrupted `{3,4}`, persists |
| 5 | lost-shipment burst | `shipment_loss` | orders in 1-3 consecutive periods never arrive |
| 6 | compound | `compound` | `m in {1.25, 1.5}` for 6-10 periods, with a 3-5 period pause |

The demand effect is **multiplicative on the baseline draw**, which is what lets the twin share the
pre-onset path exactly. Do not re-draw post-onset; scale.

**`conditional_independence`.** `true` for families 1-5, `false` for family 6. Module 05 reads this
flag and, when false, must use either a registered joint conditional likelihood or separate
e-processes with explicit alpha splitting. It must never multiply marginal likelihood ratios for
convenience, and the code path that would do so has to be unreachable. Getting this flag wrong
silently breaks the statistical guarantee, so it is worth a dedicated test.

---

## Checkpoint 1 — Day 3: families generate, twins are provably identical pre-onset

### Deliverables

1. `collie/data/families/base.py` — baseline demand from an official pattern, plus twin
   construction. One function, one seed, two series.
2. `collie/data/families/demand.py` — families 1, 2, 3.
3. `collie/data/families/supply.py` — families 4, 5. Family 6 may wait for Checkpoint 2.
4. `collie/data/writer.py` — writes a directory `collie.sim.loader.load_instance` reads back.
5. 18 dev episodes on disk, three per family.

### Interface

Every family exposes the same shape:

```python
def generate(
    *,
    seed: int,
    horizon: int,
    params: FamilyParams,
) -> GeneratedEpisode: ...

@dataclass(frozen=True, slots=True)
class GeneratedEpisode:
    demand: tuple[float, ...]
    lead_times: tuple[float, ...]          # math.inf encodes a lost shipment
    pause_active: tuple[bool, ...]         # () when no pause
    incident: HiddenIncident
    twin_demand: tuple[float, ...]         # unshocked continuation
    twin_lead_times: tuple[float, ...]
```

Returning the twin **alongside** rather than inside is deliberate, and mirrors how
`collie/fakes/fake_generator.py` returns hidden truth. It makes a leak a type error rather than a
silent pass.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_twin_identical_before_onset` | shocked and twin series are equal on `1..onset-1`, for every family and 20 seeds |
| `test_twin_differs_after_onset` | they diverge, so the test above is not vacuous |
| `test_parameter_recovery` | `m` recovered from the generated series to within tolerance, per family |
| `test_onset_invisible` | no observable field correlates with onset before onset |
| `test_bitwise_determinism` | same seed run twice gives byte-identical directories |
| `test_round_trips_through_loader` | `load_instance` reads every generated directory and returns the expected horizon, demand, and lead times |
| `test_neutral_sidecar_changes_nothing` | writing a sidecar restating `test.csv` yields an identical episode |
| `test_conditional_independence_flag` | `true` for 1-5, `false` for 6 |

`test_bitwise_determinism` is the one people skip. Do not. Without it, nothing downstream is
reproducible and every later comparison is unfalsifiable.

### Audit command

```bash
uv run pytest tests/test_families.py tests/test_generator_invariance.py -v
uv run python -m tools.build_shockspec --split dev --limit 18 --out /tmp/shockspec_dev
```

### Pass criteria

- All tests above green.
- 18 dev episodes on disk, each loading through `load_instance` without error.
- One plot or printed table showing a shocked trajectory against its twin, with onset marked, for one
  seed. The auditor should be able to see the pre-onset paths coincide.

### Not expected yet

Family 6, splits, the seed registry, the null bank, the manifest.

---

## Checkpoint 2 — Day 8: family 6, splits frozen, null bank built

### Deliverables

1. Family 6, compound demand shift plus transit pause, with `supply.csv`.
2. `collie/data/splits.py` — seed registry and the three splits.
3. `collie/data/nullbank.py` — the null and fragility episodes.
4. `manifests/shockspec_v1.json`, byte-stable on regeneration.
5. The five integrity assertions, green.

### Splits — exact counts

```
seed pools, pairwise disjoint:
  test 150 = 6 families x 25 seeds
  dev   36 = 6 x 6
  cal   24 = 6 x 4

rollouts:
  test 640 = 600 paired + 20 silent-null + 20 false-alert-null
  dev  144 = 6 families x 4 conditions x 6 seeds
  cal   96 = 6 families x 4 conditions x 4 seeds
```

A seed-family pair is one **independent unit**. The four information conditions of one seed are
paired replays of a single unit, never four samples. Emit `independent_unit_id` on every rollout;
module 07 aggregates over it, and this field is the only thing preventing a fourfold overstatement
of sample size.

Severity-by-duration combinations: dev and cal draw from combo set A; test additionally contains
held-out combo set B. Also produce an extrapolation slice (unseen values inside wider family ranges)
and an OOD slice (one held-out composition of familiar demand and supply primitives).

### The five integrity assertions

Each is a test, not a comment:

1. Seed pools are pairwise disjoint.
2. No test template id appears in dev or cal.
3. Held-out combos are absent from dev and cal.
4. Every rollout's `independent_unit_id` resolves to exactly one seed.
5. The sample-size function cannot see test data. **Check this statically**, by inspecting the
   signature and the call graph, not by trusting the caller.

### Null bank — 1,000 well-specified plus 300 fragility

| Stratum | Conditional law | Count |
|---|---|---|
| stationary IID | fixed mean and variance | 200 |
| seasonal | registered seasonal mean | 200 |
| overdispersed | registered dispersion | 200 |
| dependent | registered AR structure | 200 |
| censored observation | sales given availability | 200 |

Plus 300 fragility episodes that carry no target shock but **violate** the registered law:
unexpected autocorrelation, a variance change, unmodelled seasonality, outliers. These are reported
separately and never pooled with the 1,000. They answer a different question: not "is the test
calibrated" but "what happens when the model is wrong".

Alert schedules across both groups are balanced over silent, neutral, false, and distractor, so the
LLM is exercised rather than bypassed. The bank measures the **pipeline's** false-activation rate,
not the verifier's in isolation.

Seeds for the bank are disjoint from every other pool, and a test must assert that no audit
trajectory is reachable from tuning, compiler selection, or confirmatory code.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_pause_conservation` | units dispatched equal units received plus in transit plus declared losses, every period, random dispatch sequences |
| `test_zero_arrivals_during_pause` | and correct resumption after it |
| `test_pause_delays_by_exactly_the_pause_length` | consistent with the frozen supply semantics |
| `test_split_integrity` | the five assertions |
| `test_manifest_byte_stable` | regeneration is byte-identical |
| `test_nullbank_seeds_disjoint` | and unreachable from confirmatory code |

### Audit command

```bash
uv run pytest tests/test_families.py tests/test_splits.py tests/test_nullbank.py -q
uv run python -m tools.build_shockspec --all --out manifests/shockspec_v1.json
uv run python -m tools.build_shockspec --all --out /tmp/again.json && diff -q manifests/shockspec_v1.json /tmp/again.json && echo BYTE-STABLE
```

### Pass criteria

- Every test green, byte-stability demonstrated.
- `manifests/shockspec_v1.json` present with the exact counts above.
- A printed side-by-side of arrival timelines for pause, loss, and shift on one seed. Three visibly
  different supply behaviours from one baseline.

### Not expected yet

Running the null bank through the pipeline. That is a post-sprint task and needs LLM budget.

---

## Deferred past this sprint

Named now so nobody discovers them at day 9:

- The H&M real track. Needs an LFS pull and carries semi-synthetic caveats.
- Executing the 1,300-episode audit through the full pipeline.
- The extrapolation and OOD slices may be **built but not exercised**; they feed robustness sweeps
  that run after the pilot.

## Standing rules that bite this module hardest

- `incident.json` is hidden truth. The generator writes it; nothing but the oracle arm and the
  evaluation code reads it. Your writer must never place any incident field into `test.csv`.
- No pattern names, article ids, or family labels in anything a policy can observe.
- Every parameter above is registered in `prereg/prereg_v1.yaml` by module 07. Coordinate with P4 at
  Checkpoint 2 so the two do not disagree.
