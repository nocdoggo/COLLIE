# Module 05 — verifier, Checkpoint 1

Module: `05-verifier`, Checkpoint 1

Command: `uv run pytest tests/test_alpha.py tests/test_eprocess_demand.py tests/test_verifier_isolation.py -v`

Result: `30 passed`

Command: `uv run pytest tests/test_calibration.py -k demand --replications 200`

Result: `4 passed`; false activations were stationary IID `4/200`, seasonal `4/200`,
overdispersed `3/200`, and dependent `3/200`. All rates are at or below the proposal allocation
`alpha_1 = 0.025`. The dependent row is explicitly empirical-only.

Built:

- One-based geometric alpha allocation with a hard two-proposal cap and a budget property test.
- Frozen, log-space discrete-mixture likelihood-ratio e-processes starting strictly after `tau_j`,
  with sticky activation only at `E >= 1/alpha_j`.
- A construction registry plus rejection of mismatched family/signature, stream, and direction.
- Exact exposed-observable masses for rounded/clipped Gaussian and negative-binomial demand nulls;
  the separately labelled plug-in path carries no finite-sample guarantee.
- A reproducible registered demand episode whose trace plot shows the evidence path, threshold 40,
  proposal at period 12, and realised activation at period 16.

Deviations:

- Rounded dependent AR(1) is calibrated but labelled `no_finite_sample_guarantee`. Its exact
  conditional observable mass requires an unspecified latent-state filter. The dated rationale is
  recorded in `prereg/deviations.md`; stationary IID, seasonal, and overdispersed rows retain the
  theorem-backed label.

Blocked on: nothing for Checkpoint 1. The Module 04 `predictive_model` integration remains the
designated joint test when that compiler implementation lands; arrival recursion, lifecycle, and
the full 2,000-replication calibration remain stopped until this audit passes.
