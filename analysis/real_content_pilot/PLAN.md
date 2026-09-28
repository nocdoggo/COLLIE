# Real-content pilot: plan

Exploratory. Committed and pushed before any live model call. Not a Gate 3 vote: the stored
scripted pilot (`reports/pilot_report.md`) remains the Gate 3 record, and nothing here writes to
`reports/` or `prereg/`. The team may want to log this pilot in `prereg/deviations.md`.

## Why

The registered pilot's LLM arms (8, 9, 10) never saw a model: the scripted transport returns one
fixed `demand_level / demand_up / medium` payload, and the alert channel is a demo stand-in. The
forensics (`analysis/kill_trigger_forensics.md`) could therefore not say whether real content
changes what arms 8-10 do. This pilot replays the same episodes with live answers and module 03's
alert bank, holding everything else fixed.

## What runs

- **Episodes.** The registered 120 (`tools.run_arms.pilot_instances`, frozen), dev/cal only:
  96 shocked (6 generator families x 4 seeds (2 dev, 2 cal) x 4 information conditions) and 24
  unshocked null twins (12 `no_alert`, 12 `unreliable`). Each run checks its truth is
  byte-identical to `reports/pilot_truth.jsonl`. The runner refuses any non-dev/cal instance, and
  `collie/data/alerts/templates/test.yaml` is never opened.
- **Arms (9).** `arm1_capped_base_stock`, `arm2_telemetry_hmm_or`, `arm8_spec_immediate`,
  `arm9_spec_heuristic_rollback`, `arm10_spec_eprocess`, `ctrl_cusum_to_compiler`,
  `ctrl_keyword_parser`, `ctrl_alertspec_upper_bound`, `oracle_shockspec_headroom`, built exactly
  as `tools/run_arms.py::run_ladder` builds them. Pre-flight: with the scripted transport and demo
  alerts the runner reproduces all 1,032 registered records of these arms (ignoring only
  `analysis_class`, `call_id`, `latency_ms`). Not run: arm 7 (cost not approved) and arms 3, 4,
  5, 6, 11 (outside the question).
- **Model calls.** Only arms 8, 9, 10 call the model. They share the trigger
  (`alert_or_detector`, refractory 5, at most 2 proposals per episode), so their first call in an
  episode is one identical prompt, served once through the cache. Module 02 prompt, decoding
  `det-v1` (temperature 0, no seed), no system prompt, at most one repair attempt per proposal.
- **Endpoints (one run each).** `gemini-3.8-flash` (`gemini_primary`, $0.75 / $3.75 per Mtok,
  thinking billed as output) and `grok-4.20-0309-non-reasoning` (`grok_hosted_confirmation`,
  $1.25 / $2.50 per Mtok). Keys are resolved at runtime by the project code. Z.ai is not run.
- **References.** `scripted-bank`: the scripted transport with the same bank alerts, committed
  with this plan. `registered`: the stored scripted pilot (demo alerts), nine arms.

## Rules fixed here

None of these is registered elsewhere, so they are fixed now, before any live answer is seen.

1. **Alert selection, rule `bank-v1`** (`alerts.py`). For manifest slot `tpl_{split}_f{family}_{i}`
   and `p = 2i + (0 dev, 1 cal)`: accurate template = the `i % 4`-th accurate template of that
   split and family (sorted by id); unreliable kind cycles overstated, ambiguous, distractor by
   `p % 3`, and takes the `i % 2`-th template of that kind.
2. **Timing** is module 03's own schedule (`render_condition_batch`): early-accurate and
   unreliable at onset - 1, late-accurate at onset + 2, none for no-alert. The unreliable offset
   (-1) comes from `default_audit_config()`, whose status is `pending_team_confirmation`.
3. **Family 2 (demand level down) gets no alert in any condition.** The dev/cal bank has no
   demand-down template, and module 03 refuses to pair a demand-up one with a demand-down unit.
   Recorded per episode as `none:bank_gap_demand_down`.
4. **Nulls.** Silent nulls (`no_alert`) get nothing. False-alert nulls (`unreliable`) get one
   accurate-kind demand-level message at period 10 (the demo's null period), the
   `(2 + i) % 4`-th accurate template, which no shocked unit uses.
5. **Rule U-v1 (arm 10 only).** Module 02's frozen schema accepts a shock proposal with
   `persistence` or `duration_bin` of `none`; module 05's `maximum_lifetime` raises on exactly
   those, and `LifecycleManager.propose` refuses `tau_j >= horizon`. The frozen stack then aborts
   the whole run. Under Rule U, arm 10 receives module 02's canonical abstention instead (its
   prompt's own `no_change` spelling, parsed by its own validator); the call settles `accepted`;
   the proposal row keeps the model's payload with `arm10_coerced_abstention` and
   `rule_u_reason`. Arms 8 and 9 receive the payload unchanged. Every other module-02-legal shape
   registers and verifies in module 05 (tested: 756 shapes x 3 proposal periods). Rejected:
   swallowing the error (it breaks proposal numbering and compiles an unregistered spec), a parse
   fallback (it inflates parser failures and adds repair calls), editing module 05 (a team
   decision), aborting (teaches nothing). This is an interface finding for modules 02 and 05.
6. **Transport guard** (`transport.py`). HTTP 408/409/429/5xx, timeouts and connection errors
   are retried with exponential backoff (5 s doubling, capped at 120 s, `Retry-After` honoured,
   8 attempts). HTTP 403 (for example xAI moderation) becomes an empty answer: cached, logged as
   a refusal, and settled by the arm as a parse fallback. Any other error aborts the run; paid
   answers stay cached, so a rerun resumes for free. Request timeout 180 s, SDK retries off.
7. **Caps.** $3.00 per endpoint run, cumulative across invocations of the run (`spend_log.jsonl`),
   and at most 1,000 physical calls. A capped run is reported as incomplete, not analysed as
   complete, and the user decides whether to raise the cap.
8. **Smoke first.** Each endpoint first runs three episodes under the same run name, so the
   cache and spend log carry over: `dev/f1/s1050000/early_accurate`,
   `cal/f6/s6060000/unreliable`, `dev/f1/s1050000/unreliable__twin`. If the projected full-run
   cost exceeds $3.00 for an endpoint, or answers fail systematically (every call refused or
   unparseable), stop and ask the user before the full run.
9. **Changes after this commit** are logged under Deviations below, with the reason, before the
   run they affect.

## Analyses (`evaluate.py`, committed with this plan)

- **Readout.** The frozen evaluator on each run's records, exactly as
  `tests/test_pilot.py::_stored_pilot_decision` recomputes the registered verdict, with
  `method_freeze_or_quarantine_violation` from `tools.freeze.drift()`. It says what the registered
  machinery would say; it decides nothing. `cost_frontier` covers nine arms, not fifteen.
  `insufficient_headroom` must stay 2 (the oracle and arm 1 never see the model or the alerts).
- **Integrity.** The six arms that never call the model must replay `scripted-bank` exactly.
- **Q1. First-proposal accuracy.** Arm 8's first proposal event (the call arms 8-10 share),
  final attempt, against the hidden truth: `family_ok` (family and direction), `onset_ok` (true
  onset minus the proposal period inside the window), `magnitude_ok`, `persistence_ok`,
  `duration_ok`, and `full_ok` (= `collie.eval.truth._matches_truth`). On shocked episodes a
  missing call, a parse failure or an abstention counts as not correct. By condition, by family,
  family x condition (n = 4 per cell), timing relative to onset, and the confusion table.
- **Q2. Early-accurate versus unreliable,** paired within seed on the 20 seeds with bank alerts
  (family 2 excluded): per-seed differences in `family_ok` and `full_ok` with discordant counts,
  by unreliable kind, and the early-minus-unreliable difference in arm8-arm1 and arm10-arm1.
- **Q3. Verification and rollback by proposal class.** Each registered proposal (for arm 10,
  after Rule U) is right-family, wrong-family, or on a null. Arm 10: activated before the next
  registered proposal, median activation delay, refuted. Arm 9: refuted.
- **Q4. Outcome contrasts.** arm10-arm8, arm10-ctrl, arm10-arm1, arm8-arm1, arm10-keyword,
  keyword-ctrl, ub-ctrl, arm2-arm1, on gross (`total_profit`, the registered endpoint) and net
  (`total_reward`, which charges holding). Unweighted mean over the 120 episodes (ub-ctrl: the
  96 shocked), with the episode-level normal interval and a seed-cluster bootstrap (24 clusters,
  10,000 draws, seed 20260927). By condition, on shocked episodes, for arm8-arm1, arm10-arm1,
  arm10-ctrl.
- **Q5. Operations.** Provider calls, charged calls, tokens, latency, cost, retries, refusals,
  parse outcomes and errors, repairs, Rule U coercions, arm-10 calls over the budget of 4.
- **Q6. Nulls,** silent versus false-alert: share of nulls with any active spec for arms 8, 9, 10,
  ctrl and keyword; arm8-arm1, arm10-arm1 and ctrl-arm1 gross; first-proposal outcomes.
- **Q7. Content effect.** For arms 8, 9, 10: live outcome minus the `scripted-bank` outcome, same
  episode, gross and net, all 120 and the shocked 96, same intervals as Q4. Everything else is
  shared, so this isolates what real answers do.
- **Agreement.** On episodes where both endpoints made a first call: identical-prompt count,
  same-answer rate, Cohen's kappa over answer categories, `family_ok` concordance.

**Headline quantities** (everything else is secondary): Q1 `family_ok` on the 96 shocked
episodes and on the 20 early-accurate episodes with a bank alert; Q7 for arms 10 and 8, gross
and net; Q4 arm10-ctrl and arm10-arm1, gross.

**Reading rules.** A contrast is called different from zero only when its seed-cluster bootstrap
interval excludes zero; the normal interval is shown for comparison with the registered
evaluator. Real content "changes" an arm's outcome only when its Q7 bootstrap interval excludes
zero. No multiplicity correction: nothing here is confirmatory. No claim about language
understanding beyond these field accuracies. A favourable result does not re-vote Gate 3: these
seeds were spent by the registered pilot, so any confirmatory test needs fresh held-out seeds
under a new registration.

## Known limitations

The same 120 dev/cal episodes as the registered pilot; no alert coverage for family 2; the
unreliable offset awaits team confirmation; nine of fifteen arms; one run per endpoint, and
temperature 0 is not guaranteed deterministic at the provider (the cache fixes each answer once
made); family x condition cells hold 4 episodes; the gross endpoint ignores holding cost; the
frozen keyword control matches "port" inside words such as "reports", so some bank demand text
reads to it as an arrival claim.

## Outputs

Committed, per run, in `analysis/real_content_pilot/out/<run>/`: `records.jsonl.gz` (the frozen
record format, gzip mtime 0), `ledger.csv`, `proposals.jsonl` (every parse, with payload and
error), `alerts.jsonl`, `spend_log.jsonl` (live only: tokens, cost, latency, status and a prompt
digest per request; never prompt text, answers or credentials), `invocations.jsonl`,
`run_manifest.json`. Then `out/evaluation.json`, `out/evaluation.md` and `REPORT.md`. Local
only (`results/` is gitignored): the response cache and the raw answer texts.

Commands:

```bash
uv run python -m analysis.real_content_pilot.runner --endpoint scripted --run-name scripted-bank
uv run python -m analysis.real_content_pilot.runner --endpoint gemini --run-name gemini-bank \
    --allow-live --episodes dev/f1/s1050000/early_accurate cal/f6/s6060000/unreliable \
    dev/f1/s1050000/unreliable__twin
uv run python -m analysis.real_content_pilot.evaluate --smoke gemini-bank
uv run python -m analysis.real_content_pilot.runner --endpoint gemini --run-name gemini-bank \
    --allow-live
uv run python -m analysis.real_content_pilot.evaluate --runs gemini-bank grok-bank \
    --reference scripted-bank
```

(and the same for `grok` / `grok-bank`).

## Deviations

1. **Logging only (2026-09-28, after both smoke runs, before either full run).** The ledger's
   `prompt_hash` is the cache key, which folds in the model id, so it cannot show that Gemini and
   Grok answered the same first prompt, and the smoke projection matched no smoke call to the
   reference. `RecordingParser` now rebuilds the exact prompt each parse answered, checks it
   against the cache key, and logs its model-free digest `prompt_sha256` (the digest
   `spend_log.jsonl` already records). The agreement check and the smoke projection use it; the
   projection also reports an upper bound in which only each episode's first call is shared.
   `scripted-bank` was re-run at that commit: its alerts are byte-identical, its records and
   ledger identical except the wall-clock `latency_ms`, and its proposal log identical except the
   new field. Both smoke runs were replayed from cache, with no provider call.
