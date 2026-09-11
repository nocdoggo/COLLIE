# Deviations log

Every departure from a frozen artefact is recorded here, dated, with a reason. The point is not
ceremony: it is that a reviewer can reconstruct what was decided when, and that no frozen file can
change without leaving a trace.

### 2026-09-08 — arrival action index follows the audited runner event order

- **Artefact:** `collie/verify/arrival.py`
- **Departure:** Derivation-note §6 writes the receipt conditional using `A_{t-1}`, while the same
  note and the audited runner both specify dispatch at `t` before the receipt pop at `t`, including
  same-period arrival when `L=0`. The forward step therefore consumes the dispatch made immediately
  before that period's receipt.
- **Reason:** Using the previous period's dispatch would omit the observable contribution of an
  `L=0` order and disagree with the frozen supply process. Predictability is preserved because the
  dispatch is known before the receipt is observed.
- **Impact:** A named test covers same-period zero-delay emission, and the independent exhaustive
  oracle uses the same audited event order. Demand-side filtration and the frozen runner are
  unchanged.

### 2026-09-08 — CP2 arrival law is registered at the verifier boundary

- **Artefact:** `collie/verify/arrival.py`
- **Departure:** The derivation note says the COLLIE generator defines and registers a stochastic
  per-dispatch lead-time law. The merged Module 01 generator emits deterministic realized paths and
  parameter ranges, but exposes no conditional probability law. CP2 therefore registers its
  common-support null and alternative laws in Module 05 and accepts them explicitly at the verifier
  boundary; it does not inspect generated realizations or hidden episode files.
- **Reason:** An exact likelihood ratio requires probabilities, not a realized lead-time column.
  Inventing probabilities from the observed path would be data-dependent and invalidate the stated
  model-conditional claim.
- **Impact:** CP2 calibration and the demo exercise the registered Module 05 law. At convergence,
  generated pilot episodes may receive the theorem-backed arrival label only if they use that same
  registered law; otherwise their arrival results must remain `empirical_only`. This does not change
  demand-side claims or any frozen foundation code.

### 2026-09-08 — pause recursion is exact rather than truncated to the stated 1,296 bound

- **Artefact:** `collie/verify/arrival.py`
- **Departure:** The derivation note's fixed `(L_max + 2)^L_max = 1,296` state-count bound assumes at
  most `L_max` outstanding dispatches. A transit pause can keep old dispatches moving while new ones
  enter, so that count is not a valid universal bound. The implementation keeps every distinct
  aggregate remaining-time state instead of truncating or merging states that can emit differently.
- **Reason:** Enforcing the stated bound would silently discard compatible latent histories and make
  the receipt likelihood approximate. The checkpoint requires exact recursion and brute-force
  agreement.
- **Impact:** The recursion remains finite on the registered finite episode horizon and agrees with
  an independent exhaustive oracle on short horizons. Runtime is measured by the five-minute audit
  command; no theorem label is upgraded by this decision.

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
