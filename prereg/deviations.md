# Deviations log

Every departure from a frozen artefact is recorded here, dated, with a reason. The point is not
ceremony: it is that a reviewer can reconstruct what was decided when, and that no frozen file can
change without leaving a trace.

### 2026-09-08 — rounded dependent demand remains empirical-only

- **Artefact:** `collie/verify/demand.py`
- **Current sha256:** `3afec4970699689e7890c6858423118c91e39f7e7f75ae253970832c34159199`
- **Departure:** The dependent AR(1) null is exercised in reduced calibration but labelled
  `empirical_only`; it is not included in the theorem-backed demand claim.
- **Reason:** Module 01 exposes only rounded/clipped AR(1) observations. The exact conditional mass
  given that quantized history requires a latent-state filter that neither `docs/derivation_note.md`
  nor the frozen public contracts specify. Substituting the previous rounded observation for the
  latent Gaussian state would silently violate the registered null.
- **Impact:** Stationary IID, seasonal, and overdispersed demand retain the anytime-valid label.
  Dependent-demand activation rates are reported separately as empirical-only until an exact filter
  and its calibration are registered. No held-out or test data informed this restriction.

Two guards read this file:

- `tests/test_contract_freeze.py` (Gate 1) fails if `collie/contracts.py` differs from
  `prereg/contract_freeze.json` unless an entry below names the file and quotes the new `sha256`
  prefix (first 12 characters).
- The Gate 2 guard over `prereg/freeze_manifest.json` (Task 19) will apply the same rule to every
  registered method file.

## How to declare a deviation

1. Add an entry under the right gate heading, newest first, using the template below.
2. Re-run the freeze tool so the record matches reality:
   `uv run python -m tools.freeze_contracts`
3. Commit the deviation entry and the updated freeze record together.

```markdown
### YYYY-MM-DD — one-line summary

- **Artefact:** `path/to/file.py`
- **New sha256:** `abcdef123456` (first 12 characters are enough)
- **What changed:** the concrete edit.
- **Why:** what forced it. "Cleaner" is not a reason; a wrong result or a blocked branch is.
- **Blast radius:** which branches or published numbers this invalidates, and what was re-run.
```

---

## Gate 1 — core contracts

`collie/contracts.py` frozen. See `prereg/contract_freeze.json` for the recorded hash.

*No deviations recorded.*

## Gate 2 — registered method files

Not yet frozen. Task 19 establishes `prereg/freeze_manifest.json` at the end of week 3.

*No deviations recorded.*

## Gate 3 — pilot decision

Not yet reached.

*No deviations recorded.*

---

## Recorded design decisions that are *not* deviations

These were settled before the relevant freeze, so they need no deviation entry. Listed here
because they are the questions most likely to be asked twice.

- **Scope of the arrival-side anytime-valid claim.** Restricted to COLLIE-ShockSpec episodes,
  because the official stochastic lead-time law's probabilities are unpublished. Recorded in
  `docs/derivation_note.md` before Gate 1.
- **`eval/` is the authoritative harness.** The two upstream harnesses disagree about whether a
  lost order stays visible in in-transit. `eval/` is the submission contract, so it governs our
  runner and every figure we publish; the legacy arms may be run under `env.py` provided the
  comparison names the harness. `docs/env_contract.md` §5, §8.4, §8.5.
- **The order cap is ours.** The benchmark imposes none. Registered in `prereg/prereg_v1.yaml` and
  labelled as ours wherever it appears. Distinct from the published baseline's policy-internal
  order smoother. `docs/env_contract.md` §2.3, §8.5.
- **Transit pause freezes progress, not arrival.** Chosen because it preserves the reference
  invariant that units with zero remaining transit always land in the current period.
  `docs/env_contract.md` §8.3.
