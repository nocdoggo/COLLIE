# Module 05 verifier — Checkpoint 2 audit

Module:      `05-verifier`, Checkpoint 2

Command:

```bash
uv run pytest tests/test_arrival_forward.py tests/test_arrival_bruteforce.py \
              tests/test_lifecycle.py tests/test_spec_verifier_contract.py -v
uv run pytest tests/test_calibration.py -q
uv run python -m collie.verify.arrival --demo
```

Result:

```text
37 passed in 0.96s
9 passed in 166.36s (0:02:46)

lost-shipment burst: activated=True at=17 e=12289.867
noisy registered null: activated=False at=None e=0.118
compound lifecycle: proposed(t=12) -> active(t=16) -> expired(t=20)
```

The proposal-level threshold uses `alpha_1 = 0.025`. Every calibration summary is labelled
`analysis_class = exploratory`. Full deterministic results (95% Wilson intervals) were:

| Registered construction/null | Activations | Rate | 95% Wilson | Output validity |
|---|---:|---:|---:|---|
| demand / stationary IID | 14 / 2,000 | 0.70% | [0.42%, 1.17%] | `anytime_valid` |
| demand / seasonal | 9 / 2,000 | 0.45% | [0.24%, 0.85%] | `anytime_valid` |
| demand / overdispersed | 29 / 2,000 | 1.45% | [1.01%, 2.07%] | `anytime_valid` |
| demand / dependent rounded AR(1) | 16 / 2,000 | 0.80% | [0.49%, 1.30%] | `empirical_only` |
| arrival / lead-time shift | 9 / 2,000 | 0.45% | [0.24%, 0.85%] | `anytime_valid_collie_shockspec_only` |
| arrival / shipment loss | 13 / 2,000 | 0.65% | [0.38%, 1.11%] | `anytime_valid_collie_shockspec_only` |
| arrival / transit pause | 10 / 2,000 | 0.50% | [0.27%, 0.92%] | `anytime_valid_collie_shockspec_only` |

Built:

- Exact finite-state forward recursion over aggregate receipts, with absorbing loss, globally frozen
  pause counters, same-period zero-delay emission, complete pre-proposal conditioning, and no FIFO or
  shipment-identity input; an independent exhaustive oracle agrees on every short receipt path.
- Full lifecycle state machine: baseline OR while proposed, e-process-only activation, separately
  registered empirical refutation/expiry, duration-plus-persistence lifetime, tested supersession,
  two-proposal cap, activation-delay output, and confirmatory refusal of provisional mode.
- Compound specs build two real stream e-processes with a prior 50/50 split of proposal alpha; both
  must cross their own threshold, while combined-e-value and marginal-product paths are absent and
  tested unreachable.
- All nine section-9 validity rows are asserted in output form, including official arrival,
  censored, and plug-in `empirical_only` restrictions; the anytime label additionally requires the
  exact registered null and alternative grid.
- The bidirectional spec contract covers all seven legal frozen shapes, rejects every illegal
  family/signature and onset pairing, runs against the foundation Module 02 fake, and compares P3's
  production registry automatically when that branch is present. Full calibration is below alpha
  for all seven rows, while a genuine registered finite loss burst activates.

Deviations:

- The audited runner dispatches before the same-period receipt pop, so the recursion consumes that
  predictable dispatch; this resolves the derivation note's inconsistent action-index notation.
- Module 01 exposes deterministic realized supply paths but no stochastic conditional law. Module 05
  therefore registers a common-support law at its public boundary. Only episodes bound to that exact
  law receive the COLLIE-only theorem label; all other arrival paths remain `empirical_only`.
- The note's fixed 1,296-state bound is not universal under a pause because old dispatches can remain
  moving while new ones enter. The implementation retains every distinct state on the finite episode
  horizon instead of truncating an exact likelihood. All three decisions are dated in
  `prereg/deviations.md`.

Blocked on: nothing. Module 05 used the frozen contracts and foundation fakes and did not wait for or
modify another module. The only deferred work is exactly the document's post-sprint scope: the
1,300-episode full-pipeline null sweep and a theorem-backed censored-observation model.
