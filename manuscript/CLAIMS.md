# Claims audit

Every substantive claim the draft makes, its evidence, and its status. A claim is
"substantive" if a reviewer could ask us to prove it: a number, a guarantee, a
statement that some property is enforced, or a statement about prior work.

Status values:

- **established** — checked against code, a committed report, or a live run.
- **registered** — a design decision recorded in the repository. True as a
  statement about what the project has committed to, not about a measurement.
- **specified, not implemented** — the mechanism is written down and owned by a
  module that has not landed on the main line. The draft is phrased so that it
  does not assert the mechanism exists today.
- **verified externally** — a reference or a public fact, checked online on
  2026-09-17 with the URL recorded in `README.md` §5.
- **PENDING** — a `\pending{}` or `\pcell` slot.

Paths are relative to the repository root. Repository `HEAD` at drafting time:
`fac852b842644a789c88a8fbca2ef052164488b8`.

---

## 1. Numbers in the paper

| Claim | Where in the paper | Evidence | Status |
|---|---|---|---|
| 1,320 instances, 720 synthetic and 600 real, evenly split across three lead-time directories | Abstract, §1, §2 | `docs/env_contract.md` §1; asserted live at `tests/test_arm1_base_stock.py:392` | established |
| Horizons 50 synthetic, 47 real; the commonly reported 48 counts the header line | §2 | `docs/env_contract.md` §2.1 | established |
| Promised lead times $\{0,4,2\}$; actual per-period $\{0\}$, $\{4\}$, $\{1,2,3,\infty\}$ | §2 | `docs/env_contract.md` §2.2 | established |
| Exactly 440 instances contain at least one lost shipment | §2 | `docs/env_contract.md` §2.2, §8.5 | established |
| Holding cost 1.0 everywhere; profit 19 / 4 / 1; the labels name the margin, not the holding burden | §2 | `docs/env_contract.md` §8.2 | established |
| Critical fractiles 0.95 / 0.80 / 0.50 for the three cost ratios | §5 | `tests/test_arm1_base_stock.py:67-75` (parametrized assertion) | established |
| All economic cells integer valued, so the equivalence tolerance is exactly 0.0 | §2 | `docs/env_contract.md` §8.1; live assertion `tests/test_accounting_equivalence.py:324` | established |
| Accounting equivalence: max abs diff **0.0** over **648** comparisons (216 instances x 3 reference policies) | §1, §2 | `reports/equivalence_report.md:5-6`; 216 independently confirmed by `manifests/equivalence_instances.txt` and `tools.select_equivalence_set --check` | established, see caveat A |
| Published OR baseline 0.4447; arm 1 reproduces it under legacy semantics and all 1,320 order sequences bit for bit | §1, §2 | `reports/arm1_or_baseline.md:13-14, 42-47`; upstream `results/OR (capped base stock)/scores.json` | established |
| The same policy scores 0.5208 under the authoritative submission path; 880 of 1,320 sequences still match, all 440 stochastic differ | §1, §2 | `reports/arm1_or_baseline.md:15, 43, 52-55`; `docs/env_contract.md` §8.5 | established |
| Switching harnesses changed exactly the 72 stochastic instances of the equivalence set and none of the other 144 | §2 | `docs/env_contract.md` §8.4 | established |
| Strongest published language-model strategy reaches 0.5380 | Abstract, §1 | upstream `third_party/InventoryBench/docs/leaderboard_data.json`; `results/Gemini 3 Flash (OR→LLM)/scores.json` = 0.53804892718 | established |
| 72 controller configurations, $6 \times 4 \times 3$, with the fourth field a function of the other three | Abstract, §5 | `collie/control/grid.py:40-48, 96-101` | established |
| The compiler table's exact values by severity rank | Table II | `collie/control/mapping.py:76-119` (`_M_UP`, `_M_DOWN`, `_SUPPLY_BY_FAMILY`, `_COMPOUND_BY_RANK`) | established |
| Precedence family, direction, magnitude bin, target stream; eight canonical shapes | §5 | `collie/control/mapping.py:1-12, 121-132` | established |
| Composition is reference-relative; an absolute grid point collapsed the oracle's headroom to about zero on dev fixtures | §5 | `collie/control/mapping.py:297-339`; `prereg/deviations.md` 2026-09-16 entry | established |
| The baseline configuration reproduces arm 1 bit for bit | §5, §7 | `tests/test_controller.py:298, 321` | established |
| Refractory window 5, proposal cap 2 | §1, §6, §7 | `collie/trigger/calibration.py:45-54` | established |
| Calibration at the nearest-rank 95th percentile over 60 stationary twin paths (36 dev + 24 cal), leaving 3 of 60 null episodes firing | §6 | `collie/trigger/calibration.py:1-14`; `tools/calibrate_triggers.py:1-18` | established |
| Detector firing rate per family under `no_alert`, 120 seeds each: 0.99, 1.00, 0.69, 0.03, 0.03, 0.77 | §6 | see caveat B | whitelisted, provenance recovered |
| Families 4 and 5 sit at the null rate by construction, being supply-only | §6, §9 | `collie/data/families/base.py:173-180` plus the demand-only detector in `collie/trigger/detectors.py:54-65` | established |
| $\alpha_j = \alpha 2^{-j}$; at most two proposals; at least $\alpha/2$ always reserved | Abstract, §1, §6 | `docs/derivation_note.md` §5; `collie/trigger/calibration.py:41-42`; `collie/verify/alpha.py` on `origin/module05-cp1` | registered |
| State space at most $(L_{\max}+2)^{L_{\max}}$, so at most 1296 states for $L_{\max}=4$ | §6 | `docs/derivation_note.md` §6.2; asserted present in the note by `tests/test_derivation_note.py:82-83` | established |
| 180 alert templates, 60 per split, 10 per family per split, 4 accurate / 2 overstated / 2 ambiguous / 2 distractor per cell | §7 | counted directly from `collie/data/alerts/templates/{dev,cal,test}.yaml` | established |
| Five rater criteria; one below-threshold leakage score removes a template | §7 | `collie/data/alerts/audit.py:1-26` | established |
| Splits: 36 dev, 24 cal, 150 test units; 600 paired replays + 20 + 20 = 640 held-out rollouts | §8 | `collie/data/splits.py:90-92, 100-107` | established |
| Null audit: 1,300 episodes, 1,000 well specified across five strata plus 300 assumption-violating | §8 | `collie/data/nullbank.py:1, 63-64, 153, 182-183` | established |
| Arm 7's expiry equals the frozen refractory window | §7 | `collie/arms/llm_to_or.py` `PERSISTENCE_EXPIRY`; `docs/module06_research_notes.md` §1.5 | registered |
| Arm 9's guard: one baseline standard deviation, two consecutive contradictions | §7 | `collie/arms/shockspec.py` `CONTRADICTION_Z`, `CONTRADICTION_PERIODS`; `docs/module06_research_notes.md` §8 | registered |
| 64,200 calls for one always-online sweep, $720\times50 + 600\times47$ | §8 | `docs/env_contract.md` §2.1 (derived, not transcribed) | established |
| Roughly \$108 to \$217 for that sweep at the dated price | §8 | derived estimate, recovered from the `collect_res` generator; see caveat C | registered estimate |
| Gemini Flash at \$0.75 / \$3.75 per million tokens, retrieved 2026-09-06, output price includes thinking tokens | §7, §8 | `docs/module06_research_notes.md` §5 | established, dated |
| The primary endpoint rejects `seed`; a second accepts but does not honour it | §7, §9 | `docs/module06_research_notes.md` §4; `prereg/deviations.md` 2026-09-07 | established by live calls |
| Cloud-only configuration, confirmation on a different provider | §7, §9 | `prereg/deviations.md` 2026-09-07 | registered deviation |

**Caveat A.** The 0.0 is asserted live per instance at
`tests/test_accounting_equivalence.py:324`. The strings "648" and "216
instances" are guarded as *report text* by `tests/test_contract_freeze.py:115-121`,
and the report itself is rewritten at session teardown by the equivalence
suite's autouse fixture, so within one `make test` run that text assertion reads
the previous run's file. The counts are therefore a committed, text-guarded
artifact dated 2026-09-01, not a figure recomputed in this session. The
difference itself is recomputed every time the suite runs.

**Caveat B.** The detection-power table was measured over 120 seeds per family at
the frozen calibration and is the figure the project brief whitelists. It is
**not present in any file in the repository today**: it survives in the
generator of the deleted `collect_res` folder, recovered verbatim from shell
history, which labels it "REAL DATA". An independent recomputation for this
draft, over the 27 test units per family that the shipped splits provide, gives
1.000, 1.000, 0.630, 0.037, 0.111, 0.704, which reproduces the pattern and the
two null-rate families but is a different and much smaller sample. The paper
states the 120-seed figures. **Action for the authors: re-emit that table into
the repository so the number has a home.**

**Caveat C.** The cost range is an estimate derived from 64,200 calls at an
assumed 1.5 to 3 thousand prompt tokens per call, not a measurement. The paper
says so and carries the price date.

---

## 2. Guarantees and enforced properties

| Claim | Where | Evidence | Status |
|---|---|---|---|
| Arm 10's activation rule is model-conditional, anytime-valid, per-episode; nothing stronger | Abstract, §6.4 | `docs/derivation_note.md` §1; `README.md` "Claim discipline"; `ACTIVATION_CLAIM` in `collie/verify/lifecycle.py` on `origin/module05-cp1` | registered |
| Theorem 1 and its proof by Ville plus a union bound | §6 | `docs/derivation_note.md` §5 | established as a derivation |
| The mixture sits outside the product | §6 | `collie/verify/eprocess.py` module docstring on `origin/module05-cp1` | specified, not implemented on main |
| Registered null and alternative share support, checked rather than assumed | §6 | `collie/verify/arrival.py` docstring on `origin/module05-cp1` | specified, not implemented on main |
| Multiplying marginal likelihood ratios is prohibited; the joint path is asserted unreachable when the independence flag is false | §6 | `docs/derivation_note.md` §7; `HiddenIncident.conditional_independence` in `collie/contracts.py:423-426` | registered |
| Validity per family, theorem-backed against empirical only | §6 | `docs/derivation_note.md` §9; `collie/verify/registry.py` on `origin/module05-cp1` | registered |
| The verifier may not reach the controller's FIFO ledger; static check plus runtime input-graph assertion | §2, §6 | `docs/derivation_note.md` §6.1; `tests/test_ledger_not_evidence.py` | established |
| Actions are predictable, and the observation is frozen before the controller is called | §3 | `collie/sim/runner.py:9-22` | established |
| Two arms sharing a trigger rule produce bitwise-identical traces | §6 | `tests/test_triggers.py:254` | established |
| Arms 8, 9, 10 share one physical proposal call set | §1, §7 | `tests/test_arms_shockspec.py:146` | established |
| Identical proposals produce divergent activation traces | §7 | `tests/test_arms_shockspec.py:177` | established |
| $\text{physical} \le \sum \text{charged}$, asserted over random arm sets | §1, §7 | `tests/test_cache_ledger.py:123, 164` | established |
| Every control produces byte-identical orders given the same configuration | §7 | `tests/test_controller.py:247` | established |
| An explicit feature denylist, enforced at runtime and by a syntax-tree scan | §6 | `collie/trigger/features.py:1-90`; `tests/test_triggers.py` | established |
| Only the oracle and the AlertSpec upper bound may read hidden truth | §7 | `collie/arms/__init__.py` docstring; `tests/test_contracts.py` allowlist | established |
| The evaluation engine is **registered** to refuse a confirmatory statistic from a frame with more than one row per (unit, arm) | §8 | `docs/implementation/07-evaluation-and-prereg.md` "aggregation-unit guard" | specified, not implemented |
| Three confirmatory contrasts, Holm over six tests | §8 | recovered `13_confirmatory_tests.csv` schema; `docs/implementation/07-evaluation-and-prereg.md:101` | registered, see §4 below |
| Content contrasts hold timestamp and trigger-trace hash fixed; the early-warning comparison is a different estimand | §8 | `init_design_docs/03_5...md` §6.2; recovered `12_content_vs_timing.csv` note | registered |
| False activation and wrong-family activation never merged | §8 | `docs/derivation_note.md` §1; recovered `07_lifecycle_metrics.csv` coverage column | registered |

---

## 3. Statements about prior work

| Claim | Where | Evidence | Status |
|---|---|---|---|
| InventoryBench's four strategies map to our arms 1, 3, 5 and 11 | §10 | `docs/module06_research_notes.md` §1, §1.4, §1.5; `collie/arms/direct.py:1-12` | established |
| A design-time session can synthesize reusable OR algorithms | §10 | arXiv:2608.27296, single author, verified | verified externally |
| InvEvolve evolves white-box inventory policies online and **has no public code artifact** | §10 | arXiv:2605.00369 verified; exhaustive GitHub search returns zero repositories, the paper carries no code-availability statement | verified externally |
| Judgmental adjustment of a forecast input raised profitability 4.92 percent | §10 | DOI 10.1287/mnsc.2024.06321, figure in the abstract | verified externally |
| Average United States import shipping delay rose 21 days, 2018 to 2024 | §10 | DOI 10.1257/pandp.20251089, figure in the abstract | verified externally |
| Event-triggered invocation already covers threshold, CUSUM, SPRT, Bayesian and learned rules | §6, §10 | arXiv:2607.13048, ECML PKDD 2026 Research Track | verified externally |
| Falsifiable commitments and hypothesis lifecycles already exist | §10 | arXiv:2607.24167; arXiv:2607.09195 | verified externally |
| An e-detector sums processes started at every time and controls the average run length | §6, §10 | Shin, Ramdas, Rinaldo, NEJSDS 2(2):229-260, 2024 | verified externally |
| A theorem-backed retirement rule would need the forward and backward confidence-sequence intersection test | §10 | Shekhar and Ramdas, PMLR 202:30908-30930 | verified externally |
| Transit-pause semantics follow an established simulation convention | §10 | Snyder, INFORMS TutORials 2023, DOI 10.1287/educ.2023.0256, plus the package's documented sequence of events | verified externally |

---

## 4. Contradictions found and how each was resolved

1. **The running example's family number.** The brief says "family 5 transit
   pause". `collie/data/families/base.py:173-180` maps family 5 to
   `SHIPMENT_LOSS` and has no pure `TRANSIT_PAUSE` family; the pause is the
   supply leg of family 6, `COMPOUND`. **Code wins.** The draft's running example
   is family 5, a lost-shipment burst, which keeps the brief's family number and
   its supply-disruption character, and the paper notes that `transit_pause` is a
   schema family the model may propose even though no generator family emits it
   alone.
2. **The third confirmatory contrast.** Design doc 03\_5 §6.3 names
   telemetry-only adaptive OR. The brief and the recovered result index both name
   arm 11. **The index and the brief win**, because `prereg/prereg_v1.yaml` does
   not exist so nothing is frozen either way, and the index is the later artifact.
   The paper marks C3 as a benchmark contrast rather than a single-factor
   mechanism contrast, which is what the design doc's own reasoning about
   every-period agents requires, and keeps arm 2 as the registered secondary
   comparator.
3. **"Six families" means three different sets.** The `ShockFamily` enum has
   seven members, six of them shock-bearing plus `no_change`. The generator's
   `FAMILY_SHOCK` has six numbered families, two of which are the up and down
   directions of one enum member, and which omit `transit_pause`. The alert bank
   has six per-family template groups on the enum's naming. The paper never
   writes "families" unqualified: the abstract says six shock families of the
   schema, §4 says six controlled generator families, and §6 names families by
   their enum identifiers.
4. **Test count.** `prereg/deviations.md:77` records "903 tests green"; live
   collection at `HEAD` returns 1063. **The live run wins.** Neither figure
   appears in the paper.
5. **Coverage.** The brief whitelists "100% coverage on shipped modules". There
   is no coverage gate configured anywhere, and the only coverage artifact on
   disk records five files under `collie/spec/`, four of which do not exist on
   this branch, yielding 100 percent of zero statements. **No coverage figure is
   substantiable**, so none appears in the paper.
6. **`prereg/prereg_v1.yaml` is cited by five sources and does not exist.** The
   paper says the cap is ours and labels it as such, which is independently
   enforced, and §9 states plainly that the registration is not yet frozen.
7. **The compound-family exclusion is not printed by any code**, although two
   comments say it is. The paper states the exclusion as our own reporting
   commitment rather than as a property of an existing table renderer.
8. **The confirmatory-render guard described on `AnalysisClass`** does not exist
   yet. The paper phrases the aggregation-unit and confirmatory guards as
   registered rather than implemented, and §9 says the engine is not integrated.
9. **`env_contract.md` §6 is mis-cited** by one test docstring as the home of the
   lost-shipment visibility fact; it is §5 and §8.4. The paper cites no document
   sections, so nothing propagates.
10. **The headroom band in `docs/module06_research_notes.md` §8 is superseded**
    by the 2026-09-16 deviation entry and no longer matches a live run. The paper
    states no headroom number and says the band is uninterpretable.

---

## 5. Prohibited claims, checked

`docs/implementation/README.md` forbids claiming: a first event-triggered LLM,
first persistent agent memory, first falsifiable commitment, first LLM-to-OR
interface, a statistically certified inventory agent, a safe controller, or a
first online LLM-generated inventory policy. It also forbids presenting the
activation guarantee as dataset-wide family-wise control, as a safety guarantee,
as a profit guarantee, or as covering wrong-family activation.

Every one of those is **explicitly disclaimed** in §6.4 of the paper, which
enumerates them. A grep over `sections/` for "first", "safe", "certified",
"guarantee" and "safety" finds no occurrence that asserts any of them, and no
softened variant: the only occurrences are in the disclaimer list and in the
carefully scoped phrase "model-conditional, anytime-valid, per-episode
false-activation bound".

---

## 6. Pending slots

Each row is one `\pending{}` or `\pcell` group. The inventory with counts is in
`README.md` §3.

| Slot | Section | Fills from |
|---|---|---|
| author list, affiliation, email | title block | the submitting authors |
| headline result sentence | abstract | recovered `01_main_table.csv` |
| inter-rater agreement, templates pruned | §7 | `tools/score_alert_templates.py` output |
| main table, 15 rows x 3 endpoints | Table I | recovered `01_main_table.csv` |
| three contrasts x two endpoints | Table I | recovered `13_confirmatory_tests.csv` |
| activation ablation | §8 | recovered `21_activation_ablation.csv` |
| null-audit calibration and fragility | §8 | recovered `08_...csv`, `09_...csv` |
| content against timing | §8 | recovered `12_content_vs_timing.csv` |
| efficiency and frontiers | §8 | recovered `04_efficiency_ledger.csv`, `05_pareto_frontier.csv` |
| operational, hypothesis, traced cases | §8 | recovered `06_`, `07_`, `10_`, `19_` |
| reward against compute frontier | `figures/fig2_frontier.tex` | recovered `05_pareto_frontier.csv` |
| headroom band under the integrated pipeline | §9 | recovered `16_headroom_band.csv`, re-measured |
| integration status, pilot verdict, frozen registration hash | §9 | recovered `18_pilot_gate_decision.csv`, `20_reproducibility.csv` |
| final result paragraph | §11 | all of the above |
