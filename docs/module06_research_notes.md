# Module 06 research notes

Wave 0 output (§2 of the module brief). Everything below was established by direct inspection of
the pinned benchmark (`third_party/InventoryBench`, commit `62b1f116`), the pinned packages in
`uv.lock`, or cited public sources retrieved 2026-09-06. Findings are recorded as found; choices
the module had to make are marked **[registered]**.

## 1. The benchmark's own LLM prompt

Reconstructed from the pinned submodule (commit `62b1f116`). The benchmark ships **four**
strategies with distinct scripts (`scripts/benchmark_all_strategies.py:45-50`): `or` (arm 1's
origin), `llm` (`run_llm.py`, LLM-only direct action), `or_to_llm` (`run_or_to_llm.py`, OR
recommendation + LLM direct action), and `llm_to_or` (`run_llm_to_or.py`, LLM sets OR parameters).
All three LLM strategies have published leaderboard numbers (`docs/leaderboard_data.json`; best
`llm` = 0.4945 gemini-3-flash, best `or_to_llm` = 0.538, best `llm_to_or` = 0.5009).

**Which prompt arms 3/4 reproduce [registered]: the `llm` strategy (`run_llm.py`).** The ladder's
objection for arm 3 is "just let the LLM order" and the module brief's table says "every-period LLM
direct action"; in upstream vocabulary that is the `llm` strategy — LLM-only, no OR input. R3.1's
phrase "OR-to-LLM direct-action agent" names the *other* script; the brief outranks the spec
(precedence §1.5) and the objection is only answered faithfully without OR input. The `or_to_llm`
reconstruction is kept in this section regardless, and the choice is flagged for the Checkpoint 1
auditor; confining it to one builder function makes a swap cheap. Arms 5-7's reference is
`llm_to_or`, reconstructed separately below (§1.4).

### 1.1 Prompt assembly pipeline (`llm` strategy)

Four stages: env board (`or_agent/envs/VendingMachine/env.py:217-266`, `get_observation`) →
wrapper framing (`or_agent/envs/VendingMachine/wrapper.py:90-129`, `=== CURRENT STATUS ===` +
`=== GAME HISTORY ===`) → runner-side date injection and term normalisation
(`scripts/run_llm.py:818-852`) → agent call with `messages = [system, user]`
(`run_llm.py:169-172`). No PROMPT-type observation exists, and no news sections appear (neither
script calls `add_news`). Full multi-period history: every past period's `conclude:` block is
included every period; the model's own past rationales are NOT rendered.

### 1.2 System prompt, verbatim

Built by `make_vm_agent` (`run_llm.py:500-687`). Substitutions: `{primary_item}` = first item id
(e.g. `chips(Regular)`; real instances use numeric strings like `"108775044"`), `{promised_lead_time}`
= CLI int, `{example_action}` = `'"item_a": 100, "item_b": 100'`-style from the actual ids,
`{items_str}` = quoted comma-joined ids. Sections in order: `ROLE & OBJECTIVE`, `TIMELINE & DATA`,
`GAME MECHANISM: PERIOD EXECUTION SEQUENCE`, `LEAD TIME DEFINITION`, `CRITICAL TIMING EXAMPLE`,
`KEY IMPLICATIONS`, `INVENTORY & ORDERS`, `DEMAND REASONING`, `LEAD-TIME INFERENCE`, then
`HISTORICAL DEMAND DATA` (train samples rendered `  {item_id}:\n    {date}: {demand}`, ints via
`pandas.Series.tolist()`), then `DECISION CHECKLIST`, `CARRY-OVER INSIGHTS` (the cross-period
memory mechanism; the runner prepends recorded insights to later observations), and `OUTPUT FORMAT`
requiring JSON `{"rationale": ..., "carry_over_insight": ..., "action": {"<item_id>": qty}}`. The
full verbatim text, with every byte-level hazard, is what `collie/arms/prompts.py` reproduces; the
hazards that matter (all verified at source):

1. **Float rendering**: `Profit=${profit}/unit` uses Python `str(float)` — CSV `19` renders
   `$19.0`, `1` renders `$1.0`. Shortest-repr float formatting is load-bearing.
2. **Doubled item header**: synthetic instances have no `description_*` column, so `desc` defaults
   to the item id, producing `chips(Regular) (chips(Regular)): Profit=$4.0/unit, ...`.
3. **Literal-concatenation seams**: a double space inside the `rationale` template
   (`run_llm.py:678-679`) and literal `\"\"` sequences (`run_llm.py:680`) — easy to "fix"
   accidentally; they stay.
4. **Non-ASCII**: `× − — • ≠ ≥` must survive end-to-end (`_sanitize_text` NFKC-normalisation is
   applied only to stdout printing, never to prompts).
5. **Whitespace**: `"\n\n"` joins with embedded leading `"\n"` (two blank lines before
   `=== GAME HISTORY ===`), 2-space indents, 70-`=` fences on the carry-over block (the docstring
   says 40; the code says 70 — code wins), no trailing newline on the system prompt.
6. **Denominator trap**: `PERIOD N (Date: ...) / T` uses the full CSV row count as `T`.
7. **Lost orders stay in `In-transit` forever** in the env's rendering (`arrival_day=inf` counted
   at `env.py:250-254`) — the env.py semantics (env contract §5); the model is never told actual
   lead times, only the promised one in the system prompt.
8. Date formats pass through verbatim: real test CSVs use `2019/2/11`, real train CSVs
   `2019-01-07`, synthetic the literal `Period_1` — prompts legitimately mix formats.

### 1.3 Response format and parsing

Expected: JSON only, keys `rationale`, `carry_over_insight`, `action: {item_id: int}`.
Env-side parse (`env.py:521-627`, `_parse_json_action`) tries four strategies in order:
fence-stripped first balanced `{...}` block; naive `find/rfind` slice; regex
`"action"\s*:\s*\{([^}]+)\}`; last-resort `"(\d+)"\s*:\s*(\d+)` anywhere. Values coerced with
`int(qty)` (truncates floats); negative quantities and unknown item ids are invalid moves; **no
maximum clamping** exists upstream (ours is the registered cap — different object, env contract
§2.3). The agent retries parse failures up to 3 attempts and returns the raw text anyway on final
failure (`run_llm.py:119-230`); upstream sets **no temperature, seed, or max_tokens** — only
`reasoning_effort="low"` — so byte-exact outputs are not reproducible upstream; only the prompt is.
Decoding determinism is therefore *our* addition, registered in §4.

### 1.4 The `or_to_llm` delta and the `llm_to_or` reference

`or_to_llm` is a different prompt, not a superset: reworded role line, `TIMELINE & DATA` folded
into `ENVIRONMENT SNAPSHOT`, added `OR BASELINE (CAPPED): MATHEMATICAL DETAILS` (the arm-1 math,
quoted to the model), `COLLABORATION STRATEGY`, `RATIONALE GUIDELINES` (adds
`short_rationale_for_human` between `rationale` and `carry_over_insight`), and a per-period user
suffix `OR ALGORITHM RECOMMENDATIONS (capped policy):` (70-`=` fences) carrying the OR quantity as
a Python int (`run_or_to_llm.py:1162-1171`). Its OR recommendation is arm 1's own math recomputed
from the observation text. `llm_to_or` is reconstructed in §1.5.

### 1.5 `llm_to_or` (arms 5-7 reference)

Reconstructed from `scripts/run_llm_to_or.py` (1804 lines; rendering verified by executing
`make_llm_to_or_agent` under our venv). The **user message is byte-identical to `llm`'s** (same
env, wrapper, date injection, carry-over; no OR-recommendation suffix). What changes is the system
prompt, the response schema, and a backend that converts parameters to an order and submits
`{"action": orders}` itself — the model's raw text never reaches the env.

- **System prompt**: same skeleton through `LEAD-TIME INFERENCE`, then `DEMAND & LEAD-TIME
  ANALYSIS`, then a `PARAMETER MENU`: the model outputs `L`, `mu_hat`, `sigma_hat`, each as
  `{"method": ...}` with methods `default` / `calculate` (L only) / `recent_N` (+ integer `N`) /
  `EWMA_gamma` (mu_hat only, + `gamma in [0,1]`) / `explicit` (+ `value`). Output JSON:
  `{"rationale", "carry_over_insight", "parameters": {"<item_id>": {"L": ..., "mu_hat": ...,
  "sigma_hat": ...}}}`.
- **Backend computation** (`compute_L/mu_hat/sigma_hat`, capped base stock identical to arm 1's
  math, `cap = mu_hat/(1+L) + Phi^-1(0.95)*sigma_hat/sqrt(1+L)`, order floor 0, ceiling ceil(cap)).
  Samples = train demands + every observed demand. Inventory is regex-parsed back out of the
  observation text — the env's text format is load-bearing upstream, which is exactly the fragility
  our typed interface exists to remove.
- **Cadence: every period, unconditionally, no persistence** — parameters are recomputed from
  scratch each period. That is arm 5's reference behaviour; arms 6 (sparse, triggered) and 7
  (persistent with fixed expiry) are our controlled variations on it.
- **Hazards**: a rendered example in the prompt contains a literal `}}` (plain-string bug,
  `run_llm_to_or.py:1297`) — invalid JSON shown to the model, reproduced literally; upstream typo
  `each total periods` kept verbatim; this system prompt **ends with a trailing newline** (the
  other two do not); `explicit` values are used **raw** with no `(1+L)` multiplication despite the
  menu prose saying otherwise (the code is authoritative); the upstream runner re-parses the whole
  accumulated observation each period and blindly re-appends lead times (a real upstream bug,
  noted, not reproduced); and a *valid* JSON with out-of-range values (`gamma=1.5`, `N=0`) kills
  the entire run via `sys.exit(1)`.
- **[registered] deviation from upstream failure semantics**: our arms 5-7 keep the prompt, menu,
  and computation semantics but route invalid/unusable output through the counted repair/fallback
  path (ledger `ParseOutcome.FALLBACK`, unchanged OR parameters) instead of `sys.exit(1)`. A
  benchmark harness that aborts the sweep on a parseable-but-out-of-range response cannot serve a
  640-rollout study; the fallback is counted, which upstream's crash never could be. Declared at
  both checkpoints.
- **[registered] arm 7's fixed expiry** is 5 periods including the call period
  (`PERSISTENCE_EXPIRY` in `collie/arms/llm_to_or.py`), set equal to the frozen refractory window
  (`collie/trigger/calibration.py`): a persisted parameter set covers exactly the silence the
  trigger imposes, so arm 7 measures persistence itself, not a longer invocation budget. The
  brief and spec name a "fixed expiry" without a value; this is the registration.
- **[registered] the ledger's weak-gate dichotomy for arms 5-7.** Upstream's retry gate looks for
  braces or menu keywords, and its regex salvage can only recover parameter content when those
  keywords exist — so a gate-failing response yields exactly the default parameters and the model
  contributed nothing. The final attempt therefore settles `FALLBACK` whenever the gate never
  passed, and the order that period uses upstream's own default-substitution path. The counted
  `FALLBACK` also covers validation failure (defaults substituted, as upstream does silently) and
  the compute crash (`sys.exit(1)` upstream).

## 2. Page-Hinkley and CUSUM — formulations and calibration

**CUSUM (tabular/algorithmic form; NIST/SEMATECH e-Handbook §6.3.2.3.1,
<https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc3231.htm>):**

```
C+_t = max(0, C+_{t-1} + (x_t - mu0) - K)      # detects increases
C-_t = max(0, C-_{t-1} - (x_t - mu0) - K)      # detects decreases
alarm if C+_t > H or C-_t > H
```

with reference value `K = k * sigma` and decision interval `H = h * sigma`. The standard rule
`k = half the standardized shift size to detect quickly` (NIST; Montgomery ch. 15). Null ARL by
Siegmund's approximation: `ARL = (exp(-2*Delta*b) + 2*Delta*b - 1) / (2*Delta^2)` with
`Delta = -k` under the null, `b = h + 1.166` — reproduces the NIST table (k=0.5, h=4 gives
one-sided ARL0 ~= 337; two-sided roughly halves it, an approximation, folk-SPC).

**Page-Hinkley:** running-mean form `U_t = U_{t-1} + (x_t - xbar_t - delta)`,
`PH_t = U_t - min U`, alarm at `PH_t > lambda` (River docs; Ikonomovska thesis §6.6.2). With the
null mean **frozen** from calibration data (our setup), PH reduces to CUSUM-with-min — the two
coincide structurally, which the implementation exploits: one core, two parameterisations. No
closed-form ARL exists for PH (no citable formula found); calibration is empirical.

**Calibration [registered]:** thresholds are set by Monte Carlo on dev/cal *null* episodes only —
simulate stationary episodes at the dev-fitted `(mu0, sigma0)`, record each episode's max
statistic, and set the threshold at a high quantile of that null-max distribution, chosen so the
per-episode false-fire probability fits the <=2-proposal budget with margin. Frozen at Gate 2;
test data never touches the procedure. Dev anchor: `mu0 = 100`, `sigma0 = 25` (the registered
stationary-IID baseline law, `collie/data/families/base.py`); `k = 0.5` (K = 12.5 units) as the
robust default — the tuned value for the smallest registered downshift (0.6x = 1.6 sigma) would
be k = 0.8, costing speed on large shifts; h chosen by the Monte Carlo, not from the NIST table,
because our null mix (pulses, seasonality, overdispersion) violates its iid-normal assumptions.
Detectors are stateless about suppression: no firing counters inside a detector; reset-after-signal
is owned by the wrapper layer (standard SPC restart convention).

## 3. Two-regime detection for arm 2 **[registered]**

Decision: a **hand-rolled 2-state Gaussian HMM forward filter** (Rabiner alpha-pass, ~30 numpy
lines), not hmmlearn, not BOCPD.

```
z_t in {0 normal, 1 disrupted};  A = [[a00, a01], [a10, a11]]  (sticky)
emission phi_j(x) = Normal(x; mu_j, sigma_j)   # frozen from dev calibration
predict:  alpha~_j = sum_i alpha_{t-1}[i] * A[i, j]
update:   alpha_t[j] = alpha~_j * phi_j(x_t);  normalise
output:   p_disrupted = alpha_t[1]
```

- hmmlearn's strength is batch EM fitting; we need only filtering with frozen parameters, and it
  would add a compiled dependency to a deliberately tight pin set. High cost, zero capability gain.
- BOCPD (Adams & MacKay, arXiv:0710.3742) outputs a run-length posterior, not a regime
  probability — the mapping to "disrupted" is an extra calibration surface, and its main advantage
  (unknown post-change parameters) is moot because we calibrate regime emissions on dev data.
- The sticky transition matrix gives hysteresis for free; `p_disrupted` feeds the controller as a
  graded adjustment rather than a hard switch. Transition values are tuned on dev only, then frozen
  (starting point a00 = 0.98 / a11 = 0.90 — unsourced heuristic, flagged as such).

## 4. Serving and transport **[registered]**

**Update 2026-09-07 — confirmation provider split.** The Checkpoint-1 audit ruled the original
two-paths-one-provider arrangement circular (confirming Gemini with Gemini demonstrates nothing)
and the operator named **xAI Grok** as the second provider, with **Z.ai GLM** added as a third
provider for later benchmarking. What follows below is the 2026-09-06 Gemini record, still
accurate for the primary path; the new providers' live findings:

- **xAI Grok** (`https://api.x.ai/v1`). The published baseline's `x-ai/grok-4.1-fast` is an
  OpenRouter id retired on the direct API; the live catalog (12 models, `GET /models`) offers the
  pinned dated snapshot `grok-4.20-0309-non-reasoning` (1M context, docs.x.ai model page), which
  becomes the confirmation default — a pinned snapshot cannot drift mid-sweep, and the
  non-reasoning variant keeps token accounting clean. **`seed` is honoured**: accepted without
  error and an identical seeded repeat returned byte-identical content. Usage algebra differs
  from Gemini: `total_tokens = prompt + completion + reasoning` with reasoning *disjoint* from
  `completion_tokens` (observed on `grok-4.6`: 643 + 1 + 164 = 808), so the billable-output rule
  `total − prompt` covers reasoning exactly. A server-side `cost_in_usd_ticks` field (1 tick =
  1e-10 USD) matched the dated list prices to the micro-dollar on a probe call (63 uncached ×
  $1.25 + 128 cached × $0.20 + 1 out × $2.50 per 1M = $106.85e-6 = 1,068,500 ticks). One hazard:
  xAI applies server-side prompt moderation that 403s (`SAFETY_CHECK_TYPE_BIO`) on at least one
  innocuous JSON-shaped control prompt; a 403 surfaces as `openai.PermissionDeniedError`, not a
  parse failure, so transport error handling must not treat it as a retryable parse problem.
- **Z.ai GLM** (`https://api.z.ai/api/coding/paas/v4`, the OpenAI chat-completions variant of the
  three offered endpoints — chosen so one client shape serves all providers; the Anthropic
  Messages and OpenAI Responses variants would each need a second transport). Three live
  findings, each load-bearing: (a) the coding plan **serves `glm-5.3-flash` regardless of the
  requested model id** (requesting `glm-4.5` or `glm-4.6` echoes `glm-5.3-flash` in the response)
  — treat the model id as a label and record the echo; (b) **`seed` is accepted but not
  honoured** (identical seeded repeats returned `472819` then `427619`), so
  `supports_seed=False`; (c) requests must carry `thinking={"type": "disabled"}` (sent via the
  client's `extra_body`) or reasoning tokens consume the completion budget and content returns
  empty. Usage algebra: `total = prompt + completion` with reasoning *inside* `completion_tokens`
  (19 + 8 = 27, reasoning 4 ⊂ 8), so billable output is `completion_tokens` — the opposite flag
  value from Grok, which is exactly why the flag exists.

**Operator decision (2026-09-06): cloud-only.** No local vLLM endpoint. The primary sweep path is
**Google Gemini via the OpenAI-compatible endpoint**
(`https://generativelanguage.googleapis.com/v1beta/openai/`); the hosted confirmation path was
initially the same provider and is now xAI Grok (see the update above). One client shape serves
all providers. The brief's "local primary" language is superseded; this is declared as a
checkpoint deviation and logged in `prereg/deviations.md`. Credentials live in `cloud_endpoint/`:
key files `gemini.key` / `grok.key` / `zai.key` (operator-supplied, file mode 600, gitignored)
and `models.json` (the model registry, committed — the Checkpoint-1 audit note that a gitignored
registry is not reproducible from a clean clone). The client raises on a missing key and never
substitutes another provider or model. Gemini registry detail, live-verified against
`v1beta/models` on 2026-09-06: `gemini-3.8-flash` exists with 1,048,576 input / 65,536 output
token limits, and is the registered default per operator instruction; 18 chat-capable models
recorded.

**Determinism — empirically verified 2026-09-06 against the live endpoint.** `temperature=0`
returns stable text (two identical calls, byte-identical JSON reply — one observation, not a
guarantee), and `usage` arrives with the standard `prompt_tokens` / `completion_tokens` /
`total_tokens` fields. **The Gemini OpenAI-compatible endpoint REJECTS the OpenAI `seed`
parameter** (`400 INVALID_ARGUMENT: Unknown name "seed"`), contradicting the operator's prior
belief that both endpoints accept it; this was caught only because the check was run live. Gemini's
native API has no seed knob at all, so this is a property of the provider, not the compatibility
shim. Consequences, both registered here:

- The sweep decoding configuration is `temperature=0` with a recorded `decoding_hash`; the disk
  cache, not re-issue, is the reproducibility mechanism (vLLM's docs make the same point for the
  local stack: online serving cannot be made deterministic under continuous batching — cache stored
  bytes, never trust a re-issued seeded request).
- The three-seed robustness mode is implemented against endpoints that honour `seed` and **raises
  a clear error when the configured endpoint does not** — the endpoint config carries an explicit
  `supports_seed` flag, and the Gemini path sets it False. The robustness subset therefore cannot
  run on Gemini as the provider stands; that is surfaced to the operator rather than silently
  degraded to temperature jitter. It still refuses the confirmatory set, unchanged.

**openai client (pinned 1.109.1 in uv.lock).** `client.chat.completions.create(model=..., seed=...)`
— `seed` sent only when the endpoint config allows it; `response.usage` carries required ints
`prompt_tokens`, `completion_tokens`, `total_tokens` and is itself `Optional` (None possible —
guard). `base_url` selects the endpoint; default timeout 600 s, `max_retries=2` with exponential
backoff on 408/409/429/5xx. The OpenAI schema exposes no server-side timing (`created` is 1-second
granularity), so latency is measured client-side with `time.perf_counter()` bracketing the call —
the ledger labels it as such (connect + queue + generation + transfer).

**Usage-field subtlety, verified live:** `total_tokens` includes thinking tokens that
`completion_tokens` does not (observed: prompt 16, completion 5, total 96 — 75 thinking tokens).
Google bills thinking as output ("Output price (including thinking tokens)", §5), so the dated
cost rule for Gemini models is `input_price * prompt_tokens + output_price *
(total_tokens - prompt_tokens)`, with all three raw fields recorded so the rule can be re-derived.

## 5. Dated cost accounting **[registered]**

Cost basis: **dated list prices** for the model used, recorded with a retrieval date and source.

| Model | Input $/1M | Output $/1M | Source, retrieved |
|---|---|---|---|
| gemini-3.8-flash (primary default) | 0.75 | 3.75 (incl. thinking) | ai.google.dev/gemini-api/docs/pricing, 2026-09-06; through 2026-12-31, then 1.50 / 7.50 from 2027-01-01 |
| grok-4.20-0309-non-reasoning (confirmation default) | 1.25 | 2.50 | docs.x.ai model page, 2026-09-07 |
| glm-5.3-flash (Z.ai, benchmarking) | 0.15 | 0.50 | docs.z.ai pricing, 2026-09-07; list prices — a 50% promo (0.075 / 0.25) expires 2026-09-09 24:00 UTC+8 and the ledger prices at list so post-promo runs stay correct |

Provider-specific caveats, all live-verified:

- **Gemini**: the operator's key may be on the free tier, where list cost is zero — the ledger
  prices every call at the dated **list** price regardless of tier, so the ledger answers "what
  would this cost at list" and says so. No GPU-hours accrue because there is no local serving
  (operator decision, §4). OpenRouter list prices for the same models (retrieved 2026-09-06 from
  <https://openrouter.ai/api/v1/models>) match the shape of Google's list, corroborating the
  extraction.
- **xAI**: the usage response carries a server-side `cost_in_usd_ticks` (1 tick = 1e-10 USD) that
  matched the dated list prices to the micro-dollar on a probe call, including the cached-input
  discount ($0.20/1M). The ledger does not model the cached-input discount — it prices all input
  at list, a slight over-count, deliberately uniform across providers.
- **Z.ai**: the coding plan is a flat subscription, so no per-token bill accrues; the ledger
  prices calls at the paas **list** prices above as a shadow price, so cross-provider cost
  comparisons stay apples-to-apples. Reasoning tokens sit inside `completion_tokens` (§4), so the
  billable-output rule for this provider is `completion_tokens`.

## 6. Hypothesis, including the stateful layer

hypothesis 6.167.1 (dev pin `>=6.167.1,<7`). Confirmed current API surface: `@given`, `@settings`
(`max_examples`, `deadline`, `suppress_health_check`), `st.composite`, `assume`, `@example`, and
`hypothesis.stateful.RuleBasedStateMachine` with `@rule`, `@initialize`, `@invariant`,
`run_state_machine_as_test` — all present and non-deprecated in the pinned install (the only
deprecation in `stateful.py` is `consumes(bundle)` as a rule *target*, unused here). The
cache/ledger invariants (`physical <= sum(charged)`, warm-replay equality) are genuinely stateful
and get a `RuleBasedStateMachine` in `tests/test_cache_ledger.py`. House rules from Module 01
still bind: `--strict-markers` (no new marker needed for property tests; `needs_llm` already
registered for live-endpoint tests), `error::DeprecationWarning`, `@example` pins every
counterexample, file-writing generators get `deadline=None`.

## 7. InvEvolve

arXiv:2605.00369, "InvEvolve: Evolving White-Box Inventory Policies via Large Language Models with
Performance Guarantees" (v1 2026-05-01, v4 2026-06-05; arXiv-only). **No official code artifact
exists** as of 2026-09-06: zero GitHub repositories name it, and the paper text contains no code
availability statement (the only repository link is to a third-party RL framework it used).
Deferred this sprint per the cut line; when implemented it must be labelled a faithful
reimplementation and never presented as the authors' result.
