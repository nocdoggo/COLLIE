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

*Note (2026-09-29).* A fourth stage was added later: **D. Cost ratios and noisy lead times**
(registered before its runs at the end of this plan, with pre-run amendments DA1 to DA12).

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
   4.20) and H2 +162.8 and +145.3; the largest one-sided sign-flip p is 0.0024.
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

## Stage D. Cost ratios and noisy lead times

Registered 2026-09-29, before any stage D run on its pools. Exploratory with respect to Gate 3,
as stages A to C are. Stage D asks two questions that stage C left open and that its post-hoc
readouts (`out/sensitivity.json`, `out/posthoc.json`) raised on stage C's own episodes: does the
method keep its advantage at InventoryBench's other two cost ratios, and does the model's text
earn anything when stockouts dominate; and does the lead-time gain survive noisy lead times.

**Frozen.** Every stage C file at its current hash, unchanged since the stage C runs (first 16 hex
of sha256): `cth.py` 343835b85d32a69e, `arms.py` 6d1f468e43a5f9f9, `registry.py`
73c7952dc77b80ef, `runner.py` c753ef5e9e348aa2, `episodes.py` 4f0d9df15c05ca7e, `endpoints.py`
1051f372754f6e25 (after C2), `confirm.py` 7b7db9f47db8476b; and two new files, `stage_d.py`
38b79c716fe02836 (swaps the runner's layout for stage D's pools, for one call, and records the
pool in `stage_d.json`) and `confirm_d.py` 1c924d0e5699f91b (the evaluator). Any later change to
these files is a logged deviation. The method under test is `arm12_cth` exactly as in stage C,
with stage C's arm set (`confirm`), trigger, alert rule `bank-v1` and Rule U on arm 10 only. The
cost ratio reaches the arms only through the instance (the critical fractile each arm reads from
its observations) and through the prompt, which shows the margin.

**Episodes.**

- *Stage D pool:* seeds `family * 1_000_000 + 200_000 + i`, `i = 0..7` in every family (48
  units; disjoint from every registered pool, from stage C's reserved `100_000 + 0..23` and from
  the throwaway `900_000` pool), built exactly as stage C's layout: four conditions plus a twin
  per unit, 24 silent and 24 false-alert twins, 240 episodes, one cluster per unit. Run twice,
  at `p = 19` and at `p = 1` (`h = 1`), the benchmark's other two ratios; the demand, lead-time
  and alert paths are the same at both.
- *Stochastic-lead stratum:* the stratum reserved in `episodes.py` (family 4, seeds
  `4_000_000 + 100_000 + i`, `i = 12..19`; 8 units, the bank's text capacity for one family; 32
  shocked episodes and 8 twins, 4 silent and 4 false-alert; 40 episodes, 8 clusters), at `p = 4`.
  Each order's lead time is `max(0, L_t + xi_t)` with `xi_t` iid on `{-2, ..., 2}` with
  probabilities `(2, 27, 48, 18, 4) / 99`. For the four units whose baseline lead is 2 this is,
  before onset, the registered arrival null's delay law (without its loss and pause terms); for
  the four whose baseline lead is 1 it is that law shifted down one period and truncated at
  zero, and after their one-period shift it is the registered law itself. The lead-time
  e-process's null therefore roughly matches the generator for half the units and is
  conservative for the other half, while the demand e-processes keep the plug-in null.

**Endpoints (models).** `gemini-3.8-flash` and `grok-4.20` only. Runs, each through
`python -m analysis.commitment.stage_d`: `d19-<model>` (`--pool main --profit 19`), `d1-<model>`
(`--pool main --profit 1`), `dsl-<model>` (`--pool stochastic --profit 4`). Caps: $8, $8 and $2
for Gemini 3.8; $2, $2 and $1 for Grok 4.20. Each run first smokes three episodes under its full
run name (main pool: `dev/f4/s4200000/early_accurate`, `dev/f1/s1200000/unreliable`,
`dev/f1/s1200000/no_alert__twin`; stratum: `dev/f4/s4100012/early_accurate`,
`dev/f4/s4100012/unreliable`, `dev/f4/s4100012/no_alert__twin`) and goes ahead only if the
smoke's cost scaled to the run's episodes stays below its cap. Nothing is evaluated until all
six full runs have finished.

**Primary hypotheses** (net reward = `total_reward` per episode, all episodes of the run;
one-sided cluster sign-flip p-values and seed-cluster bootstrap intervals exactly as stage C
computes them; Holm's step-down at 0.05 within each family, each family controlling its own
error rate):

- *High margin* (`p/h = 19`, 48 clusters), per model: D1 `arm12_cth - arm10 > 0`; D2
  `arm12_cth - arm1 > 0`; D3 `arm12_cth - ctrl_cth_uniform > 0`, the value of the text. 6 tests.
- *Low margin* (`p/h = 1`, 48 clusters), per model: D4 `arm12_cth - arm10 > 0`. 2 tests.
- *Noisy lead* (`p/h = 4`, stochastic stratum, 8 clusters), per model: D5
  `arm12_cth - arm1 > 0`. 2 tests. With 8 clusters the smallest attainable p is about 1/256.

Each test is reported for its model; a hypothesis holds for a model when its Holm-adjusted test
rejects.

**Secondary (no multiplicity claim).** Stage C's full readout for every run (`confirm.evaluate_run`:
every stage C contrast on net and gross, null safety against arm 1 with the -25 margin, net by
family, exposure, perception, cost). For each low-margin run, the non-inferiority of
`arm12_cth - arm1` over all 240 episodes at the same margin. The text's value at `p/h = 1`
(`arm12_cth - ctrl_cth_uniform`) is read from its two-sided interval, since the post-hoc replay
showed it negative there with Grok. Paired across ratios on the stage D pool, the change in each
contrast from `p = 1` to `p = 19`, and each gain as a share of arm 1's net reward.

**What the plan expects** (from the post-hoc replay on stage C's episodes and the throwaway
development check; neither is evidence here): D1, D2 and D4 to reject with both models; D3 with
Gemini more likely than with Grok; D5 to reject if the content-free development gain on noisy
lead times (+506 per shocked episode on throwaway seeds, against +884 with deterministic leads)
carries over to the method.

**Prior contact.** Development used the throwaway pool only: a scripted structural run of both
stage D layouts through `stage_d.py` and `confirm_d.py` (`base 900_000`, all eleven arms), and a
content-free check of arm 1 and `ctrl_cth_uniform` on noisy lead times. No stage D seed has been
materialised or run: `base 200_000` has never been used, and a search of the working tree, the
repository history and the scratch directories finds no output for the stratum's seeds
(`4100012` to `4100019`), which `episodes.py` has reserved since `662c7e5`.

**Evaluator.** `python -m analysis.commitment.confirm_d` writes `out/confirm_d.json`; it refuses a
run whose pool, ratio or episode count differs from the registered one.

### Stage D amendments (before any stage D call)

Logged 2026-09-29, before any stage D call (smokes included), from a pre-run audit of the
registration by an independent reviewer and a fact-check of the study notes. Numbered DA so as
not to collide with the hypotheses D1 to D5. None changes a hypothesis, a family, a pool or a
cap. DA1, DA2 and DA7 change `confirm_d.py`, DA10 changes the stratum's lead-time generator in
`stage_d.py`, and DA3 and DA11 add `readout_d.py` (new hashes below).

- **DA1 (evaluator: registered runs only).** `confirm_d.check_run` checked the pool by its label
  alone, so a 240-episode run on any base would have passed. It now refuses a run unless
  `stage_d.json` records the registered base (200000 for the main pool, 100000 for the
  stratum), the episodes' unit seeds are exactly the registered pool's (48 main-pool seeds;
  4100012 to 4100019), the manifest says `partial: false`, arm set `confirm` and the run's own
  name, and its ladder rung is the run name's model with that rung's served model id (the
  endpoint block's own name is the project's base configuration, `gemini-primary` or
  `grok-hosted-confirmation`). `--throwaway-base` runs the same checks on the
  throwaway pool for structural tests (skipping the model and run-name checks) and marks the
  output not confirmatory.
- **DA2 (flip test).** Stage C's flip test compares draws with the observed mean at an absolute
  tolerance of `1e-12`; with net rewards about 19 times stage C's, rounding could drop the
  all-positive pattern. The tolerance is now `1e-9 * max(1, |observed|)`. With 16 clusters or
  fewer the p-value is the exact enumeration over all `2^k` sign patterns, and the exact value
  decides; this applies to D5 (8 clusters, smallest p `1/256`). D1 to D4 (48 clusters) keep
  stage C's 100,000 random flips with the same seed. `confirm_d.json` stores both p-values and
  stage C's rule next to them. On the throwaway structural runs the new evaluator reproduces
  every mean, interval and p-value of the registered one.
- **DA3 (the two secondaries, defined).** `readout_d.py` (new, `out/readout_d.json`) computes
  them. (i) *Across ratios:* per model, for hedge - gate, hedge - arm 1 and hedge -
  content-free on net reward, the per-episode change from `d1-<model>` to `d19-<model>`,
  paired by episode id (the two runs share the pool, the paths and the alerts; the readout
  refuses different episode sets), with its mean and a two-sided 95% seed-cluster bootstrap over
  the 48 paired clusters (stage C's seed and 10,000 draws). (ii) *Share of arm 1:* for every
  run and each of those contrasts, the mean gain over arm 1's mean net reward, with a
  ratio-of-means interval from the same cluster draws. It also reports, descriptively, the
  null-safety contrast against the margin scaled by `p / 4` (DA4) and, on the lead-time units,
  hedge - arm 1 by true shift size (DA8).
- **DA4 (scale).** Profit is `p` times units sold, so contrasts in currency scale with `p`, and
  a change from `p = 1` to `p = 19` in currency is mostly that scale. The across-ratio change is
  therefore read per unit of `p` (`c19 / 19 - c1 / 1` per episode); the currency change is
  reported beside it. The primaries D1 to D5 are within one ratio and are unaffected. The null
  safety margin stays -25 in currency as registered; the margin scaled by `p / 4` (-118.75 at
  `p = 19`, -6.25 at `p = 1`) is descriptive.
- **DA5 (what the expectations rest on).** Stage D's model answers are new paid calls at each
  ratio, and the prompt shows the margin, so the models may answer differently at `p = 19` and
  `p = 1` than at `p = 4`. The post-hoc replay behind "What the plan expects" held stage C's
  answers fixed; it is not a like-for-like prediction, and D3 and D4 can include answer changes
  caused by the margin.
- **DA6 (models).** Only the default two-model evaluation is confirmatory. `--models` with a
  subset would shrink the Holm families (6 to 3, 2 to 1); it is refused unless
  `--not-confirmatory` is given, which marks the output. No evaluation of any kind, on any
  subset, before all six runs have finished.
- **DA7 (completeness).** The episode count counted ids across all arms, and the contrast
  silently drops unpaired episodes. Every arm a contrast reads (the eight arms of stage C's
  contrasts) must now have every episode, or the run is refused. The alert upper bound and the
  oracle run on shocked episodes only, by design, and enter no contrast.
- **DA8 (the lead-time shift sizes).** Every family-4 unit moves to a lead of 3
  (`COMBO_A[4] = ((1, 3), (2, 3))`, cycling every two units): units `i = 0, 1, 4, 5, ...`
  (`(i // 2)` even) have a baseline lead of 1 and shift by two periods; units `i = 2, 3, 6, 7,
  ...` have a baseline of 2 and shift by one. The study notes said every true shift was one
  period; that was wrong (the `low` magnitude bin in `truth.jsonl` for supply families is a
  binning convention, not a shift size). The gate compiles `medium` as +2 on the running lead,
  exact for the baseline-1 units. In the stratum paragraph above, the sentence that the
  baseline-1 units have the registered law itself after a one-period shift is wrong: after onset
  every stratum unit's lead is 3 plus noise, the registered delay law shifted up one period
  (clipped at 4 by DA10); before onset the reading above stands (the lead-time null roughly
  matches the generator for the baseline-2 units and is conservative for the baseline-1
  units). Stage C's post-hoc reading of the models' lead-time proposals is corrected
  in `REPORT.md`.
- **DA9 (runs that stop).** A run that stops at its spend cap or on a provider error after its
  smoke passed is resumed from its cache under the same name by calling `stage_d.py` directly
  (not the driver, whose smoke projection would count the aborted run's spend). A cap stop is
  resumed with the cap raised by at most $4 (Gemini 3.8) or $1 (Grok 4.20), within the study's
  budget; each resumption is logged here as a dated amendment. A run that cannot complete is
  reported as incomplete, and the evaluator records its hypothesis family as not evaluated, with
  the reason, rather than testing the other model alone (no single-model Holm, DA6); the other
  families are evaluated as registered.

- **DA10 (the stratum's leads stay inside the arrival null).** After onset every stratum unit's
  lead is `3 + xi`, on 1 to 5, and a lead of 5 (probability 4/99 per order) is outside the
  registered arrival null's finite support (delays 0 to 4). The null explains such a receipt
  only through its small pause term or not at all; then `ArrivalForwardFilter.step` raises. The
  certify-then-hedge arms catch it and drop their lead-time hypothesis for the episode, but
  nothing between arm 10's e-process and the runner catches it, so one such receipt would abort
  a run with no records. The reviewer's development check (throwaway units 12 to 19, 12
  synthetic noise draws, scripted proposals that name the true family) found arm 10 raising in
  15 of 288 alerted episode runs, and in at least one unit of 4 of the 12 synthetic strata; the
  throwaway structural run had not exercised the path because its scripted proposals were
  demand rises. The stratum's leads are therefore clipped to 4: `min(4, max(0, L_t + xi_t))`,
  the twin's likewise, in `stage_d.py`'s stratum builder (`episodes.py` is unchanged; the rule
  is recorded in `stage_d.json` as `lead_rule`). After onset the lead's law is (2, 27, 48, 22) /
  99 on leads 1 to 4. The same check rerun (same 12 draws): without the clip, arm 10 raised in 15 of 288 episode
  runs and the method dropped its lead-time hypothesis in 15 episodes; with it, 0 and 0. The main pool is
  unaffected.
- **DA11 (reading D5).** The stratum's mix is fixed by the unit index: units 12, 13, 16 and 17
  have a baseline lead of 1 and shift by two periods, units 14, 15, 18 and 19 a baseline of 2 and
  shift by one, so shift size is confounded with the baseline and with how well the lead-time
  null matches the pre-onset noise. On throwaway units the content-free arm's gain comes mostly
  from the two-period units, and its sign on the one-period units varies. D5 stays as
  registered; it is read as "the gain survives noisy leads across the stratum's mix of one- and
  two-period shifts", its evidence being the sign consistency of the 8 unit-level gains (the
  exact test's smallest p is 1/256), with the 8-cluster bootstrap interval descriptive.
  `readout_d.py` reports, descriptively and without tests (4 clusters per shift size, smallest
  p 1/16): hedge - arm 1 per unit and per shift size, the two-period units' share of the gain,
  per information condition (the no-alert episodes are not structurally zero: the demand
  detector fires on some family-4 paths, and then the arms consult the model), and null
  exposure and null safety per baseline lead (4 twins each, 2 of them false-alert). The
  stratum's exposure is not pooled with the main pool's.
- **DA12 (provenance and launch).** "What the plan expects" compares +506 (content-free gain per
  shocked episode on throwaway units 12 to 19 with noisy leads, computed before DA10's clip)
  with +884 (throwaway units 0 to 7, deterministic): different units. On the same units 12 to 19
  with deterministic leads the reviewer measured +1,115, so noise removed about 55% of the gain
  there. Every run is launched exactly as registered, through the driver, which passes
  `--profit` and `--spend-cap-usd` explicitly (the runner's own defaults are p = 4 and $2).

New hashes (first 16 hex of sha256): `confirm_d.py` f52005a900552931, `stage_d.py`
d77e2e2b4c792fb8, `readout_d.py` 51b152001901b8af. Every other stage C and D file is unchanged.
