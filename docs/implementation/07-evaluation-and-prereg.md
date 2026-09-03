# 07. Preregistration, evaluation engine, and the pilot

| | |
|---|---|
| **Owner** | P4 |
| **Checkpoint 1** | Day 5 |
| **Checkpoint 2** | Day 10 |
| **Depends on** | every other module; the pilot depends on all of them |
| **Consumed by** | the pilot decision, and everything after this sprint |
| **Joint work** | Day 10, the pilot, all four |

## What you are building

The thing that decides whether the project has a result, and the discipline that stops us from
deciding it twice.

Three pieces:

1. **The preregistration.** Every threshold, weight, contrast, and kill criterion, written down and
   hashed **before** any test trajectory runs.
2. **The evaluation engine.** Every reported number, computed from stored run records, with a guard
   that refuses to label anything confirmatory unless the preregistration names it.
3. **The pilot.** A real run at reduced scale, evaluated against the frozen criteria, with the verdict
   recorded and dated.

**The pilot is allowed to kill the project.** That is not a formality. Eight kill-or-reframe triggers
are registered, and a run that fires one produces a negative result written up honestly rather than a
positive result found by looking harder. The purpose of writing them down first is that they cannot be
renegotiated once the estimates are visible.

## Where the code goes

```
prereg/
  prereg_v1.yaml            the registration
  freeze_manifest.json      generated
  contract_freeze.json      exists, Gate 1
  deviations.md             exists
collie/eval/
  endpoints.py     primary endpoints and stratum weighting
  guards.py        aggregation-unit guard, confirmatory-render guard
  operational.py   CVaR10, fill rate, recovery time, streaks
  hypothesis.py    per-field macro-F1, abstention, activation delay
  efficiency.py    calls, tokens, latency, cost, Pareto frontiers
  report.py        table and figure rendering
  submission.py    exists
tools/
  freeze.py        the method freeze over all registered files
  run_pilot.py
tests/
  test_prereg_freeze.py  test_endpoints.py  test_guards.py
  test_operational.py    test_hypothesis_metrics.py  test_efficiency.py
```

## Checkpoint 1 — Day 5: the preregistration, written and hashed

Deliberately early. A registration written **after** the code is a rationalisation of what the code
happens to do.

### `prereg/prereg_v1.yaml` must contain

- **Primary endpoints.** Cumulative undiscounted profit; total lost-sales units.
- **Stratum weights.** Equal across 6 families plus 1 null; equal across the 4 information conditions
  within a family; equal across silent and false-alert controls.
- **The three confirmatory contrasts** and the **Holm family** over the six endpoint-by-contrast tests.
- **Alpha allocation.** Episode-level alpha and the `2^-j` split.
- **Trigger thresholds**, calibrated on dev and cal only.
- **The controller grid and our cap**, labelled as ours.
- **The compiler mapping table**, from P1. Coordinate; it must match the code exactly.
- **Schema thresholds**, oracle mappings, and the provisional trust-region definition.
- **The power rule**, which may read calibration data only.
- **All seven numeric kill thresholds** and the eight kill-or-reframe triggers.

Values come from the module owners. Your job is that they are written down, internally consistent, and
frozen. A threshold that exists only in code is not registered.

### `tools/freeze.py` and the guard

Hash the registered file list plus the git SHA into `prereg/freeze_manifest.json`. The guard fails on
any mismatch without a dated entry in `prereg/deviations.md`.

The Gate 1 pattern already exists in `tools/freeze_contracts.py`; follow it, including the rule that a
declared deviation must quote the **new** hash, so one stale entry cannot authorise every later edit.

`make freeze` is currently a stub that errors and points at `make freeze-contracts`. Task 19.2 replaces
it. Registered files at minimum:

```
collie/contracts.py            collie/spec/registry.py      collie/spec/schema.py
collie/control/mapping.py      collie/control/grid.py       collie/control/forecast.py
collie/verify/registry.py      collie/verify/alpha.py       collie/trigger/detectors.py
prereg/prereg_v1.yaml          manifests/shockspec_v1.json
```

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_prereg_parses_and_is_complete` | every required section present, no `TODO` |
| `test_all_seven_kill_thresholds_are_numeric` | not prose |
| `test_holm_family_has_six_members` | three contrasts x two endpoints |
| `test_stratum_weights_sum_to_one` | per weighting scheme |
| `test_compiler_mapping_matches_the_code` | registered table equals `collie.control.mapping` |
| `test_freeze_manifest_covers_every_registered_file` | |
| `test_deliberate_edit_turns_the_guard_red` | prove the tripwire fires |
| `test_power_rule_cannot_see_test_data` | statically |

### Audit command

```bash
uv run pytest tests/test_prereg_freeze.py -v
make freeze && uv run python -m tools.freeze --check
```

### Pass criteria

- `prereg_v1.yaml` complete, with no placeholder.
- `make freeze` emits the manifest; a deliberate edit demonstrably turns the guard red.
- A printed summary of the three contrasts, the six Holm tests, and the seven kill thresholds. The
  auditor reads these as commitments, because that is what they are.

### Not expected yet

The evaluation engine, the pilot.

---

## Checkpoint 2 — Day 10: engine renders, pilot run, decision recorded

### The aggregation-unit guard, first

Write this before any metric.

> **Refuse any confirmatory statistic computed from a frame with more than one row per
> `(independent_unit_id, arm)`.**

The four information conditions of one seed are **paired replays of one independent unit**. Treating
them as four samples would inflate the effective sample size fourfold and narrow every interval by
roughly half. It is the single easiest way to produce a confident wrong answer in this design, and it
would not be visible in any output.

The guard raises. It does not warn.

### Metrics

**Primary.** Cumulative undiscounted profit; total lost-sales units. Equal stratum weights as
registered.

**Compatibility.** The official normalized reward, a micro-average, and a 70/15/15 deployment mixture
with prevalence sensitivity. The official metric matters because it is what a leaderboard reader
recognises. Where you report it against the published OR figure, **name the harness** — the published
0.4447 is an `env.py` number and is not reachable from the submission path. See `docs/env_contract.md`
sections 8.4 and 8.5.

**Operational.** CVaR10, worst decile, fill rate, lost-sales units, max stockout streak, holding cost,
post-recovery excess inventory, and time to recovery, defined as the first of three consecutive
post-shock periods with fill rate at or above 0.95.

Time to recovery needs two adversarial fixtures, both required: an episode that **never** recovers, and
one that touches 0.95 twice with a dip between. A naive implementation returns the first touch and is
wrong in exactly the cases that matter.

**Hypothesis and lifecycle.** Per-field macro-F1, exact match, abstention precision and recall,
magnitude coverage, activation delay, rollback delay, expiration accuracy, wrong-spec exposure, and
benefit given activation.

Keep **false activation** (theorem-covered) separate from **wrong-family activation** (empirical only).
They are different claims with different backing, and merging them would overclaim the theorem.

**Efficiency.** Attempted, repair, and rejected calls; tokens; p50 and p95 latency; dated cost; actions
per accepted call. Pareto frontiers for profit against calls, tokens, and cost on **realised** budgets,
AUC over call fraction on `[0,1]`, and matched-budget points for the token and dollar frontiers.

### The confirmatory-render guard

Every record carries `analysis_class`, which already exists on `EpisodeResult`. The renderer **refuses**
to present anything as `confirmatory` unless its identifier appears in the frozen preregistration.
Family-level CVaR is forced to `exploratory`.

Labelling lives in the record, not in the prose around it. A number that travels without its label
eventually appears in a table without one.

### The pilot

100 to 150 stratified dev and cal episodes, roughly 2,000 to 4,000 calls, through the **real** engine.
Not a smoke test: the same code path the full run will use.

1. Assemble and run.
2. Evaluate the **seven go criteria** with paired intervals. Thresholds are read from the frozen
   preregistration and **never adjusted after seeing the estimates**.
3. Evaluate the **eight kill-or-reframe triggers** explicitly, one by one, in writing.
4. **Quarantine enforcement.** If any frozen hash changed, the confirmatory runner refuses the seeds
   and templates listed in `reports/pilot_manifest.json`. A pilot run against changed method files has
   spent those episodes.
5. **Record the decision and the date, before any test trajectory runs.**

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_aggregation_unit_guard_raises_on_duplicate_rows` | the guard is real |
| `test_confirmatory_render_guard_refuses_unregistered` | |
| `test_family_level_cvar_forced_to_exploratory` | |
| `test_time_to_recovery_never_recovers_fixture` | returns no recovery |
| `test_time_to_recovery_double_touch_with_dip_fixture` | returns the sustained one |
| `test_false_activation_distinct_from_wrong_family` | separate fields |
| `test_stratum_weighting_matches_prereg` | |
| `test_pareto_uses_realised_budgets` | not intended |
| `test_quarantine_refuses_seeds_when_a_hash_changed` | |
| `test_every_reported_number_traces_to_a_record` | no hand-entered values anywhere |

### Audit command

```bash
uv run pytest tests/test_endpoints.py tests/test_guards.py tests/test_operational.py \
              tests/test_hypothesis_metrics.py tests/test_efficiency.py -v
make table-main
uv run python -m tools.run_pilot --episodes 120 --report reports/pilot_report.md
```

### Pass criteria

- All tests green, both recovery fixtures included.
- `make table-main` renders the main table and the frontier plots from dev runs.
- `reports/pilot_report.md` exists, with a **per-criterion verdict** across all seven go criteria and
  all eight kill triggers, and the decision recorded with its date.
- The aggregation-unit guard demonstrably raises on a duplicated frame.

---

## The seven go criteria and eight kill triggers

Their numeric values live in `prereg/prereg_v1.yaml` and are yours to fill in with the module owners at
Checkpoint 1. Fill them in **before** the pilot runs. Two rules:

- A criterion evaluated after seeing the estimate is not a criterion.
- A kill trigger that fires is a **result**, not a setback. The negative-result framing is planned for,
  and a clean negative finding about a mechanism this specific is publishable. What is not publishable
  is a positive finding produced by moving a threshold.

## Deferred past this sprint

Everything downstream of the pilot verdict:

- The full held-out test sweeps, 640 rollouts per sparse arm.
- The 1,300-episode null audit through the full pipeline.
- The robustness sweeps, including the hosted confirmation subset and three decoding seeds.
- Separating semantic content value from early-warning value.
- The confirmatory statistics: paired randomization inference, seed-level cluster bootstrap, Wilcoxon
  secondary, Holm across the six tests.
- Error analysis and the traced case studies.
- Artifact packaging and the reproducibility audit.
- Related-work refresh and the paper.

The engine you build in this sprint is what runs all of it. Build the metrics fully even though the
sweeps come later; retrofitting a metric after the runs means rerunning them.

## Risks specific to this module

- **The registration written too late.** Checkpoint 1 is day 5 for this reason. A registration that
  post-dates the code is a rationalisation.
- **The aggregation-unit trap.** Fourfold sample inflation, invisible in output. The guard is the only
  defence and it must raise rather than warn.
- **Comparing against the published figure without naming the harness.** It is an `env.py` number.
- **Renegotiating a threshold after seeing an estimate.** The freeze guard and the dated deviation log
  exist to make this visible. If a threshold really was wrong, say so in writing, in
  `prereg/deviations.md`, with the date, and accept that the affected contrast becomes exploratory.
