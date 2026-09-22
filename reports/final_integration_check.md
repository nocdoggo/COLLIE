# Final integration check — modules 01-06 as one system

Date: 2026-09-21. Baseline audited: `main` at `da9209c` ("Merge module 02: ShockSpec interface
— registry, prompt, parse, arm adapters (#7)"). Fixes shipped on `final-integration-polish`.

**Verdict: PRISTINE-AFTER-FIXES.** The six modules operate as one pipeline. Every joint
invariant holds, the arm ladder runs end to end with each module's real implementation, and the
statistical fencing is intact. Nothing semantic was wrong. What was wrong was the record: twelve
docstrings and comments still described unlanded dependencies, and the demo runner still injected
a hand-rolled stand-in for module 02's prompter and parser even though the real pair had merged.
Both are fixed. Five items remain open and belong to named owners; none blocks this certification.

This is not a re-audit of any single module. Each passed two checkpoint audits and a pre-merge
integration audit. What is certified here is the whole: cross-module coherence, stale-reference
removal, joint invariants, and end-to-end operation.

---

## Step 1 — Baseline, proven green before anything was touched

```text
uv run ruff check collie tests tools        -> All checks passed!
uv run ruff format --check collie tests tools -> 137 files already formatted
uv run python -m tools.freeze_contracts --check
  -> contract freeze intact (2026-09-01): collie/contracts.py
uv run python -m tools.select_equivalence_set --check
  -> manifests/equivalence_instances.txt is up to date (216 instances)
uv run pytest -m equivalence -q            -> 219 passed, 1368 deselected in 3.13s
uv run pytest -q                           -> 1 failed, 1586 passed in 165.92s (0:02:45)
```

**The one failure is environmental, not a regression.** It is
`tests/test_llm_client.py::test_live_grok_smoke`, which failed on
`openai.RateLimitError: 429 ... The model is currently at capacity due to high demand` from the
xAI endpoint. That test is marked `needs_llm`, runs only when operator key material is present,
and per its own module docstring never runs in CI — which is why CI is green on all seven merges
while a local run with keys present can see a provider 429. Re-running the live set immediately
afterwards passed:

```text
uv run pytest -q -m "needs_llm" -rs        -> 3 passed, 1584 deselected in 6.22s
```

1,586 + 1 = 1,587 collected, consistent with the stated baseline. Baseline accepted.

## Step 2 — Coverage re-certification

Measured on `main` with `uv run pytest --cov=collie --cov-report=term-missing -q`
(1587 passed in 547.99s):

```text
TOTAL                               6357     24    99%
```

Six of the seven subpackages at the house bar were at 100%. **One was not**, and the
ground-truth brief was slightly optimistic on it:

| Path | On `main` | Missing | Class |
|---|---|---|---|
| `collie/data/instances.py` | 97% | 114, 121 | untested error paths |
| `collie/eval/submission.py` | 99% | 91 | untested error path |
| `collie/adapter/inventorybench.py` | 84% | 63, 74, 84, 99-101, 160-179 | frozen file |
| `collie/contracts.py` | 99% | 359, 370, 445, 627-628 | frozen file |
| `collie/sim/reference_policies.py` | 97% | 79 | frozen file |
| `collie/sim/supply.py` | 98% | 152, 162 | frozen file |

All three non-frozen misses are untested error paths, not dead code, so each got a test rather
than a pragma: `_read_header_economics` raising on a header-only `test.csv` and on a file with no
`demand_*` column (it parses the first data row of 1,320 external CSVs, so a truncated file is the
realistic failure), and `SubmissionScores.batch` raising with the available batch names on a
mistyped name (every published comparison selects a batch by name).

After the fixes, on `final-integration-polish`:

```text
TOTAL                               6357     21    99%
1595 passed in 554.25s (0:09:14)
```

```text
collie/arms     10 files, 0 missed statements
collie/verify    9 files, 0 missed statements
collie/spec      6 files, 0 missed statements
collie/control   6 files, 0 missed statements
collie/trigger   6 files, 0 missed statements
collie/llm       5 files, 0 missed statements
collie/data     14 files, 0 missed statements
```

All seven subpackages at the house bar are now at 100%, and `collie/eval` joins them. The
remaining 21 statements are entirely inside the four frozen files listed above, every one a
defensive guard branch: period-range checks in `collie/sim/supply.py`, the unreachable dispatch
`else` in `collie/sim/reference_policies.py`, abstention-validation branches and the
`BaseModel` arm of the hidden-state walk in `collie/contracts.py`, and error paths in the
InventoryBench adapter. Those files are never-touch under the audit's own constraints, so the
gap is reported, not closed.

## Step 3 — Stale-reference sweep

Searched the whole tree excluding `.kiro`, `results`, `third_party`, `manuscript`, `.venv`,
`.git`, `.hypothesis`, `.kilo`.

Clean already:

- **`reference_control`** — the deleted module-04 stand-in leaves no stale reference. The only
  hits are `tests/test_arms_isolation.py`, which *pins its deletion* and bans arms from importing
  it, and a `reference_controller` fixture in `tests/conftest.py` that is a real
  `OrCompilerController`. Both are correct as they stand.
- **`TODO` / `FIXME` / `XXX` / `HACK` across `collie/`, `tools/`, `tests/`: zero.**

Twelve stale sites found and fixed. Each replaced with an accurate statement citing its source of
truth:

| Site | Was | Now |
|---|---|---|
| `collie/arms/protocols.py` | "Modules 02 and 05 are still stood in for" | all three seams named with the real class that satisfies each; fakes re-described as the isolation stand-in they now are |
| `collie/arms/shockspec.py` (×2) | "the real one will inherit the seam"; "`fake_verifier.py` today, module 05's e-processes unchanged later" | both policies on the seam raise on violation today; `VerifierActivationPolicy` is what the runner injects, and `EProcessActivation` stays for verifier objects that are not policies |
| `collie/control/mapping.py` (×2) | "Module 02's registry ... has not landed on `main` yet"; "will need to shrink ... once module 02's registry lands" | the registry has landed and is deliberately not consumed here; removal is the open P1/P3 item, with the pulse-down divergence named |
| `collie/verify/registry.py` | `resolve_construction` "Resolve the exact key emitted by the deterministic compiler" | contradicted the 2026-09-18 deviation; now states this is module 05's own key space, that the runtime path uses `resolve_spec`, and that this lookup is for inspection and tests |
| `collie/trigger/demo.py` (×2) | "module 03 lands later"; "until module 03 lands" | module 03 landed; the synthetic alert is now stated as a deliberate choice, with the reason (bank rendering would make firing times depend on template sampling and decoy conditions) |
| `collie/arms/controls.py` (×2) | "provisional until module 03 owns alert parsing" | module 03 landed and owns alert *generation*, not a text parser, so the keyword table is module 06's own and is reviewed at Gate 2 |
| `tools/run_arms.py` | "(module 03 lands later)" | rewritten: names every real collaborator, and states the two deliberately synthetic inputs and why |
| `tests/test_ledger_not_evidence.py` | "`collie/verify/` (today an empty stub, since module 05 has not landed)" | the scan runs over the real merged sources; test renamed off `_today` |
| `tests/test_control_mapping.py` | "Module 05 has not landed on `main` yet" | points at `tests/test_key_compatibility.py`, where the joint compatibility assertions actually landed |
| `tests/test_controller.py` | "Once module 06 exists, extend this ..." | module 06 landed and the extension exists; now cites `test_every_control_and_the_oracle_route_identically` and admits this half is close to tautological on its own |
| `tests/test_key_compatibility.py` | "pending module 02's pairing registry" | the registry landed and settled it as `demand_up` only; the assertion is the standing guard, not a placeholder |
| `tests/test_spec_verifier_contract.py` | dead `except ModuleNotFoundError` fallback | removed; the test now reads module 02's production registry unconditionally *and* keeps the independent transcription as a third cross-check |

Two notes on the brief's expectations. `tests/conftest.py` did **not** contain the
"stood in for" language; its docstring was accurate but silent about modules 02 and 05, so it
gained a paragraph naming where those two seams are wired. And
`docs/module05_integration_audit.md`, `docs/module04_implementation_summary.md`, and the
2026-09-18 entry in `prereg/deviations.md` all contain similar language but are **dated
historical artifacts** — a checkpoint summary that says "as of this checkpoint" is a record, not
a stale claim, and rewriting one would destroy the audit trail. Left alone deliberately.

## Step 4 — Joint invariants

```text
uv run pytest tests/test_key_compatibility.py tests/test_spec_lifecycle_contract.py \
              tests/test_spec_verifier_contract.py tests/test_control_mapping.py \
              tests/test_arms_isolation.py tests/test_arms_shockspec.py -q
-> 74 passed in 0.36s
```

All six pass on the branch: 04↔05 label/construction compatibility in both directions, 02↔05
spec contract in both directions, 02↔04 registry consumption, protocol conformance over
`register` *and* `observe`, and arm isolation. None was adjusted to pass.

One real divergence between two merged modules sits inside these tests and is *supposed* to:
module 04's tier-1 `CANONICAL_SHAPES` admits `(temporary_pulse, demand_down, demand)`, while
module 02's `legal_pairs()` registers `sig_demand_pulse` as `demand_up` only — eight shapes
against seven actionable pairs. `test_pulse_down_is_rejected_loudly` pins the rejection, so the
shape cannot leak through as a level shift. This is the known tier-2 coordination item, not a
defect.

## Step 5 — End-to-end operation

```text
uv run python -m tools.run_arms --split dev --episodes 18 --table    (exit 0)
```

All fifteen arms render, every cell populated from stored records. Arm 10 runs through module
05's real `VerifierActivationPolicy(episode_horizon=horizon)`, not `FakeVerifier` — the fake has
no non-test importer anywhere in the tree. The activation spread across the three ShockSpec arms
is real and ordered as the divergence test expects: 0.6419 (immediate) < 0.6931 (heuristic
rollback) < 0.7486 (e-process). The ledger conserves, `physical 2763 <= charged 2856`, and
`ledger.assert_conserved()` passes.

```text
| arm1_capped_base_stock       | 0.7624 | 0.8674 |
| arm8_spec_immediate          | 0.6419 | 0.9135 |
| arm9_spec_heuristic_rollback | 0.6931 | 0.9057 |
| arm10_spec_eprocess          | 0.7486 | 0.8693 |
| oracle_shockspec_headroom    | 0.8038 | 0.9070 |
Headroom band: stationary OR 0.7624 -> oracle 0.8038, width +0.0414
```

### The demo wiring, and exactly what changed

`tools/run_arms.py` defined `_DemoPrompter` and `_DemoParser` — self-labelled module-02
stand-ins — and injected them into all three ShockSpec arms, while already injecting module 04's
and module 05's real implementations. `collie.spec.adapters` had no non-test importer. The
consequence was not cosmetic: `_DemoPrompter` has no `observe` / `reset` / `repair_prompt`, so it
failed `isinstance(..., RepairingSpecPrompter)` and **the repair path was dead in the runner**,
and `_DemoParser` never consulted `collie.spec.registry`, so the legality closure was never
exercised end to end.

Now fixed. The runner builds one real `ShockSpecPrompter` / `ShockSpecParser` pair **per arm**
(the parser validates against its own prompter's last-rendered evidence identifiers, so a shared
pair would cross-contaminate the permitted evidence set), and the scripted transport is re-keyed
off module 02's real prompt instead of a demo prefix.

The order-identity check, `main` baseline against the branch:

```text
15,17c15,17
< | arm8_spec_immediate          | 0.6419 | 0.9135 | 26 |   792 | 1716 | 0.007029 |
< | arm9_spec_heuristic_rollback | 0.6931 | 0.9057 | 26 |   792 | 1716 | 0.007029 |
< | arm10_spec_eprocess          | 0.7486 | 0.8693 | 26 |   792 | 1716 | 0.007029 |
---
> | arm8_spec_immediate          | 0.6419 | 0.9135 | 26 | 33016 | 1716 | 0.031197 |
> | arm9_spec_heuristic_rollback | 0.6931 | 0.9057 | 26 | 33013 | 1716 | 0.031195 |
> | arm10_spec_eprocess          | 0.7486 | 0.8693 | 26 | 33007 | 1716 | 0.031190 |
27c27
< ledger: physical 2759, charged 2856, conserved
---
> ledger: physical 2763, charged 2856, conserved
```

**No arm's orders changed.** Mean normalised reward and fill rate are bit-identical for all
fifteen arms, the headroom band is unchanged, and each spec arm still makes 26 calls. This is
reported rather than asserted because it is the whole safety argument for the change: the
scripted payload is the same nine model-controlled fields, they still validate against the
registry, so the compiled `ControlConfig` and every order are the same.

Three things did change, all of them the metering record rather than behaviour, and all of them
consequences of the prompt now being real:

1. **Input tokens 792 → ~33,010 and cost ×4.4 per spec arm.** The real prompt carries the
   registered value lists, the legality table, the required JSON shape, and the visible history;
   the one-line stand-in carried none of that. The ledger prices what was actually sent.
2. **Physical calls 2759 → 2763.** The prompt embeds per-period observable state, so at a
   *second* proposal — after the three arms' own orders have moved that state — their prompt
   bytes genuinely differ and must not collapse to one call. Four such decision points stopped
   sharing. The charged total is unchanged at 2,856, and every decision point is still charged to
   all three arms.
3. **`prompt_hash` provenance.** The arm stamps `sha256(prompt)` itself, so the stamped hash
   moved with the prompt bytes. Verified consistent with module 02's own
   `PromptBundle.prompt_hash` over the same text.

Point 2 exposed an overclaim in the demo's own printed output, which said "shared proposal calls
across arms 8/9/10 collapse to one physical call each". That was already loose on `main` (33
physical calls for 26 decision points) and would have become misleading. It now prints the
measurement: `26 decision points, 78 charged copies, 37 physical`, with the reason sharing stops.
A test pins `charged == 3 * points` and `points <= physical <= charged`.

Provenance invariants re-confirmed on the real path: evidence identifiers are the prompt's own
(`("obs_t1", "obs_t2", "alert_2")` for a two-period history with an alert), the repair prompt
reuses them and adds no episode information, and the marker the scripted transport routes on is
pinned against a freshly built prompt — so a re-wording on module 02's side now fails a test
instead of silently routing every proposal to the direct-action payload and turning it into a
parse fallback.

### The rest of Step 5

```text
make equivalence                              -> 219 passed, 1376 deselected
uv run pytest tests/test_arm1_base_stock.py -q -> 34 passed
uv run pytest tests/test_alert_bank.py tests/test_alert_conditions.py \
              tests/test_alert_controls.py -q  -> 158 passed
```

Module 01's replay guarantee is intact through the merged tree.

## Step 6 — Per-module spot checks

| Module | Command | Result |
|---|---|---|
| 01 | `pytest tests/test_families.py tests/test_splits.py tests/test_nullbank.py -q` | 105 passed |
| 03 | `python -m tools.score_alert_templates --report` | `human ratings missing: reports/alert_audit_ratings.csv`, **exit 2 — the expected state**, Task 11 human-rater audit pending |
| 04 | `python -m collie.control.mapping --print-table` | 271 legal specs enumerated, 72 distinct configs reached, tier1/tier2 tagged |
| 05 | `pytest tests/test_calibration.py -k demand --replications 200 -q` | 4 passed, 5 deselected |
| 05 | `python -m collie.verify.arrival --demo` | validity table, official-arrival scope, compound lifecycle `proposed(12) -> active(16) -> expired(20)` |
| 06 | `python -m collie.trigger.detectors --trigger-table --episodes 12` | `alert_or_detector 12, random_matched 2` within ±3 of onset |

## Step 7 — Hygiene

```text
git log main --format='%an <%ae> | %cn <%ce>' -20
  15  Noctis <45600261+nocdoggo@users.noreply.github.com>   (author and committer)
   4  Crescent_79 <lujingyijy@gmail.com>                    (author and committer)
   1  CR7-cr777 <chelseatiann@gmail.com>                    (author and committer)

git ls-files | grep -cE "^\.kiro/|^results/|\.key$|^cloud_endpoint/"   -> 0
git ls-files | grep -c "^manuscript/"                                  -> 0
git check-ignore -v cloud_endpoint/*
  .gitignore:232:/cloud_endpoint/   cloud_endpoint/{gemini,grok,zai}.key
```

Module owners' own commits on their merged branches, as expected. No foreign identity. The three
key files are present on disk and ignored by path; their contents were never read.

`ls collie/` — `adapter arms contracts.py control data eval fakes llm sim spec trigger verify`.
No stray subpackages: the six modules plus `fakes`, `sim`, `adapter`, `eval`.

## Final state on `final-integration-polish`

```text
make lint                                     -> All checks passed! / 137 files already formatted
make check-freeze                             -> contract freeze intact (2026-09-01)
uv run pytest -q                              -> 1595 passed in 168.64s (0:02:48)
uv run pytest --cov=collie --cov-report=term-missing -q
                                              -> 1595 passed; TOTAL 6357 21 99%
                                                 (all 21 inside frozen files; the seven
                                                  house-bar subpackages at 100%)
make equivalence                              -> 219 passed, 1376 deselected
joint invariants                              -> 74 passed
uv run python -m tools.run_arms --split dev --episodes 18 --table  -> exit 0, ledger conserved
```

Eight tests added (1,587 → 1,595): three closing the coverage gaps, five pinning the module-02
wiring and the shared-call accounting. No frozen file changed. Both protected test files touched
(`tests/test_arm1_base_stock.py`, `tests/test_instance_loader.py`) gained tests only — no
assertion was weakened or removed.

---

## The three claim-hygiene fences hold

The 2026-09-21 entry in `prereg/deviations.md` records three findings on module 05 and asserts
they are fenced because "all output is stamped `analysis_class = exploratory` (with a hard guard
refusing `empirical_only` rows a confirmatory label)". **Verified in code. That sentence is
accurate for the merged runtime path**, and the fencing was not weakened by anything in this
change.

- `VerifierActivationPolicy` defaults `analysis_class = AnalysisClass.EXPLORATORY`
  (`collie/verify/adapter.py`), and the **only** production construction site is arm 10 in
  `tools/run_arms.py`, which passes no override. Every `LifecycleEvent` is stamped by one
  code path (`ProposalLifecycle._event`), so no record escapes unlabelled.
- Four hard guards raise rather than degrade: `collie/verify/lifecycle.py` refuses an
  analysis-class mismatch between evidence and lifecycle, refuses `empirical_only` evidence in a
  confirmatory lifecycle, and refuses the provisional flag under a confirmatory runner;
  `collie/verify/arrival.py` refuses to label an `empirical_only` arrival verifier confirmatory;
  `collie/verify/demand.py` is stricter still, refusing anything that is not `anytime_valid`.
- Finding 1 (prefix-estimated demand null), finding 2 (alternative arrival filters starting from
  the null posterior, `arrival.py` — validity preserved, power degraded for already-in-progress
  shocks), and finding 3 (`arrival_source` defaulting to `collie_shockspec` with no provenance
  binding — confirmed: nothing compares it against episode provenance) are all present exactly as
  described, unfixed, and fenced.
- Fences are pinned by tests in `tests/test_lifecycle.py`, `tests/test_verifier_error_paths.py`,
  `tests/test_arrival_forward.py`, `tests/test_eprocess_demand.py`, `tests/test_calibration.py`,
  and `tests/test_verifier_adapter.py`.

One honest qualification for P4, offered as an observation and not acted on: the fence is a
default plus constructor-level string comparisons, not a structural invariant.
`MixtureEProcess` and `EProcessPoint` will hold `validity_label = empirical_only` together with
`analysis_class = confirmatory` if constructed directly, and the lifecycle guard tests the exact
string `empirical_only`, so the sibling labels `no_finite_sample_guarantee` and
`empirical_only_permanently` would pass it. Nothing today constructs those combinations. It
matters only for the Gate 2 decision the deviation entry already assigns to P4.

The only certified guarantee in this system remains what it was: **arm 10's activation is
model-conditional, anytime-valid, per-episode.** No label, docstring, or comment was strengthened
beyond it in this change.

---

## Findings handed to owners

None of these was touched. All five are reported as found.

1. **Three claim-hygiene findings on module 05** — the prefix-estimated demand null still earning
   the `anytime_valid` label, whose finite-sample argument covers the exact-null case only;
   alternative arrival filters copying the null posterior; `arrival_source` without a provenance
   binding. Fencing confirmed above. **Owner: P4, before Gate 2.**
2. **Tier-2 closure removal in `collie/control/mapping.py` — ready, and now due.** Module 02's
   `legal_pairs()` has landed, which was the stated trigger. `mapping.py` still imports nothing
   from `collie.spec`: tier 1's `CANONICAL_SHAPES` duplicates the registry rather than consuming
   it, and removal requires re-deriving grid reachability from tier 1 alone, because tier 2 is
   what currently makes all 72 configs reachable. The eight-shapes-versus-seven-pairs divergence
   on pulse-down must be settled in the same conversation. The stale "has not landed" comments are
   fixed and now name this as the open item. **Owners: Crescent and ksu62, jointly.**
3. **`tools/run_arm1.py --limit` is unvalidated** — same *class* of defect as the already-fixed
   `tools/run_arms.py --episodes`, but the symptom differs from the one in the audit brief, so
   here is what the code actually does. Line 193 is `keys = keys[: args.limit]`, a slice, so a
   value above the 1,320-instance pool **silently clamps rather than raising `IndexError`**. The
   two real cases are `--limit 0`, which surfaces as an uncaught traceback instead of an argument
   error:

   ```text
   uv run python -m tools.run_arm1 --limit 0 --no-write --harness eval
     ValueError: cannot aggregate an empty submission     (exit 1)
   ```

   and a negative value, which silently drops instances from the *end* of the census and still
   writes a submission — the quieter and worse of the two. A positive-integer guard would close
   both. **Owner: module 01.**
4. **Task 11 human-rater alert audit** — `tools/score_alert_templates.py --report` exits 2 until
   `reports/alert_audit_ratings.csv` exists. Confirmed to be exactly that, and nothing else.
   **Owner: module 03 / P3.**
5. **Module 07 does not exist.** `prereg/` holds only `contract_freeze.json` and
   `deviations.md`; `prereg/prereg_v1.yaml` is absent, while four code files already cite it as
   the registry of record — `collie/contracts.py` (the order cap), `collie/sim/accounting.py`,
   `collie/control/mapping.py` (the tier-1 mapping table), and `tools/audit_benchmark.py` — plus
   `docs/env_contract.md` and three implementation briefs. Out of scope here; flagged because
   those forward references go wrong if module 07 registers those parameters anywhere else.
   **Owner: P4, module 07.**

Two smaller observations, no owner action implied:

- `collie/control/mapping.py`'s `__main__` block parses `--print-table` and then calls
  `_print_table()` unconditionally, discarding `args`, so the flag is decorative. It is inside a
  `# pragma: no cover - CLI only` block. Left alone because honouring the flag would change what
  the bare `python -m collie.control.mapping` invocation prints, and that is a behaviour change,
  not pristine-ization.
- `collie/llm/demo.py` is the one production module that imports `collie.fakes` at module level.
  `collie/control/grid.py` and `collie/spec/parse.py` do the same thing function-locally, behind
  the demo boundary, which is the cleaner convention. Not changed: `tools/run_arms.py` imports
  `scripted_endpoint` from it, so moving the import is a wiring change to a working path.

## Deliberately left alone

- Every frozen or protected artefact: `collie/contracts.py`, `collie/sim/*`,
  `collie/adapter/inventorybench.py`, `third_party/**`. Their 21 uncovered statements are
  reported above, not closed.
- CI structure and the ~1h52m runtime. Splitting module 05's 2,000-replication calibration out
  of the coverage job is a maintainer decision.
- Calibration replication counts, every statistical label, and every registered deviation.
- The trigger demo's and the arm ladder's synthetic alert channel. Module 03's bank has landed
  and *could* be rendered in, but that would make trigger firing times and every arm's orders
  depend on template sampling and on the bank's noise and decoy conditions. That is a behaviour
  change, not pristine-ization. The wording now states it as a choice with its reason instead of
  as a missing dependency.
- `manuscript/`, which exists untracked on `main` and is committed only on `manuscript-uv2026`.
  Never staged, never deleted.
- All remote branches.
