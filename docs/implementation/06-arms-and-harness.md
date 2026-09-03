# 06. Arms, triggers, LLM client, and controls

| | |
|---|---|
| **Owner** | P1, with P2 on the controls in week 2 |
| **Checkpoint 1** | Day 5 |
| **Checkpoint 2** | Day 10 |
| **Depends on** | 02 schema, 03 alerts, 04 compiler, 05 verifier. All available as fakes from day 1. |
| **Consumed by** | 07 evaluation, and the pilot |
| **Joint work** | Days 8-9 with P4 on arms 8, 9, 10 |

> **Blocked on two answers.** Checkpoint 1 is unaffected; Checkpoint 2 cannot complete without them.
> 1. **Local LLM serving.** Which open-weight model, and is an OpenAI-compatible endpoint running on
>    the 4x RTX 4090 + RTX A6000 box? vLLM is assumed but unconfirmed.
> 2. **Hosted API key.** Which provider for the preregistered confirmation subset, and is a key
>    available?
>
> Escalate on day 1 if you have not been told. Do not silently substitute a different model, and do
> not let the hosted path fall back to local: a fallback would make the confirmation subset
> meaningless. Missing hosted credentials must raise.

## What you are building

The arm ladder, and the shared plumbing that makes comparisons across it legitimate.

The ladder exists to isolate one thing: **what does the typed, verified handshake add over cheaper
alternatives?** Every rung answers a possible objection.

| Arm | What it is | The objection it answers |
|---|---|---|
| 1 | capped base-stock OR | **done**, the published baseline |
| 2 | telemetry-only adaptive OR | "a changepoint detector would do this" |
| 3 | every-period LLM direct action | "just let the LLM order" |
| 4 | trigger-only LLM direct action | "the gain is from calling less often" |
| 5 | every-period LLM to OR parameters | "the gain is from the OR layer" |
| 6 | sparse ephemeral LLM to OR | "the gain is from sparsity" |
| 7 | persistent one call, fixed expiry | "the gain is from persistence" |
| 8 | ShockSpec, immediate activation | "the gain is from typing the hypothesis" |
| 9 | ShockSpec, heuristic rollback | "a heuristic guard would do" |
| 10 | ShockSpec, e-process activation | **the contribution** |

Arms 8, 9, 10 share **one physical proposal call set** and differ only in their activation policy.
That is what makes the comparison clean: identical proposals, different decisions about when to trust
them. If they differed in their calls too, any difference could be attributed to the calls.

## Where the code goes

```
collie/trigger/
  __init__.py
  protocol.py     Trigger wrappers: refractory, max-proposals
  detectors.py    AlertOnly, PageHinkley, Cusum, AlertOrDetector, PeriodicEveryK, RandomMatched
  trace.py        TriggerTrace
collie/llm/
  __init__.py
  client.py       OpenAI-compatible, local primary, hosted secondary
  cache.py        disk cache keyed by model, prompt, state, decoding hash
  ledger.py       physical vs charged accounting
collie/arms/
  direct.py       arms 3, 4
  llm_to_or.py    arms 5, 6, 7
  shockspec.py    ShockSpecArm base, arms 8, 9, 10
  controls.py     arm 2, detector control, keyword parser, upper bounds
  oracle.py       oracle ShockSpec headroom bound
tests/
  test_triggers.py  test_llm_client.py  test_cache_ledger.py
  test_arms_direct.py  test_arms_llm_to_or.py  test_arms_shockspec.py  test_controls.py
```

`collie/arms/base_stock.py` already holds arm 1. `collie/arms/oracle.py` and `collie/arms/controls.py`
are already on the hidden-state allowlist, so those are the only two files permitted to read hidden
truth.

## Triggers are shared plumbing, not per-arm logic

Every arm that shares a rule must produce a **bitwise-identical trigger trace**. Otherwise a
comparison between two arms conflates a different invocation pattern with a different policy.

The refractory window and the two-proposal cap live in **one place**, as wrappers:

```python
RefractoryWrapper(inner, window=W)      # suppress firing within W periods of the last
MaxProposalsWrapper(inner, limit=2)     # suppress after the cap
```

Not reimplemented per detector. Wrapping is what guarantees the cap holds uniformly, including for
detectors written later.

Detectors: `AlertOnly`, `PageHinkley`, `Cusum`, `AlertOrDetector` (**the primary rule**),
`PeriodicEveryK`, `RandomMatched`.

`PeriodicEveryK` and `RandomMatched` are budget-matched baselines: they answer whether the *timing* of
calls matters or only the *number*. They must be matched on **realised** calls, not on intended calls,
because suppression by the wrappers changes the realised count.

Thresholds are calibrated on dev and cal only, then frozen at the method freeze.

**Feature legality.** An explicit denylist, enforced: future demand, benchmark pattern names, instance
and article ids, test labels, any `incident.json` field. A trigger that peeks is worse than a bad
trigger, because it looks like a good one.

## LLM client, cache, and the cost ledger

The compute-frontier claims depend entirely on this accounting being right.

- **Local primary**, hosted secondary. Missing hosted credentials **raise**; they never fall back.
- **Fixed deterministic decoding**, with a three-seed robustness mode that **refuses to execute
  against the confirmatory test set**.
- **Disk cache** keyed by model, full prompt text hash, state, and decoding hash. A warm replay must
  return identical responses, or reruns are not reproducible.
- **Physical versus charged.** One physical request shared by arms 8, 9, 10 produces one `physical=True`
  log and three charged copies. Assert `physical <= sum(charged)`.
- **Full ledger fields**: attempted, repaired, rejected or unusable, input and output tokens, p50 and
  p95 latency, dated cost.

`CallLog` in the frozen contracts already carries all of this. Populate it; do not invent a parallel
record.

---

## Checkpoint 1 — Day 5: triggers identical across arms, transport shaped

### Deliverables

1. `Trigger` protocol, `TriggerTrace`, and both wrappers.
2. The six detectors, thresholds calibrated on dev.
3. Feature-legality denylist, enforced.
4. LLM client, cache, and ledger, complete in shape and fully tested **against `FakeLLM`**.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_third_proposal_suppressed` | the cap, via the wrapper |
| `test_repeated_firing_inside_window_suppressed` | the refractory window |
| `test_identical_trace_across_arms_sharing_a_rule` | bitwise |
| `test_periodic_and_random_matched_on_realised_calls` | not intended calls |
| `test_trigger_reads_no_denylisted_feature` | static and runtime |
| `test_missing_hosted_key_raises` | never falls back to local |
| `test_cache_key_includes_full_prompt_hash` | not a truncation or a summary |
| `test_warm_replay_returns_identical_responses` | |
| `test_three_arms_one_call_gives_one_physical_three_charged` | |
| `test_physical_never_exceeds_charged` | property over random arm sets |
| `test_robustness_mode_refuses_the_confirmatory_set` | |
| `test_ledger_records_every_field` | attempted, repaired, rejected, tokens, latency, cost |

### Audit command

```bash
uv run pytest tests/test_triggers.py tests/test_llm_client.py tests/test_cache_ledger.py -v
uv run python -m collie.trigger.detectors --trigger-table --episodes 12
```

### Pass criteria

- All tests green against `FakeLLM`.
- A trigger-time table across all rules for 12 dev episodes. The auditor checks that `AlertOrDetector`
  fires near onset more often than `RandomMatched` at the same budget — if it does not, the primary
  rule is not doing anything and that needs to surface now.
- A cost-ledger CSV for a 10-episode fake run, then a warm replay with **identical** charged totals.
- Explicit statement of whether the two serving blockers have been answered.

### Not expected yet

Any real model call. Any arm. Controls.

---

## Checkpoint 2 — Day 10: ten arms run, ledgers balance, isolation holds

### Deliverables

1. Arms 3, 4 — direct action, on a prompt builder that reproduces the benchmark agent's prompt verbatim.
2. Arms 5, 6, 7 — LLM to OR parameters.
3. Arms 8, 9, 10 — the handshake. **Joint with P4, days 8-9.**
4. Controls: arm 2, the detector control, the keyword parser, and both upper bounds. **P2 assists.**
5. End-to-end hidden-state isolation over every assembled arm.

### Arms 3 and 4

Share a prompt builder that reproduces the benchmark agent's prompt **verbatim**, asserted by
prompt-identity hash equality at the same state. Reproducing it exactly is what makes arm 3 a fair
representation of the existing approach rather than a strawman we built.

### Arms 5, 6, 7

Arm 5 calls every period. Arm 6 is sparse and ephemeral. Arm 7 makes one persistent call with a fixed
expiry. Arms 4 and 6 must be **matched on realised calls**, so the sparsity comparison is not a budget
comparison.

### Arms 8, 9, 10 — the joint deliverable

```python
class ShockSpecArm:
    """Owns proposal, compilation, and lifecycle. Parameterised by ActivationPolicy."""
```

One base class, three activation policies: `Immediate`, `HeuristicRollback`, `EProcess`.

Two tests carry the design:

- **Shared call set.** One physical proposal call set serves all three. Assert it.
- **Divergence.** Given identical proposals, the three produce **different activation traces**. If
  they do not, the activation mechanism is not doing anything and there is no result.

### Controls, and the cut line

**In scope for this sprint:**

- Arm 2, telemetry-only adaptive OR, an HMM or changepoint over normal versus disrupted.
- CUSUM and Page-Hinkley into the **identical** compiler.
- A keyword or rule parser into the **identical** compiler.
- The canonical `AlertSpec` parsing upper bound: feed `HiddenAlertSpec` straight to the compiler. This
  is the ceiling for perfect parsing.
- The oracle ShockSpec headroom bound. May read hidden truth. **Never tuned on test.**

**Deferred past this sprint**, named now so nobody plans around them:

- The value-of-computation gate. Explicitly an optional module.
- The low-data supervised classifier, a labelled diagnostic.
- Compile-once, which needs a sandboxed no-network design-time session.
- InvEvolve-style regeneration at matched budget.

**Shared routing.** Every control routes through module 04's compiler and controller. There is a test
for byte-identical orders given the same `ControlConfig`; every new control must be added to it.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_benchmark_prompt_identity_hash` | arms 3 and 4 reproduce the agent prompt verbatim |
| `test_arms_4_and_6_matched_on_realised_calls` | |
| `test_arms_8_9_10_share_one_physical_call_set` | |
| `test_arms_8_9_10_diverge_in_activation_trace` | identical proposals, different activation |
| `test_every_arm_passes_controller_isolation` | `check_controller_isolation=True`, oracle excepted |
| `test_oracle_is_the_only_arm_reading_hidden_truth` | |
| `test_every_control_routes_through_the_shared_compiler` | byte-identical orders |
| `test_ledger_balances_across_all_arms` | `physical <= sum(charged)` over a full dev sweep |

### Audit command

```bash
uv run pytest tests/test_arms_direct.py tests/test_arms_llm_to_or.py \
              tests/test_arms_shockspec.py tests/test_controls.py -v
uv run python -m collie.eval.report --table main --split dev
```

### Pass criteria

- All tests green.
- The main-table **shape** on dev, all ten arms plus controls, with their ledgers. Numbers need not be
  good; the table must be real and every cell populated from stored records.
- A control table showing the headroom band between stationary OR and the oracle. If that band is
  narrow, nothing in between can be distinguished, and the pilot will say so.
- The ledger balancing across the full dev sweep.

---

## Risks specific to this module

- **The serving blockers.** They are at the top of this document for a reason. Escalate on day 1.
- **This is the largest module.** Arms 8, 9, 10 are jointly owned precisely because they are the
  integration point. If week 2 is going badly, the correct sacrifice is the deferred controls, never
  the arm-8/9/10 divergence test or the ledger accounting.
- **Trigger traces drifting between arms.** Enforced by the shared-plumbing design. Do not let a
  detector implement its own suppression.
- **Cache keys that are too weak.** A key missing part of the prompt makes warm replay return the wrong
  response, which corrupts a rerun silently. Hash the full prompt text.
