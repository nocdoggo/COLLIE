# Commitment study: plan

Exploratory throughout. Nothing here is a Gate 3 vote, re-votes Gate 3, or edits a frozen file;
`tools.freeze.drift()` must stay `[]`, nothing is written to `reports/` or `prereg/` except a dated
`prereg/deviations.md` entry when a stage finishes, and `collie/data/alerts/templates/test.yaml`
is never opened. Each stage is committed and pushed before any of its runs.

The study has three stages:

- **A. Model ladder** (this section): the registered 120 dev/cal pilot episodes with older and
  smaller Gemini and Grok models, to see how perception and outcomes change with model quality.
- **B. Method development** (appended before its runs): the graded, evidence-sized commitment
  method, developed on the same 120 spent episodes. Development only; no claim.
- **C. Fresh-seed confirmation** (appended before its runs): the frozen method against the
  registered arms on a reserved seed pool no run has touched (`episodes.py`).

## Stage A. Model ladder on the pilot episodes

Registered 2026-09-28, before any ladder call.

**Question.** How do first-proposal perception and the downstream outcomes of arms 8, 9 and 10
change when the model is older or smaller? In particular: does the harm of acting on unverified
proposals (arm 8) grow as perception weakens, while the verified arm (arm 10) stays close to the
baseline?

**Episodes, alerts, arms.** Exactly the real-content pilot's (`analysis/real_content_pilot/PLAN.md`):
the registered 120 dev/cal episodes, module 03 bank alerts under rule `bank-v1`, the nine arms
wired as `tools/run_arms.py::run_ladder` wires them, Rule U-v1 for arm 10, decoding `det-v1`
(temperature 0, no seed, no system prompt), each model's default thinking behaviour as served.
The runner is `analysis.commitment.runner --layout pilot --arm-set nine`; a scripted run through
it reproduces the committed `scripted-bank` records exactly (ignoring wall-clock latency).

**Models.** Five new rungs, each probed live on 2026-09-28 (the response echoed the requested
model):

| rung | released | tier | $/1M in | $/1M out | cap |
|---|---|---|---|---|---|
| `gemini-2.5-flash-lite` | 2025-07 | small | 0.10 | 0.40 | $0.50 |
| `gemini-2.5-flash` | 2025-06 | mid | 0.30 | 2.50 | $2.00 |
| `gemini-3-flash-preview` | 2025-12 | mid | 0.50 | 3.00 | $2.00 |
| `gemini-3.1-flash-lite` | 2026-05 | small | 0.25 | 1.50 | $0.75 |
| `grok-build-0.1` (alias `grok-code-fast-1`) | 2025-08 | small | 1.00 | 2.00 | $1.50 |

The two existing live runs are the top rungs and are not re-run: `gemini-3.8-flash` (2026-09) and
`grok-4.20-0309-non-reasoning` (2026-03). Prices are dated list prices (`endpoints.py`). xAI serves
retired ids (`grok-3`, `grok-3-mini`, `grok-4-fast-non-reasoning`) as `grok-4.3`, so no older Grok
is reachable except `grok-build-0.1`; the runner refuses any response whose echoed model differs
from the rung. Total cap $6.75.

**Procedure per rung.** A 3-episode smoke run under the full run's name (the real-content pilot's
smoke set: `dev/f1/s1050000/early_accurate`, `cal/f6/s6060000/unreliable`,
`dev/f1/s1050000/unreliable__twin`), then the full 120 episodes, whose cache replays the smoke
calls. The full run goes ahead only if the smoke run's cost scaled to 120 episodes stays below
the cap. Retries, refusals and caps follow the real-content pilot's transport rules.

**Analyses (descriptive; no multiplicity correction; nothing confirmatory).** For every rung,
including the two existing ones, against the committed `scripted-bank` reference:

1. Perception: first-proposal family-and-direction accuracy on the 96 shocked episodes, and on
   the 20 early-accurate episodes that carry an alert; abstention rate; parse validity.
2. Outcomes: arm8-arm1, arm9-arm1 and arm10-arm1 on net reward and gross profit, with the
   seed-cluster bootstrap interval (24 clusters, 10,000 draws, seed 20260927).
3. Safety on nulls: arms 8, 9 and 10 active on the 12 false-alert nulls.
4. Verification: arm 10 activations of right-family and wrong-family proposals.
5. Operations: provider calls, cost, latency, thinking-token share.
6. The model-scale readout: items 1-3 plotted against rung, ordered by release date within
   provider. The expectation stated in advance: perception falls with older and smaller models;
   arm 8's net harm grows as perception falls; arm 10's net outcome stays within its interval of
   arm 1 on every rung. Any rung that contradicts this is reported as such.

Reading rules are the real-content pilot's: a contrast is called different from zero only when
its seed-cluster bootstrap interval excludes zero.

### Stage A amendments (logged before the full runs)

**A1 (2026-09-28, after the smoke runs, before any full run).** Smoke projections of the full
120-episode cost (the real-content pilot's `smoke_summary`): `gemini-2.5-flash-lite` $0.05,
`gemini-3.1-flash-lite` $0.12, `gemini-2.5-flash` $1.55, `gemini-3-flash-preview` $2.55,
`grok-build-0.1` $1.511. Under the registered rule:

- `gemini-3-flash-preview` is **not run**: its projection exceeds its $2.00 cap, and single calls
  took up to 6.6 minutes. It is neither older nor smaller than the remaining rungs.
- `grok-build-0.1`'s cap is raised from $1.50 to $2.00: its projection exceeds the cap by $0.011,
  and it is the only older Grok the provider still serves. Disclosed: all 15 of its smoke parses
  were abstentions, which is seen before this change; the change is to the spend cap only.

The full runs are `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-2.5-flash` and
`grok-build-0.1`. The stage A total cap becomes $5.25.

**A2 (2026-09-28, before any call on these rungs). Two more providers.** The owner added a
StepFun Step Plan key and an OpenRouter key (both stored in the gitignored `cloud_endpoint/`,
mode 600). Fifteen rungs are added, each probed live once with a one-word request (the echoed
model matched; reasoning tokens are counted inside the completion on both providers):

| rung | provider, model id | released | size or tier | $/1M in | $/1M out | cap |
|---|---|---|---|---|---|---|
| `step-3.5-flash` | StepFun `step-3.5-flash` | 2026-01 | reasoning | 0.10* | 0.30* | $2.00 |
| `step-3.5-flash-2603` | StepFun `step-3.5-flash-2603` | 2026-03 | reasoning | 0.10* | 0.30* | $2.00 |
| `step-3.7-flash` | StepFun `step-3.7-flash` | 2026-05 | reasoning | 0.20* | 1.15* | $2.00 |
| `step-5-preview` | StepFun `step-5-preview` | 2026-09 | reasoning | 0.20* | 1.15* | $2.00 |
| `llama-3.2-1b` | OpenRouter `meta-llama/llama-3.2-1b-instruct` | 2024-09 | 1B | 0.027 | 0.201 | $0.50 |
| `llama-3.2-3b` | OpenRouter `meta-llama/llama-3.2-3b-instruct` | 2024-09 | 3B | 0.05 | 0.33 | $0.50 |
| `llama-3.1-8b` | OpenRouter `meta-llama/llama-3.1-8b-instruct` | 2024-07 | 8B | 0.05 | 0.08 | $0.50 |
| `llama-3.3-70b` | OpenRouter `meta-llama/llama-3.3-70b-instruct` | 2024-12 | 70B | 0.10 | 0.32 | $0.50 |
| `qwen-2.5-7b` | OpenRouter `qwen/qwen-2.5-7b-instruct` | 2024-10 | 7B | 0.10 | 0.20 | $0.50 |
| `qwen-2.5-72b` | OpenRouter `qwen/qwen-2.5-72b-instruct` | 2024-09 | 72B | 0.36 | 0.40 | $1.00 |
| `gemma-3-27b` | OpenRouter `google/gemma-3-27b-it` | 2025-03 | 27B | 0.08 | 0.45 | $0.50 |
| `deepseek-v3` | OpenRouter `deepseek/deepseek-chat` | 2024-12 | 671B MoE | 0.257 | 1.029 | $1.00 |
| `gpt-oss-20b` | OpenRouter `openai/gpt-oss-20b` | 2025-08 | 21B MoE, reasoning | 0.018 | 0.09 | $0.50 |
| `gpt-3.5-turbo` | OpenRouter `openai/gpt-3.5-turbo` | 2023-05 | legacy | 0.50 | 1.50 | $1.00 |
| `gpt-4o-mini` | OpenRouter `openai/gpt-4o-mini` | 2024-07 | legacy | 0.15 | 0.60 | $1.00 |

\* StepFun's Step Plan is flat-rate, so its rungs carry a shadow price (see `endpoints.py`); the
caps then bound shadow cost. OpenRouter serves open-weight models through third-party providers
it picks per request, so temperature-0 answers may vary more than on a first-party endpoint;
the served model id is still checked. Everything else is stage A as registered: the same
episodes, alerts, nine arms, Rule U, decoding, smoke-then-full procedure with the projection
rule, and the same analyses, now read along three axes: provider family, release date and
parameter count (the Llama series 1B, 3B, 8B, 70B and the Qwen pair 7B, 72B are the
within-family size comparisons). Small models are expected to fail the module 02 schema more
often; parse failures, repairs and fallbacks are reported per rung as part of the result.
Stage A's cap becomes $5.25 plus $17.00 for these rungs.

**A3 (2026-09-29, after the StepFun smoke runs, before their full runs).** Projected shadow cost
of the full 120-episode runs: `step-3.5-flash` $0.39, `step-3.5-flash-2603` $0.85,
`step-3.7-flash` $2.82, `step-5-preview` $1.74. The Step Plan is flat-rate, so these are shadow
prices with no cash consequence; the StepFun caps are raised from $2.00 to $4.00 (shadow) so that
`step-3.7-flash` runs. Its smoke parses are disclosed as seen (15/15 valid, 3 abstentions). No
other rule changes. The OpenRouter projections were all below their caps ($0.03 to $0.21).

## Stage B. Method development: certify-then-hedge

Written 2026-09-28. Stage B is development: it supports no claim, tuning is allowed, and its
numbers are post hoc on the 120 spent pilot episodes. Its development runs are offline replays
with no model calls (`dev.py`); the harness was written and first run on the same day as this
text. Everything that stage C tests is frozen at the end of stage B, in stage C's registration.

**Method** (`cth.py`, `CertifyThenHedgeArm`). At each trigger firing `j` (at most two, the frozen
trigger's limit), a fixed action-aligned hypothesis set `H = {demand_up, demand_down, lead_time,
pulse_up}` is registered with prior mass `a_j * w_jh`, where `a_j = alpha * 2^-j` is the frozen
alpha schedule and `w_jh = lam / |H| + (1 - lam) * 1{h = the LLM's family}`. Each hypothesis has
its own module 05 e-process from a canonical legal spec (the LLM's onset window for the LLM's
hypothesis, the widest registered window otherwise), conditioned through `tau_j` and fed every
later period. The posterior shock mass of `(j, h)` is proportional to `a_j w_jh E_jh,t-1`. The
size of the shock comes from the data (a working likelihood over the registered multipliers,
starts and durations; lead-time offsets 1-3 from visible receipts and in-transit), never from the
LLM's magnitude bin. The order-up-to requirement is the `p / (p + h)` quantile of the
posterior-predictive mixture; with no live hypothesis the arm orders exactly as arm 1. Families
module 04 cannot profitably act on (compound, shipment_loss, transit_pause) carry no hypothesis.

**Variants.** `lam = 0.25` (the method), `lam = 0` (LLM family only), `lam = 1` (content-free: no
model call, the same trigger and machinery), and the decision-rule ablations `map` (compiled
target iff the shock mass is at least 1/2) and `linear` (target interpolated by the shock mass).

**Guarantees stated for the paper** (proof sketches in the manuscript; all conditional on module
05's null holding, which the plug-in demand null only approximates):

1. Exposure: `N_t = sum a_j w_jh E_jh,t` is a nonnegative supermartingale under the null with
   `N_0 <= A = sum a_j <= 3 alpha / 4`; the shock mass `pi_t <= N_t / (1 - A + N_t)`, so for every
   stopping time `sigma`, `E_0[pi_sigma] <= A` and `P_0(sup_t pi_t >= c) <= A (1 - c) / (c (1 - A))`.
   This holds for any LLM output, including abstentions, wrong families and adversarial content.
2. Odds-regret in cost units: per period, the newsvendor surrogate regret against arm 1's target
   is at most `pi_t / (1 - pi_t) * V_t`, where `V_t` is the value of acting on the hypotheses if
   they were true; hence `E_0[sum_t regret_t] <= T A Vbar / (1 - A)`.
3. The registered gate is, up to one unit of threshold, the MAP decision of this posterior
   (`a_j E / (1 - a_j) >= 1` iff `E >= 1 / a_j - 1`).
4. Hedged prior: `E` of the LLM's hypothesis enters with at least `(1 - lam) a_j`, and every
   hypothesis keeps at least `lam a_j / |H|`, so a wrong LLM family costs at most `log(|H| / lam)`
   nats of evidence relative to the content-free arm, and a right one saves up to that much.

**Development readout** (`out/dev/*.json`): each variant against the stored arm 1, arm 8 and arm
10 of every cached bank (the real-content pilot's three and the stage A ladder's), net and gross,
with seed-cluster bootstrap intervals; null-episode harm and exposure; net by family.

## Stage C. Fresh-seed confirmation

Registered 2026-09-28, before any fresh-seed run that produces outcomes. Frozen at this commit
(first 16 hex of sha256): `cth.py` 343835b85d32a69e, `arms.py` 6d1f468e43a5f9f9, `registry.py`
73c7952dc77b80ef, `runner.py` c753ef5e9e348aa2, `episodes.py` 4f0d9df15c05ca7e, `endpoints.py`
eac79a2094ff81db, `confirm.py` 7b7db9f47db8476b. Any later change to these files is a logged
deviation.

**Method under test.** `arm12_cth`: certify-then-hedge with `lam = 0.25`, the Bayes-mixture
hedge, `n0 = 5`, persistence prior 1/2, lead-time offsets {1, 2, 3}, the hypothesis set and prior
budget of stage B, and no other tuning. Comparators in the same run: `arm12b_cth_llm`
(`lam = 0`), `ctrl_cth_uniform` (`lam = 1`, content-free, no model call), arm 1, arm 2, arm 8,
arm 10, the detector and keyword controls, and the two hidden-truth references (AlertSpec upper
bound, oracle). Arm 9 is dropped: it enters no stage C contrast.

**Episodes.** The reserved fresh pool of `episodes.py`: seeds `family * 1_000_000 + 100_000 + i`,
`i = 0..11` for each of the six families (72 units, disjoint from every registered pool), dev/cal
labels alternating by `i`, set-A combos only, generator onsets; four paired conditions per unit
plus one unshocked twin (36 silent, 36 false-alert, balanced by family and split); 360 episodes;
`p = 4`, `h = 1`, no order cap, horizon 50; module 03 bank alerts under rule `bank-v1`
(family 2 again has no demand-down template and so no alert). One cluster per unit.

**Endpoints (models).** Primary: `gemini-3.8-flash` and `grok-4.20` (the real-content pilot's
two). Secondary, descriptive, for the model-scale readout: `gemini-2.5-flash-lite` (older,
over-commits), `llama-3.1-8b` (small open model, frequent schema failures), `deepseek-v3` (large
open model) and `gpt-3.5-turbo` (legacy). Caps: $12 (Gemini 3.8), $3 (Grok 4.20), $1 each for the
others ($2 for `gpt-3.5-turbo`). Each endpoint first runs a 3-episode smoke under the full run's
name (`dev/f4/s4100000/early_accurate`, `dev/f1/s1100000/unreliable`,
`dev/f1/s1100000/no_alert__twin`); the full run goes ahead only if the smoke's cost scaled to 360
episodes stays below the cap.

**Primary hypotheses** (net reward = `total_reward`, per episode, all 360 episodes; one-sided):

- H1: `arm12_cth - arm10 > 0`, on each primary endpoint.
- H2: `arm12_cth - arm1 > 0`, on each primary endpoint.

p-values: cluster sign-flip test on the 72 cluster sums (100,000 Monte Carlo flips, seed
20260927); Holm's step-down over the four tests at 0.05. H1 (or H2) is confirmed when both of its
tests reject. Estimates are reported with the seed-cluster bootstrap 95% interval (10,000
draws, same seed). Gross profit (`total_profit`, the frozen Gate 3 endpoint) is reported for
every contrast and decides nothing.

**Secondary (no multiplicity claim):** `arm12_cth - arm8`; the value of language
`arm12_cth - ctrl_cth_uniform` and `arm12b_cth_llm - ctrl_cth_uniform`; `ctrl_cth_uniform - arm1`;
`arm10 - arm1` and `arm8 - arm1` (the gate and immediate action on fresh seeds); null safety,
`arm12_cth - arm1` on the 72 null twins, non-inferior if its bootstrap lower bound exceeds -25
per episode; exposure, the mean over null twins of the summed per-period shock mass (sidecar
`cth_log.jsonl.gz`); net by family; first-proposal perception and provider cost. The secondary
models get the same table, read descriptively along the model-quality axis.

**Declared departures.** (1) Certify-then-hedge acts on a hypothesis before any activation
threshold is crossed, which departs from the frozen contract's wording that a hypothesis
influences orders only while ACTIVE (`collie/contracts.py` docstring); it is a new, declared arm,
not a reading of arm 10. (2) Net reward is this study's primary endpoint; Gate 3's frozen primary
(gross profit) is reported, never used to decide. (3) The fresh units are outside the frozen
manifest; they carry dev/cal labels only so that dev/cal templates render.

**Disclosed prior exposure.** A structural test of the fresh-layout runner (scripted transport,
`--n-per-family 1`: units `i = 0` of each family, 30 episodes) was run on 2026-09-28 before this
registration; only record counts and sidecar row counts were read. Stage B tuned the method on the
120 spent pilot episodes and the stage A ladder banks.

### Stage C amendments

**C1 (2026-09-28, after a failed smoke start, before any model call or outcome).** The first
smoke start refused the 72-unit layout inside module 03's own renderer (`render_condition_batch`:
"repeated rollout text", units `f4 s4100000` and `f4 s4100008`): the dev/cal bank has four
accurate templates per split and family, so under rule `bank-v1` at most four units per split,
eight per family, get distinct texts. No provider call was made and no record was written. The
layout becomes `i = 0..7` per family: 48 units (clusters), 192 shocked episodes and 48 twins (24
silent, 24 false-alert), 240 episodes. Nothing else changes; the frozen files are untouched
(`--n-per-family` is a runtime argument). Caps scale by 2/3: $8 (Gemini 3.8), $2 (Grok 4.20), $1
each for the secondary models. With 48 clusters, H2 (versus arm 1) is expected to have moderate
power at the development effect size; H1 (versus arm 10) keeps high power.

**C2 (2026-09-29, during the secondary runs).** The `deepseek-v3` full run aborted after 209
calls: one OpenRouter response carried an empty model field, which the echo check refused as a
mismatch. An empty field names no model, so `endpoints.py` now re-requests such a response up to
three times and bills every attempt's tokens; a named mismatch is still refused at once (new
sha256 prefix `1051f372754f6e25`; test `test_an_empty_echo_is_retried_and_billed`). Nothing else
changes. The primary runs are unaffected: `grok-4.20` finished before the change without an empty
echo, and `gemini-3.8-flash` runs on the code it started with. `deepseek-v3` is re-run from its
cache (the 209 answered calls are replayed, not re-bought).

**C3 (2026-09-29, after the runs: disclosures from an independent audit).** A second session
recomputed `out/confirm.json` from the run files without `confirm.py` and matched every registered
number exactly (means, bootstrap intervals, sign-flip p-values, Holm, secondaries); it found no
leakage in `cth.py`. It also found the following departures from what this plan and `episodes.py`
say. None changes a run, a rule, a cap or a number; post-hoc checks are in `out/posthoc.json`.

1. *Interim look.* At 02:57:39Z, 22 s after the `grok-4.20` full run finished, the registered
   evaluator was run on that run alone (H1 and H2 for Grok) while the `gemini-3.8-flash` primary
   run was still going and before C2 was written. Nothing changed after it except C2, which
   concerns an unrelated transport failure in a secondary run.
2. *Outcomes on units `i = 0`.* The structural test disclosed above computed outcomes for all
   eleven arms on the 30 episodes of units `i = 0` (6 of the 48 clusters), contrary to
   `episodes.py`'s "sealed" docstring and to "no run has touched" at the top of this plan; the
   outcomes were not read. Without those six clusters, H1 is +328.6 (Gemini 3.8) and +187.7 (Grok
   4.20) and H2 +162.8 and +145.3, every one-sided sign-flip p at most 0.0024.
3. *Layout materialised early.* At 23:53Z on 2026-09-28, before stages A and C were registered,
   a smoke check of an earlier `episodes.py` wrote the data and truth files of units `i = 0..7`
   (the later C1 layout) to a scratch directory and counted them; no arm ran on them.
4. *Manifest SHA.* `runner.py` stamps `run_manifest.json`'s `git.sha` when a run ends, so
   `fresh-gemini-3.8-flash` records `4eb361b` (C2) although it started and ran at `f1a289a` with
   the pre-C2 `endpoints.py`; `invocations.jsonl` records the starting SHA. The frozen hashes match
   at every commit a run used.
5. *Rule U.* Rule U-v1 applies to arm 10 only: `arms.py` gives the certify-then-hedge arms
   `rule_u_horizon=None` (they read only family and direction and always register canonical
   specs). On `grok-4.20`, Rule U turned 7 of arm 10's answers into abstentions; 4 of the same
   answers registered `demand_up` for arm 12.
6. *Evaluator and strata.* `confirm.py` at its frozen hash is the only confirmatory evaluator. The
   stochastic-lead stratum in `episodes.py` is not part of stage C. An unregistered parallel
   implementation (untracked `cth_core.py`, `evaluate.py`, `evidence.py`, `hypotheses.py` and
   later files) sat in this directory during the runs; no run imported it (arm 12's and the
   content-free arm's committed orders reproduce exactly from the frozen `cth.py` and the logged
   answers), and it was moved out at about 04:05Z.
7. *C1's caps.* "Caps scale by 2/3" is inexact for the secondary models (set at $1 each, not
   $0.67; `gpt-3.5-turbo` from $2 to $1). Every run stayed under a strict 2/3 scaling.
8. *Stage B's guarantees, restated.* (1) holds when every e-process is a nonnegative
   supermartingale under the null. The demand e-processes use module 05's plug-in prefix null
   (mean and spread from the periods before `tau_j`), which the audit's simulation found
   anti-conservative at the early firings that occurred; the bound is exact for a known null and
   approximate as run. (3) holds only with `lam = 0`, one live hypothesis and the same e-process;
   arm 10 certifies the model's full spec (magnitude, persistence, duration) while the method
   certifies a canonical spec, and the `map` ablation thresholds the total shock mass, so it is
   an analogy, not an identity. (4) Against the content-free arm, a hypothesis the model does not
   name enters with `lam` times the content-free weight, a cost of exactly `log(1 / lam)` nats
   (log 4), and the named one with `lam + (1 - lam) |H|` times it, a saving of
   `log(lam + (1 - lam) |H|)` (log 3.25); `log(|H| / lam)` is a valid but loose bound on the cost.
