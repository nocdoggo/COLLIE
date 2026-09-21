# Module 05 — verifier, Checkpoint 1

Module: `05-verifier`, Checkpoint 1

Command: `uv run pytest tests/test_alpha.py tests/test_eprocess_demand.py tests/test_verifier_isolation.py -v`

Result: `38 passed`

Command: `uv run pytest tests/test_calibration.py -k demand --replications 200`

Result: `4 passed`; false activations were stationary IID `4/200`, seasonal `1/200`,
overdispersed `3/200`, and dependent `3/200`. All rates are at or below the proposal allocation
`alpha_1 = 0.025`. The dependent row is explicitly `empirical_only`; all calibration summaries are
stamped `analysis_class = exploratory` because this is checkpoint evidence, not a confirmatory run.

Built:

- One-based geometric alpha allocation with a hard two-proposal cap and a budget property test.
- Frozen, log-space discrete-mixture likelihood-ratio e-processes starting at exactly `tau_j + 1`
  and consuming every subsequent period without gaps, with sticky activation only at
  `E >= 1/alpha_j`; future-length history is rejected.
- A construction registry plus rejection of mismatched family/signature, stream, and direction.
- Exact exposed-observable masses for rounded/clipped Gaussian and negative-binomial demand nulls,
  plus exact alternative masses under Module 01's round-scale-round shock transform for all five
  registered demand multipliers; runtime isolation covers construction and observation inputs.
- A reproducible registered demand episode whose trace plot shows the evidence path, threshold 40,
  proposal at period 12, and realised activation at period 16; plug-in output is separately labelled
  `no_finite_sample_guarantee` and cannot be marked confirmatory.

Deviations:

- Rounded dependent AR(1) is calibrated but labelled `empirical_only`. Its exact
  conditional observable mass requires an unspecified latent-state filter. The dated rationale is
  recorded in `prereg/deviations.md`; stationary IID, seasonal, and overdispersed rows retain the
  theorem-backed label.

Blocked on: nothing for Module 5 Checkpoint 1. The registry is implemented and tested against the
frozen/documented key space without waiting for another branch. The real Module 04-to-05 joint test
will be rerun as a convergence check when branches merge; it is not a Module 5 development blocker.
Arrival recursion, lifecycle, and the full 2,000-replication calibration remain stopped until this
audit passes.
