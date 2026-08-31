# Compile Once, Think at Shocks, or Think Every Period?

## A value-of-computation study of agentic inventory control

## 1. One-sentence claim and story

Inventory agents should compile routine reasoning into a cheap controller and spend online LLM computation only when its predicted **delayed operational value** exceeds its cost.

The paper compares three clean placements of language-model computation:

1. **Compile once:** one design-time LLM session writes an executable replenishment policy, which is frozen before test episodes.
2. **Think at shocks:** a conventional OR controller acts by default; a learned gate invokes an LLM only when paired counterfactual rollouts predict that intervention will improve downstream reward.
3. **Think every period:** InventoryBench's OR-to-LLM agent calls the model at each decision.

This is a stronger story than generic “token-efficient routing.” In inventory control, invoking the model changes an order, which changes future arrivals, stockouts, inventory, and observations. The value of a call is therefore endogenous and delayed. A trigger trained only to detect surprising demand may call at irrelevant anomalies and miss economically important pipeline failures. Our gate directly estimates the value of computation (VoC) over the resulting control trajectory.

The motivating evidence is unusually balanced. [InventoryBench](https://arxiv.org/abs/2602.12631) reports normalized reward of 0.445 for OR, 0.494 for LLM-only, 0.538 for OR-to-LLM, and 0.501 for LLM-to-OR with Gemini 3 Flash. Its analyses credit LLMs with recognizing shifts, seasonal product context, and lost shipments, but also show false shift diagnoses, weak cost calibration, and pipeline-arithmetic errors. At the opposite extreme, the 2026-08-27 paper [*LLMs Can Design Near-Optimal OR Algorithms*](https://arxiv.org/abs/2608.27296) finds that one design-time LLM session can synthesize reusable algorithms competitive with specialist methods on well-specified OR tasks. This makes “compile once” a mandatory new baseline and creates a timely question: when is online agenticity actually necessary?

## 2. Research questions and hypotheses

- **RQ1—placement:** What operational reward is obtained per call, token, dollar, and second by design-time, shock-time, and every-period computation?
- **RQ2—concentration:** Is most positive LLM-over-OR advantage concentrated in a few states near demand shifts or delayed/lost arrivals?
- **RQ3—effectiveness:** Can selective invocation outperform always-online reasoning by preventing harmful overreaction to ordinary noise?
- **RQ4—generalization:** Does a gate transfer across demand families, products, lead-time regimes, and base LLMs?

We expect compile-once to be strongest on stationary, well-specified instances; selective consultation to dominate the reward–compute frontier under shifts and stochastic lead times; and always-online calls to waste compute or reduce reward on stationary/variance-only episodes. A credible negative result is also possible: strong statistical exception handling or compile-once may make deployment-time LLM calls unnecessary.

## 3. Formalization and proposed method

At period \(t\), state \(s_t\) contains on-hand inventory, aged outstanding orders, demand/arrival history, costs, promised lead time, date, and allowed product context. Action \(a_t\ge 0\) is the order quantity; exogenous demand and lead-time realization are \(\omega_t\):

\[
s_{t+1}=F(s_t,a_t,\omega_t).
\]

Let \(a_t^O=\pi_O(s_t)\) be the cheap capped base-stock action and \(a_t^L\) the OR-to-LLM action. A gate selects \(z_t\in\{0,1\}\) and optimizes

\[
\max_{\pi_z}\;\mathbb E\!\left[\sum_t r(s_t,a_t)-\lambda z_t c_t\right],
\quad a_t=(1-z_t)a_t^O+z_ta_t^L,
\]

or equivalently maximizes reward under a call/token budget \(B\). Both views will be reported so conclusions do not depend on one temporary API price.

The training label is an \(H\)-step counterfactual advantage:

\[
\Delta_t^{(H)}=R_{t:t+H}(s_t,a_t^L,\pi_c;\omega)-R_{t:t+H}(s_t,a_t^O,\pi_c;\omega).
\]

The branches share the same future demand and lead-time realization and use the same continuation policy \(\pi_c\). This paired common-random-number design isolates the causal consequence of the present intervention and captures delayed arrivals, avoided stockouts, and later holding cost. A lightweight gradient-boosted or calibrated linear model predicts \(\Delta_t^{(H)}\), or its probability of exceeding call cost. Thresholding its conservative estimate yields the entire reward–compute frontier.

Features must be available online: recent demand residuals; Page–Hinkley/CUSUM statistics; trend and seasonal residuals; inventory position; aged-pipeline mass; promised-versus-observed lead-time discrepancy; critical fractile; and cheap date/category encodings. Future demand, benchmark pattern names, and test labels are prohibited. The gate itself makes no LLM call.

For **compile once**, the same base LLM receives the environment contract and development-range description and returns sandboxed Python. The primary arm permits one design session for the entire problem class; the policy is unit-tested, then frozen. Count every model inference, token, and sandbox round, and report both user-level sessions and model invocations. Five independent generations with development-only selection are a robustness analysis and their extra computation is counted. For **think at shocks**, triggered calls use exactly the always-online OR-to-LLM prompt and model, so invocation timing is the only treatment. For **think every period**, we reproduce the benchmark agent unchanged.

## 4. Dataset audit, readiness, and license

The primary artifact is [InventoryBench](https://github.com/TianyiPeng/InventoryBench), pinned to commit [`62b1f1162f19a41d428d47c6cd4ca431f098f6f3`](https://github.com/TianyiPeng/InventoryBench/commit/62b1f1162f19a41d428d47c6cd4ca431f098f6f3). It has **1,320 instances**:

- **720 synthetic:** 10 demand patterns × 4 variants × 2 realizations × 3 lead-time regimes × 3 critical-fractile settings. The patterns cover stationarity, upward/downward shifts, trends, variance changes, seasonality, multiple changes, temporary spikes/dips, and autocorrelation.
- **600 real:** 200 H&M articles × 3 lead-time regimes, with weekly demand plus description, category, color, garment group, and 2019 calendar context.

Each instance has five initial observations. Synthetic episodes have 50 decisions. The paper's Appendix E says the real test horizon is \(T=47\), whereas the README says 48. At the pinned commit, a representative real `test.csv` has 48 physical lines **including the header**, hence 47 observations. We will generate and publish a manifest that parses every CSV, records row counts and hashes, and derives call totals rather than hard-coding either claim. Under the audited 47-period interpretation, one full always-online sweep is \(720\times50+600\times47=64{,}200\) calls.

Readiness is high: the repository provides fixed trajectories, all four published agents, evaluator, perfect-information normalization, and prior outputs. OR runs require no key; LLM runners use OpenRouter and can be adapted to an OpenAI-compatible local endpoint. The repository is large and uses Git LFS, so pin the commit and document the download requirements.

**Licensing caveat.** The root license is MIT, but its copyright line names Leon Guertler rather than the InventoryBench authors, apparently inherited from TextArena. The real trajectories derive from the [H&M Kaggle competition](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data); a repository-level MIT file does not automatically override the upstream competition terms. We should request author clarification before redistributing those trajectories. The safe artifact releases code, prompts, split IDs, manifests, synthetic extensions, and hashes, while directing users upstream for restricted data. The primary claim remains testable on the synthetic portion.

## 5. Experimental design

### Splits and leakage prevention

- Group real data by article ID so all three lead-time variants remain in one fold.
- Group synthetic data by family, parameter variant, and realization; the hard split holds out entire variants or families.
- Generate fresh seeds, shifted changepoints, and mixed anomalies from the documented processes for contamination-resistant testing.
- Produce rollout labels only on development states. Tune horizon, features, and thresholds on a separate calibration fold.
- Hide filenames/pattern labels; expose only information legitimate at decision time. Compile-once sees the class specification, never test trajectories or article IDs.

### Baselines

The non-LLM controls must be strong: published capped base-stock OR; dynamically re-estimated base stock; trend/seasonal forecast plus base stock; CUSUM/Page–Hinkley changepoint adaptation; and aged-pipeline/lost-order correction. These test whether LLM gains merely repair a weak controller.

LLM controls are published LLM-only, LLM-to-OR, and OR-to-LLM; compile once; one episode-start call; periodic calls every \(k\) periods; and random equal-budget calls. Trigger baselines include anomaly thresholds, CUSUM, Page–Hinkley, SPRT, uncertainty, logistic/boosted routing, and a contextual bandit. On a small subset, jointly optimize up to \(B\) interventions with exhaustive search for tiny budgets and beam search otherwise; this is the upper comparator. Report top-$B$ isolated advantages only as a non-interacting concentration diagnostic, because an intervention changes later states. Evaluate \(B\in\{0,1,2,4,8,16,T\}\) and matched percentage budgets.

### Metrics and statistics

Effectiveness: official normalized reward, raw profit, regret to perfect information, fill rate, stockout quantity, holding cost, and ending inventory. Efficiency: calls, input/output tokens, p50/p95 latency, dated dollar cost, and local GPU-hours. Primary plots are reward–call, reward–token, and reward–cost Pareto curves. The scalar summary is area under normalized reward versus call fraction, integrated over the fixed interval $[0,1]$ with larger values better; token and dollar frontiers use preregistered matched-budget points rather than an ambiguously scaled area. Report results by demand family, lead time, critical fractile, and real/synthetic source.

Gate diagnostics include error/calibration for \(\Delta_t^{(H)}\), AUROC/AUPRC for beneficial intervention, precision among triggered states, recall of top-value events, and trigger time relative to a true change or first evidence of a lost order.

All policy comparisons are paired by instance and exogenous trajectory. Report paired-bootstrap 95% confidence intervals, a paired permutation or Wilcoxon test, effect sizes, and false-discovery-rate correction for subgroup tests. Deterministic decoding covers the full benchmark; at least three decoding seeds run on a preregistered stratified subset.

### Essential ablations

Remove demand, pipeline, cost, or textual/context features in turn; compare immediate, four-step, lead-time-matched, and long rollout labels; mean versus lower-confidence-bound triggering; gate training on one LLM and transfer to another; with/without product/calendar text and carry-over memo; and action-level correction versus an LLM-produced parameter revision with a validity horizon.

## 6. Budget, pilot, and kill criteria

Stage inference rather than labeling every state. Use 100–150 stratified instances and roughly 4,000–6,000 calls for the pilot; actively label about 12,000–15,000 development states; run the frozen primary open-weight model on all instances only after the pilot passes; use three seeds on about 10%; and reserve at most 5,000–6,000 paid-model calls for confirmatory results. Cache every prompt/output by model, prompt, state, and decoding hash. Set a provisional ceiling of 120,000 local calls and publish actual tokens, latency, hardware hours, and dated prices.

Proceed if a 20–25% call budget (i) retains about 80% of OR-to-LLM uplift or beats always-online reward, (ii) beats equal-budget random and periodic calls by a non-negligible paired margin, and (iii) improves the frontier over the best statistical controller on at least two anomaly families. When $R_{\text{always}}>R_{\text{OR}}$, define retention as $(R_{\text{gate}}-R_{\text{OR}})/(R_{\text{always}}-R_{\text{OR}})$; otherwise use absolute reward and a preregistered non-inferiority test. The joint-search upper comparator must also show concentrated rather than linear value.

**Kill or reframe** if statistical exception handling matches the gate at zero LLM cost, random/periodic calls match its frontier, or rollout labels do not transfer. If compile-once matches shock-time even under contextual and out-of-distribution conditions, publish a negative result about unnecessary online agenticity. If gains occur only on released H&M IDs and vanish on fresh synthetic seeds, assume memorization/contamination until disproved.

## 7. Nearest work and novelty boundary

- [InventoryBench](https://arxiv.org/abs/2602.12631) establishes LLM–OR complementarity but calls a stateless model each period and does not optimize invocation.
- [*LLMs Can Design Near-Optimal OR Algorithms*](https://arxiv.org/abs/2608.27296) establishes single-session algorithm synthesis; we add deployment-time misspecification and measure whether selective online intervention has value.
- [*Uncertainty-Aware Sequential Decision Rules for Event-Triggered LLM Invocation*](https://arxiv.org/abs/2607.13048), with [ECML PKDD 2026 code](https://github.com/GeoffreyWang1117/event-triggered-llm-streaming), already covers threshold, CUSUM, SPRT, Bayesian, and learned triggers for passive streaming diagnosis. An anomaly trigger alone is not novel. Our boundary is endogenous action, delayed operational reward, paired causal rollouts, and the three-way computation-placement comparison.
- [*Budget-Aware Tool Use*](https://arxiv.org/abs/2511.17006) and [*Utility-Guided Agent Orchestration*](https://arxiv.org/abs/2603.19896) motivate explicit cost frontiers, but study tool/search orchestration rather than delayed physical control.
- [RouteLLM](https://arxiv.org/abs/2406.18665) is the standard preference-trained strong/weak router. [InvAgent](https://arxiv.org/abs/2407.11384) is prior multi-agent LLM inventory work.
- [MABIM](https://arxiv.org/abs/2306.07542) and its [Apache-2.0 environment](https://github.com/VictorYXL/ReplenishmentEnv) offer optional external validation on 51 multi-echelon tasks and more than 2,000 real-demand SKUs; this is a stretch goal, not required for the compact paper.

The precise novelty claim is: **we introduce a value-of-computation gate for LLM intervention in endogenous inventory control, trained from paired delayed-reward rollouts, and use it to identify the boundary between design-time compilation, sparse shock-time consultation, and always-online reasoning.** A final related-work search should still be repeated before submission to account for concurrent work.

## 8. Ten-week plan, artifact, and venue fit

Weeks 1–2: pin/reproduce the benchmark, publish the manifest, implement strong OR and compile-once, and run the kill-test pilot. Weeks 3–4: paired rollouts, features, gate, and calibration. Week 5: equal-budget baselines and the search-based upper comparator. Weeks 6–7: primary evaluation. Week 8: fresh-seed, transfer, and stochastic robustness. Week 9: statistics, qualitative cases, license clarification, and artifact cleanup. Week 10: writing and reproducibility audit.

Release the lockfile, commit/manifest, split IDs, generators, prompts, compiled code, gate checkpoints, token/latency logs, and table scripts. Release cached responses only where upstream-data licenses and model-provider terms permit; otherwise release hashes, IDs, and aggregate telemetry. Central results should use an open-weight model; proprietary APIs are confirmation only. No real ordering or financial transaction occurs.

According to the [ICORE 2026 portal](https://portal.core.edu.au/conf-ranks/), AAMAS and ECAI are CORE A and are the cleanest homes for resource-bounded sequential agency/hybrid OR–AI. [NAACL](https://portal.core.edu.au/conf-ranks/1648/) or [EACL](https://portal.core.edu.au/conf-ranks/468/) (A) become plausible if analysis foregrounds language product/date context and reasoning failures. ECML PKDD (A) is thematically suitable but has the closest event-trigger collision. [COLING](https://portal.core.edu.au/conf-ranks/949/) (B) is a realistic compact-paper fallback.

## 9. Annotated primary sources

- [Baek et al., 2026, InventoryBench paper](https://arxiv.org/abs/2602.12631) and [official artifact](https://github.com/TianyiPeng/InventoryBench): benchmark, agents, evaluator, fixed trajectories, reported scores, and behavioral evidence.
- [Baek, 2026, *LLMs Can Design Near-Optimal OR Algorithms*](https://arxiv.org/abs/2608.27296) and [public run records](https://anonymous.4open.science/r/llm-or-algorithms-F9F2): 2026-08-27 design-time algorithm-generation result that motivates compile once.
- [Wang, 2026, event-triggered LLM invocation](https://arxiv.org/abs/2607.13048): nearest methodological collision and source of classical trigger baselines.
- [Liu et al., 2026 revision, budget-aware tool use](https://arxiv.org/abs/2511.17006): explicit agent budgets and cost–performance reporting.
- [Ong et al., 2024, RouteLLM](https://arxiv.org/abs/2406.18665): preference-based routing and cross-model transfer baseline.
- [Yang et al., 2023, MABIM](https://arxiv.org/abs/2306.07542): optional public multi-echelon inventory environment.
- [H&M competition data page](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data): upstream real-data source and licensing constraint.
