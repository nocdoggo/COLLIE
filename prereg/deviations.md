# Deviations log

Every departure from a frozen artefact is recorded here, dated, with a reason. The point is not
ceremony: it is that a reviewer can reconstruct what was decided when, and that no frozen file can
change without leaving a trace.

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
