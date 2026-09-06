# Module 05 — verifier, Checkpoint 1

Module: `05-verifier`, Checkpoint 1

Command: `uv run pytest tests/test_alpha.py tests/test_eprocess_demand.py tests/test_verifier_isolation.py -v`

Result: `24 passed`

Command: `uv run pytest tests/test_calibration.py -k demand --replications 200 -v`

Result: `4 passed`

Regression: `make test-fast`

Result: `339 passed, 235 deselected`

## Built

- One-based geometric alpha allocation with a property test that the episode budget is never
  exceeded and a hard rejection beyond the two-proposal cap.
- A log-space discrete-mixture likelihood-ratio e-process whose mixture is outside the product,
  with sticky activation only after crossing `1 / alpha_j`.
- Exact exposed-observable probability masses for rounded/clipped Gaussian and negative-binomial
  demand nulls, plus persistent level and bounded-pulse alternative mixtures.
- A future-only demand adapter that rejects observations at or before `tau_j`, carries an explicit
  validity label on every trace point, and reads no hidden state or FIFO-ledger object.
- A reduced calibration harness and an auditable evidence trace plot at
  `reports/module05_cp1_eprocess_trace.png`.

## Calibration summary

One proposal receives `alpha_j = 0.025` from `alpha_episode = 0.05`. Each row uses 200 null
replications, horizon 50, and proposal time 12.

| Registered null | Activations | Rate | Wilson 95% interval |
|---|---:|---:|---:|
| stationary IID | 4 / 200 | 0.020 | [0.0078, 0.0503] |
| seasonal | 4 / 200 | 0.020 | [0.0078, 0.0503] |
| overdispersed | 3 / 200 | 0.015 | [0.0051, 0.0432] |

The power sanity fixture activates on a genuine persistent upward shift. The demo crosses the
threshold at period 15 after a proposal at period 12.

## Deviations

- `BaselineKind.DEPENDENT` is explicitly labelled `no_finite_sample_guarantee` and excluded from
  theorem-backed calibration. Module 01 generates a latent Gaussian AR(1) path and exposes only its
  rounded/clipped value. The exact conditional mass given the rounded history therefore requires a
  latent-state filter that is not specified in `docs/derivation_note.md`. Treating the previous
  rounded value as the latent state would silently overclaim the theorem. Audit decision requested:
  either specify and implement that filter, or record this stratum as empirical-only.

## Blocked on

Nothing for Checkpoint 1. Before Checkpoint 2, audit must fix or explicitly resolve the arrival
receipt/action indexing and the claimed finite-state bound under transit pauses.

## Demo

```bash
MPLCONFIGDIR=/tmp/collie-mpl uv run python -m collie.verify.demand \
  --demo --plot reports/module05_cp1_eprocess_trace.png
```
