# 03. Alert bank, information conditions, and text controls

| | |
|---|---|
| **Owner** | P3 |
| **Checkpoint 1** | Day 5 |
| **Checkpoint 2** | Day 8 |
| **Depends on** | 01 shock generator, for seeds and the independent-unit id |
| **Consumed by** | 06 arms, 07 evaluation |
| **Joint work** | Day 8, with P4 as second rater, time-boxed to one session |

## What you are building

The operational text a human colleague would plausibly send: *"supplier flagged a customs hold on
next week's container."* Sometimes accurate, sometimes overstated, sometimes vague, sometimes about
something else entirely.

Behind every message sits a hidden `HiddenAlertSpec` recording what is **actually** happening, even
when the message misleads. That is what lets downstream metrics compare a model's reading against
truth rather than against the text.

You are also building the experimental controls that separate two things people routinely conflate:

- **Semantic value** — did the *meaning* of the message help?
- **Early-warning value** — did *knowing sooner* help?

These are different estimands. A design that cannot separate them cannot support either claim. The
mechanism is that content controls hold the timestamp and trigger trace **fixed** while varying only
the text; the early-warning comparison is reported separately and is allowed to differ in call time.

## Where the code goes

```
collie/data/
  alerts/
    __init__.py
    templates/          180 YAML files, or grouped YAML with 180 entries
    bank.py             loader, validation, deterministic slot instantiation
    conditions.py       the four information conditions
    controls.py         content controls and the ContentVariantSet
    audit.py            two-rater rubric scoring and agreement
tools/
  build_alert_bank.py
  score_alert_templates.py
tests/
  test_alert_bank.py
  test_alert_conditions.py
  test_alert_controls.py
```

## Template schema

```yaml
- id: tpl_042
  family: transit_pause
  split: dev              # dev | cal | test
  kind: overstated        # accurate | overstated | ambiguous | distractor
  wording_family: wf_customs_hold
  text: "Freight forwarder reports {port} congestion; {product} containers held {vague_duration}."
  slots:
    port: [Rotterdam, Felixstowe, Ningbo]
    vague_duration: ["for now", "until further notice", "indefinitely"]
  alert_spec:
    family: transit_pause
    target_stream: arrival
    direction: arrival_interrupted
    onset_window: [-1, 1]
    magnitude_bin: medium
    persistence: transient
    duration_bin: "4_8"
    prospective_signature: sig_arrival_stall
    kind: overstated
```

`alert_spec` uses **the same field names and closed vocabularies as `ShockSpec`**, deliberately. It
is the canonical answer against which a model's proposal is scored, so any divergence in vocabulary
would make the comparison lossy. Load it into `HiddenAlertSpec` from `collie/contracts.py`.

`wording_family` is the holdout axis. Test wording families must never appear in dev or cal, so
generalisation to unseen phrasing is measurable rather than assumed.

The loader rejects unknown enum values and missing slots. Loudly, at load time.

## Bank composition — exact counts

```
6 families x 10 templates per split x 3 splits = 180
```

Within each family-split cell of 10:

| Kind | Count | What it does |
|---|---|---|
| `accurate` | 4 | says what is happening |
| `overstated` | 2 | right family, exaggerated severity or duration |
| `ambiguous` | 2 | right family, too vague to pin down magnitude or timing |
| `distractor` | 2 | plausible operational noise, **no** shock; `alert_spec.family = no_change` |

Distractors are the ones that catch an overeager model. A pipeline that proposes a shock on every
alert will look competent until the distractors are scored.

## The four information conditions

| Condition | `InformationCondition` | Timing |
|---|---|---|
| none | `no_alert` | no message at all |
| early accurate | `early_accurate` | accurate message at `onset - 1` |
| late accurate | `late_accurate` | accurate message at `onset + 2` |
| unreliable | `unreliable` | overstated, ambiguous, or distractor |

**All four share bitwise-identical exogenous draws for a given seed.** Same demand, same lead times,
same losses, same onset, same slot draws. Only the message and its timing change. This is what makes
them paired replays of one independent unit rather than four samples, and it is the single most
important property in this module.

Emit `independent_unit_id` from `manifests/shockspec_v1.json` on every rollout. Module 07 aggregates
over it. Without it, a four-condition design silently claims four times the sample size it has.

## Content controls, with the timestamp held fixed

| Variant | Text | Timestamp |
|---|---|---|
| true | the real message | fixed |
| masked | content removed, length matched | fixed |
| shuffled within timing | words shuffled, timing preserved | fixed |
| wrong text | a different family's message | fixed |
| neutral baseline | equal-length operational filler | fixed |

Masked and neutral are length-matched within a registered tolerance, so message length is not a
confound.

**Make the mistake structurally impossible.** `ContentVariantSet` carries **one** shared timestamp and
**one** shared trigger-trace hash for the whole set, and the comparison helper accepts nothing else.
Assembling a content contrast from variants with differing call times must raise, not warn. Getting
this wrong produces a result that looks like a semantic finding and is actually a timing finding.

Two further controls answer **different** questions and must be documented as such, not folded in:

- **numeric-history-removed** — what does the model contribute beyond the numbers?
- **no-alert** — what does the alert channel contribute at all?

---

## Checkpoint 1 — Day 5: 180 templates, composition proved, leakage scan biting

### Deliverables

1. Template schema and loader with strict validation.
2. All 180 templates authored.
3. Deterministic slot instantiation.
4. The leakage scan, with a deliberately leaky fixture that fails it.

### Deterministic instantiation

Draw slot values from a hash of `(template_id, seed)`. The `template_id` must survive instantiation
so it can reach `RunRecord.template_id` for the language analysis.

Same `(template_id, seed)` gives the same rendered string, always. And no rendered string repeats
within a split, or two rollouts share text while claiming to be different stimuli.

### The leakage scan

Reject any template whose rendered text contains:

- an exact multiplier, `1.5`, `50%`, `half`
- a latent family name or a close paraphrase, `demand_level`, "level shift"
- an exact onset period or duration, "starting period 17", "for exactly 4 weeks"
- any value from `incident.json`
- a benchmark pattern name, an article id, or an instance path

Alerts are allowed to be **informative**. They are not allowed to be the answer. An alert saying
"demand will be 1.5x from period 17 for 4 weeks" turns the task into copying.

Write the leaky fixture first, watch the scan fail, then author the real bank. A scan that has never
failed has never been tested.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_loader_rejects_unknown_enum` | and missing slots |
| `test_composition_per_family_split_cell` | exactly 4/2/2/2, every one of the 18 cells |
| `test_total_is_180` | |
| `test_distractors_are_no_change` | `alert_spec.family == no_change` for every distractor |
| `test_instantiation_is_deterministic` | same `(template_id, seed)`, same string |
| `test_no_repeated_rendered_string_within_split` | |
| `test_template_id_survives_instantiation` | |
| `test_leakage_scan_rejects_a_leaky_fixture` | the scan is not vacuous |
| `test_no_test_wording_family_in_dev_or_cal` | the holdout holds |
| `test_alert_spec_vocabulary_matches_shockspec` | field names and enums line up |

### Audit command

```bash
uv run pytest tests/test_alert_bank.py -v
uv run python -m tools.build_alert_bank --render-sheet 24
```

### Pass criteria

- All tests green.
- A rendered sheet of 24 messages printed beside their hidden `AlertSpec`s. The auditor reads these as
  a human: do they sound like something a colleague would actually write? An implausible bank
  invalidates the realism claim no matter how well the code works.
- The leaky fixture demonstrably fails the scan.

### Not expected yet

Information conditions, content controls, the rater audit.

---

## Checkpoint 2 — Day 8: conditions paired, controls structurally sound, audit done

### Deliverables

1. The four-condition renderer, with bitwise-identical exogenous draws.
2. `ContentVariantSet` and the content-control renderer.
3. The numeric-history-removed and no-alert controls, documented separately.
4. Two-rater audit complete over all 180 templates, with per-criterion Cohen's kappa.

### The rater audit

Five criteria, each scored 1 to 5 by both raters:

1. **Operational plausibility** — would a real colleague send this?
2. **Consistency with the canonical label** — does `alert_spec` match what the text implies?
3. **Could this information exist at this time?** — no retrospective knowledge.
4. **Absence of hidden-state leakage** — independent of the automated scan.
5. **Realistic uncertainty** — hedged where a real message would hedge.

P3 authors and scores; **P4 is the second rater**. Both score all 180 base templates plus a stratified
sample of instantiated renderings. Time-box it to one session; it is bounded work, not open-ended.

Rules that are not negotiable:

- Every template gets two scores per criterion. A missing score is a failed test, not a gap.
- **A below-threshold leakage score from either rater removes the template unconditionally**, no
  consensus, no discussion. Leakage is not a matter of opinion.
- Adjudication is logged, with the disagreement and the resolution.
- Report per-criterion Cohen's kappa.
- **If kappa is low, shrink to 120 templates and record a dated deviation** in
  `prereg/deviations.md`. A smaller bank two raters agree on beats a larger one they do not.

### Tests that must pass

| Test | What it asserts |
|---|---|
| `test_four_conditions_share_exogenous_draws` | bitwise identity of demand, lead times, losses, onset, slot draws |
| `test_independent_unit_id_on_every_rollout` | and it resolves to exactly one seed |
| `test_content_variants_share_timestamp` | one timestamp and one trigger-trace hash per set |
| `test_cross_timestamp_contrast_raises` | assembling from differing call times raises |
| `test_masked_and_neutral_length_matched` | within the registered tolerance |
| `test_every_template_has_two_scores_per_criterion` | |
| `test_leakage_failure_removes_template` | regardless of the other rater's score |

### Audit command

```bash
uv run pytest tests/test_alert_conditions.py tests/test_alert_controls.py -v
uv run python -m tools.score_alert_templates --report
uv run python -m tools.build_alert_bank --replay-one-seed --show-diff
```

### Pass criteria

- All tests green.
- Agreement report with per-criterion kappa, plus the removal log.
- One seed replayed under all four conditions and all four controls, with a diff showing **only
  message content changed**. The auditor will read that diff carefully; it is the evidence that the
  pairing is real.

### Not expected yet

Running conditions through the LLM pipeline. That is module 06 plus the pilot.

---

## Deferred past this sprint

- Held-out wording generalisation runs, which use the test-split wording families.
- Full robustness sweeps over unreliable-alert cells.
- The censored-sales replay of the alert conditions.

## Risks specific to this module

- **Alerts too informative.** The leakage scan plus criterion 4 are the defence. When unsure, make
  the message vaguer; a bank that is too subtle is recoverable, one that leaks is not.
- **Length as a confound.** Length-match masked and neutral variants, and test it.
- **Low inter-rater agreement.** Plan for the 120-template fallback rather than negotiating a
  borderline template into the bank.
- **Timestamp drift between content variants.** Structurally prevented by `ContentVariantSet`. Do not
  add a convenience constructor that bypasses it.
