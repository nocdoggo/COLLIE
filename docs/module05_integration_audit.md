# Module 05 — pre-merge integration audit

Date: 2026-09-18. Auditor: integration pass ahead of the module-05 merge, requested by P4.
Branch audited: `module05-cp1` (9 commits, `e4a2d4b`..`3d3e549`), forked from `main` at the
module-01 merge. Merge rehearsal branch: `module05-merge-audit` (pushed for reference and CI).

This document is the fix list for P4 plus the one decision that is not P4's to make alone (F1).
Nothing in module 05's checkpoints is being re-litigated: both reports were verified against
the branch and stand. The findings below are all *convergence* findings — things that only
exist because main moved while module 05 was in flight.

## Verified clean

- **Branch as-is:** 630 tests passed; CI green on every push (`gh run list --branch module05-cp1`).
- **Merge with main:** exactly one conflict, `tests/conftest.py` (add/add: module 05's
  `pytest_addoption` vs module 06's injection wiring). Resolution keeps main's wiring wholesale
  and appends `pytest_addoption` unchanged. `prereg/deviations.md` auto-merges cleanly.
- **Merged state:** 1147 passed, `make lint` clean, `make check-freeze` intact, `make equivalence`
  219 passed. Reference resolution is commit `0d45250` on `module05-merge-audit`.
- **Boundary condition:** mutating `period <= self.tau_j` to `period < self.tau_j` in
  `eprocess.py` fails `test_no_observation_at_or_before_tau_j_enters_the_product` on contact.
  The assertion the validity argument rests on is live.
- **Isolation:** `collie/verify/` is on the static forbidden list (`tests/test_contracts.py:290`);
  `tests/test_verifier_isolation.py` covers the runtime walk. No frozen file touched in the
  branch diff; no forbidden path staged.
- **Calibration:** all seven rows at or below alpha with Wilson intervals; power sanity
  demonstrated (loss burst activates, noisy null does not); plug-in labelled
  `no_finite_sample_guarantee`; all four deviations dated and defensible.

## F1 — DECISION NEEDED (not P4's alone): the `predictive_model` key space has zero overlap

The joint invariant the paper's defensibility rests on ("every key the compiler emits resolves
in the verifier registry") is red at convergence, and it is a design fork, not a bug:

- Module 04 (merged) derives `predictive_model` as a **pure function of the grid coordinates**
  `(m, l_eff, gamma)` — 12 keys: `stationary`, `demand_up`, `demand_down`, `lead_time_delay`,
  `shipment_loss`, `transit_stall`, and 6 `compound_*` crosses (`collie/control/grid.py:62-92`).
- Module 05 registers 7 **spec-semantic** keys: `demand_level_up/down`, `demand_pulse`,
  `arrival_delay/loss/stall`, `compound_split` (`collie/verify/registry.py:37-101`).
- Measured overlap: **none**. Every compiled config raises `unregistered predictive_model`;
  every registered construction is unreachable from the compiler.

Two further disagreements inside the same fork:

- **Shape coverage.** Module 04 compiles `TEMPORARY_PULSE` with `DEMAND_DOWN`
  (`mapping.py:126`); module 05 registers pulse only as `DEMAND_UP`. The derivation note §9
  lists pulse once, direction-agnostic; the frozen contracts delegate the legal
  family-signature registry to module 02 (`contracts.py:293-295`), which has not landed.
  **All three modules guessed; the guesses differ.**
- **Pulse duration is unrecoverable under module 04's scheme.** `_compile_canonical` treats
  pulse exactly like level shift (`mapping.py:140`), so a pulse proposal carries key
  `demand_up` — module 05's `bounded_duration_mixture_lr` construction could never be selected
  by key, and the note's family-3 row would be untestable.

Options:

- **A. Module 05 re-keys to module 04's coordinate keys.** Rejected as-is: loses pulse/duration
  and per-family semantics; the §9 table could not be asserted per family.
- **B. Module 04 emits spec-derived keys.** Fixes the semantics but breaks module 04's
  registered "pure function of coordinates" design (its 72-point enumeration story), touches
  merged code, and needs P1's sign-off plus a dated deviation.
- **C. Split the roles (recommended).** `ControlConfig.predictive_model` stays
  coordinate-derived as *descriptive metadata about the controller's belief*; the verifier
  resolves constructions from the spec itself — `resolve_spec` already does exactly this. The
  joint invariant becomes a **consistency test**: for every legal spec, the compiled key's
  family/stream/direction must be compatible with the resolved construction (one registered
  compatibility table, asserted both directions). The defensibility claim survives via the spec
  path: the model selects a registered family/signature, and the system derives the test from
  it. Needs P1 agreement (his docstring in `grid.py` promises the key resolves in module 05)
  and lands naturally alongside module 02's pairing registry.

Also in scope for the F1 conversation: module 05 hardcodes `REGISTERED_ONSET_WINDOWS`
(`registry.py:23`) while the frozen contracts assign the onset-window registry to module 02.
One registry conversation should settle keys, pairings, and onset windows together.

## F2 — P4: the `ActivationPolicy` adapter is missing, and the seam is too narrow

Nothing in `collie/verify/` implements module 06's `ActivationPolicy`
(`collie/arms/protocols.py:98-133`), so arm 10 still runs on `FakeVerifier`. This is expected
at checkpoint time, but it is pilot-blocking, and the mismatch is semantic, not just
signatures:

- The protocol's `observe(period, value)` carries **one scalar**. Module 05's arrival verifier
  needs `(dispatch_quantity, receipt)` per period; the compound verifier needs
  `(demand_value, dispatch_quantity, receipt)` (`lifecycle.py:382-396`). The arm holds all
  three in its history (`shockspec.py:_evidence_value`, `note_dispatch`) but can only pass one.
- **Fix, two parts.** (i) Widen the protocol's evidence channel — e.g.
  `observe(period, *, demand, dispatch, receipt)` — owned by module 06 (offer made; it touches
  `protocols.py`, the fakes, the three arm policies, and the conformance tests). (ii) P4 ships
  a thin adapter in `collie/verify/` implementing `reset` / `register(spec, *, baseline)` /
  `observe` / `is_active` / `state` over `LifecycleManager` and the stream verifiers, with
  `baseline=(mean, sd)` mapping onto `BaselineSpec`. Requirements: evidence stays strictly
  after `tau_j` (reuse `MixtureEProcess.validate_period`), validity labels flow into the
  `RunRecord`, and conformance tests in the style of `tests/test_arms_shockspec.py`'s
  signature-conformance pair prove the adapter satisfies the protocol *as the arm calls it*.

## F3 — P4: coverage is 81% against the 100% house bar

Measured on the merged tree with the slow calibration tests included
(`--cov=collie.verify`, 84 passed, 445 s): `arrival.py` 80%, `demand.py` 75%,
`eprocess.py` 92%, `lifecycle.py` 80%, `alpha.py` 94%, `registry.py` 95%. Two concentrations:

- `__main__` demo blocks: `arrival.py:889-978`, `demand.py:483-547`, `lifecycle.py:548-608`.
  House convention (modules 01/04/06) is a subprocess test that runs the demo and asserts its
  printed output — which also pins the CP2 demo contract.
- Scattered error paths (the `ValueError` guards) in all four main files.

## F4 — coordination: `tests/test_spec_verifier_contract.py` exists on both branches

Module 02's branch has a same-named file with parser-side semantics. Module 05's name is
prescribed by its own brief's audit command, so **module 02 renames** (added to Crescent's
instruction list). Separately: when module 02 lands, confirm
`test_module02_and_verifier_registries_match_when_p3_is_present` actually exercises the
production-registry branch rather than the mirror-table fallback.

## F5 — nits and notes

- Merged `tests/conftest.py`: the module docstring now describes only module 06's wiring; add
  one line for `--replications` (module 05) when the merge is committed for real.
- Slow calibration adds ~3 min to the default suite (~7.5 min under coverage). Fine for now;
  if CI time becomes painful, the deselect strategy is a maintainer decision, not P4's.

## What P4 should do, in order

1. F2(ii): the adapter, against the widened protocol (already on main — see below).
2. F3: demo subprocess tests plus error-path tests to 100%.
3. The full verification block: `make lint`, `uv run pytest -q`, `make check-freeze`,
   `make equivalence`, `--cov=collie.verify` at 100%.

## Resolution status — 2026-09-18 (updated post-audit)

- **F1: decided, option C, implemented.** Dated entries in `prereg/deviations.md`. The
  compiler label is descriptive metadata; the verifier keys off the spec. The joint
  consistency test is `tests/test_key_compatibility.py` on this branch — it already earned
  its keep on first run by surfacing that module 04's low/medium transit-pause row compiles
  to the `lead_time_delay` label; the table records that pairing explicitly with a pointer to
  the open tier-1 calibration question. Main-side docstrings updated (`grid.py`,
  `mapping.py`, `test_control_mapping.py`, `00-foundation.md`).
- **F2(i): done.** `ActivationPolicy.observe` is now
  `observe(period, demand, *, dispatch=None, receipt=None)` on main; the arm feeds all three
  channels from its history (new never-popped dispatch book), the rollback guard reads the
  receipt channel for arrival directions and raises on a missing channel, and the conformance
  test covers `observe` as well as `register`. **What remains for P4 is F2(ii): the adapter**
  — a thin `collie/verify/` class implementing the protocol over `LifecycleManager` and the
  stream verifiers, with `baseline=(mean, sd)` mapping onto `BaselineSpec`, evidence strictly
  after `tau_j`, validity labels into the `RunRecord`, and conformance tests in the style of
  `tests/test_arms_isolation.py`.
- **F3: unchanged, still P4's.** 81% → 100%, demo subprocess tests plus error paths.
- **F4: done.** Rename instruction added to `docs/module02_review_instructions.md` on
  Crescent's branch (module 02 renames; module 05's filename is brief-prescribed).
- **F5: done.** The merge on this branch carries the docstring line for `--replications`.
- **New main is merged into this branch** (single `conftest.py` conflict, resolved as
  documented above). The branch is at: full suite, lint, freeze, equivalence — all green.

## Final resolution — 2026-09-19

- **F2(ii): done.** `collie.verify.VerifierActivationPolicy` implements the widened activation
  protocol over the registered stream verifiers and `LifecycleManager`. The arm's `(mean, sd)`
  tuple is frozen into a `BaselineSpec`; demand, dispatch, and receipt remain period-aligned; the
  proposal-period observation conditions the arrival recursion without entering the strictly
  post-`tau_j` e-process product. Lifecycle output records carry the consumed evidence-validity
  label. Arm 10's pilot wiring now uses this adapter rather than `FakeVerifier`, and signature,
  channel, boundary, reset, and end-to-end conformance tests cover the production call path.
- **F3: done.** Subprocess audit tests execute the demand and arrival demos (the arrival demo also
  runs the compound lifecycle path). In-process mirrors keep those child-process paths under the
  coverage tracer, and deterministic guard tests cover the remaining error branches. The focused
  command reports `1326/1326` statements and `100.00%` coverage for `collie.verify`.
- **Final gates:** `1184 passed, 3 skipped` in the full suite (only provider-key tests skipped),
  equivalence `219 passed`, lint clean, and the frozen core-contract hash intact.
