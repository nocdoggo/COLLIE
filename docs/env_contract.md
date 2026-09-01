# InventoryBench environment contract (audited)

Task 2 output. Generated evidence lives in `manifests/benchmark_v1.json`; regenerate both with
`make audit`. Benchmark pinned at `62b1f1162f19a41d428d47c6cd4ca431f098f6f3`, read-only.

**Every downstream module reads the cap, the event ordering, and the horizon from here or from
the manifest. No module may hard-code them, and no module may transcribe them from either design
document's prose.**

## 1. Instance inventory

| | count | horizon (decisions) | promised lead time | actual lead times |
|---|---|---|---|---|
| `synthetic_trajectory/lead_time_0` | 240 | 50 | 0 | {0} |
| `synthetic_trajectory/lead_time_4` | 240 | 50 | 4 | {4} |
| `synthetic_trajectory/lead_time_stochastic` | 240 | 50 | 2 | {1, 2, 3, inf} |
| `real_trajectory/lead_time_0` | 200 | 47 | 0 | {0} |
| `real_trajectory/lead_time_4` | 200 | 47 | 4 | {4} |
| `real_trajectory/lead_time_stochastic` | 200 | 47 | 2 | {1, 2, 3, inf} |
| **total** | **1320** | | | |

10 synthetic families `p01_stationary_iid … p10_autocorrelated`, 4 variants × 2 realizations ×
3 cost ratios (`low`/`med`/`high`) × 3 lead-time settings = 720. 200 H&M article ids × 3
lead-time settings = 600. All 600 real instances carry a `description_<id>` column; no synthetic
instance does. Profit per unit is constant within every one of the 1,320 instances, which is why
the evaluator may read it from the first row.

## 2. Ambiguities, resolved

### 2.1 Horizon — real is 47 decisions, not 48

Unanimous across all instances: real `test.csv` has 47 data rows, synthetic has 50. The root
README's "48" counts physical lines including the header; files end with a trailing newline, so
`wc -l` returns header + data. Doc 3.5's audit was correct. Real dates run 2019/2/11 → 2019/12/30
weekly. `eval/run_baseline_policy.py` sets `num_periods = len(test_df)`, so the horizon is the
data-row count.

**Derived, not transcribed:** one always-online sweep over the full benchmark is
`720 × 50 + 600 × 47 = 36,000 + 28,200 =` **64,200 calls**. Our independent derivation matches
doc 3's audited figure.

### 2.2 Lead times — the two documents are both correct, about different quantities

Not a contradiction. There are two distinct quantities:

- **Promised** lead time, passed to `InventoryPolicy.__init__`, derived from the directory name by
  `eval/run_baseline_policy.py::detect_promised_lead_time`: `lead_time_0 → 0`, `lead_time_4 → 4`,
  `lead_time_stochastic → 2`. So `eval/README.md`'s `{0, 2, 4}` is right.
- **Actual** per-period lead time, a `lead_time_<item_id>` column in `test.csv`, never shown to
  the policy: `{0}`, `{4}`, or `{1, 2, 3, inf}`. So the root README's
  `{0, 4, stochastic{1,2,3,inf}}` is also right.

`inf` encodes a **lost shipment**. 440 instances (exactly the stochastic third) contain at least
one lost period.

### 2.3 Order cap — none exists, so ours is registered as ours

There is no upper bound on the order anywhere in the benchmark. The only order-side validations
are unknown-item and negative-quantity rejection in `env.py`; the eval harness applies
`max(0, int(order_quantity))`, which truncates toward zero and imposes no ceiling.

**Consequence:** COLLIE defines `C_t` itself and registers it in `prereg/prereg_v1.yaml`. Every
table that depends on the cap must state that the cap is ours, not the benchmark's. The controller
reads it from the contract object, never from a literal.

**Do not confuse this with the published baseline's cap.** The published entry is named "OR
(capped base stock)", and its `capped` policy does contain a quantity limit — but that limit is
*inside the policy*, an order smoother its authors chose, computed from the demand history as
`mean + Φ⁻¹(0.95)·std` (see §8.5). It is not a constraint the environment enforces, and a policy
is free to ignore it. Ours is an environment-side constraint applied by the runner after the
policy has spoken. Two different objects that happen to share a word.

## 3. Per-period event ordering (authoritative)

Identical in `eval/run_baseline_policy.py` and `eval/evaluate_results.py`:

```
for each period t:
  1. DECISION   policy sees on_hand, aggregate in_transit_total, previous_{demand,order,arrivals},
                profit_t, holding_t, promised_lead_time
                q_t <- policy.get_order(...)
                q_t <- max(0, int(q_t))                 # truncation toward zero, NO upper cap
                if L_actual(t) is finite: schedule q_t to arrive at t + L_actual(t)
                else:                     q_t is LOST (never scheduled)
  2. ARRIVAL    arrivals_t <- pop(scheduled for t); on_hand += arrivals_t
  3. DEMAND     units_sold = min(demand_t, on_hand); on_hand -= units_sold
  4. REWARD     period_profit  = profit_t  * units_sold
                period_holding = holding_t * on_hand      # ENDING inventory, after demand
```

Episode aggregates:

```
total_reward       = total_profit - total_holding_cost
perfect_foresight  = profit_per_unit[first row] * total_demand      # sell everything, zero holding
normalized_reward  = max(0, total_reward / perfect_foresight)
```

Three consequences that the runner must reproduce exactly:

1. **`L = 0` arrives same-period.** Scheduling happens in step 1 and the pop in step 2, so an
   order placed at `t` with `L_actual = 0` is available to meet demand at `t`.
2. **The in-transit total shown at `t` still includes units that land at `t`,** because the pop
   happens after the decision. A controller crediting the pipeline must not also expect those
   units to appear again.
3. **Holding is charged on ending inventory,** so units that arrive and immediately sell incur no
   holding cost.

Unmet demand is **lost**, never backordered: the shortfall is not carried forward and no backorder
state exists. This is what makes "total lost-sales units per episode" a coherent safety endpoint.

## 4. Observability

| Quantity | Visible to the policy? |
|---|---|
| on-hand inventory | yes |
| aggregate in-transit total | yes, **scalar only, no shipment ages** |
| previous demand | yes, **uncensored actual demand**, not sales |
| previous order, previous arrivals | yes |
| per-period profit and holding cost | yes |
| promised lead time | yes, at init |
| **actual** lead time | **no** |
| product description | real instances only |
| which shipment a receipt belonged to | **no** |

Two load-bearing consequences, both confirmed at the code level:

- Because `previous_demand = actual_demand` (not `units_sold`), the headline setting exposes true
  demand even during a stockout. The censored-sales sensitivity setting is therefore a genuinely
  different observation model, not a relabeling.
- Because in-transit is a scalar with no ages, a shipment-age view must be **imputed** from our own
  orders plus observed receipts. That imputation is a control convenience only and must never be
  used as evidence, since many shipment-level histories are consistent with the same aggregate
  receipts. This is exactly why the verifier marginalises over cohort assignments (Task 16) instead
  of adopting the controller's FIFO ledger.

## 5. Divergence between the two harnesses — pick one and say so

The benchmark ships two simulators and they **disagree on lost-order visibility**:

| | `or_agent/envs/VendingMachine/env.py` | `eval/run_baseline_policy.py` |
|---|---|---|
| lost order (`L = inf`) | stays in in-transit **forever** (`arrival_day = inf`, never popped; comment: "lost orders still show as in-transit") | **never added** to in-transit |
| used by | the four published agents via `scripts/run_*.py` | the submission/scoring path |

This changes what pipeline crediting (`γ`) means. Under the env path a lost shipment permanently
inflates the perceived pipeline, so a `γ = 1` controller is misled indefinitely. Under the eval path
a lost shipment is invisible except as an absent arrival.

**Decision:** the **`eval/` path is authoritative** for COLLIE's runner, for arm 1, and for every
arm we implement, because it is the contract we are scored against. Legacy every-period arms 3 and 5
are reproductions of published agents that run through the env path, so any comparison involving them
must state which in-transit semantics applied. Recorded in `prereg/prereg_v1.yaml`.

## 6. Things we defined ourselves

Anything in this list is ours, not the benchmark's, and must be labelled as such wherever it affects
a reported number.

1. **Order cap `C_t`** — no cap exists upstream (§2.3). Registered in the prereg.
2. **Authoritative simulator choice** — the `eval/` path, given the §5 divergence.
3. **Project-owned instance extensions** — `supply.csv` and `incident.json` (§7).

## 7. What our shock families can and cannot encode natively

The audit revises an assumption carried in both design documents. `test.csv` already contains a
per-period `lead_time` column, so more is natively expressible than assumed:

| Family | Natively expressible in `test.csv`? |
|---|---|
| 1–3 demand shocks (level up, level down, temporary pulse) | **yes**, via the `demand` column |
| 4 persistent lead-time shift | **yes**, via the `lead_time` column |
| 5 lost-shipment burst | **yes**, via `lead_time = inf` |
| 6 transit pause (and the compound family containing it) | **no** |

Transit pause is not expressible because both harnesses fix `arrival_day` at order time
(`env.py::update_item_config` states that lead-time changes affect only *new* orders). A pause must
freeze cohorts **already in transit**, which no per-period order-time lead time can express. So the
project-owned `supply.csv` + `incident.json` sidecar is required specifically for the pause and
compound families, and is neutral elsewhere.

This is narrower than "supply shocks need a sidecar" and it is the better outcome: four of six
families ride on the unmodified instance format, and our runner's neutral-sidecar mode is exercised
by the majority of the dataset.

## 8. Facts established while proving accounting equivalence (Task 4)

Four further facts came out of Task 4, all of them checked against all 1,320 instances rather than
assumed. Each one is load-bearing for a claim made elsewhere.

### 8.1 Every economic cell is integer-valued

Across all 1,320 instances, every `demand_*`, `profit_*`, and `holding_cost_*` cell is an integer.
Orders are integers too, after the benchmark's own `max(0, int(q))`. On-hand inventory is therefore
integral at every step, and every product and sum in the accounting is exact in float64.

This is why the equivalence suite demands a maximum absolute difference of **exactly `0.0`** rather
than a tolerance: at this scale there is no floating-point noise to absorb, so a nonzero difference
could only mean a semantic disagreement. It also means the two different summation strategies inside
`evaluate_results.py` — a sequential loop for `total_demand`, pandas' pairwise `.sum()` for the
perfect-foresight bound — cannot disagree.

### 8.2 Holding cost is always 1.0; the cost ratio is a three-valued label

`holding_cost` is `1.0` in every instance, and `profit` takes exactly three values. The synthetic
directory tokens line up with them exactly, and the real instances use the same three:

| Label | Profit | Holding | holding/profit | Synthetic count | Real count |
|---|---|---|---|---|---|
| `high` | 19.0 | 1.0 | 1/19 | 240 | 207 |
| `med` | 4.0 | 1.0 | 1/4 | 240 | 181 |
| `low` | 1.0 | 1.0 | 1 | 240 | 212 |

**The labels name the margin, not the holding burden.** `low` is the punishing case, where holding a
unit for one period costs a full unit of profit. Any table axis built on these labels has to say so
or it reads backwards. Stratification uses exact profit identity, never distance-based binning; an
unaudited profit value raises rather than being assigned to the nearest bin.

Note the real instances are *not* balanced across the three (207/181/212), and an article's profit is
not constant across its three lead-time copies, so the counts are not divisible by three.

### 8.3 Transit pause freezes progress, not arrival

Our cohort supply model carries remaining transit time rather than an absolute arrival period, since
an absolute arrival date cannot be deferred. Where the pause semantics were underdetermined we chose:
**a pause freezes the transit clock of cohorts still moving, and never holds back a cohort whose
transit is already complete.**

The reason is that it preserves the reference invariant that units with zero remaining transit at
decision time always land in the current period — which is exactly what the OR compiler's pipeline
crediting relies on. Under either candidate rule a pause of length `k` delays each affected shipment
by exactly `k` periods, so nothing is lost by taking the one that keeps the invariant. With no pause
active the cohort model is proved indistinguishable from the reference's arrival-keyed dict.

### 8.4 The harness divergence moves policy inputs, not physics

Section 5 records that `env.py` keeps lost orders in in-transit forever while `eval/` never adds
them. Task 4 pinned down its consequences:

- It reaches a policy that reads `in_transit_total`, and **cannot** reach one that ignores it.
- It never changes the physics. Replaying a run's orders under the other harness reproduces the
  arrivals, the reward, and the lost-unit total exactly.
- Switching our runner to `env.py` semantics changes the numbers on **exactly** the 72 stochastic
  lead-time instances in the equivalence set and on none of the other 144. This was measured, by
  running the suite both ways.

So a base-stock policy orders *less* under `env.py` semantics — it credits units that will never
arrive — and consequently loses fewer units. That is a consequence of different orders, not of
different physics, and it is why `eval/` is authoritative for anything we submit or report.

### 8.5 The published OR baseline, reproduced exactly — and which harness produced it

Arm 1 reimplements `scripts/run_or.py::ORAgent` with `policy='capped'`, the published "OR (capped
base stock)" entry that scores 0.4447. Reimplemented rather than wrapped, because the published
agent reads its state by parsing a text observation built for a game harness.

The policy, with `L` the **promised** lead time, `d̄` and `s_d` the running mean and sample standard
deviation (`ddof=1`) of the train samples followed by every demand observed so far:

```
q  = p / (p + h)                          z* = Φ⁻¹(q)
μ̂  = (1 + L)·d̄                            σ̂  = √(1 + L)·s_d
S  = μ̂ + z*·σ̂
a_uncapped = max(0, ⌈S − (on_hand + in_transit)⌉)
a          = max(0, min(a_uncapped, ⌈cap⌉))
```

**The cap is lead-time independent.** Upstream writes it as `μ̂/(1+L) + Φ⁻¹(0.95)·σ̂/√(1+L)`, but
substituting the definitions of `μ̂` and `σ̂` cancels every `L`, leaving `d̄ + Φ⁻¹(0.95)·s_d` — one
period of demand at the 95th percentile. Upstream's separate `L = inf` branch computes that exact
expression, so it is mathematically redundant. We implement the reduced form.

**The estimator has already seen period `t−1` when it decides at `t`.** Recording the observation
after deciding leaves it one sample short and lags the entire order sequence by a period. Invisible
in an aggregate score, obvious at order level; `tests/test_arm1_base_stock.py` guards it.

Reproduction results, scored by the official `eval/evaluate_results.py`:

| Batch | Published | arm 1, `env` | arm 1, `eval` |
|---|---|---|---|
| `real_trajectory/lead_time_0` | 0.670765 | 0.670765 | 0.670765 |
| `real_trajectory/lead_time_4` | 0.301651 | 0.301651 | 0.301651 |
| `real_trajectory/lead_time_stochastic` | 0.209993 | 0.209993 | **0.339931** |
| `synthetic_trajectory/lead_time_0` | 0.817876 | 0.817876 | 0.817876 |
| `synthetic_trajectory/lead_time_4` | 0.535855 | 0.535855 | 0.535855 |
| `synthetic_trajectory/lead_time_stochastic` | 0.106834 | 0.106834 | **0.416796** |
| **overall** | **0.4447102** | **0.4447102** | **0.5207544** |

Under `env.py` semantics the reproduction is exact: all six batch means agree to 1e-12, the overall
agrees to one ULP, and **all 1,320 published order sequences match bit for bit**. Order-level
identity is a far stronger check than an aggregate, which many different policies could hit.

**Therefore the published OR figure was generated under `env.py` lost-order semantics.** Under the
authoritative `eval/` path, exactly 880 of the 1,320 order sequences still match and all 440 differ
— and 440 is precisely the number of instances §2.2 found to contain at least one lost shipment, so
the divergence is fully accounted for with no residue.

The direction is worth noting: the `eval/` path scores **higher** (0.5208 vs 0.4447). Under `env.py`
the policy keeps crediting units in transit that will never arrive, so it under-orders after every
loss. That is a harness artefact penalising the baseline, not a property of the policy.

**Reporting rule.** The published 0.4447 is not reachable from the submission path. Any table
comparing against it must name the harness, and our own submitted figures use `eval/`. Both numbers
are regenerated by `make arm1` into `reports/arm1_or_baseline.md`.
