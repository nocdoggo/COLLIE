# Follow-up at an ACL-family venue: design notes (not registered)

Status: working design, 2026-09-29. Nothing here is registered, and no run has been made on any
pool described here except the throwaway development check in section 6. A future stage E
registration would freeze the parts marked *to register*. Literature, datasets and venue facts,
each checked at its source, are in `LITERATURE.md`.

## 1. The question

Does operational text carry decision-relevant information that language models extract before
the telemetry reveals it, and can a certified controller use that information without giving up
its error budget?

The UV 2026 paper (certify-then-hedge; archival in IEEE Xplore) answers the second half and
leaves the first open. On its simulator, at the registered ratio, the text added no detectable
value over a content-free variant timed by the same alerts (stage C: +9.34 [-4.94, 23.60] with
Gemini 3.8, -6.24 [-28.67, 10.68] with Grok 4.20); the model's label lowered null exposure by
37% and 45% (post hoc). Stage D tests the high-margin case (p/h = 19) under registration.

## 2. Why the UV setting cannot answer the first half

The alert bank was built so that text is informative but never the answer
(`docs/implementation/03-alert-bank.md`):

- No dev/cal template states a size, a date or a lead time. Intensity and timing words
  ("somewhat", "markedly", "far longer", "crippling", "through the coming quarter") are slot
  draws hashed from (template, unit seed, slot), unrelated to the episode's true size.
- The hidden label `alert_spec.magnitude_bin` is `medium` on every non-distractor template and
  disagrees with the provisional truth binning (80 of 96 pilot shocks bin `low`).
- The leakage scanner on the alert path refuses digit percentages, "N x", "N times", "N
  percent", decimals, "half", "week/period/day N" and "for/lasting N weeks", but lets spelled-out
  forms through; the regex is a guard, not a policy.
- The dev/cal bank has no demand-down template (family 2 is alert-free), no template for transit
  pauses, and distinct texts for four accurate templates per family and split: 8 units per family
  per layout.
- True lead-time shifts are one or two periods (every family-4 unit moves to a lead of 3), and
  demand shifts are revealed within a few periods at the simulator's noise.
- Certify-then-hedge takes the shock's size from the data; the model sets only the prior weights
  and the named hypothesis's onset window, and the shared trigger gives every arm the alert's
  timing.

## 3. The informative-alert benchmark

Generate the shock first, then render the text, so every label is exact by construction.

- **Information levels** (a text-ablation ladder; it also removes the UV control's confound,
  since the content-free arm keeps the alert channel): L0 a content-free ping; L1 family and
  direction (the UV level); L2 plus magnitude; L3 plus onset and duration; L4 plus a lead-time
  size ("lead times move from about two to five weeks").
- **Forms of expression**, which make the reading an NLP problem rather than a regex: exact
  numerals, relative forms ("roughly doubled"), vague quantifiers, ranges, unit changes (days,
  weeks, periods), absolute dates against relative offsets, hedging and negation.
- **Long-horizon warnings.** Onsets announced k periods ahead, with k shorter and longer than the
  lead time. Before onset no e-process can gather evidence, so the text alone drives
  pre-positioning; this is where text can be uniquely valuable and where false warnings cost the
  most. Include warnings that never materialise, postponed onsets and follow-up messages
  ("update: delay resolved"), read as threads.
- **Reliability classes**, crossed with the levels: accurate, overstated, understated,
  mis-timed, stale, wrong entity, retracted, and distractor numerals (order numbers, prices,
  dates) to test anchoring. Keep null twins with false alerts.
- **Complementarity.** For each episode compute the telemetry reveal time (the first period at
  which a telemetry-only detector identifies family and magnitude at a fixed error level) and
  vary the alert's lead over it; report the value of text as a function of that lead.
- **Templates and scale.** A new bank under `analysis/aacl/templates/` (never in frozen
  `collie/`), with held-out wording families and human paraphrases, and at least 24 templates
  per family and class so that a layout holds 24 or more units per family (144+ units against
  the UV study's 48). If templates are drafted with a model, use a family that is not among the
  readers, and record it.
- **Real-text validation** (no public dataset pairs supplier notices with measured lead times, so
  the full loop stays synthetic): openFDA drug-shortage notices (CC0) and ShortageSim for reading
  to realised duration, with calibration; ICNDelay (NOTAM/METAR text to delay minutes) as an
  out-of-domain check. See `LITERATURE.md`, section 4.

## 4. Method extensions (tools, not claims)

The method is the UV paper's contribution; here it is the instrument.

- *Size prior from text.* For the named hypothesis, replace the uniform prior over the
  within-hypothesis size grid (`cth.py`: `_within_demand` over `MAGNITUDE_SETS`, `_lt_posterior`
  over offsets 1 to 3) by `q` on the stated bin and `1 - q` over the rest, in a subclass under
  `analysis/aacl/` (never in the frozen `cth.py`). The exposure guarantee concerns prior mass and
  e-process validity, not sizing, so it is unchanged. Section 6 shows this buys little on the UV
  simulator.
- *Future onset.* Register the named hypothesis of a warning with an e-process that starts at the
  stated onset window, and let its prior act on orders placed before onset (the pipeline needs
  lead-time periods of notice). The certificate still prices the hypothesis on post-onset data
  only.
- *Trust as a parameter.* `lam` (the uniform share of the prior) set per model from its measured
  reading accuracy or elicited confidence, so that calibration sets exposure; fixed against
  confidence-set weights as a registered secondary. The exposure bound holds for any `lam`.

## 5. NLP-side analyses

- Reading accuracy per field (family, direction, magnitude, onset, lead-time size, horizon) by
  information level, form of expression and reliability class, across the 21-model ladder and
  newer models; ordinal error (over or under) for binned fields; abstention when the text is
  silent (hallucinated fields), with selective accuracy against abstention rate.
- An error taxonomy: stream confusion, direction flips, magnitude misbinning, unit errors,
  timing errors, distractor and wrong-entity uptake.
- Calibration per field (Brier score, log loss, ECE) with at least two elicitation methods, and
  on the real-text subset against realised outcomes.
- Decision-weighted error: replace one read field with the truth, recompile, and measure the
  change in cost; this links NLP errors to consequences.
- Dose-response across models: value of text against reading accuracy. The UV ladder's finding
  (commitment, not accuracy, drives the loss from acting at once) is re-tested on new data, not
  re-reported.
- Human ceiling: two annotators on a sample, for agreement and ambiguous alerts.
- Baselines reviewers expect: a rule-based extractor, a small fine-tuned extractor,
  context-aided LLM forecasting feeding the compiler, text-to-prior (LLM Processes style),
  end-to-end LLM ordering, telemetry only, and a perfect reader.

## 6. Development check: does a stated size help? (throwaway pool, no claim)

`dev_text_size.py`, output `out/dev_text_size.json`: the UV fresh layout rebuilt on the throwaway
base (900000; 48 units, 240 episodes) with a scripted reader that names the true hypothesis and
states the true size bin with probability `q_read`, read by the registered hedge and by a
text-sized hedge (`q = 0.8` on the stated bin).

| p/h | q_read | text-sized minus method | method minus arm 1 | method minus content-free |
|---|---|---|---|---|
| 4 | 0.5 | +0.73 [-0.41, 2.08] | +170 | +43 |
| 4 | 0.9 | +1.69 [-0.00, 3.58] | | |
| 4 | 1.0 | +2.45 [0.93, 4.33] | | |
| 19 | 0.5 | -2.15 [-5.90, 0.51] | +1,019 | +182 |
| 19 | 1.0 | +3.83 [-0.13, 9.21] | | |

(2,000 cluster draws; the method's own columns do not depend on `q_read` in this set-up.)

Readings: on this simulator a correctly stated size is worth a few units per episode at most,
because the data reveal size within a few periods. A reader that always names the right family
beats the content-free hedge by +43 per episode at p/h = 4 and +182 at 19, while the live models
did +9 and -6 at p/h = 4 in stage C: the family label has headroom that reading accuracy, not
sizing, controls. The informative benchmark should therefore lean on timing (long-horizon
warnings), slower-revealing shocks (smaller steps against demand noise, noisy lead times), and
reading accuracy, not on stated sizes of shocks the data reveal quickly.

## 7. Power and stage E (sketch, *to register*)

- Power from throwaway replays with a scripted reader at controlled accuracy on the new
  benchmark; units chosen for 80% power at one-sided 0.05 per model with Holm over the primary
  models, for the smallest effect worth reporting (set before the power runs). The UV study had
  48 clusters and an interval width of about 28 for the text contrast at p/h = 4.
- Pools: a new base (for example 300000); the stage D pool is spent.
- Primary, per model, Holm within family: E1 value of text on the informative levels
  (text-reading hedge minus content-free hedge); E2 null safety on distractor, retraction and
  false-warning episodes (non-inferiority against arm 1); E3 the reading hedge against the gate.
- Secondary: reading accuracy by level, form and class; calibration; decision-weighted error;
  dose-response across the ladder; L1 as the within-study replication of the UV result.

## 8. What counts as a result

- *Positive:* E1 rejects for at least two models on the informative levels, the value grows
  with reading accuracy and with the alert's lead over the telemetry reveal time, and null safety
  holds on false and misleading text.
- *Negative:* E1 fails even on informative text. Reportable if the reading and calibration
  analyses show why (for example, which forms of expression models misread), and if the
  benchmark and the decision-weighted error metric stand on their own.

## 9. Paper outline

Title options:
- "Reading the Warning: When Operational Text Pays Off Under Certified Control"
- "Before the Data Know: Language Models, Early Warnings and Certified Inventory Decisions"
- "What the Alert Said: Measuring the Decision Value of Reading Operational Text"

Contributions (none restated from the UV paper, which is cited in the third person and disclosed
on the submission form):
1. A benchmark of short operational alerts with graded, typed information content, forms of
   expression and reliability classes, aligned with simulated outcomes, with a real-text
   validation subset and human realism ratings.
2. Field-level reading accuracy, error taxonomy and calibration across a 21-model ladder.
3. A decision-weighted error metric linking each field's reading error to downstream cost.
4. The value of reading, and the damage from false text, measured under a controller whose
   exposure to false hypotheses is bounded (the UV method as instrument).

## 10. Venue (official pages, 2026-09-29; details and sources in `LITERATURE.md`, section 1)

- AACL-IJCNLP 2026 (Hengqin, 6 to 10 November 2026) is closed: its ARR deadline was 25 May
  2026. No AACL 2027 is announced on aaclnet.org or in ARR's venue table.
- Next ACL-family routes: ARR's October 2026 cycle (submission 12 October 2026) feeds NAACL 2027
  and COLING 2027 (commitment 23 December); ACL 2027 is listed only as "January, 2027".
- From the October cycle every ARR submission names a qualified service contributor or enters
  a lottery, and all authors need OpenReview profiles with ORCID.
- ARR will not consider a paper that "overlaps significantly in content or results" with a
  published paper, allows "no overlap in stated contributions", caps re-used text at 10% of
  tokens (a refereed IEEE paper is not exempt), and asks for disclosure and an anonymous,
  third-person citation of the prior paper.
- Implication: the 12 October cycle would need stage E designed, registered, run and written in
  two weeks alongside the UV camera-ready (due 15 October); the January 2027 cycle (ACL 2027), or
  AACL 2027 if announced, is the realistic target. The owner decides.
