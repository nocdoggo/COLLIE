# Module 02 — review and fix instructions (2026-09-16)

For: Crescent_79, branch `module-2-shockspec-interface`.
Reviewed against `docs/implementation/02-shockspec-interface.md` and
`.kiro/specs/collie-shockspec-interface/` (R1–R4, task 12). Verified independently on the branch:
suite green (1205 passed, 2 deliberately skipped), lint clean, contract freeze intact.

## What is already good — keep it

- Checkpoint suites pass: `test_spec_registry.py` + `test_spec_schema.py` (259 tests) and
  `test_prompt_legality.py` + `test_parse_repair.py` + `test_spec_verifier_contract.py` (105).
- 19 of the 21 named tests the brief lists are present, with negative cases per rule.
- The fuzz corpus runs 24 adversarial cases and prints the outcome/ledger table.
- The fail-forward skip guards in `tests/test_spec_verifier_contract.py` are a good pattern —
  they turn into loud failures the day a dependency lands instead of silently skipping forever.
- The schema reuses the frozen contract's abstention canonicalizer rather than duplicating it.
- hypothesis is in use; pydantic was already pinned; no TODOs in `collie/spec/`.

## 1. Merge `main` into your branch first

Modules 03 (alert bank) and 04 (OR compiler) merged on 2026-09-16. Consequences for you:

- `collie.control.mapping` now exists, so the guard in
  `test_no_change_placeholder_is_ignored_by_real_compiler_and_verifier` narrows to just
  `collie.verify.registry` (module 05, in progress on `module05-cp1`). Keep the guard; do not
  weaken it.
- The module-04 side of the joint invariant is now testable: `compile_spec` consumes every
  shape your registry declares. Module 04's tier-2 closure in `collie/control/mapping.py` is
  explicitly provisional pending *your* `legal_pairs()` registry — coordinate with ksu62 to
  replace the closure with `collie.spec.registry.legal_pairs()` and re-derive grid
  reachability from tier 1 alone.
- Read `prereg/deviations.md` (2026-09-16 entry): `GridCompiler` now composes compiled configs
  relative to the *running* config, so anything of yours that asserts absolute grid outputs
  through the seam needs to expect the composed result.
- After the merge, `*.key` and `cloud_endpoint/` are gitignored; never commit key material.

## 2. Add the two missing named tests

- `test_every_history_line_has_an_identifier` — every rendered history line in the prompt
  carries an enumerated identifier, and identifiers are unique (brief, Checkpoint 2).
- `test_ledger_counts_attempted_repaired_rejected` — one `CallLog` per attempt, and the
  conservation identity `attempted == accepted + repaired + rejected` (mirror module 06's
  ledger invariant).

## 3. Bring `collie/spec/` to the 100% house bar

`uv run pytest --cov=collie.spec --cov-report=term-missing -q` currently shows:

- `registry.py` 72% — add negative tests for every `_validate_registry` rule (mutate the
  tables, assert the specific `RuntimeError`) and for `expected_direction` on an unregistered
  pair. Checkpoint 1's pass criterion is "every rule has a passing negative case".
- `parse.py` 85% — the misses are the demo/CLI block. Either mark it `# pragma: no cover` -
  `CLI only` (module 04's precedent) or, better, add a smoke test running
  `main(["--demo-corpus"])` asserting exit 0 and at least 20 printed rows, since the demo is
  an audit command and should stay exercised.
- `prompt.py` 97% — cover or justify lines 69 and 132.

## 4. Add the module-06 seam adapters (this is what blocks the arms from using your work)

The arms receive every collaborator by injection against `collie/arms/protocols.py`:

- `SpecParser.parse(text) -> ProposalPayload | None` — a pure text-to-payload validation
  class wrapping your `validate_extracted_payload`. Provenance (`tau_j`, `proposal_index`,
  `model_id`, `decoding_hash`, `prompt_hash`) is stamped by the arm after validation, never
  accepted from the model — your payload model already has exactly the nine model-controlled
  fields, so the adapter is mechanical.
- `SpecPrompter.prompt(obs) -> str` — accumulates one observation per period and renders
  through your `build_prompt`.

With those, the R4 repair loop lives in the arm (parse → one repair prompt via your
`build_repair_prompt` → parse once more → clean fallback); keep your standalone two-call
`parse_shockspec` as the convenience path, both tested. Add runtime conformance tests in the
style of `tests/test_control_mapping.py::test_grid_compiler_satisfies_the_spec_compiler_protocol`.

## 5. Hygiene

- Translate the one remaining Chinese comment in `tests/test_prompt_legality.py`.
- Tick the 12.x checkboxes in `.kiro/specs/collie-shockspec-interface/tasks.md` as you finish
  them (the file stays local; never commit `.kiro/`).
- Add `docs/module02_research_notes.md` in the style of the module-01/06 notes, with
  `[registered]` markers on frozen choices.
- When the above is green — full suite, `make lint`, `make check-freeze`, `make equivalence`,
  plus the brief's two checkpoint audit commands — push and open the PR.

## Not yours to fix

- `collie/verify/registry.py` (module 05) — the joint construction test stays skip-guarded
  until it lands.
- The `collie/control/` tier-2 closure removal — coordinate with ksu62, don't edit it
  unilaterally.
