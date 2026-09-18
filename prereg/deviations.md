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

### 2026-09-16 — module 04's controller gains arm-1 parity; the compiler seam composes relative to the running baseline

- **Artefact:** the written controller formula and mapping semantics of
  `docs/implementation/04-or-compiler.md` (`q = min(max(0, S−IP), C_t)`, grid applied
  absolutely). No frozen file changes hash; module 04's files are not yet registered.
- **New sha256:** n/a — no frozen artefact is edited.
- **What changed:** (1) `OrCompilerController` now ceilings the order shortfall to integral
  units and applies the published baseline's policy-internal smoother (`mean + z·std`,
  quantile whitelisted by reference in the AST cap guard) as a second cap alongside `C_t`;
  (2) the controller skips the period-1 `prev_demand` sentinel, matching arm 1's
  pre-loop-initialisation convention; (3) `GridCompiler` composes compiled configs relative
  to the running config — reference-held axes are inherited, moved axes apply as absolute
  `m`, `l_eff` reference offset, and `gamma` reference ratio — and returns `current` on
  abstention; (4) module 06's merged oracle arm gates its dispatch to the ground-truth
  hazard window (`onset + duration − 1`) through a new `_dispatch_active` hook that defaults
  to the controls' deliberate switch-and-hold.
- **Why:** with the brief's literal formula, no arm routed through the shared controller ran
  the published baseline policy — orders were non-integral, the smoother absent, the baseline
  lead time fixed at a grid reference (`l_eff=1`) no benchmark instance uses — so every
  arm-versus-baseline contrast confounded hypothesis with controller. Worse, the absolute
  grid cancelled hypotheses outright: on a promised-2 instance a demand-up spec compiled to
  `m·(1+l_eff)` exactly equal to the baseline's, and the oracle's headroom measured ~0
  (demand-up configs made it order *less* during a demand-up shock). And module 04's own
  checkpoint demo had shown an un-windowed hazard config manufactures a holding blowup
  (measured again post-merge: −542/episode on temporary_pulse).
- **Blast radius:** module 04's checkpoint-demo numbers (headroom +793 against the grid
  reference baseline) are superseded — under the arm-1-equivalent baseline with the composed
  seam the fixture headroom is demand_level +388, temporary_pulse +118, lead_time_shift +391,
  shipment_loss +32, transit_pause −176 per episode; the negative transit_pause cell is a
  tier-1 calibration question referred to the module owner (their summary already directs
  re-validation against the real shock distribution) and was not tuned. The stand-in-era dev
  table in `docs/module06_research_notes.md` was exploratory and is likewise superseded.
  `compile_spec`'s static table, the 72-point grid, and `collie/contracts.py` are unchanged;
  903 tests green including a hypothesis differential pinning baseline-config parity with
  arm 1 bit for bit.

### 2026-09-07 — LLM serving moved to cloud providers; confirmation provider split from primary

- **Artefact:** the serving assumptions of `docs/implementation/06-arms-and-harness.md` §0.6
  (local vLLM primary, hosted confirmation TBD) and R2.2's three-seed robustness mode. No frozen
  file changes hash.
- **New sha256:** n/a — no frozen artefact is edited.
- **What changed:** (1) the primary sweep runs on Google Gemini via its OpenAI-compatible
  endpoint (operator decision 2026-09-06), replacing the assumed local vLLM open-weight primary;
  (2) the hosted confirmation path is xAI Grok `grok-4.20-0309-non-reasoning` (operator decision
  2026-09-07) after the Checkpoint-1 audit ruled a same-provider confirmation circular; (3) Z.ai
  GLM (`glm-5.3-flash`, coding-plan endpoint) is registered as a third provider for later
  benchmarking; (4) `EndpointConfig.supports_seed` records live-verified seed behaviour — Gemini
  rejects `seed` outright (400), Z.ai accepts but does not honour it, Grok honours it — and the
  three-seed robustness mode raises on endpoints that cannot honour a seed.
- **Why:** no local serving was available; a confirmation subset on the primary's own provider
  demonstrates nothing; seed behaviour could only be established by live calls.
- **Blast radius:** the paper can no longer claim an open-weight primary; R2.2's decoding-seed
  robustness subset runs on the Grok path only. No published number exists yet, so nothing is
  invalidated. Evidence in `docs/module06_research_notes.md` §4–§5.

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
