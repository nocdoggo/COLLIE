# 02. ShockSpec interface — schema, prompt, repair, fallback

| | |
|---|---|
| **Owner** | P3 |
| **Checkpoint 1** | Day 3 |
| **Checkpoint 2** | Day 9 |
| **Depends on** | `00-foundation.md`. `ShockSpec` already exists in the frozen contracts. |
| **Consumed by** | 04 or compiler, 05 verifier, 06 arms |
| **Joint work** | Day 9, with P4: the spec-to-verifier contract test |

## What you are building

The only channel through which a language model can influence an order. Everything the model is
allowed to say, it says here, in a closed typed object that cannot be edited afterwards.

Two settings on that object carry the entire validity argument, and they are already in the frozen
contract:

- **`extra="forbid"`** — the model cannot smuggle in a falsifier, a threshold, a likelihood, an order
  equation, or code. If it tries, validation fails; the field is not silently dropped.
- **`frozen=True`** — a hypothesis frozen at stopping time `tau_j` cannot be revised by the evidence
  that later tests it.

Your job is to make those settings meaningful: a registry so the *system* derives the statistical
test from a registered key while the model merely selects a key, a prompt that provably contains no
prohibited quantity, and a parse path that turns hostile model output into either a valid object or a
clean, counted abstention.

**The model never chooses its own test.** That sentence is the paper's core defensibility claim, and
this module is where it is either true or false.

## Where the code goes

```
collie/spec/
  __init__.py
  registry.py     registered vocabularies; hashed at the method freeze
  schema.py       payload sub-model, validators, provenance injection
  prompt.py       deterministic prompt construction, enumerated identifiers
  parse.py        extract -> validate -> one repair -> fallback, with accounting
tests/
  test_spec_registry.py
  test_spec_schema.py
  test_prompt_legality.py
  test_parse_repair.py
  test_spec_verifier_contract.py    joint with 05
```

`collie/contracts.py` already holds `ShockSpec` itself. Do not redefine it. `schema.py` adds the
payload-only sub-model and the registry-dependent validators that would otherwise force the contract
to import your registry.

## The registry is the contract

```python
# collie/spec/registry.py
ONSET_WINDOWS: tuple[tuple[int, int], ...] = ((-2, 0), (-1, 1), (0, 2), (-2, 2))

SIGNATURES: tuple[str, ...] = (
    "sig_demand_level_up", "sig_demand_level_down", "sig_demand_pulse",
    "sig_arrival_delay", "sig_arrival_loss", "sig_arrival_stall", "sig_compound",
)

FAMILY_SIGNATURE: dict[ShockFamily, frozenset[str]] = {...}
```

Windows are **relative to `tau_j`**, so `(-1, 1)` claims onset within one period either side of the
proposal. They are a closed set: an arbitrary window would let the model widen its claim until it
could not be wrong.

The verifier looks up its construction by `(shock_family, prospective_signature)`. Illegal pairings
are rejected at validation: `shock_family: demand_level` with
`prospective_signature: sig_arrival_stall` is not a coherent commitment, and allowing it would let
the model pick a mismatched test.

Two invariants, both tested: every family has at least one legal signature, and no signature is
orphaned.

## The nine payload fields

The model produces exactly these, and nothing else:

```
target_stream  shock_family  direction  onset_window  magnitude_bin
persistence    duration_bin  evidence_refs  prospective_signature
```

The five provenance fields — `tau_j`, `proposal_index`, `model_id`, `decoding_hash`, `prompt_hash` —
are injected by `parse.py` **after** the payload validates. Validate raw model JSON against a
payload-only sub-model so the model cannot set them. A spec claiming a `tau_j` earlier than
generation must raise.

`proposal_index` is 1-based because the alpha allocation is `alpha_j = alpha * 2^-j`.

### Cross-field rules

| Rule | Where |
|---|---|
| `no_change` implies null onset and magnitude, `none` stream and direction | already in the frozen contract |
| non-`no_change` implies onset and magnitude present | already in the frozen contract |
| `onset_window in ONSET_WINDOWS` | your field validator |
| `prospective_signature in FAMILY_SIGNATURE[shock_family]` | your model validator |
| `target_stream` consistent with `shock_family` | your model validator |
| `evidence_refs` subset of the prompt's enumerated ids | `parse.py`, which holds the prompt |

The frozen contract already normalises the cooperative-but-wrong spelling `magnitude_bin: "none"`
alongside `shock_family: "no_change"` into `null`, before construction. Do not re-handle it.

## Prompt construction

Permitted content, and nothing beyond it: alert text if any, demand and arrival history through
`tau_j`, inventory position, an aggregate pipeline summary, costs, permitted product context, and an
explicit statement that abstention is allowed.

**Every history line carries an identifier**: `obs_t17`, `alert_17`. Two purposes. It gives
`evidence_refs` a closed target set, and it makes the prompt auditable line by line in the later case
studies.

The abstention instruction needs care. The prompt must make `no_change` a first-class option without
nudging toward it or away from it. A model that always predicts a shock is a real failure mode, and
abstention precision and recall exist to make it visible.

**Prohibited content is a build-time test, not a runtime hope.** Construct a prompt from an episode
whose `incident.json`, `HiddenAlertSpec`, pattern name, article id, and future demand are all known,
then assert none of those strings or values appear anywhere in the prompt text. Assert the same for
actual lead times.

`build_prompt` must be deterministic and return a stable `prompt_hash`. Same state, same string,
same hash, across processes and runs.

## Parse, repair, fallback

```
attempt 1 -> extract JSON -> payload model
  ok    -> inject provenance -> frozen ShockSpec        ParseOutcome.ACCEPTED
  fail  -> attempt 2, repair prompt: schema restated, NO new episode information
             ok   -> inject provenance -> frozen ShockSpec   ACCEPTED_AFTER_REPAIR
             fail -> ParseOutcome.FALLBACK, unchanged OR for this opportunity
every attempt emits a CallLog entry
```

Extraction order, all three paths covered by the fuzz corpus: strict parse, then fenced-block
extraction, then first-balanced-object scan, then failure.

**Exactly one repair attempt.** The repair prompt restates the schema and adds no episode
information; otherwise it becomes a second look at the data and the commitment is no longer frozen at
`tau_j`.

**Fallback is observationally identical to no proposal.** The arm proceeds on baseline OR. It is not
an error to be swallowed; it is counted.

**Abstention is not failure.** `ACCEPTED` with `shock_family == no_change` is the model declining, and
feeds capability metrics. `FALLBACK` is a formatting failure, and feeds reliability metrics. Collapsing
them would confuse two different phenomena, which is why `ParseOutcome` is an enum rather than
`ShockSpec | None`.

---

## Checkpoint 1 — Day 3: registry and schema reject everything they should

### Deliverables

1. `registry.py` complete, with `FAMILY_SIGNATURE` filled in for all seven families.
2. `schema.py` — payload sub-model, all cross-field validators, provenance injection.
3. A table-driven test suite covering every rule, positive **and** negative.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_every_family_has_a_legal_signature` | and no signature is orphaned |
| `test_enum_closure_per_field` | an out-of-vocabulary value raises, per field |
| `test_unknown_field_is_rejected_not_ignored` | `extra="forbid"` is doing work |
| `test_post_validation_assignment_raises` | `frozen=True` is doing work |
| `test_onset_window_must_be_registered` | an unregistered window raises |
| `test_illegal_family_signature_pairing_raises` | table-driven over all pairs |
| `test_abstention_nullity_rules` | both directions |
| `test_model_cannot_set_provenance` | payload containing `tau_j` raises |
| `test_tau_j_earlier_than_generation_raises` | provenance sanity |
| `test_smuggled_threshold_field_raises` | the specific attack the design fears |

Table-driven means one test function iterating an explicit case table, each case naming the rule it
exercises and its expected outcome. A validator with only a positive case is not tested.

### Audit command

```bash
uv run pytest tests/test_spec_registry.py tests/test_spec_schema.py -v
```

### Pass criteria

- Every rule has a passing negative case. The auditor will look for this specifically.
- `registry.py` contains no `TODO` and no empty signature set.
- Printed count of legal `(family, signature)` pairs.

### Not expected yet

Prompt construction, JSON extraction, repair, the verifier contract test.

---

## Checkpoint 2 — Day 9: hostile output in, valid object or clean fallback out

### Deliverables

1. `prompt.py` with enumerated identifiers, determinism, and a stable hash.
2. `parse.py` with the three-stage extractor, one repair, fallback, and full accounting.
3. `evidence_refs` validated against the prompt's identifier set.
4. The joint spec-to-verifier contract test, with P4.
5. A demo over at least 20 adversarial outputs.

### The fuzz corpus

Build from `collie/fakes/fake_llm.py`'s `canned` payloads and extend. Minimum coverage:

```
valid                       valid + prose wrapper        valid in ``` fence
truncated JSON              two JSON objects             empty string
extra unknown field         smuggled "threshold"         wrong type (str for int)
onset_window unregistered   illegal family/signature     evidence_ref not in prompt
no_change with a magnitude  numeric string enum          unicode quotes
nested code block           JSON with trailing comma     null where enum expected
```

Every one must end in a validated `ShockSpec` or a counted `FALLBACK`. Never an unhandled exception,
never a silently dropped field.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_prompt_contains_no_prohibited_content` | against a known-truth episode: no incident values, no `HiddenAlertSpec`, no pattern name, no article id, no future demand, no actual lead time |
| `test_prompt_is_deterministic` | same state, same string, same hash, across processes |
| `test_every_history_line_has_an_identifier` | and identifiers are unique |
| `test_evidence_ref_outside_the_set_fails_validation` | it must fail, not be dropped |
| `test_extraction_handles_the_fuzz_corpus` | parametrised over every case above |
| `test_exactly_one_repair_attempt` | never two |
| `test_repair_prompt_adds_no_episode_information` | diff against the original prompt |
| `test_fallback_is_identical_to_no_proposal` | order sequence equality against a no-proposal run |
| `test_abstention_distinguished_from_failure` | `ACCEPTED` + `no_change` vs `FALLBACK` |
| `test_ledger_counts_attempted_repaired_rejected` | `CallLog` per attempt |
| `test_spec_maps_to_exactly_one_verifier_construction` | joint with P4, both directions |

That last test is the one the paper leans on. Both directions matter: every legal spec resolves to
exactly one registered construction, **and** no construction is reachable by a spec the schema cannot
express. If it is green, the model demonstrably did not choose its own test.

### Audit command

```bash
uv run pytest tests/test_prompt_legality.py tests/test_parse_repair.py \
              tests/test_spec_verifier_contract.py -v
uv run python -m collie.spec.parse --demo-corpus
```

### Pass criteria

- Full fuzz corpus handled, no unhandled exceptions.
- Prompt legality test green against a known-truth episode.
- A printed table of the 20+ adversarial outputs against their `ParseOutcome` and the resulting call
  ledger.
- The joint contract test green, with P4 confirming they co-reviewed it.

### Not expected yet

Real model calls. Module 06 owns transport; you depend only on the narrow `LLMClient` protocol and
develop entirely against `FakeLLM`.

---

## Deferred past this sprint

- Three-seed decoding robustness. Needs real transport.
- Held-out wording generalisation. Needs module 03's test-split templates and runs after the pilot.

## Risks specific to this module

- **A model that always predicts a shock.** Abstention metrics make it visible; the prompt must not
  nudge toward reporting. Check your wording against this explicitly.
- **Registry drift.** Any edit after the method freeze changes what the verifier means. `registry.py`
  and `schema.py` are both covered by the freeze guard.
- **Over-permissive `evidence_refs`.** Validating against prompt-enumerated identifiers is the only
  defence. A ref to a nonexistent identifier must fail validation. Dropping it silently would let the
  model cite evidence it never saw.
