# Module 02 research notes

Complete design record for the ShockSpec interface. Sources are the Module 02 brief, the frozen
core contract, the implemented Module 02/04/06 seams, and the pinned package set. Choices owned by
this module are marked **[registered]**.

## 1. Scope and validity boundary

ShockSpec is the only channel through which model output may affect an order. The model selects a
closed semantic claim; it never supplies an order, statistical test, threshold, likelihood,
falsifier, formula, or executable code. The system derives the verifier and controller behavior
from registered keys.

The ownership boundary is:

| Concern | Owner |
|---|---|
| vocabulary, payload validation, prompt, extraction, one repair | Module 02 |
| model transport, cache, and charged-call ledger | Module 06 |
| ShockSpec-to-control compilation | Module 04 |
| statistical construction and lifecycle | Module 05 |
| hidden incident truth and evaluation | generator/evaluation only |

The frozen `ShockSpec` uses `extra="forbid"` and `frozen=True`. Module 02 adds the
registry-dependent rules and ensures untrusted model output cannot cross the boundary before
validation.

## 2. Payload and provenance **[registered]**

The model controls exactly nine fields:

| Field | Restriction |
|---|---|
| `target_stream` | must agree with the family |
| `shock_family` | closed enum |
| `direction` | must agree with family and signature |
| `onset_window` | one registered window |
| `magnitude_bin` | closed enum; null only for abstention |
| `persistence` | closed enum |
| `duration_bin` | closed enum |
| `evidence_refs` | subset of identifiers in the exact prompt |
| `prospective_signature` | registered for the selected family |

Five provenance fields are system-owned and absent from `ShockSpecPayload`:

- `tau_j`
- `proposal_index`
- `model_id`
- `decoding_hash`
- `prompt_hash`

They are attached only after payload validation. `proposal_index` is one-based for
`alpha_j = alpha * 2^-j`; invalid proposal context fails before any model call.

The payload reuses the frozen contract's abstention normalizer. For `no_change` only, the
cooperative spelling `"none"` for onset or magnitude is normalized to JSON `null`. The validated
object always contains Python `None` for those fields.

## 3. Registry **[registered]**

The registry has eight legal family/signature pairs, seven of them actionable:

| Family | Stream | Direction | Signature |
|---|---|---|---|
| `no_change` | `none` | `none` | `sig_demand_level_up` (ignored placeholder) |
| `demand_level` | `demand` | `demand_up` | `sig_demand_level_up` |
| `demand_level` | `demand` | `demand_down` | `sig_demand_level_down` |
| `temporary_pulse` | `demand` | `demand_up` | `sig_demand_pulse` |
| `lead_time_shift` | `arrival` | `arrival_delayed` | `sig_arrival_delay` |
| `shipment_loss` | `arrival` | `arrival_interrupted` | `sig_arrival_loss` |
| `transit_pause` | `arrival` | `arrival_interrupted` | `sig_arrival_stall` |
| `compound` | `both` | `mixed` | `sig_compound` |

The registered onset windows, relative to `tau_j`, are:

```text
(-2, 0), (-1, 1), (0, 2), (-2, 2)
```

A closed set prevents a model from widening its claim after observing the data. Window cells use
strict integers and the frozen contract requires `lo <= hi`.

`_validate_registry()` checks complete family coverage, non-empty signature sets, one direction
per signature, no orphaned or unknown signatures, and no duplicates. Every rule has a negative
test.

### 3.1 Temporary pulse direction **[registered]**

`TEMPORARY_PULSE + DEMAND_DOWN` is not expressible. The controlled Module 01 temporary-spike family
uses multipliers above one, and the single `sig_demand_pulse` construction is therefore
`DEMAND_UP`. A downward pulse would require a separately registered signature and verifier
construction; the existing signature is not given two meanings.

### 3.2 Abstention placeholder

The frozen wire shape requires a signature for `no_change`. `sig_demand_level_up` is retained as an
ignored placeholder. Consumers must branch on `spec.is_abstention` before resolving the signature,
so it never becomes a demand-up claim.

## 4. Schema validation

`ShockSpecPayload` uses the pinned Pydantic v2 API with forbidden extra fields, frozen instances,
closed enums, and strict onset integers. Validation applies:

1. frozen-contract abstention normalization;
2. field and enum validation;
3. registered onset-window validation;
4. family/signature validation;
5. family/stream validation;
6. derived-direction validation; and
7. the frozen contract's universal abstention/nullity rules.

Rejected inputs include unknown fields, model-supplied provenance, thresholds, confidence values,
wrong types, unknown enums, illegal family/signature pairs, phantom evidence, and malformed
abstentions. Validated payloads and final specs cannot be mutated.

## 5. Prompt boundary **[registered]**

The prompt may contain only observable information through `tau_j`:

- operational alert text;
- previous demand, or previous sales and availability in censored mode;
- previous orders and arrivals;
- on-hand and aggregate in-transit inventory;
- inventory position, promised lead time, and costs; and
- permitted product context.

It must not contain hidden incident fields, `HiddenAlertSpec`, pattern/template/article identity,
future observations, realized lead times, generator seeds, or baseline-twin truth.

`assert_no_hidden_state` checks the supplied object graph structurally. Future observations are
filtered before rendering. Known-truth and differential tests verify that changing hidden metadata
or future demand does not change prompt bytes.

Alert text is encoded with ASCII JSON escapes so newlines, Unicode separators, and lone surrogates
cannot forge history lines. Operational text and product context are explicitly labeled as data,
not instructions.

### 5.1 Evidence identifiers **[registered]**

Every observation line begins with `obs_tN`; every alert line begins with `alert_N`. Periods must
be unique and alert identifiers are checked for collision. Tests verify that every history line has
one unique identifier and that the rendered order equals `PromptBundle.evidence_ids`.

`evidence_refs` is validated against the exact rendered bundle. Unknown, future, or phantom
identifiers cause rejection rather than being dropped.

### 5.2 Prompt identity

Observations are sorted by period and serialized deterministically. `prompt_hash` is SHA-256 over
the exact UTF-8 prompt bytes. Determinism is tested both in-process and in a fresh Python process.

`no_change` is presented as a first-class option without rewarding or discouraging abstention.

## 6. Extraction, repair, and fallback **[registered]**

Extraction is deterministic:

1. parse the whole response as strict JSON;
2. try fenced blocks in appearance order; and
3. scan for the first balanced object while respecting strings and escapes.

The result must be one object and still passes full schema and evidence validation. Duplicate keys,
`NaN`, `Infinity`, trailing commas, Unicode quotes, wrong types, and unknown fields remain invalid.
The balanced-object path accepts surrounding prose; it does not repair invalid JSON.

There is exactly one format-only repair:

```text
attempt 1 -> validate
  success -> ACCEPTED
  failure -> record rejection and append the fixed repair suffix
attempt 2 -> validate
  success -> ACCEPTED_AFTER_REPAIR
  failure -> FALLBACK with no spec
```

The repair suffix adds no episode information or new evidence identifiers. Each attempted call has
one `CallLog`, a unique attempt index, the exact prompt hash, and an explicit outcome. Therefore:

```text
attempted = accepted + repaired + rejected
```

| Path | Counts `(accepted, repaired, rejected)` |
|---|---|
| direct success | `(1, 0, 0)` |
| repair success | `(0, 1, 1)` |
| two failures | `(0, 0, 2)` |

An accepted `no_change` is abstention, not failure. `FALLBACK` is a reliability outcome. Fallback
registers no spec and produces the same order sequence as no proposal.

The audit corpus contains 24 cases spanning valid wrappers, abstention, nested/multiple objects,
malformed JSON, duplicate and smuggled fields, illegal combinations, phantom evidence, Unicode,
and clean fallback.

## 7. Module 06 adapters **[registered]**

Module 06 consumes injected `SpecPrompter` and `SpecParser` collaborators.

`ShockSpecPrompter`:

- accumulates observable history;
- rejects conflicting observations for one period;
- renders and retains the current `PromptBundle`;
- produces the fixed repair prompt; and
- clears episode state on reset.

`ShockSpecParser` validates text against the paired prompt's evidence identifiers and converts the
nine fields to `ProposalPayload`. It does not call a model or attach provenance.

`RepairingSpecPrompter` is runtime-checkable and adds `observe`, `reset`, and `repair_prompt` while
preserving compatibility with legacy one-shot prompters. `isinstance` tests verify conformance to
`SpecPrompter`, `SpecParser`, and `RepairingSpecPrompter`.

The arm owns transport, charged-call accounting, repair dispatch, and provenance. Integration tests
use the real prompt, parser, ShockSpec arm, and `GridCompiler`; only model responses are scripted.
Arms 8/9/10 can share physical calls while retaining separate charged entries.

## 8. Downstream boundaries

### 8.1 Module 04

`GridCompiler` composes relative to the running control configuration. Integration tests therefore
call `compile(spec, current=current)` and verify that abstention preserves `current`.

Module 04's tier-2 closure predates this registry. Replacing it and re-deriving grid reachability is
owned by the Module 04 maintainer; Module 02 does not edit that mapping unilaterally.

`ControlConfig.predictive_model` is descriptive grid metadata. The verifier derives its
construction from the ShockSpec family/signature pair; the two key spaces are checked for
compatibility rather than string equality.

### 8.2 Module 05

The required joint invariant is bidirectional:

1. every legal Module 02 spec resolves to exactly one verifier construction; and
2. every registered construction is reachable from a legal spec.

The real `collie.verify.registry` is not yet present on `main`. The joint test remains intentionally
skip-guarded and must be completed when that dependency lands. No fake registry is introduced.

## 9. Verification status

The final local audit after merging the latest `main` produced:

| Gate | Result |
|---|---|
| full suite | 1,461 passed; 5 expected skips |
| `collie/spec` coverage | 342 statements, 0 missed, 100% |
| Checkpoint 1 | 267 passed |
| Checkpoint 2 | 112 passed; 2 expected Module 05 skips |
| demo corpus | 24 cases |
| lint and format | clean |
| contract freeze | intact |
| accounting equivalence | 219 passed |

The two Module 05 skips reflect the missing real registry. The other three skips require local
provider credentials and are unrelated to Module 02.

## 10. Deferred work

- Complete the bidirectional verifier compatibility test when Module 05 lands.
- Coordinate removal of Module 04's provisional tier-2 closure.
- Run three-seed robustness when supported real transport is available.
- Evaluate held-out wording generalization with Module 03 test-split runs.

Registry changes after Gate 2 affect the meaning of both compiler and verifier results and must be
recorded as dated deviations rather than silent edits.
