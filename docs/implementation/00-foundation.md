# 00. Foundation — the substrate you build on

**Status: built, on `main`, and frozen.** This is not a work assignment. It is the reference for
what already exists, what you may rely on, and what you must not change.

Read this before your module document. Most integration mistakes in the next two weeks will come
from re-implementing something listed here.

## What is guaranteed

| Guarantee | Where it is proved |
|---|---|
| Our runner matches the official pipeline exactly, max abs diff `0.0`, 648 comparisons | `reports/equivalence_report.md` |
| Arm 1 reproduces the published OR baseline, all 1,320 order sequences bit for bit | `reports/arm1_or_baseline.md` |
| The environment contract is audited from code and data, not from prose | `docs/env_contract.md`, `manifests/benchmark_v1.json` |
| Hidden state cannot reach a policy | `tests/test_contracts.py`, `tests/test_episode_runner.py` |
| Only `collie/adapter/` reaches the benchmark | `tests/test_project_skeleton.py` |
| The statistical argument, with its scope limits | `docs/derivation_note.md` |

Verify the whole lot in one command:

```bash
make gate1
```

## Frozen: `collie/contracts.py`

The shared vocabulary of every module. **Hashed in `prereg/contract_freeze.json` and guarded.**
Changing it requires a dated entry in `prereg/deviations.md` quoting the new sha256, then
`uv run python -m tools.freeze_contracts`. `make check-freeze` fails until both are done.

If you think you need a new field, raise it before writing code. A contract change mid-sprint
invalidates work in every other module.

**Closed vocabularies.** `ShockFamily`, `TargetStream`, `Direction`, `MagnitudeBin`, `Persistence`,
`DurationBin`, `LifecycleState`, `ParseOutcome`, `SupplyEffectKind`, `ObservationMode`, `AlertKind`,
`InformationCondition`, `Split`, `AnalysisClass`. All `StrEnum`. Do not add a member locally; add it
to the registry in your own module if it is module-specific vocabulary.

**Observable types.** `AlertMessage`, `EpisodeSpec`, `PeriodObservation`.

`PeriodObservation` is the complete list of what a controller may see. It carries
`promised_lead_time` and deliberately carries no actual lead time: upstream's own contract states
the policy must infer arrival behaviour from arrivals. `in_transit_total` is a scalar with no
shipment ages, and at decision time it already includes units landing this period.

**The commitment.** `ShockSpec` is a pydantic model with `extra="forbid"` and `frozen=True`. Those
two settings carry the validity argument: the model cannot smuggle in a falsifier, threshold,
likelihood, order equation, or code, and the object cannot be edited after `tau_j`.

**Hidden types.** `SupplyEffect`, `HiddenAlertSpec`, `HiddenIncident`, `SupplyRealization`. These
are what the isolation rules are about.

**Outputs.** `ControlConfig`, `Decision`, `CallLog`, `RunRecord`, `EpisodeResult`.

`CallLog` distinguishes `physical` from charged. One physical request shared by three arms is one
physical log and three charged copies. `RunRecord` carries `template_id` because language claims
bootstrap jointly over seed and template; `AlertMessage` deliberately does not, so no policy can key
on it.

**Protocols.** `Controller`, `SupplyProcess`, `Trigger`, `LLMClient`. Implement these; the runner
never learns which arm it is executing.

**Isolation tooling.**

```python
from collie.contracts import find_hidden_state, assert_no_hidden_state, HiddenStateLeak

assert_no_hidden_state(obj, context="my verifier inputs")   # raises HiddenStateLeak
paths = find_hidden_state(obj)                              # ['obj.foo[2].incident', ...]
```

Structural, not name-based: a leak through an undeclared attribute, a dict value, or a nested
container is caught the same way. Use it in your own tests.

## The simulator: `collie/sim/`

```
loader.py             load_instance(dir, *, episode_id, promised_lead_time, order_cap,
                                    observation_mode, split) -> LoadedInstance
supply.py             LeadTimeSupply (cohort remaining-time), ArrivalKeyedSupply (test oracle)
observation.py        build_observation(...), PriorPeriod
accounting.py         clamp_order, settle_period, aggregate_episode
runner.py             EpisodeRunner, EpisodeOutcome
reference_policies.py frozen instrumentation for the equivalence suite, not a research arm
```

**`EpisodeRunner` is the only place an episode is executed.** It implements the audited event order
and takes no arm-specific branches.

```python
outcome = EpisodeRunner(
    instance=loaded,
    alerts={7: AlertMessage(...)},          # period -> message, from module 03
    template_ids={7: "tpl_042"},            # analysis-side only
    lost_orders_visible_in_transit=False,   # False = authoritative eval/ semantics
    strict_isolation=True,                  # walks every observation for hidden state
    check_controller_isolation=False,       # turn on for every arm except the oracle
).run(controller)
```

Per-period order, which you must not reimplement: read `in_transit_total`, build the observation,
call the controller, clamp with `max(0, int(q))` then our cap, dispatch, pop arrivals, resolve
demand as `min(demand, on_hand)`, charge holding on **ending** inventory.

Consequences that trip people up: with `L = 0` an order lands in the same period; unmet demand is
lost, never backordered; holding is never charged on units that arrived and sold in the same period.

**Supply semantics.** `LeadTimeSupply` carries remaining transit time per cohort, because an
absolute arrival date cannot be deferred and a transit pause must defer one. A pause freezes the
clock of cohorts still moving and never holds back a cohort whose transit is already complete. With
no pause active it is provably indistinguishable from the reference's arrival-keyed dict.

## The one seam: `collie/adapter/inventorybench.py`

The only module permitted to reach `third_party/InventoryBench`, by import or by path. Both are
enforced by AST test, including string literals naming the submodule path.

```python
from collie.adapter.inventorybench import (
    benchmark_root, submodule_root,
    official_simulate_instance, official_simulate_and_score,
    official_detect_promised_lead_time, official_load_instance, official_policy_base,
)
```

If you need something from upstream, add a thin pass-through here. Do not reach around it. The point
is that when the pin moves, exactly one file needs re-auditing.

## Instance selection: `collie/data/instances.py`

```python
enumerate_instances() -> tuple[InstanceKey, ...]     # all 1,320, sorted, with strata
stratify(keys) -> dict[(trajectory, lead_time_label, cost_ratio_label), tuple[InstanceKey, ...]]
stratified_sample(keys, per_cell=12) -> tuple[InstanceKey, ...]   # even stride, no RNG
```

**Cost-ratio labels name the margin, not the holding burden.** Holding cost is `1.0` in every one of
the 1,320 instances and profit is one of three values: `high` is profit 19, `med` is 4, `low` is 1.
So `low` is the punishing case. Any axis you label from these has to say so or it reads backwards.

## Arm 1 and scoring

```python
from collie.arms import CappedBaseStockController, BaseStockParams, base_stock_order
from collie.eval.submission import run_submission, score_instance, write_results_csv
```

Arm 1 is the published baseline, not an approximation of it. Two properties of it are load-bearing
for anyone writing a similar policy:

- Its cap is **lead-time independent**. Upstream writes `mu_hat/(1+L) + z*sigma_hat/sqrt(1+L)`, which
  cancels to `mean + z*std`. That cap is a policy-internal order smoother and is a **different
  object** from our registered environment-side `order_cap`, despite sharing a word.
- Its estimator has already seen period `t-1` when it decides at `t`. Recording after deciding lags
  the whole order sequence by a period. Invisible in an aggregate score, obvious at order level.

`run_submission` writes the official `results/<relpath>/results.csv` layout and scores through
upstream's own evaluator, so a number you publish is the same object as a leaderboard number.

## Which harness, and why it matters

The two upstream harnesses disagree on one thing: whether a lost shipment stays visible in
in-transit. `env.py` keeps it forever; `eval/` never adds it.

**`eval/` is authoritative for everything we submit or report.** The divergence reaches a policy that
reads `in_transit_total` and cannot reach one that ignores it, and it never changes the physics.

The published OR figure of 0.4447 was generated under `env.py`, which we established by reproducing
all 1,320 of its order sequences exactly. Under `eval/` the same policy scores 0.5208, because
`env.py` makes it credit units that will never arrive. **Any table comparing against the published
figure must name the harness.** Details in `docs/env_contract.md` sections 5, 8.4, and 8.5.

## Develop against fakes: `collie/fakes/`

This is how seven modules proceed in parallel. Use them from day 1.

```python
from collie.fakes import (
    FakeLLM, canned,              # scripted model outputs, incl. adversarial ones
    FakeVerifier,                 # threshold-crossing stand-in with a lifecycle
    FakeGenerator, fixture_episode, fixture_episodes,   # one episode per family
    NullController, ConstantController,
)
```

- **`FakeLLM`** replays scripted strings and counts calls. Constructors:
  `FakeLLM.repair_then_succeed()`, `FakeLLM.always_invalid()`, `FakeLLM.cycling(items)`. The `canned`
  class holds ready payloads including malformed, fenced, prose-wrapped, extra-field, and
  smuggled-`threshold` outputs. Module 02 should fail against every one of them before it sees a real
  model.
- **`FakeVerifier`** exposes `register(spec)`, `observe(period, value) -> LifecycleState`,
  `is_active`, `activation_delay`. Enough to build arms 8-10 before module 05 lands.
- **`fixture_episode(family)`** returns a `FixtureEpisode` with a 20-period horizon, onset at 10,
  base demand 100, sigma 10. Hidden truth is returned **alongside** the observable episode, never
  inside it, so a test that leaks hidden state into a controller fails the isolation walk instead of
  quietly passing.

Fakes are excluded from coverage. Do not ship logic in them.

## Tooling

```
tools/audit_benchmark.py         regenerates manifests/benchmark_v1.json, byte-stable
tools/select_equivalence_set.py  the committed 216-instance equivalence set
tools/run_arm1.py                arm 1 over the benchmark under either harness
tools/freeze_contracts.py        the Gate 1 freeze and its guard
```

Pytest markers: `slow`, `needs_benchmark`, `needs_llm`, `equivalence`. Mark anything that needs the
LFS payload or a live endpoint, so `make test-fast` stays usable.

## House style

Line length 100. `ruff` with `E,F,I,UP,B,SIM,RUF`. Frozen dataclasses with `slots=True` for value
types; pydantic only where validation of untrusted input is the point, which in practice means
anything derived from model output.

Docstrings explain **why**, not what. The existing modules are the reference: a reader six months
from now needs to know which decisions were forced and which were chosen.

## What to do when the foundation is wrong

It will be, somewhere. The response is not a local workaround.

1. Write a failing test that demonstrates it.
2. If it touches `collie/contracts.py`, stop and raise it — that is a freeze deviation and affects
   everyone.
3. Otherwise fix it, keep the test, and note it in your checkpoint submission under Deviations.
