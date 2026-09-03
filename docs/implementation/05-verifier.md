# 05. Verifier — e-processes, forward algorithm, lifecycle

| | |
|---|---|
| **Owner** | P4 |
| **Checkpoint 1** | Day 4 |
| **Checkpoint 2** | Day 9 |
| **Depends on** | 01 shock generator, 02 shockspec interface |
| **Consumed by** | 06 arms, specifically arm 10 |
| **Joint work** | Day 9 with P3 on the spec contract, and P1 on ledger isolation |

## What you are building

The component that decides whether a frozen hypothesis has **earned** the right to influence orders.

`docs/derivation_note.md` is the specification. It is already written and reviewed. Implement it
section by section; section 10 is an explicit list of what this module must produce. Where the code
and the note disagree, the note wins — or you found a mistake in the note, which is a finding and
needs a dated deviation, not a quiet code fix.

**This is the hardest module in the project and the one with the least slack.** It is scheduled
first-half heavy because arm 10 cannot exist without it and the pilot cannot run without arm 10.

## The claim you are protecting

> **Model-conditional, anytime-valid, per-episode** control of false activation.

Not dataset-wide family-wise control. Not safety. Not profit. Not wrong-family activation. Every one
of those overclaims is easy to make by accident and each one is listed as prohibited.

Two limits, from the note, that must appear in your output records rather than only in prose:

- The arrival-side anytime-valid claim applies **only to COLLIE-ShockSpec episodes**, because the
  official stochastic lead-time law's probabilities are unpublished. Official-instance arrival results
  are `empirical_only`.
- The **plug-in variant carries no finite-sample guarantee**, permanently. It is reported separately
  and labelled.

## Where the code goes

```
collie/verify/
  __init__.py
  alpha.py        alpha allocation across proposals
  registry.py     construction registry keyed by predictive_model
  demand.py       mixture likelihood-ratio e-processes
  arrival.py      finite-state forward recursion
  eprocess.py     the shared e-process object and activation rule
  lifecycle.py    the state machine
tests/
  test_alpha.py
  test_eprocess_demand.py
  test_arrival_forward.py
  test_arrival_bruteforce.py
  test_lifecycle.py
  test_verifier_isolation.py
  test_calibration.py           marked slow
```

## Filtration and event ordering — get this exactly right

From section 2 of the note. Everything else depends on it:

- `F_t` is information through period `t`, **immediately before** action `A_t`.
- `A_t` affects only `Y_{t+1}` onward, never `Y_t`.
- The verifier conditions `Y_r` on `(F_{r-1}, A_{r-1})`.
- `h_j`, the hypothesis, is `F_{tau_j}`-measurable.

**The e-process starts strictly after `tau_j`.** No observation at or before `tau_j` may enter the
product. This is the single boundary condition that makes the whole thing valid: the hypothesis was
chosen using data up to `tau_j`, so only data after `tau_j` can test it.

Write that boundary test first. It is one assertion and it is the difference between a valid result
and a post-selection artefact.

The runner already guarantees the causal half of this: the observation is built and frozen before the
controller is called, and there is a differential test proving an action at period `k` cannot change
any observation at or before `k`. You inherit that; do not re-derive it.

## Alpha allocation

```
alpha_{e,j} = alpha_episode * 2^{-j}      j = 1, 2, ...   (1-based)
```

Assert `sum_j 2^{-j} <= 1` over the permitted proposal count. With at most two proposals per episode
this is `0.5 + 0.25 = 0.75 <= 1`, which holds with room. Assert it anyway, as a property over the
permitted count, so raising the proposal cap later cannot silently break the budget.

## The construction registry

Keyed by the `predictive_model` value that module 04's compiler emits.

```python
CONSTRUCTIONS: dict[str, Construction] = {...}
```

Two invariants, both joint tests:

1. Every key the compiler emits resolves here. **Joint with P1.**
2. Every legal `ShockSpec` maps to exactly one construction, and no construction is reachable by a
   spec the schema cannot express. **Joint with P3, day 9.**

The second is the test the paper's defensibility rests on. If it is green, the model demonstrably did
not choose its own test: it selected a registered key, and the system derived the test from that key.

## Demand-side e-processes

Section 4 of the note. **Discrete mixtures**, so the integral is an exact finite sum you can audit by
hand, not a numerical approximation whose error you would then have to bound. This was a deliberate
choice over continuous or conjugate priors and it is not a simplification to be optimised away.

The registered null `p_0` comes from the environment contract, so every method faces the same null. A
method that got to pick its own null would be measuring something else.

Freeze every density, mixture, and nuisance procedure on dev and cal only. The method freeze covers
them.

### The plug-in variant

Re-estimates `p_0` online. Implement it, report it separately, and label it as carrying **no**
finite-sample guarantee. It exists because it is what a practitioner would actually do, and showing
the honest gap between it and the guaranteed version is a contribution. Never fold its numbers into a
confirmatory contrast.

## Arrival-side forward recursion

Sections 6.1 to 6.4. **A FIFO shortcut is not allowed** — 6.1 explains why, and module 04's ledger is
exactly the forbidden object.

State: outstanding cohort quantities by remaining transit time, truncated at the registered maximum.
Loss is an absorbing outcome. A pause freezes the counters. Emission is aggregate receipts, because
that is all the observation model exposes.

This mirrors the frozen `LeadTimeSupply` in `collie/sim/supply.py`, which carries remaining transit
time per cohort for the same reason. Read it before writing this; the state representation should
correspond, and where the semantics are subtle, `docs/env_contract.md` section 8.3 records the
decision: a pause freezes the clock of cohorts still moving and never holds back a cohort whose
transit is already complete.

The recursion produces exact `p_0(R_t | F_{t-1}, A_{t-1})` and the registered alternative. The exact
likelihood ratio feeds the e-process.

**Validate by brute force.** On short horizons, enumerate every consistent assignment of receipts to
cohorts and compare the enumerated density to the recursion. They must agree to floating-point
tolerance. This is the test that catches an off-by-one in the state transition, and there is no
substitute for it.

## Compound shocks

Section 7. When `HiddenIncident.conditional_independence` is `false`, which is family 6, you must use
either a registered joint conditional likelihood or two separate e-processes with **explicit alpha
splitting**.

**Multiplying marginal likelihood ratios is prohibited**, and the code path that would do it must be
unreachable. Not discouraged in a comment. Unreachable, with a test proving it.

Family 6 drives both streams from one incident, so the innovations share a latent cause and the
marginals are not independent. Multiplying them would overstate the evidence, and it would do so in
exactly the cell where the method looks most impressive.

## Isolation

The verifier is the component most tempting to leak into, and a leak here produces results that look
valid.

Forbidden inputs: hidden spec truth, latent parameters, `incident.json`, `supply.csv`, the FIFO
ledger, shipment ages, actual lead times.

Enforced by runtime object-graph walk and static AST scan. Note that `collie/verify/` is already on
the statically forbidden list for hidden symbols, so `HiddenIncident` and friends cannot even be
named in your module. That is intentional.

---

## Checkpoint 1 — Day 4: demand e-processes, calibrated

### Deliverables

1. `alpha.py` — allocation with the budget assertion.
2. `registry.py` — construction registry, keyed as the compiler emits.
3. `demand.py` — mixture likelihood-ratio e-processes starting strictly after `tau_j`.
4. `eprocess.py` — the e-process object and activation rule.
5. A calibration run, reduced size is fine at this checkpoint.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_no_observation_at_or_before_tau_j_enters_the_product` | the boundary condition |
| `test_alpha_budget_never_exceeds_one` | property over the permitted proposal count |
| `test_alpha_is_one_based` | `alpha_1 = alpha/2` |
| `test_mixture_integral_is_exact` | discrete sum against hand computation |
| `test_registered_null_comes_from_the_contract` | not a literal |
| `test_e_process_is_a_supermartingale_under_the_null` | Monte Carlo, reduced replications |
| `test_activation_requires_crossing_one_over_alpha` | and never before |
| `test_verifier_reads_no_forbidden_input` | runtime walk plus static scan |
| `test_plug_in_variant_is_labelled_unguaranteed` | in the record, not only in prose |

### Calibration at this checkpoint

Reduced size is acceptable: 200 replications per registered null rather than the full 2,000. Enough to
show empirical false activation is at or below alpha and that the machinery runs. The full 2,000 lands
at Checkpoint 2.

### Audit command

```bash
uv run pytest tests/test_alpha.py tests/test_eprocess_demand.py tests/test_verifier_isolation.py -v
uv run pytest tests/test_calibration.py -k demand --replications 200
```

### Pass criteria

- All tests green.
- An e-process trace plot for one episode: the evidence path, the `1/alpha_j` threshold, and the
  realised activation time.
- Empirical false activation at or below alpha on the reduced calibration.
- The boundary test visibly present. The auditor will look for it by name.

### Not expected yet

The arrival side, the lifecycle, the full 2,000-replication calibration.

---

## Checkpoint 2 — Day 9: arrival recursion validated, lifecycle complete

### Deliverables

1. `arrival.py` — the finite-state forward recursion.
2. Brute-force agreement on short horizons.
3. `lifecycle.py` — the full state machine.
4. Per-family validity flags asserted against the note's section 9 table.
5. Full calibration: 2,000 replications per registered null.
6. The joint spec-to-verifier contract test, with P3.

### The lifecycle state machine

```
proposed  ->  active | expired | superseded
active    ->  refuted | expired | superseded
```

Baseline OR runs while a spec is `proposed`. A hypothesis influences nothing until it is `active`.

- **Refutation and expiry rules are registered separately**, evaluated empirically, and are
  **explicitly outside the activation theorem**. Say so in the output record.
- Maximum lifetime comes from `duration_bin` combined with `persistence`.
- **Supersession uses alpha splitting, at most two proposals.** A third proposal is rejected. A
  superseding spec must itself have been tested; it does not inherit its predecessor's activation.
- The **bounded-provisional trust region** sits behind an exploratory flag. The confirmatory runner
  must refuse to set that flag, and outputs must be tagged so module 07 cannot fold them into a
  confirmatory contrast.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_brute_force_agrees_with_recursion` | exhaustive enumeration on short horizons |
| `test_pause_freezes_the_state_counters` | consistent with the frozen supply semantics |
| `test_loss_is_absorbing` | |
| `test_no_fifo_identity_used` | static scan for ledger symbols, runtime input assertion |
| `test_transition_table_coverage` | every legal transition exercised, every illegal one rejected |
| `test_no_stale_belief` | no episode ends with an active spec past its maximum lifetime |
| `test_third_proposal_rejected` | |
| `test_superseding_spec_was_itself_tested` | |
| `test_marginal_product_path_is_unreachable` | the compound prohibition |
| `test_compound_uses_alpha_splitting` | when `conditional_independence` is false |
| `test_confirmatory_runner_refuses_the_exploratory_flag` | |
| `test_validity_flags_match_the_note` | per family, against section 9 |
| `test_spec_maps_to_exactly_one_construction` | joint with P3, both directions |

### Audit command

```bash
uv run pytest tests/test_arrival_forward.py tests/test_arrival_bruteforce.py \
              tests/test_lifecycle.py tests/test_spec_verifier_contract.py -v
uv run pytest tests/test_calibration.py -q          # full 2,000 replications
uv run python -m collie.verify.arrival --demo
```

### Pass criteria

- All tests green, brute-force agreement demonstrated.
- Full calibration: empirical false activation at or below alpha per registered null, with intervals.
- Power sanity: the e-process activates under a genuine shift, so calibration was not achieved by
  never firing.
- The demo shows activation on a lost-shipment burst and **non-activation** on a noisy-but-null arrival
  stream, with the per-family validity table printed and `empirical_only` families marked.
- A lifecycle timeline for one compound episode.

### Not expected yet

The 1,300-episode null-audit bank through the full pipeline. Post-sprint, and it needs LLM budget.

---

## Deferred past this sprint

- Running the full null-audit bank end to end.
- The censored-observation model beyond `empirical_only` status. The note flags it as pending; do not
  upgrade its status without a dated deviation.

## Risks specific to this module

- **The boundary condition.** An off-by-one at `tau_j` invalidates every activation result while
  leaving all tests green if the boundary test is missing. Write it first.
- **Numerical drift in the recursion.** Brute force is the only real check. Do not skip it because the
  recursion "looks right".
- **The temptation to multiply marginals.** It is convenient, it is wrong, and it inflates evidence
  precisely in the compound cell. Make the path unreachable.
- **Schedule.** This is the tightest module. If the arrival side is going to slip, say so at
  Checkpoint 1. Demand-side-only activation with arrival families marked `empirical_only` is a
  defensible reduced scope; a rushed and unvalidated recursion is not.
