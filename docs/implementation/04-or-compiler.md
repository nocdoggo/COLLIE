# 04. OR compiler, controller, and the FIFO ledger

| | |
|---|---|
| **Owner** | P1 |
| **Checkpoint 1** | Day 4 |
| **Checkpoint 2** | Day 9 |
| **Depends on** | 02 shockspec interface, for the registered vocabularies |
| **Consumed by** | 06 arms, every single one of them |
| **Joint work** | Day 9, with P4: the ledger-is-not-evidence boundary |

## What you are building

The deterministic bridge from a typed hypothesis to inventory-model inputs. A `ShockSpec` goes in, a
`ControlConfig` comes out, and the same capped base-stock controller turns that config into orders.

The design property that matters: **the mapping is a pure, total function of registered spec fields,
and it is registered in the preregistration before any test data is touched.** No learning, no
tuning, no lookup that could be adjusted after seeing results. Given a legal spec, the config is
determined. That is what makes the LLM's contribution auditable — the model chose a hypothesis, and
everything after it is arithmetic anyone can recompute.

**Every arm routes through this controller.** The detector control, the parsing upper bound, the
oracle, and all three ShockSpec arms. If they did not, a profit difference could come from a
different control path rather than from a different hypothesis, and the comparison would be
meaningless. There is a test for this and it is not optional.

## Where the code goes

```
collie/control/
  __init__.py
  grid.py         the 72 configurations
  mapping.py      ShockSpec -> ControlConfig, registered and total
  forecast.py     the frozen base estimator, shared by every arm
  controller.py   capped base-stock, parameterised by ControlConfig
  ledger.py       imputed FIFO ledger
tests/
  test_control_grid.py
  test_control_mapping.py
  test_controller.py
  test_ledger.py
  test_ledger_not_evidence.py
```

## The 72-configuration grid

```python
M_VALUES     = (0.6, 0.75, 1.0, 1.25, 1.5, 2.0)   # 6, demand multiplier
L_EFF_VALUES = (1, 2, 3, 4)                        # 4, effective lead time
GAMMA_VALUES = (0.0, 0.5, 1.0)                     # 3, pipeline credit
# 6 * 4 * 3 = 72
```

`ControlConfig` already exists in the frozen contracts: `m`, `l_eff`, `gamma`, `predictive_model`.

`gamma` is how much in-transit inventory counts toward the position. It is a parameter rather than a
constant because the right answer depends on whether shipments are arriving: crediting a full
pipeline that has stalled is exactly the failure the transit-pause family induces. This connects
directly to the harness divergence in `docs/env_contract.md` section 8.5, where the published
baseline credits units that will never arrive and under-orders as a result.

Enumeration must yield exactly 72 distinct configs, and every one must be reachable from some legal
spec. An unreachable config is dead code in a registered table, which the freeze then blesses.

## The mapping

A pure function with a fixed precedence order:

```
shock_family  ->  direction  ->  magnitude_bin  ->  target_stream
```

Requirements:

- **Total.** Every legal `ShockSpec` maps to exactly one config. Enumerate the schema's legal space in
  a test and assert no gaps; do not sample it.
- **`no_change` maps to the baseline configuration.** Abstention must mean "carry on as before",
  identically to no proposal at all.
- **Registered.** The table goes into `prereg/prereg_v1.yaml`, authored with P4 in module 07. Coordinate
  at Checkpoint 2 so the code and the registration cannot disagree.
- **Pure.** No episode state, no history, no clock. Spec in, config out.

### The `predictive_model` key

`ControlConfig.predictive_model` is emitted here and consumed **twice**: it selects the control
behaviour, and it selects module 05's registered verifier construction.

One key, two consumers. Control acts on it, verification tests it. Every key the compiler emits must
resolve in module 05's construction registry, and that is a joint test.

## The controller

```
IP_t = I_t + gamma * P_t
S_t  = base_stock(m, l_eff, forecast, critical_fractile)
q_t  = min( max(0, S_t - IP_t), C_t )
```

where `I_t` is on hand, `P_t` is the in-transit scalar, and `C_t` is **our** order cap.

Rules:

- `C_t` is read from the environment contract, **never a literal**. The benchmark imposes no cap, so
  ours is registered and must be labelled as ours wherever it appears in a table.
- **No access to actual lead times.** `l_eff` is a compiled belief, not an observation. The
  observation type does not carry actual lead times, so this holds structurally, but assert it.
- The critical fractile is `p / (p + h)` from the per-period cost columns.

**Do not confuse this with arm 1's cap.** Arm 1 reproduces the published baseline, whose "cap" is a
policy-internal order smoother equal to `mean + z_0.95 * std` and algebraically independent of lead
time. That is a different object from `C_t`, which is an environment-side constraint the runner
applies after the policy has spoken. Both exist; they are not the same thing. See
`docs/env_contract.md` sections 2.3 and 8.5.

### The frozen forecast estimator

A plain mean and standard deviation over observed demand history. Deliberately simple, frozen at the
method freeze, and **shared by every arm**, so no arm gets an advantage from a better forecaster. The
comparison is about hypotheses, not about estimators.

One detail that arm 1 already had to get right: the estimator has seen period `t-1`'s demand when it
decides at `t`. Recording after deciding lags the entire order sequence by one period. It is invisible
in an aggregate score and obvious at order level. Use the same convention.

## The imputed FIFO ledger

Reconstruct which order a receipt probably came from, using **only** your own order history and
observed aggregate receipts.

This is an **imputation**, and it must say so. In-transit is a scalar with no ages by benchmark
contract, so any age-resolved view is inferred. Expose the aged-mass estimate behind an explicit
imputation marker.

When the ledger cannot reconcile — receipts that no outstanding order explains — **record the
inconsistency and move on**. Do not rebalance to make the books look tidy. The inconsistency is data:
it is the observable signature of a lost shipment or a stalled pipeline.

Forbidden inputs, all four: `supply.csv`, `incident.json`, shipment ages, actual lead times.

### Ledger is not evidence

The ledger informs **control**. It must never reach the **verifier**.

The verifier's validity argument rests on conditioning only on quantities whose conditional law is
registered. The ledger is an imputation built from the controller's own actions, so feeding it to the
verifier would condition the test on the policy being tested. Circular, and it silently voids the
guarantee.

Enforced two ways, both required:

1. **Static.** AST scan over `collie/verify/` for ledger symbols.
2. **Runtime.** Object-graph walk over verifier inputs using
   `collie.contracts.assert_no_hidden_state` plus an explicit ledger check.

Write a deliberately leaky verifier fixture and prove **both** checks fail on it. This is the joint
deliverable with P4 at Checkpoint 2.

---

## Checkpoint 1 — Day 4: grid, mapping, controller, shared path proved

### Deliverables

1. `grid.py` — 72 configs, enumerable.
2. `mapping.py` — total registered mapping.
3. `forecast.py` — the frozen estimator.
4. `controller.py` — capped base-stock parameterised by `ControlConfig`.
5. The shared-control-path equality test.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_grid_has_exactly_72_distinct_configs` | |
| `test_every_config_is_reachable` | from some legal spec |
| `test_mapping_is_total_over_the_legal_space` | enumerate, do not sample |
| `test_mapping_is_deterministic` | same spec, same config, no state |
| `test_no_change_maps_to_baseline` | |
| `test_predictive_model_key_resolves_in_verifier_registry` | joint with P4 |
| `test_critical_fractile_arithmetic` | against hand-computed values |
| `test_order_is_within_cap` | property: `0 <= q_t <= C_t` over random states |
| `test_higher_m_raises_the_target` | monotonicity in `m` |
| `test_higher_gamma_lowers_the_order` | monotonicity in `gamma`, given in-transit |
| `test_cap_comes_from_the_contract` | AST check: no numeric cap literal in the module |
| `test_controller_never_reads_actual_lead_times` | |
| `test_shared_control_path_byte_identical` | detector control, parsing upper bound, and oracle produce identical orders given the same `ControlConfig` |

`test_shared_control_path_byte_identical` is the most valuable test in this module. Everything the
paper claims about arms rests on the arms differing **only** in how they arrive at a config.

### Audit command

```bash
uv run pytest tests/test_control_grid.py tests/test_control_mapping.py tests/test_controller.py -v
uv run python -m collie.control.mapping --print-table
```

### Pass criteria

- All tests green.
- Printed mapping table: every legal spec shape against its config. The auditor will check that it
  looks like a considered engineering judgement rather than an arbitrary assignment.
- Confirmation that the mapping table has been handed to P4 for registration.

### Not expected yet

The FIFO ledger, the isolation proofs, the regret sweep.

---

## Checkpoint 2 — Day 9: ledger built, isolation proved both ways

### Deliverables

1. `ledger.py` — imputed FIFO with explicit imputation markers.
2. Inconsistency recording, not rebalancing.
3. Static and runtime ledger-not-evidence enforcement, with a failing leaky fixture.
4. Age-binned telemetry behind an all-arms ablation flag.
5. The 72-configuration regret sweep on one family.

### Age-binned telemetry

If enabled, it is available to **every** relevant arm, never ShockSpec-only. Giving one arm a richer
observation and then attributing its advantage to the hypothesis mechanism would be a straightforward
confound. It is an ablation flag, not a feature of one arm.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_fifo_assignment_correctness` | against hand-worked sequences |
| `test_inconsistency_is_recorded_not_rebalanced` | books stay unbalanced, the event is logged |
| `test_ledger_never_reads_forbidden_inputs` | `supply.csv`, `incident.json`, ages, actual lead times |
| `test_aged_mass_carries_imputation_marker` | |
| `test_leaky_verifier_fails_static_check` | AST scan fires |
| `test_leaky_verifier_fails_runtime_check` | object-graph walk fires |
| `test_age_binned_telemetry_available_to_all_arms` | or to none |

### Audit command

```bash
uv run pytest tests/test_ledger.py tests/test_ledger_not_evidence.py -v
uv run python -m collie.control.grid --regret-sweep --family demand_level
```

### Pass criteria

- All tests green, including **both** leaky-fixture failures.
- The oracle-ShockSpec arm on 18 dev episodes, with its profit gap over stationary OR printed. This is
  the headroom number: if the oracle barely beats stationary OR on your generated episodes, the shocks
  are too mild for anything downstream to detect, and module 01 needs to know at day 9 rather than at
  the pilot.
- The 72-configuration regret sweep on one family, showing which region of the grid matters.

### Not expected yet

Running the compiler under real LLM proposals. Module 06 plus the pilot.

---

## Deferred past this sprint

- Tuning the mapping table. It is registered, so tuning it later requires a dated deviation. Get it
  considered now; it is not meant to be revisited.
- The full cross-family regret sweep. One family is enough for the checkpoint.

## Risks specific to this module

- **A mapping that is not total.** A spec with no config crashes an arm mid-episode. Enumerate the
  legal space rather than sampling it.
- **Cap literals creeping in.** Read from the contract. There is an AST test; keep it green.
- **The ledger reaching the verifier.** The most dangerous failure in the project, because it produces
  results that look valid. Two independent checks, and both must have been seen to fail.
- **Oracle headroom too small.** Surface it at Checkpoint 2, not at the pilot. It is a module 01
  problem discovered here.
