# Ask What Changed, Not What to Order

## Verified ShockSpecs for sparse LLM–OR inventory control

## 1. Executive decision

The stronger paper is no longer primarily about **when to call an LLM**. Recent work already covers event-triggered invocation, fast–slow routing, cached guidance, budgeted replanning, and online inventory-policy generation. A new trigger or value-of-computation gate would now be an incremental contribution.

The proposed paper instead asks a more distinctive question:

> Can one sparse LLM call turn an unstructured operational warning into a typed, persistent, and prospectively testable hypothesis about what changed, while statistics decides whether the hypothesis deserves influence and OR decides every order?

We call the object a **ShockSpec**. The LLM never chooses an order, writes policy code, selects its own statistical test, or judges whether it was correct. It makes one bounded semantic commitment about the exogenous process, such as a temporary demand pulse, a persistent lead-time increase, or a shipment-loss burst. A deterministic compiler maps that commitment into an inventory model. Only observations arriving after the commitment may activate, refute, expire, or supersede it.

The one-sentence claim is deliberately precise:

> A selectively invoked frozen LLM commits to a typed exogenous shock model, chosen from past information, whose influence on a deterministic OR controller is governed by prospective, post-selection-valid sequential evidence.

This is a cleaner and more defensible contribution than asking an LLM to repair the policy itself. It also creates a memorable division of labor:

> **The LLM says what changed once. Statistics decides whether to trust it. OR decides what to do repeatedly.**

## 2. The opening story

Imagine that an inventory planner receives a short note saying that customs inspections may stop outbound scans for roughly four days. A per-period agent rereads the warning at every decision, repeatedly revises its estimated lead time, and may double-order because it has weak pipeline arithmetic. A conventional controller ignores the note until missing receipts become visible, by which point the useful response window may have passed. A policy-generation agent can write a new rule, but that rule is difficult to attribute, test, and retire.

ShockSpec gives the expensive model a smaller job. At the alert, it records a frozen claim such as `transit_pause`, onset within two periods, medium severity, four-period duration, supported by the message and current pipeline discrepancy. The system, not the model, translates this object into a registered arrival model and a bounded controller configuration. New observations then accumulate evidence. If due shipments stop progressing, the claim becomes active and the controller discounts frozen pipeline stock. If receipts continue normally, the claim never activates. When transit resumes, the object expires or is refuted, so the controller cannot quietly carry a stale disruption belief forever.

This story matters outside the benchmark. A field experiment in *Management Science* reports an average **4.92% profitability increase** when human judgment was allowed to adjust inputs to an inventory algorithm, supporting an interface in which contextual interpretation modifies a model while an algorithm retains the final calculation ([Kesavan et al., 2025](https://pubsonline.informs.org/doi/10.1287/mnsc.2024.06321)). Separately, *The Cost of Delivery Delays* documents an approximately **21-day increase in U.S. import delays between 2018 and 2024** and estimates meaningful downstream output costs ([Carreras-Valle and Ferrari, 2025](https://www.aeaweb.org/articles?id=10.1257/pandp.20251089)). The paper therefore studies a genuine operational failure mode, while making only a controlled, semi-synthetic policy-evaluation claim rather than pretending to be a live deployment.

## 3. Research questions and hypotheses

- **RQ1, representation.** Is a typed event-level ShockSpec more useful than a direct action or a one-shot numerical parameter revision at the same LLM-call budget?
- **RQ2, verification.** Does future-only sequential verification reduce false adaptation, stale beliefs, and downside risk enough to justify its activation delay?
- **RQ3, language value.** Do operational messages provide actionable information before telemetry alone, or can CUSUM, Page–Hinkley, an HMM, a keyword parser, or a small classifier match the LLM?
- **RQ4, amortization.** Can one accepted semantic commitment support several correct OR actions and approach the reward of every-period LLM–OR control with far fewer calls?
- **RQ5, boundary conditions.** Under which shock families, warning times, message reliabilities, and model misspecifications is the LLM useful, unnecessary, or actively harmful?

The primary hypothesis is not that ShockSpec wins everywhere. We expect the largest gain when text arrives before the numerical effect, the shock persists long enough to act on, and a wrong response is costly. Telemetry-only adaptation should be competitive when the shock is immediately observable. Future-only verification may be too slow for a one-period pulse. Those boundaries make the result more scientific and more interesting than a single average benchmark score.

## 4. Method

### 4.1 Triggering is infrastructure, not the contribution

All selective LLM interfaces use the same preregistered invocation rule. A proposal is permitted when an operational alert arrives or when a cheap telemetry detector such as Page–Hinkley or CUSUM crosses its calibrated threshold. A refractory window prevents repeated calls about the same incident, and the primary design permits at most two proposals per episode. Random and periodic schedules are matched to the same call budget.

This intentionally avoids a weak novelty claim. Event-triggered LLM invocation already includes threshold, CUSUM, SPRT, Bayesian, optimal-stopping, and learned rules ([Wang, 2026](https://arxiv.org/abs/2607.13048)). Related systems already learn whether to query, cache, drop, or replan under latency and token constraints, including [ASSCG](https://arxiv.org/abs/2606.25509) and [BRACE](https://arxiv.org/abs/2608.01428). The paper begins after invocation and asks what durable, auditable object the call should return.

### 4.2 A closed, typed commitment

At proposal time \(\tau_j\), a frozen LLM receives only information in \(\mathcal F_{\tau_j}\): permitted product context, the available alert, demand and arrival history, inventory position, an aged pipeline summary, and costs. It must return valid JSON under a closed schema:

```json
{
  "target_stream": "none | demand | arrival | both",
  "shock_family": "no_change | demand_level | temporary_pulse | lead_time_shift | shipment_loss | transit_pause | compound",
  "direction": "none | demand_up | demand_down | arrival_delayed | arrival_interrupted | mixed",
  "onset_window": [-2, 2],
  "magnitude_bin": "none | low | medium | high",
  "persistence": "none | transient | persistent | unknown",
  "duration_bin": "none | 1_3 | 4_8 | longer",
  "evidence_refs": ["alert_17", "arrival_residual_t19"],
  "prospective_signature": "schema_defined_identifier"
}
```

Onset endpoints are registered period offsets relative to the proposal, so a delayed message may describe a recent onset and an early warning may describe an anticipated one. `no_change` is a first-class abstention output, uses null onset and magnitude fields, and leaves baseline OR active; the LLM is never forced to invent a shock when evidence is insufficient. The model may select only registered families, intervals, and signatures. It cannot write an arbitrary falsifier, likelihood function, order equation, test threshold, or executable code. `evidence_refs` point to visible message spans or observation IDs and do not request hidden chain-of-thought. An invalid object receives one format-repair attempt; failure falls back to the unchanged OR controller, and every attempt is counted.

This restriction is central to soundness. If the LLM could invent its own vague test after seeing the trigger window, “falsifiability” would be cosmetic. The system derives the verifier and control mapping from the schema, and the proposal is immutable after generation.

### 4.3 Deterministic compilation into OR

For each registered family, a deterministic compiler maps the ShockSpec into a predictive model \(p_{h_j}\) and a bounded controller configuration. A compact primary grid is:

\[
m\in\{0.6,0.75,1.0,1.25,1.5,2.0\},\qquad
L_{\mathrm{eff}}\in\{1,2,3,4\},\qquad
\gamma\in\{0,0.5,1\},
\]

where \(m\) is the demand multiplier, \(L_{\mathrm{eff}}\) is effective lead time, and \(\gamma\) is the fraction of outstanding pipeline credited as likely to arrive. The 72 configurations are small enough to enumerate for oracle and regret analyses and include the generator's main demand magnitudes. A conventional capped base-stock controller computes

\[
IP_t=I_t+\gamma P_t,
\qquad
q_t=\min\!\left\{\max\{0,S_t(m,L_{\mathrm{eff}})-IP_t\},C_t\right\},
\]

where \(C_t\) is the preregistered InventoryBench order cap shared by every relevant arm. The compiler, base forecast, cap, and order equation are otherwise identical across relevant baselines. InventoryBench exposes aggregate in-transit inventory rather than shipment ages, so the controller may maintain a deterministic FIFO ledger from its own orders and observed receipts. That imputed ledger is a control feature only and is never used to justify the theorem-backed supply likelihood. Age-binned pipeline telemetry is an optional ablation, not information given only to ShockSpec.

The semantic and control roles are therefore separated. The LLM estimates the environment. Statistics controls the influence of that estimate. OR performs the action calculation.

### 4.4 Prospective, post-selection-valid activation

The main statistical trap is reusing the observations that caused the LLM to select a hypothesis as evidence confirming that same hypothesis. We avoid this by freezing \(h_j\) at stopping time \(\tau_j\) and using only \(Y_{\tau_j+1},Y_{\tau_j+2},\ldots\) for its verifier.

Before touching the test set, select one theorem-backed construction. On the **registered-model slice**, the public environment contract gives every method the same pre-shock conditional law \(p_0\). Every \(p_{h,\theta}\), mixture \(W_h\), and nuisance-parameter procedure is then frozen using development or calibration data before observing \(Y_{\tau_j+1}\). This public baseline model is not the hidden incident sidecar. A practical plug-in verifier estimated from the same online stream is reported separately and receives no finite-sample guarantee. Neither the verifier nor any policy may read the hidden ShockSpec or latent test parameters.

Demand tests use the registered conditional law for the observation actually exposed by the simulator. For theorem-backed supply activation, a finite-state forward algorithm marginalizes over every shipment-cohort assignment consistent with the observable order and aggregate-receipt history. It computes \(p_0(R_t\mid\mathcal F_{t-1},A_{t-1})\) and the corresponding registered alternative without selecting a FIFO identity. The exact marginal likelihood ratio is the e-process input; the controller's convenient FIFO ledger is never treated as evidence. If this recursion or its supermartingale argument cannot be established for a supply family, that family remains an empirical stress test and receives no formal false-activation claim.

Compound shocks use a registered joint conditional likelihood. The synthetic generator may factor demand and supply innovations only when conditional independence is explicitly part of the environment contract. Otherwise use separate valid e-processes with explicit alpha splitting and no independence assumption; never multiply marginal ratios merely for convenience.

For a registered simple null \(p_0\) and an alternative parameter region \(\Theta_j\), one implementation maintains a mixture likelihood-ratio e-process

\[
E_{j,t}=\int_{\Theta_j}
\prod_{r=\tau_j+1}^{t}
\frac{p_{h_j,\theta}(Y_r\mid\mathcal F_{r-1},A_{r-1})}
     {p_0(Y_r\mid\mathcal F_{r-1},A_{r-1})}
\,dW_j(\theta).
\]

Actions are predictable from past information. Index proposals within episode \(e\) as \(j=1,2,\ldots\); the primary design stops after two. Proposal \(j\) receives \(\alpha_{e,j}=\alpha_{\mathrm{episode}}2^{-j}\) and becomes active only when \(E_{j,t}\ge 1/\alpha_{e,j}\). Because \(\sum_{j\ge1}2^{-j}=1\), the registered stochastic model, future-only construction, and e-process assumptions let Ville's inequality plus a union bound give

\[
\Pr_0\!\left(\text{any false activation in episode }e\right)
\le \sum_j\alpha_{e,j}\le\alpha_{\mathrm{episode}}.
\]

This is a **model-conditional anytime-valid false-activation guarantee**, not a universal safety guarantee and not a guarantee of higher profit. It controls activation under the registered global no-change null within one episode; it neither provides dataset-wide family-wise control nor automatically controls choosing the wrong shock family when a different shock is genuinely present. Refutation and expiry use separately registered operational rules and are evaluated empirically unless an additional confidence-sequence coverage result is proved. The paper will state which demand and arrival models make the likelihood ratio valid, then explicitly stress autocorrelation, overdispersion, seasonality, outliers, and an incomplete shock vocabulary. The relevant foundations are safe anytime-valid inference ([Ramdas et al., 2022](https://arxiv.org/abs/2210.01948)), [e-detectors](https://arxiv.org/abs/2203.03532), and [backward confidence sequences for changepoints](https://proceedings.mlr.press/v202/shekhar23a.html).

Let \(\mathcal F_t\) contain all observations through period \(t\), immediately before choosing \(A_t\). The event order is fixed. Order \(A_t\) affects only the next observation \(Y_{t+1}\), which joins \(\mathcal F_{t+1}\) before \(A_{t+1}\) is selected. Therefore evidence from \(Y_r\) may affect \(A_r\), never \(A_{r-1}\), and the verifier conditions \(Y_r\) on \((\mathcal F_{r-1},A_{r-1})\) throughout.

Each object has a deterministic lifecycle:

1. `proposed`, while baseline OR remains active.
2. `active`, after sufficient prospective evidence.
3. `refuted`, when a separately registered contradiction rule fires.
4. `expired`, at its schema-defined maximum lifetime.
5. `superseded`, when a separately tested later proposal replaces it.

False-activation control does not eliminate the central tradeoff. Waiting for future evidence can make the statistically clean method operationally late. Proposal-to-activation delay is therefore a primary outcome. An exploratory **bounded provisional** arm may immediately apply a small trust-region adjustment while evidence accumulates, but that arm does not inherit the hard activation claim.

## 5. InventoryBench-ShockSpec dataset

### 5.1 Base environment and honest scope

The executable base is [InventoryBench](https://arxiv.org/abs/2602.12631), using the [official repository](https://github.com/TianyiPeng/InventoryBench) pinned to commit [`62b1f1162f19a41d428d47c6cd4ca431f098f6f3`](https://github.com/TianyiPeng/InventoryBench/commit/62b1f1162f19a41d428d47c6cd4ca431f098f6f3). It contains 720 synthetic and 600 H&M-derived instances, fixed trajectories, existing LLM and OR agents, and a reproducible evaluator.

The H&M trajectories are real sales histories, but their supply disruptions are simulated, selected products are unusually stable, and true demand remains visible during stockout. We will describe this as **controlled or semi-synthetic policy evaluation on real demand**, not real-world deployment evidence. The headline simulator-observable setting exposes the same uncensored demand signal to every arm. A required censored-sales sensitivity setting exposes only sales and availability; there, the verifier models observed sales conditional on availability and action and never reads latent demand. Any formal e-process claim is restricted to the observation model for which validity is actually established.

The root code license is MIT, while redistribution of H&M-derived files remains governed by the [upstream H&M Kaggle terms](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data). The release will include code, generators, prompts, split IDs, manifests, and hashes, while directing users to the upstream source where necessary.

### 5.2 Six controlled shock families

The project-owned extension introduces hidden-onset incidents that a policy cannot read directly. Magnitude and duration vary within each family so the task cannot collapse into six fixed-class lookups:

1. Persistent demand increase with multiplier sampled from \(\{1.25,1.5\}\).
2. Persistent demand decrease with multiplier sampled from \(\{0.6,0.75\}\).
3. Temporary demand spike with multiplier in \(\{1.5,2.0\}\) for two to four periods.
4. Persistent deterministic lead-time shift from a baseline in \(\{1,2\}\) to a disrupted value in \(\{3,4\}\).
5. Lost-shipment burst affecting orders from one to three consecutive periods.
6. Compound event with a demand multiplier in \(\{1.25,1.5\}\) for six to ten periods and a three-to-five-period transit pause.

Onset is uniformly sampled from periods 14 through 22 and hidden from the policy. Parameter combinations are split so held-out severity-duration combinations occur only at test time; an additional extrapolation slice uses preregistered unseen values inside wider family ranges. A small OOD slice also holds out one composition of otherwise familiar demand and supply primitives. Transit-pause behavior follows the operational semantics documented by [Stockpyl](https://stockpyl.readthedocs.io/en/latest/tutorial/tutorial_sim.html): material already in transit stops progressing and newly shipped material joins the frozen pipeline until recovery. We port only the semantics into the InventoryBench-compatible generator; Stockpyl's [MIT-licensed code](https://github.com/LarrySnyder/stockpyl) remains an implementation reference.

### 5.3 Crossed information conditions

For each shock trajectory, cross the identical exogenous realization with four information conditions:

1. No alert.
2. An accurate alert one period before onset.
3. An accurate alert two periods after onset.
4. An unreliable alert drawn from inaccurate, overstated, ambiguous, or distractor messages.

The minimum held-out test contains **640 episode-condition rollouts**: six shock families by 25 independent trajectory seeds by four information conditions, yielding 600 paired replays, plus 20 silent-null and 20 false-alert-null controls. Development contains 144 rollouts, from six families by four information conditions by six seeds, and calibration contains 96, using four seeds per family-condition cell. A preregistered power rule may use calibration data to set a larger final count, but the seed count and every message-template assignment are frozen before any test trajectory is run. No test result may trigger sample-size expansion.

The independent shocked unit is one of 150 exogenous trajectory/shock seeds; the four information cells are paired replays, not 600 independent incidents. Family-level tail estimates remain exploratory even with 25 seeds per family. Because held-out alert templates are reused across seeds, language-level uncertainty must additionally treat template as a sampling unit.

Forty main-table nulls still cannot estimate a 5% horizon-wide error rate precisely. We therefore add a cheap **1,300-episode end-to-end verifier audit bank**. One thousand are well-specified registered-model nulls spanning every baseline conditional law used in theorem-backed headline cells, with stationary IID as one sanity-check stratum; report false activations with exact or Wilson binomial intervals. The theorem-backed null must match the actual baseline generator and exposed observation process, including any registered seasonality, dispersion, dependence, or censoring. Three hundred additional episodes contain no target shock but deliberately violate those assumptions through unexpected autocorrelation, variance, seasonality, or outliers.

A null-audit episode is one independent exogenous trajectory with one fixed alert schedule and at most two proposal opportunities. Both audit groups contain balanced silent, neutral, false, and distractor alert schedules and run the full alert-to-LLM-to-proposal-to-verifier pipeline. Counts, retries, and invalid outputs are reported per method. No audit trajectory is reused for threshold tuning, compiler selection, or confirmatory evaluation. Formal calibration is claimed only for matched registered-model strata; the 300 misspecified episodes are reported separately as fragility tests. If no valid conditional null is available for a family, that family's result is empirical and excluded from the anytime-valid claim.

### 5.4 A manageable, audited alert bank

Create **180 short synthetic operational templates**, with ten per shock family in each of the development, calibration, and test splits. Within every family-split cell, four are accurate, two are inaccurate or overstated, two are ambiguous, and two are operational distractors. Wording families and parameter combinations are held out across splits. Controlled slots for supplier, location, timing, and qualitative severity are instantiated per episode so exact strings do not repeat, while template IDs remain available for crossed uncertainty estimates.

Two independent reviewers rate every base template for operational plausibility, consistency with the canonical label, whether the information could exist at the scheduled time, absence of hidden-state leakage, and realistic uncertainty. They also audit a stratified sample of instantiated messages. Disagreements are adjudicated and agreement is reported. Messages should not reveal the exact multiplier or latent class name.

A hidden machine-readable `AlertSpec` accompanies each message. Giving this canonical structure directly to the same compiler is the parsing upper bound. Synthetic messages are preferable to scraped current news because their provenance, license, timing, and information content are controllable.

## 6. Experiments that isolate the contribution

### 6.1 Core preregistered ablation ladder

Hold the base model, available information, trigger, controller, decoding settings, and call budget fixed wherever applicable. The compact main table needs ten central arms:

1. Stationary capped-base-stock OR.
2. Telemetry-only adaptive OR with an HMM or changepoint detector over normal and disrupted regimes.
3. Every-period InventoryBench OR-to-LLM direct action, included as the strongest published legacy reference.
4. Selectively invoked OR-to-LLM direct action, where the common trigger permits one LLM-produced order and baseline OR acts otherwise.
5. Every-period InventoryBench LLM-to-OR numerical parameter estimation.
6. Selectively invoked ephemeral LLM-to-OR using the common trigger.
7. Persistent one-call LLM-to-OR parameters with fixed expiry.
8. Persistent ShockSpec with immediate unverified activation.
9. ShockSpec with heuristic residual-based rollback.
10. Full future-only verified ShockSpec.

Arms 5 through 10 form a preregistered ablation ladder, not a complete factorial; arm 4 supplies the missing matched-call direct-action comparison, and arm 3 anchors the study against the benchmark's strongest published action-level agent. For every sparse representation, persistence, and verification contrast, fix trigger time, information, controller, model, decoding, and realized call/token budget. Comparisons with every-period agents are efficiency-frontier comparisons on identical episodes rather than single-factor causal contrasts. This design isolates the important mechanisms without hiding the strongest legacy result.

### 6.2 Hard non-LLM controls and upper bounds

Additional decisive comparisons are a CUSUM or Page–Hinkley detector feeding the identical compiler, a keyword/rule parser, a low-data supervised text classifier trained only on development templates, the canonical structured `AlertSpec`, and an oracle ShockSpec with the true family and onset. The classifier is a diagnostic rather than a decisive baseline unless its development corpus is expanded enough to support a fair supervised comparison.

Early-warning value and semantic-content value are estimated separately. The end-to-end early-warning comparison permits different call times. Every semantic-content comparison instead fixes the same alert timestamp, trigger trace, and call opportunity across true-text, masked-text, shuffled-within-timing, and wrong-text arms. A neutral equal-length alert provides the timing-only baseline. These controls prevent an earlier call opportunity from being mistaken for evidence that message meaning helped. Numeric-history-removed and no-alert controls answer separate questions.

Compile-once remains a baseline because [LLMs Can Design Near-Optimal OR Algorithms](https://arxiv.org/abs/2608.27296) shows that a single design session can synthesize reusable OR algorithms. An [InvEvolve](https://arxiv.org/abs/2605.00369)-style full policy-regeneration baseline at matched calls and tokens is desirable on a stratified subset, but must be labeled a faithful reimplementation if no official artifact is available. The paper does not need to make either method a second central contribution.

### 6.3 Metrics

The primary reward endpoint is cumulative undiscounted profit per episode over the fixed horizon. The primary safety endpoint is total lost-sales units per episode. Both are macro-averaged equally across six shock-family strata and one null stratum; the four information conditions receive equal weight within each shock family, and silent and false-alert controls receive equal weight within the null stratum. This fixed endpoint and weighting prevent choosing after the run among raw profit, a ratio, or a favorable test mixture.

The three confirmatory method contrasts are full verified ShockSpec against persistent unverified ShockSpec, selectively invoked ephemeral LLM-to-OR, and telemetry-only adaptive OR. Apply Holm correction across the six endpoint-by-contrast tests. Official normalized reward, unclipped profit ratio, CVaR, service metrics, every family/information subgroup, and all remaining method pairs are secondary or exploratory. The official score remains useful for InventoryBench compatibility, but a clipped normalized score can conceal catastrophic losses.

The primary estimand uses equal stratum weighting. Also report the micro-average over independent trajectories and a preregistered illustrative deployment mixture with 70% no-shock, 15% demand-shock, and 15% supply-or-compound episodes, plus sensitivity to the assumed shock prevalence. Conclusions are not chosen from whichever weighting looks favorable.

Operational metrics include CVaR at 10%, worst-decile profit, fill rate, lost-sales units, maximum stockout streak, holding cost, post-recovery excess inventory, and time to recovery. Predefine recovery as the first of three consecutive post-shock periods with fill rate at least 0.95. Family-level CVaR is exploratory because 25 independent seeds do not support a stable confirmatory tail estimate.

Hypothesis and lifecycle metrics include per-field macro-F1, complete-object exact match, `no_change` abstention precision and recall, magnitude-interval coverage, proposal-to-activation delay, refutation or rollback delay, expiration accuracy, wrong-spec exposure as periods under an incorrect active specification, and realized benefit or harm conditional on activation. **False activation** means activation under the registered global no-change null and is the only activation error covered by the probability statement. **Wrong-family activation** means activating a specification inconsistent with the latent held-out mechanism when another shock may be present; it is an empirical error metric with no theorem-backed bound.

Efficiency metrics include calls, input/output tokens, p50 and p95 latency, dated dollar cost, actions supported per accepted call, and profit–call, profit–token, and profit–cost Pareto frontiers. For every arm, count every attempted call, format-repair call, rejected or unusable response, token, latency measurement, and monetary cost. Cost-frontier points are matched by realized per-episode calls or tokens rather than expected budgets alone.

### 6.4 Statistical design

Policies share the same demand, lead-time, loss, onset, and message-template random draws. Their endogenous inventory, pipeline, receipts, stockouts, and subsequent observations are regenerated separately, as they must be when actions differ. The primary analysis uses two-sided paired randomization inference on per-seed method differences after repeated condition cells are aggregated within their independent exogenous seed. Cluster-bootstrap intervals at the seed level are the primary uncertainty estimate; Wilcoxon tests are secondary robustness checks only. For every language claim, bootstrap jointly over trajectory seed and message-template ID, or use a preregistered mixed-effects model with template as a random effect. Repeated slot instantiations of one template are never counted as independent language examples. All unlisted subgroup and ablation analyses are explicitly exploratory.

Use fresh demand, supply, onset, and message-template seeds at test time. Do not treat crossed cost settings, information conditions, or lead-time variants that share a base trajectory as independent samples. Freeze the controller grid and caps, compiler mappings, schema thresholds, alpha allocation, trigger thresholds, power analysis, provisional trust region, and all oracle mappings using development and calibration data only. The oracle may read hidden truth solely as a labeled upper bound and is never tuned on test trajectories. If every-period agents run only on a stratified subset, every reward, risk, and Pareto comparison involving them is restricted to that identical subset.

## 7. Nearest work and the exact novelty boundary

The proposal must acknowledge the 2026 collision landscape directly:

| Work | What it already establishes | What remains different here |
|---|---|---|
| [InventoryBench](https://arxiv.org/abs/2602.12631) | Per-period LLM-to-OR parameter estimates and editable carry-over memos | A frozen event-level stochastic hypothesis, future-only verification, automatic lifecycle, and one-call amortization |
| [InvEvolve](https://arxiv.org/abs/2605.00369) | Online white-box inventory-policy generation, retrospective replay, confidence screening, and rolling deployment | The LLM estimates the environment rather than the policy; no arbitrary code; evidence is prospective after commitment; every action remains fixed-form OR |
| [Event-triggered invocation](https://arxiv.org/abs/2607.13048), [ASSCG](https://arxiv.org/abs/2606.25509), and [BRACE](https://arxiv.org/abs/2608.01428) | Triggers, query/cache/drop choices, compute budgets, and replanning | Invocation is fixed infrastructure; the contribution is the returned object's semantic-to-statistical-to-control lifecycle |
| [FCPAgent](https://arxiv.org/abs/2607.24167) | Structured procedural commitments with explicit confirming and falsifying evidence, tested using lightweight evidence matching and LLM diagnostic verification | ShockSpec parameterizes an exogenous stochastic model and uses a preregistered sequential statistic compiled into OR inputs |
| [HEP](https://arxiv.org/abs/2607.09195) | Persistent hypothesis objects, provenance, evidence attachments, belief updates, and lifecycle states for scientific investigation | It does not provide this post-selection sequential activation result or compile hypotheses into inventory-control inputs |
| [EventCast](https://arxiv.org/abs/2602.07695) | LLM summaries of campaigns, holidays, incentives, and other event data fused with demand history in a dual-tower forecaster | It does not freeze a typed data-generating-process hypothesis, govern post-generation activation and retirement, execute inventory actions, or measure calls per supported action |
| [InstructMPC](https://arxiv.org/abs/2512.05876) | Text-to-disturbance trajectories for model-predictive control | Sparse event-level commitments, future-only validation, explicit lifecycle, and matched persistent-interface ablations |

The safe novelty statement is:

> We study a bounded LLM-to-environment-model-to-OR handshake in which an adaptively selected typed shock hypothesis is frozen before prospective evidence can authorize its influence on repeated inventory decisions.

Do **not** claim the first event-triggered LLM, persistent agent memory, falsifiable commitment, LLM-to-OR interface, statistically certified inventory agent, safe controller, or online LLM-generated inventory policy. The novelty comes from the particular handshake and its controlled factorization, not from any one ingredient in isolation.

This boundary reflects a primary-source search completed on **August 30, 2026**. It must be rerun immediately before submission because several of the nearest papers are concurrent preprints.

## 8. Pilot, kill criteria, and negative-result value

Run a 100–150 episode pilot before the full benchmark, requiring roughly 2,000–4,000 LLM calls. Freeze the numerical kill thresholds before inspecting pilot outcomes and report paired confidence intervals around every go/no-go estimate. If the pilot changes the schema, compiler, controller, or verifier, none of its trajectories or message templates may reappear in the confirmatory test. Continue only if all of the following hold:

- An oracle ShockSpec improves raw profit by at least 5%, or CVaR10 by at least 10%, over stationary OR on at least four of six shock families. Otherwise the task or compiler has too little headroom.
- At a fixed alert time and call opportunity, the canonical structured-alert upper bound beats both telemetry-only HMM and the neutral-alert timing control on at least some early-warning cells. Otherwise language contains no actionable advance information.
- Verified ShockSpec beats selectively invoked ephemeral LLM-to-OR at matched calls on the preregistered primary reward endpoint.
- Verification improves downside risk, false activation, wrong-spec exposure, or rollback over persistent unverified ShockSpec.
- Median activation delay is shorter than the economically useful response window for a material fraction of persistent shocks.
- Wrong and stale specifications are rejected or retired before producing major cumulative harm.
- The core effect survives fresh seeds and a second LLM on a confirmatory subset.

Kill or explicitly reframe the method claim if a keyword parser or adequately trained classifier matches the LLM, same-time masked or shuffled-text controls are unchanged, CUSUM/HMM feeding the same compiler matches the LLM, prospective verification is consistently too late, false activation substantially exceeds nominal levels under mild misspecification, unverified activation dominates with negligible harm, gains exist only for synthetic wording, or matched-compute full policy regeneration performs equally well.

Several of these failures still support a publishable boundary result. For example, “language alerts help only before telemetry reveals a persistent supply shock,” or “prospective verification is statistically valid but too slow for short shocks,” is more informative than another average-score leaderboard. A null result showing that a strong HMM makes the LLM unnecessary would also be operationally valuable.

## 9. Scope, compute, and ten-week plan

The project intentionally avoids LLM fine-tuning, arbitrary generated code, a new simulator, and mandatory integration of a second benchmark.

- **Weeks 1–2:** reproduce InventoryBench, pin the artifact, implement and audit the ShockSpec generator and alert bank.
- **Week 3:** finalize JSON schema, deterministic compiler, FIFO pipeline ledger, and schema-repair handling.
- **Week 4:** implement family-specific e-processes or confidence sequences and the lifecycle state machine.
- **Week 5:** run pilot and kill tests before expensive sweeps.
- **Weeks 6–7:** run the core ablation ladder and matched non-LLM controls.
- **Week 8:** run held-out wording, compound-shock, null-bank, and model-misspecification tests.
- **Week 9:** perform clustered statistics, error analysis, and qualitative case reconstruction.
- **Week 10:** complete artifact, license notes, reproducibility audit, and writing.

Use one primary open-weight model for all sparse methods and one hosted model on a preregistered confirmation subset. Use one fixed deterministic decoding configuration for the full sweep and at least three decoding seeds on a stratified robustness subset. Each sparse interface should require roughly 2,000–4,000 calls including retries and the 1,300-trajectory null audit. Cache identical prompt-state calls shared by ablations, while still charging the logged call to every counterfactual arm's accounting. If every-period agents are expensive, run them on a stratified 100–150 episode subset and label the comparison accordingly. A practical overall ceiling is roughly 40,000 calls, with actual tokens, latency, cost, and hardware time fully reported.

Release the versioned generator, hidden-state sidecar schema, alert bank, reviewer rubric, splits, prompts, compiler, verifier, policy state machine, hashes, and table scripts. Release model outputs only where provider and upstream-data terms permit.

## 10. Venue positioning

The [ICORE 2026 portal](https://portal.core.edu.au/conf-ranks/) currently lists AAMAS, ECAI, NAACL, and EACL as **A**, and COLING as **B**. The best paper identity depends on which analysis is strongest:

- **AAMAS or ECAI, ICORE A**, if the central result is resource-bounded sequential agency, hypothesis lifecycle, and hybrid LLM–OR control.
- **NAACL or EACL, ICORE A**, if the central result is semantic grounding, held-out alert generalization, typed-hypothesis faithfulness, and when language adds information beyond telemetry.
- **COLING, ICORE B**, as the realistic fallback for a compact but complete empirical paper.

The NLP version must foreground the language question rather than merely using an LLM inside an inventory application. The agents version must foreground the persistent commitment, delayed evidence, control consequence, and compute frontier. Conference dates and current CORE rankings should be checked again at submission time.

## 11. Why this version is stronger

The original paper's best intuition survives: an expensive model should not reason from scratch at every routine decision. The stronger version makes that intuition concrete through a durable object rather than another routing score. It replaces an easily copied “call or do not call” gate with a constrained semantic interface that can be audited field by field, tested prospectively, reused across actions, and retired automatically.

The story has tension. Language can arrive early but be wrong. Telemetry is trustworthy but late. Verification can prevent damage but also erase the value of advance warning. OR is numerically reliable but semantically blind. The experiments are designed to reveal where each side wins rather than force a universal victory.

Most importantly, the method has a clean accountability boundary. When an order fails, one can inspect the alert, the frozen claim, the evidence path, the activation time, the compiler mapping, and the final OR calculation. That combination of freshness, operational importance, statistical honesty, and manageable scope is the strongest path from the old topic to a credible AAMAS, ECAI, NAACL-family, or COLING paper.

## 12. Primary sources to read first

- [Baek et al., InventoryBench, 2026](https://arxiv.org/abs/2602.12631) and its [official artifact](https://github.com/TianyiPeng/InventoryBench).
- [InvEvolve, 2026](https://arxiv.org/abs/2605.00369), the closest inventory-policy generation and certification collision.
- [LLMs Can Design Near-Optimal OR Algorithms, 2026](https://arxiv.org/abs/2608.27296), motivating the compile-once comparator.
- [Uncertainty-Aware Sequential Decision Rules for Event-Triggered LLM Invocation, 2026](https://arxiv.org/abs/2607.13048), establishing that triggering alone is not new.
- [FCPAgent, 2026](https://arxiv.org/abs/2607.24167) and [HEP, 2026](https://arxiv.org/abs/2607.09195), establishing the prior art on falsifiable commitments and persistent hypothesis lifecycles.
- [EventCast, 2026](https://arxiv.org/abs/2602.07695) and [InstructMPC, 2025](https://arxiv.org/abs/2512.05876), the closest language-to-forecast and language-to-control interfaces.
- [Safe Anytime-Valid Inference, 2022](https://arxiv.org/abs/2210.01948), [E-detectors, 2022](https://arxiv.org/abs/2203.03532), and [Backward Confidence Sequences, ICML 2023](https://proceedings.mlr.press/v202/shekhar23a.html), for the statistical construction.
- [Kesavan et al., Management Science, 2025](https://pubsonline.informs.org/doi/10.1287/mnsc.2024.06321), for field evidence on human contextual input combined with inventory algorithms.
- [Carreras-Valle and Ferrari, AEA Papers and Proceedings, 2025](https://www.aeaweb.org/articles?id=10.1257/pandp.20251089) and their [CC BY 4.0 replication package](https://doi.org/10.3886/E230383V1), for real-world delivery-delay motivation rather than policy evaluation.
