# Module 04 — OR compiler, controller, and FIFO ledger: implementation summary

Branch: `module-4-or-compiler`. Two commits, matching the two-week checkpoint structure in
`docs/implementation/README.md` and `docs/implementation/04-or-compiler.md`:

- `cc60294` — Checkpoint 1 (week 1): grid, mapping, forecast, controller.
- `9da9e2e` — Checkpoint 2 (week 2): FIFO ledger, isolation proofs, telemetry, headroom demo.

`collie/contracts.py` (frozen) was not touched in either commit.

## Checkpoint 1 — what was built

| File | Purpose |
|---|---|
| `collie/control/grid.py` | The 72-configuration grid: `M_VALUES × L_EFF_VALUES × GAMMA_VALUES = 6 × 4 × 3`. `predictive_model` is derived as a pure function of `(m, l_eff, gamma)`, not a 4th free axis, so the grid has exactly 72 elements. CLI: `--print-table`. |
| `collie/control/mapping.py` | `ShockSpec -> ControlConfig`: total, pure, deterministic. Two tiers — tier 1 is the semantic core (the 8 shapes a real generator/prompt/repair path would produce); tier 2 is an automatically-built closure covering every other combination the *frozen* schema currently permits, guaranteeing all 72 grid points are reachable. |
| `collie/control/forecast.py` | The frozen mean/std demand estimator shared by every arm, matching arm 1's "record before deciding" convention. |
| `collie/control/controller.py` | `OrCompilerController`, the single controller class every OR-compiler arm wraps: `IP_t = I_t + gamma·P_t`, `S_t = base_stock(...)`, `q_t = min(max(0, S_t - IP_t), C_t)`. |
| `tests/test_control_grid.py`, `test_control_mapping.py`, `test_controller.py` | 48 tests covering every test name `04-or-compiler.md` names for Checkpoint 1. |

### What I did to check it

**Command:**
```bash
pytest tests/test_control_grid.py tests/test_control_mapping.py tests/test_controller.py -v
python -m collie.control.mapping --print-table
```

For each named test, I read the assertion itself rather than trusting a green check mark, specifically to rule out the README's rework triggers ("a test that asserts nothing, or that would pass against a stub"):

- `test_grid_has_exactly_72_distinct_configs` — asserts `len(set(configs)) == 72`, not just `len(configs) == 72`; a dedup bug in `predictive_model_for` would fail this.
- `test_every_config_is_reachable` — set-equality between `{compile_spec(s) for s in iter_legal_specs()}` and `set(all_configs())`, run over the *whole* legal space (271 specs) rather than a sample, per the doc's explicit instruction.
- `test_mapping_is_total_over_the_legal_space` — calls `compile_spec` on all 271 legal specs and requires no exception.
- `test_no_change_maps_to_baseline` — checks equality against `BASELINE_CONFIG` specifically, not "some config."
- `test_predictive_model_key_resolves_in_verifier_registry` — flagged as the weakest test in this checkpoint: module 05 doesn't exist on `main` yet, so it only checks internal consistency against `grid.predictive_model_keys()`, not a real cross-module registry. Recorded as a coordination gap, not silently passed off as done.
- `test_critical_fractile_arithmetic` — hand-computed against `p/(p+h)` for the three registered cost ratios (19, 4, 1 over holding cost 1.0) from `docs/env_contract.md` §8.2, not arbitrary numbers.
- `test_order_is_within_cap`, `test_higher_m_raises_the_target`, `test_higher_gamma_lowers_the_order` — each has both a hand-worked example and a Hypothesis property test with randomized `on_hand`/`in_transit`/`config`, so the claim is checked over a range of states, not one convenient point.
- `test_cap_comes_from_the_contract` — AST-walks `controller.py`'s class body and asserts `order_cap` has no default value, which is the actual mechanism ruling out a hardcoded cap, not a string grep.
- `test_shared_control_path_byte_identical` — read directly rather than trusted: as of this checkpoint it only proves two `OrCompilerController` instances given the same config produce byte-identical decisions, since the real detector/parsing-upper-bound/oracle arms don't exist until modules 02/05/06 land. Documented as a known limitation in the test's own docstring rather than overclaimed.

I also ran `python -m collie.control.mapping --print-table` and read the `[tier1]`-tagged rows by hand against the doc's own criterion ("looks like a considered engineering judgement") — 24 rows (8 shapes × 3 magnitudes), each with a monotonic severity response along the axis its family actually concerns.

**Deviations flagged, per the README's audit-submission format:**
- The mapping table has **not** been handed to P4 for `prereg/prereg_v1.yaml` registration — that file and module 07 don't exist on `main` yet.
- Enumeration is against the *current* frozen `ShockSpec` validator (271 combinations), not module 02's eventual narrower registry, which doesn't exist yet either.

## Checkpoint 2 — what was built

| File | Purpose |
|---|---|
| `collie/control/ledger.py` | Imputed FIFO ledger: assigns aggregate receipts to outstanding orders oldest-first, marks every assignment `imputed=True`, and **records, never rebalances,** a receipt no outstanding order can explain. Provides both the static (AST) and runtime (object-graph) "ledger must never reach the verifier" checks. |
| `collie/control/controller.py` (updated) | Added an optional `ledger: FIFOLedger \| None` hook — a plain constructor kwarg available identically regardless of `arm_id`, not a per-arm feature. |
| `collie/control/mapping.py` (updated) | Recalibrated the `transit_pause`/`compound` severity tables — see the finding below. |
| `collie/arms/oracle.py` | Minimal oracle-arm factory: translates `HiddenIncident` into a `ShockSpec`, compiles it through the identical path every ShockSpec arm uses, and gates activation to the ground-truth onset/duration window. Built only to demonstrate compiler headroom at this checkpoint; the full oracle arm (proposal budget, triggering) is module 06's job. |
| `tests/test_ledger.py`, `test_ledger_not_evidence.py` | 15 tests covering every test name the doc names for Checkpoint 2, including the ablation-flag and both leaky-fixture tests. |

### What I did to check it

**Command:**
```bash
pytest tests/test_ledger.py tests/test_ledger_not_evidence.py -v
python -m collie.control.grid --regret-sweep --family demand_level
python -m collie.control.grid --oracle-headroom
```

- `test_fifo_assignment_correctness` — recomputed the hand-worked sequence in the test by hand (order 10@t1, order 5@t2, receive 12@t3 → ages 2 and 1, 3 outstanding) rather than trusting the assertion.
- `test_inconsistency_is_recorded_not_rebalanced` — checked that `outstanding_total == 0.0` **and** `inconsistencies` is non-empty **and** the aged mass still reflects only what was actually explained — the doc calls this the dangerous failure mode, so I read the ledger's `record_receipt` logic directly rather than trusting the test alone.
- `test_ledger_never_reads_forbidden_inputs` — implemented as an AST walk rather than a string grep, deliberately: a grep version failed during development because the module's own docstring legitimately names `supply.csv`/`incident.json` as the forbidden inputs it's explaining. Confirmed the AST version excludes docstring nodes specifically and nothing else.
- `test_leaky_verifier_fails_static_check` / `test_real_verify_package_has_no_ledger_references_today` — ran both together on purpose: one proves the scan fires on a real leaky fixture written to a temp file, the other proves it's clean against the actual (currently empty) `collie/verify/`. Either alone would leave open the possibility the check passes vacuously.
- `test_leaky_verifier_fails_runtime_check` — nests a real `FIFOLedger` three levels deep in a fake verifier-input dataclass and confirms `assert_no_ledger_state` raises with the exact access path (`obj.telemetry['pipeline']`), not just that it raises *something*.
- `test_age_binned_telemetry_available_to_all_arms` — builds two `OrCompilerController`s with different `arm_id`s, each given its own ledger, and asserts identical recording. I additionally grepped `controller.py` for `arm_id ==` to independently confirm there's no branch keying the telemetry hook on arm identity.

**The regret sweep and oracle-headroom numbers were read, not just checked for a zero exit code:**
- `--regret-sweep --family demand_level` — sanity-checked that the top-ranked configs have `m > 1.0` (a demand-level fixture is an up-shock), which they do.
- `--oracle-headroom` — this is where a real problem surfaced (below). I did not accept the first run's output at face value; a negative gap prompted investigation rather than being reported as-is.

### A real finding: the oracle-headroom demo caught a bad calibration

Building `--oracle-headroom` first came back **negative** (oracle mean reward 2935.54 vs. stationary 4265.66, gap **-1330.13**) instead of the expected "headroom, possibly small" signal the checkpoint doc anticipates. I did not treat this as acceptable exploratory noise and instead traced it to two causes:

1. **No lifecycle gating.** The first version applied one static `ControlConfig` for the entire episode. Fixed by giving the oracle a privileged activation window from `HiddenIncident.onset_period`/`duration` — real ShockSpec arms will get this from module 05's verifier lifecycle instead; this is a documented demo-only shortcut in `oracle.py`.
2. **`transit_pause`/`compound` overshoot.** Their original mapping paired a `gamma` cut with an `l_eff` raise. Under this project's authoritative `eval/` in-transit semantics (`docs/env_contract.md` §5, a lost order is never added to in-transit), there is no phantom pipeline credit for a gamma cut to correct — it only makes the controller distrust real, arriving inventory, and when a merely-*paused* (not lost) shipment lands, the resulting double-order and the delayed shipment arrive together, a bullwhip spike. I isolated this by sweeping `(l_eff, gamma)` combinations directly against the fixture and confirming `gamma=1.0` dominated every cut value at every severity level tested. Recalibrated both families in `mapping.py` to keep `gamma = 1.0` through low/medium severity, cutting it only at high severity.

After both fixes: oracle beats stationary OR on all 6 non-abstention families (overall mean gap **+793** reward over 18 dev episodes). I reran the full test suite and lint after the recalibration to confirm nothing else regressed.

## Full verification, both checkpoints combined

- `pytest tests/ -m "not needs_benchmark and not needs_llm and not equivalence and not slow"` — 377/377 pass (pre-existing tests untouched; 232 deselected tests need the InventoryBench submodule/LFS, not present in this environment).
- `ruff check` / `ruff format` — clean across `collie/` and `tests/`.
- CI (`.github/workflows/ci.yml`) triggers automatically on push to any branch and runs the broader suite plus lint, the frozen-contract check, and the benchmark-manifest drift checks — a regression safety net, not a substitute for the checkpoint-specific judgment calls above.

## Open coordination items (not blockers)

- Mapping table (tier 1) needs to be handed to P4 for registration in `prereg/prereg_v1.yaml` — that file and module 07 don't exist on `main` yet.
- `test_predictive_model_key_resolves_in_verifier_registry` checks internal consistency only today; extend it to cross-check `collie.verify.registry.CONSTRUCTIONS` once module 05 lands.
- Tier 2's closure in `mapping.py` is provisional pending module 02's legal-pairing registry; reachability will need re-deriving from tier 1 alone once that lands, and the `transit_pause`/`compound` severity numbers above should be re-validated against module 01's real (non-fixture) shock distribution before the prereg freezes.
