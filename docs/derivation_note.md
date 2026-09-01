# Derivation note — future-only activation of a frozen ShockSpec

Task 14 (branch F, `collie-verifier`, P4). Written in Week 1 and **blocking Tasks 15 and 16**:
the code transcribes this note, the note does not document the code afterwards.

Every claim below cites either a primary source (§10) or the audited environment contract
(`docs/env_contract.md`, Task 2). Where neither supports a claim, the claim is marked
**empirical-only** and is excluded from the formal guarantee.

---

## 1. What is claimed, and what is not

**Claim (Theorem 1, §5).** For a single episode `e`, under the registered global no-change null,
the probability that *any* proposal in that episode is ever activated is at most
`alpha_episode`, uniformly over stopping times.

This is a **model-conditional, anytime-valid, per-episode false-activation bound**. Precisely:

| | |
|---|---|
| *model-conditional* | it presumes the registered `p_0` is the true conditional law of the exposed observable. It is a statement *within* a model, not a distribution-free one. |
| *anytime-valid* | it holds at all stopping times simultaneously, so continuous monitoring and optional stopping are permitted [S1]. |
| *per-episode* | the union bound runs over proposals **within one episode**. It is **not** dataset-wide family-wise control across the 640 test rollouts. |

It is **not**:

- a safety guarantee — activation being rare under the null says nothing about loss magnitude when
  activation does occur;
- a profit guarantee — an activated correct hypothesis can still lose money through a bad control
  mapping;
- a bound on **wrong-family activation** — activating `transit_pause` when a `shipment_loss` is
  genuinely present is not a null event, so no part of Theorem 1 covers it. That quantity is
  reported as an empirical metric with no theorem-backed bound;
- a statement about **refutation or expiry** — those are separately registered operational rules,
  evaluated empirically (§8);
- applicable to **official benchmark instances** for arrival-side families (§6.4).

## 2. Notation, filtration, and event ordering

Grounded in `docs/env_contract.md` §3, which was derived from the code rather than from prose.

- `Y_t` — the exposed observable at period `t`. In the headline setting `Y_t` is uncensored demand;
  in the censored setting it is the pair (sales, availability). The contract confirms the benchmark
  reports true demand even during a stockout, so these are genuinely different observation models.
- `R_t` — aggregate receipts at `t`. Scalar; **no shipment ages** (contract §4).
- `A_t` — our order at `t`, coerced by `max(0, int(q))` then capped by our own `C_t` (contract §2.3).
- `F_t` — the sigma-algebra of all observations through period `t`, **immediately before `A_t` is
  chosen**.

The contract fixes the per-period order as: decide `A_t` → schedule at `t + L_actual(t)` (or drop if
`L_actual = inf`) → pop arrivals due at `t` → resolve demand → charge holding on ending inventory.

Two consequences are load-bearing:

**(A1) Actions are predictable.** `A_t` is `F_t`-measurable.

**(A2) Actions affect only the future.** `A_t` influences `Y_{t+1}` and later, never `Y_t`.

Therefore conditioning `Y_r` on `(F_{r-1}, A_{r-1})` is well defined and does not condition on
anything `A_{r-1}` could have altered retroactively. Every density below is written in that form.

> Note that `L = 0` means an order placed at `t` arrives at `t` (scheduling precedes the arrival
> pop). That does **not** violate A2: `L = 0` affects `R_t`, not `Y_t`. Arrival-side e-processes must
> therefore condition `R_r` on `(F_{r-1}, A_{r-1})` **including** `A_{r-1}`'s contribution, which
> §6 does explicitly.

## 3. The post-selection problem, and why freezing solves it

The LLM chooses `h_j` *because* something looked unusual. If the periods that motivated the choice
were then reused as confirming evidence, the apparent evidence would be an artifact of selection,
and "falsifiability" would be decorative.

Two structural facts remove the circularity:

**(A3) Closed selection space.** The hypothesis is drawn from a registered vocabulary, and the
system — not the model — maps `(shock_family, prospective_signature)` to a construction
(`collie/spec/registry.py`, frozen at Gate 2). The model selects a key; it cannot write a falsifier,
threshold, likelihood, order equation, or code. Enforced by the closed schema
(`extra="forbid"`, `frozen=True`) and by the pairing-window-2 contract test.

**(A4) Frozen at a stopping time.** `tau_j` is a stopping time and `h_j` is `F_{tau_j}`-measurable.
The evidence product starts at `tau_j + 1`.

Because `h_j` is fixed before any datum entering its own test, the selection is admissible: the
construction below is a valid test of a *pre-specified* alternative, conditional on `F_{tau_j}`.

## 4. The demand-side construction

For a proposal `j` with registered null `p_0` and alternative region `Theta_j`, define

```
                 t                p_{h_j,theta}(Y_r | F_{r-1}, A_{r-1})
E_{j,t}  =  INT  PROD  ------------------------------------------------  dW_j(theta)
            Theta_j r=tau_j+1        p_0(Y_r | F_{r-1}, A_{r-1})
```

with `E_{j,tau_j} = 1` by convention (empty product).

**Lemma 1 (unit conditional mean).** For fixed `theta`, under the null,

```
E[ p_{h,theta}(Y_r | F_{r-1}, A_{r-1}) / p_0(Y_r | F_{r-1}, A_{r-1}) | F_{r-1} ] = 1,
```

because the expectation integrates the ratio against the null density `p_0`, giving
`INT p_{h,theta} dmu = 1`. This requires only that `p_{h,theta}` be a probability density with
respect to the same dominating measure `mu`, and that `p_0 > 0` wherever `p_{h,theta} > 0`
(absolute continuity).

**The closed-loop point.** Lemma 1 holds *whatever policy generated `A_{r-1}`*, including a policy
that reacts to `E_{j,t}` itself. Only A1 (predictability) and correct specification of the
conditional law *given the action* are needed. This is why an adaptive, self-referential controller
does not invalidate the test — and it is the reason the plan insists that actions be predictable.

**Lemma 2 (mixture preserves the martingale property).** The fixed-`theta` product is a nonnegative
martingale with unit initial value, i.e. a *test martingale* [S1]. A mixture over `theta` with prior
`W_j` is again a nonnegative martingale with unit initial value, by Fubini given integrability. A
test martingale is a special case of an **e-process**, which is the more general object built from
nonnegative supermartingales [S2].

So `E_{j,t}` is an e-process started at `tau_j`. Mixing (rather than plugging in a point alternative)
is what handles a *composite* alternative without estimating `theta` from the data being tested
[S1, S2].

**Design choice: discrete mixtures.** `W_j` is a discrete prior on a registered grid inside
`Theta_j`, so the integral is a finite sum — exact, auditable, and free of numerical-integration
error. The grid is frozen at Gate 2.

## 5. Activation rule, alpha allocation, and the theorem

Ville's inequality for a nonnegative supermartingale `M` with `M_0 = 1` gives
`P(sup_t M_t >= 1/alpha) <= alpha`.

Index proposals within episode `e` by `j = 1, 2, ...` and allocate

```
alpha_{e,j} = alpha_episode * 2^{-j},      activate proposal j at the first t with E_{j,t} >= 1/alpha_{e,j}.
```

**Theorem 1.** Under the registered global no-change null, with A1–A4,

```
P_0( any false activation in episode e )  <=  SUM_j alpha_{e,j}  <=  alpha_episode * SUM_{j>=1} 2^{-j}  =  alpha_episode.
```

*Proof.* Each `E_{j,·}` is a unit-initial nonnegative martingale (Lemmas 1–2), so Ville bounds its
own crossing probability by `alpha_{e,j}`. A union bound over `j` and `SUM_{j>=1} 2^{-j} = 1` give the
result. ∎

The geometric allocation is why `proposal_index` is 1-based in `collie/contracts.py`; `j = 0` would
break the summation. The primary design permits at most two proposals, so at least
`alpha_episode / 2` is always reserved and never spent.

**Relationship to prior art.** An e-detector sums e-processes started at *every* time and controls
the average run length [S2]. We instead start an e-process only at LLM-selected stopping times, at
most twice per episode, and control per-episode false activation by alpha splitting. That is a
different accounting target (per-episode error, not ARL) reached with the same underlying objects,
and the note records it as such rather than claiming novelty in the statistics.

## 6. The arrival side: exact marginal likelihood by forward recursion

### 6.1 Why a FIFO shortcut is not allowed

Only aggregate `R_t` is observed (contract §4). Many shipment-level histories are consistent with the
same receipt sequence, so *assuming* FIFO would inject an assumption as if it were data. The
controller's imputed FIFO ledger is a control convenience only; the verifier must marginalise.
Enforced by a static grep and a runtime input-graph assertion (`collie/control/ledger.py` symbols are
unreachable from `collie/verify/`).

### 6.2 Finite state

Our own dispatch quantities are known exactly. The only latent quantity is the **lead-time
realization of each outstanding order**. With the registered lead-time law supported on
`{0, ..., L_max} ∪ {inf}`, define the state at `t` as the vector of remaining transit times of the
outstanding cohorts, truncated at `L_max`, with `inf` an absorbing "lost" outcome:

```
s_t  in  ({0,...,L_max} u {lost})^{#outstanding},     |S|  <=  (L_max + 2)^{L_max}
```

For `L_max = 4` this is at most `6^4 = 1296` states — small enough for exact recursion. A transit
pause freezes the remaining-time counters instead of decrementing them, which keeps the state space
unchanged (contract §7 establishes that a pause is *not* expressible as an order-time lead time,
which is exactly why it needs its own transition).

### 6.3 The recursion

Standard hidden-Markov forward variables `alpha_t(s) = P(R_1..R_t, s_t = s | A_1..A_{t-1})`:

```
alpha_t(s)  =  SUM_{s'}  alpha_{t-1}(s') * T(s' -> s ; A_{t-1})  *  1[ emit(s', s) = R_t ]
p(R_t | F_{t-1}, A_{t-1})  =  SUM_s alpha_t(s)  /  SUM_s alpha_{t-1}(s)
```

`T` is the registered lead-time law applied to the newly dispatched order plus deterministic
decrement (or freeze) of existing cohorts; `emit` is the total quantity of cohorts reaching remaining
time zero. Evaluating this under the null law and under the registered alternative gives an **exact**
marginal likelihood ratio, which is the e-process input.

**Lemma 3.** Because both numerator and denominator are exact conditional densities of the *same*
observable `R_t` given `(F_{t-1}, A_{t-1})`, Lemma 1 applies verbatim and the arrival-side product is
again a test martingale. Theorem 1 therefore covers arrival families **whenever the state space is
genuinely finite and the recursion exact**.

Both conditions are verified per family in Task 16 by brute-force agreement on short horizons. If
either fails, the family is empirical-only.

### 6.4 Scope restriction — this is the honest limitation

For official benchmark instances the *probabilities* of the stochastic lead-time law are not
published; the CSVs record realizations only (contract §2.2). A null with unknown parameters is not a
registered null, so **theorem-backed arrival claims are restricted to COLLIE-ShockSpec episodes**,
where our generator defines the law by construction and registers it. On official instances the
arrival-side procedure is reported as an empirical stress test.

This restriction must appear in every table caption that reports an arrival-side activation rate.

## 7. Compound shocks: alpha splitting, never a product of marginals

The generator records a per-family conditional-independence flag (branch B, Task 7; surfaced as
`HiddenIncident.conditional_independence`). It is `True` for families 1–5 and **`False` for the
compound family**, where one incident drives both streams.

- If the environment contract makes conditional independence explicit for a construction, a
  registered **joint** conditional likelihood `p(Y_t, R_t | F_{t-1}, A_{t-1})` may be used.
- Otherwise, run **two separate e-processes** with an explicit prior split of the proposal's budget,
  e.g. `alpha_{e,j}/2` each. Theorem 1 then applies with the finer partition, since the union bound
  is indifferent to how the budget is subdivided in advance.

Multiplying marginal ratios when independence is not part of the contract is **prohibited**: the
product of two marginal ratios is not the ratio of joint densities under dependence, and its
conditional mean need not be 1, so Lemma 1 fails and the bound is void. Task 16 asserts that the
joint code path is unreachable when the flag is `False`.

## 8. Nuisance parameters, refutation, expiry, and the plug-in variant

**Nuisance parameters.** Where the contract exposes dispersion or seasonal structure, it is plugged
in as known and frozen on dev/cal. Where it does not, it enters `Theta_j` and is integrated out by
`W_j`, which is the composite-alternative route [S1].

**The plug-in variant is not covered.** Re-estimating `p_0` from the same online stream that is being
tested breaks Lemma 1: the "null" becomes data-dependent and the ratio no longer has unit conditional
mean. It is implemented because it is what a practitioner would do, reported separately, and labelled
as carrying **no finite-sample guarantee**.

**Refutation and expiry are empirical.** Theorem 1 bounds *activation* under the null. It says
nothing about retiring an active hypothesis. Both rules are separately registered and evaluated
empirically. If a theorem-backed retirement is wanted later, the route is the forward/backward
confidence-sequence intersection test of [S3], which yields nonasymptotic false-alarm and delay
guarantees; adopting it would require registering a coverage result and is out of scope for the
five-week plan.

**The unavoidable tension.** Waiting for post-commitment evidence makes the statistically clean
method operationally late. Proposal-to-activation delay is therefore a **primary reported outcome**,
and pilot criterion 5 is precisely the test of whether the delay fits inside the economically useful
response window.

## 9. Family-by-family validity table

Authoritative. Task 16 asserts code agreement with this table; any disagreement is a test failure.

| # | Family | Stream | Observation model | Construction | Status |
|---|---|---|---|---|---|
| 1 | `demand_level` (up) | demand | uncensored | mixture LR, one-sided mean shift | **anytime-valid** |
| 2 | `demand_level` (down) | demand | uncensored | mixture LR, one-sided mean shift | **anytime-valid** |
| 3 | `temporary_pulse` | demand | uncensored | mixture LR, bounded-duration shift | **anytime-valid** (low power by construction; a 2–4 period pulse may end before activation) |
| 4 | `lead_time_shift` | arrival | uncensored | forward recursion, §6 | **anytime-valid on COLLIE-ShockSpec only** (§6.4) |
| 5 | `shipment_loss` | arrival | uncensored | forward recursion with absorbing `lost` | **anytime-valid on COLLIE-ShockSpec only** (§6.4) |
| 6 | `transit_pause` | arrival | uncensored | forward recursion with frozen counters | **anytime-valid on COLLIE-ShockSpec only** (§6.4); alternative transition is project-defined |
| 7 | `compound` | both | uncensored | two e-processes, alpha split (§7) | **anytime-valid** via splitting; joint path forbidden (flag is `False`) |
| 8 | any | either | **censored sales** | requires `p_0` for sales given availability and action | **empirical-only pending establishment in Task 15.8**; no formal claim until derived and validated |
| 9 | any | either | any | **plug-in** null estimated online | **empirical-only, permanently** (§8) |

## 10. What Tasks 15–17 must implement

1. `alpha.py` — `alpha_{e,j} = alpha_episode * 2^{-j}`; assert `SUM_j 2^{-j} <= 1` over the permitted
   proposal count; refuse `j < 1`.
2. `eprocess.py` — discrete-mixture LR starting strictly at `tau_j + 1`; boundary assertion; frozen
   densities/mixtures/nuisance procedures; separate plug-in path flagged as unguaranteed.
3. `supply_forward.py` — the §6.3 recursion; brute-force agreement on short horizons; per-family
   validity flags asserted against §9; no ledger access.
4. `lifecycle.py` — activation from the e-process only; registered refutation and expiry marked
   empirical; alpha split on supersession; ≤2 proposals; provisional arm blocked in confirmatory runs.
5. Calibration harness — 2,000 Monte-Carlo replications per registered null; empirical false
   activation `<= alpha`; power sanity under a true shift of registered magnitude.

## 11. Sources

- **[S1]** Ramdas, A. et al. *Game-theoretic statistics and safe anytime-valid inference.*
  arXiv:2210.01948 (v2, June 2023). Establishes e-processes and confidence sequences valid at all
  stopping times, built on **test martingales** — nonnegative martingales starting at one — with the
  betting/game-theoretic reading, and covers composite-hypothesis testing.
- **[S2]** Shin, J., Ramdas, A., Rinaldo, A. *E-detectors: a nonparametric framework for sequential
  change detection.* arXiv:2203.03532 (v4, October 2023). Introduces **e-detectors** as sums of
  e-processes started at consecutive times; describes e-processes as a generalization of nonnegative
  supermartingales; gives Shiryaev-Roberts and CUSUM-style constructions, mixture designs, and
  nonasymptotic average-run-length and detection-delay bounds.
- **[S3]** Shekhar, S., Ramdas, A. *Sequential Changepoint Detection via Backward Confidence
  Sequences.* ICML 2023, PMLR 202:30908–30930. Reduces sequential changepoint detection to sequential
  estimation by testing whether a forward and a backward confidence sequence ever fail to intersect,
  with nonasymptotic false-alarm and detection-delay guarantees. The route to a theorem-backed
  retirement rule, should we later want one (§8).
- **[C]** `docs/env_contract.md` — the audited environment contract (Task 2): event ordering,
  observability, lost-order semantics, horizons, and the absence of an upstream order cap.

Content of [S1]–[S3] is paraphrased from the published abstracts; no more than a short phrase is
quoted from any source.
