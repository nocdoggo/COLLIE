# Plan B evaluation harness (Wave 3)

This is the tooling for the Wave 3 comparison: the freeze, the held-out suites, the episode
runner, the metrics and the report. The protocol itself (policies P0–P3, common conditions,
cases C01–C08 and T01–T04, metric definitions, reporting gates) is
[`PEEAI_plan/08_evaluation.md`](../../../PEEAI_plan/08_evaluation.md); where this file and the
protocol disagree, the protocol wins and this file is wrong. Nothing here claims a result: the
commands below produce results only when they are run, and a development dry run is never a
reported result.

| Module | Role |
| --- | --- |
| [`plan_b/evaluation/manifest.py`](../plan_b/evaluation/manifest.py) | `freeze.json` and `heldout.json`: compute, write, verify |
| [`plan_b/evaluation/run.py`](../plan_b/evaluation/run.py) | the held-out loader, the run plan, parallel episode processes, the truth split, resume |
| [`plan_b/evaluation/metrics.py`](../plan_b/evaluation/metrics.py) | every protocol metric, per episode and per policy, from state and receipts |
| [`plan_b/evaluation/report.py`](../plan_b/evaluation/report.py) | `evaluation_results.md`, `metrics.json` and `figure.svg` from a results directory |
| `plan_b/evaluation/manifests/` | the committed `freeze.json` and `heldout.json` |

## Commands

Run from `apps/plan_b` (`unset VIRTUAL_ENV` first). P1–P3 make paid model calls through the
configured endpoint (`.local/keys/model_endpoint.env`; the key file is read by the provider only,
per call) under the spend ledger's per-run and cumulative caps.

```bash
uv run plan-b eval freeze [--seeds 101,202,303] [--order-seed 20261025]   # writes manifests/freeze.json
uv run plan-b eval lock-heldout                                         # writes manifests/heldout.json
uv run plan-b eval verify-freeze [--require-heldout]                    # exit 1 on any drift
uv run plan-b eval run --suite campus --policies P0,P1,P2,P3 --jobs 4 --out <dir>
uv run plan-b eval run --suite pantry --cases T01 T02 --policies P0,P2 --jobs 2 --out <dir>
uv run plan-b eval report --results <dir>                               # writes <dir>/report/
```

`eval run` options: `--suite campus|pantry`; `--cases` held-out evaluator ids (`C01`…) or opaque
case refs, default every held-out case of the suite, or development case refs for a dry run;
`--policies` any of `P0,P1,P2,P3`; `--seeds` three ints (default the preregistered seeds);
`--jobs N` parallel episode processes; `--out` the results directory; `--order-seed`;
`--timeout` (episode wall time, seconds); `--policy-factory MODULE:CALLABLE` (dry runs on
development cases only, see below). Exit codes: 0 run (whatever the episodes' outcomes), 2
refused before anything ran, or stopped because the measured code, the held-out cases or the
model changed while it ran (the episodes that found it recorded nothing; see "The run").

A development dry run with scripted model transports (no network, no spend; the test helper
`tests/test_eval_harness.py:scripted_policy_factory`):

```bash
uv run plan-b eval run --suite campus --cases dev01 dev04 dev05 --policies P0,P1,P2,P3 \
    --seeds 101,202,303 --jobs 2 --out <dir> \
    --policy-factory tests.test_eval_harness:scripted_policy_factory
uv run plan-b eval report --results <dir>
```

## The freeze

`plan-b eval freeze` writes `plan_b/evaluation/manifests/freeze.json`:

* **Measured files.** The SHA-256 of every file under `plan_b/` plus `pyproject.toml` and
  `uv.lock`, except `manifest.EXCLUDED`: fixture data (`scenarios/public/`,
  `scenarios/private/`, which `heldout.json` covers), the manifests, the development run
  records, the browser server (`api/`), `cli.py`, `scenarios/demos.py` and `evaluation/report.py`
  (it formats `metrics.py`'s output and computes nothing). So the policies, prompts, agent
  modules, the tool registry and executor, the store and clock engine, the planner, candidates,
  constraints, objective, adapters, scoring, metrics, the runner and policy host, the world
  loader and this harness are frozen, and a new file anywhere under those roots is drift.
* **Settings.** The model and provider (from the endpoint configuration's public form), the
  generation settings (the provider's request template and every generation, cap and retry
  constant the agent modules declare), the per-episode caps (the policy host's frozen caps, else
  its development values 48 tool calls and 8 model calls), the retry rules, the episode timeout
  (`manifest.EPISODE_TIMEOUT_S`, 900 s of wall time), P3's relevance rule id, the three seeds and
  the policy-order seed, the policy names and ids, the prompt hashes, the protocol version
  (`plan_b.eval_protocol/1.0.0`), `model_response_cache: false`, the per-episode USD cap
  (`model.max_run_cost_usd`) and the runtime (the Python version and the installed versions of
  the runtime dependencies: `uv.lock`'s hash does not prove the environment matches it).
* **Entries.** The walk follows no symbolic link: a link under a measured root is an entry
  (`symlink:<target>`), so adding or re-pointing one is drift, and an unreadable file is an entry
  (`unreadable:<error>`) rather than an error.

`plan-b eval verify-freeze` recomputes the measured files and the settings the code declares and
prints every changed, added or removed file and every changed setting, then exits 1 with
`FREEZE VERIFICATION FAILED`. With a `heldout.json` present (or `--require-heldout`) it verifies
that too: its files, its own aggregate hash and protocol version, and that it was locked against
this `freeze.json` byte for byte (`freeze_sha256`). The seeds, order seed and model are inputs
recorded in `freeze.json`, not recomputed from code; the lock's `freeze_sha256` and each run's
`plan.json` bind them. Once `freeze.json` exists, every file it hashes is frozen; changing one invalidates the
freeze and the matched comparison (`waves/03_evidence_showcase.md`).

## Held-out cases

Held-out cases are evaluator-only and live in `plan_b/scenarios/private/eval/`:

* `<case_ref>.json`: a `PrivateCase` (`artifact: plan_b.private_case`) whose `case_ref` is the
  opaque file stem. Its `scenario_id` names a development public fixture or one under
  `plan_b/scenarios/public/eval/` (a `PublicScenario`; its `scenario_id` must be new). Public
  fixtures are agent-visible: opaque and label-free.
* `<case_ref>.eval.json`: its evaluator data (`run.EvalCase`, `artifact: plan_b.eval_case`):

| Field | Meaning |
| --- | --- |
| `case_id` | the evaluator id: `C01`…`C08` (campus) or `T01`…`T04` (pantry), with its outcome class fixed by the protocol; appears only in evaluator output |
| `case_ref` | the opaque ref of the case file |
| `suite` | `campus` or `pantry`; must fit the public fixture's profile |
| `condition` | the protocol condition, in words |
| `outcome_class` | campus `goal` (C01–C07) or `infeasible` (C08); pantry `target` (T01–T02) or `partial` (T03–T04) |
| `negative_control`, `negative_control_evidence` | the designation: true exactly for C02–C04, with the evidence (required) that the original plan stays feasible; `lock-heldout` replays it |
| `requires_recovery`, `actionable_record_ids` | whether recovery delay applies, and the `source_record_id`s of the first actionable public update (default: the first notice) |
| `target_quantity`, `achievable_on_time` | pantry: the original target, and the quantity achievable by the deadline on a `partial` case |
| `annotations` | per message (`MessageAnnotation`): `source_record_id`, `event_id`, `resource_id`, `effective_time`, `claimed_change` (`delay`, `unavailability`, `availability`, `attendance_change`, `priority_change`, or `no_change`), `source_id`, `booking_ref`, `unknown_fields`. They describe the text, not the truth |

The loader (`run.heldout_specs`) validates every case against its public fixture
(`world.validate.validate_case`) and refuses a case without evaluator data, evaluator data
without a case, a reused development ref, a world (statuses, world events, scripted actors)
identical to a development case's, a duplicated evaluator id, an id outside the protocol's or an
outcome class other than the protocol's for it (C01–C07 `goal`, C08 `infeasible`, T01–T02
`target`, T03–T04 `partial`), a negative-control designation other than exactly C02–C04 (or one
without its evidence), and identifiers that are not opaque: a case ref or held-out public
scenario id must not contain its case id, a `C0n`/`T0n` token or a revealing word
(`run.REVEALING`: `delay`, `false`, `stale`, `duplicate`, `infeasib`, `partial`, `deficit`...).
The frozen loaders read only the development directories, so a run with held-out cases installs
them in each episode process (`run.CaseRegistry`): the private cases are copied with the
development cases into `runner_private/cases/` (evaluator side), which becomes
`world.PRIVATE_DIR`, and the public fixtures are added to `fixtures.PUBLIC_SCENARIOS`. Only the
private case files are copied, never the `*.eval.json` evaluator data, and no policy has a
filesystem tool: what a policy sees is what the runner's tools return, as on development cases.
A held-out ref cannot equal a development ref, a held-out public scenario id cannot equal a
registered one, and a run is either held-out or development (`--cases` mixing them is refused),
so a development case cannot be run as a held-out one. Nothing changes in the parent process; the
run removes the copy at the end.

`plan-b eval lock-heldout` writes `manifests/heldout.json`: each suite's cases (evaluator id,
opaque ref, outcome class, private, evaluator and public file with their hashes, and for a
negative control the evaluator's replay: with a coordinator that changes nothing,
`run.replay_original_plan`, the original plan must complete the goal with no executed
violation, or the lock is refused), every file under `scenarios/private/eval/` and
`scenarios/public/eval/` with one aggregate over all and one each over the public fixtures the
cases use (`public_files_sha256`, development fixtures included) and the evaluator-only files
(`private_files_sha256`), the freeze it was locked against (`freeze_files_sha256` and the
manifest's own `freeze_sha256`) and the case-freeze time. Any later change, addition or removal
there is drift.

**A held-out run starts only when** `freeze.json` and `heldout.json` both verify, the lock was
made against that freeze, every case is in the lock, the seeds, order seed and timeout are the
frozen ones, the policies are among the frozen ones, the configured model, provider and base URL
are the frozen ones, and no `--policy-factory` is given. Its caps are the frozen caps with phase
`frozen`. Anything else is refused (exit 2) before an episode runs.

`tests/test_eval_harness.py` proves the loader and the lock with held-out copies of `dev01` (as
C01) and `dev04` (as the negative control C03) in temporary directories put in place of
`scenarios/{private,public}/eval/` (`manifest.HELDOUT_PRIVATE_DIR`/`HELDOUT_PUBLIC_DIR`); it
asserts the real directories are unchanged, so no test can disturb a locked `heldout.json`.

## The run

`run.build_plan` makes P0 one episode per case and P1–P3 one episode per seed, and shuffles the
runs of each case over all four policies with `random.Random(f"{order_seed}:{case_ref}")`; a run
of a subset of the policies keeps the positions its episodes have in that full order, and
`plan.json` says so (`policy_subset`; the report notes that a comparison assembled from several
such runs is not order-randomized). Episodes start in that order, `--jobs` at a time, each in
its own `spawn`ed process with a fresh SQLite database (`<out>/work/<key>.sqlite3`, deleted
afterwards; kept in `runner_private/failed/` when the episode timed out or crashed) and a fresh
policy instance, so no state, policy memory or model response is shared. An episode process
ends itself when the runner that started it is gone, and one invocation at a time holds a
results directory (an exclusive lock on `<out>/.lock`). Nothing caches model
responses; fixtures are fixed by design. P1–P3 get the seed through `run_case(..., seed=...)`
when `run_case` takes it (`seed_passed` in the record); otherwise each trial is an independent
run id and the report says so.

An episode keyed `<case_ref>__<P>__s<seed>` (P0: `__once`) writes:

| File | Content | Side |
| --- | --- | --- |
| `episodes/<key>/trace.json.gz` | the sanitized trace (verified before writing; gzip, mtime 0) | public |
| `episodes/<key>/record.json` | status (`completed`, `capped`, `timeout`, `crashed`), seed, trial, order position, policy id, mode label, the public outcome summary, caps used, model calls, tokens, latency, provider-reported cost, recorded seed fields, tool calls by tool and status, rejected calls, decision failures, errors, wall time, the trace's hash and verification | public |
| `runner_private/<key>.runner.json` | the evaluator id, outcome class, expected outcome, `matches_expectation`, predicate results, the full report and the scripted actors' log | evaluator |

The public record never carries `matches_expectation`, predicates, the expected outcome, the
evaluator id or the staff schedule (this closes Wave 2 audit item D4 for new records;
`scripts/run_live_cases.py` now writes its verdict to
`runner_private/live_<label>_run.private.json` the same way). `plan.json` and
`invocations.jsonl` (one line per invocation: git head, tree cleanliness, freeze and lock
verification, seed support, the model's public configuration) are public; `runner_private/cases.json`
holds the evaluator data of the run's cases.

A process over the timeout is terminated and recorded `timeout`; one that exits without its
records is recorded `crashed`. The public record names only the exception's type (its text may
come from privileged code: the trace exporter's leak refusal quotes what it refused); the text
goes to the evaluator record. Both stay in the outcome-class denominators as failures. A capped
episode (an episode cap or the per-run spend cap reached) runs to its hard end and is scored as
it stands. An episode the harness stopped, not the policy (the cumulative spend cap, an
unreadable ledger, or the endpoint configuration halted its model calls), is recorded
`aborted`: not scored, listed apart, and rerun by a resume once the cause is fixed.

**Binding.** `plan.json` records the measured files' hash and, for a held-out run, the held-out
files' hash, both manifests' digests and the model configuration (provider, model, base URL,
per-run cost cap). A resume under any other is refused ("a different run plan"). Each episode
process checks them again before it runs (`run._drift`): one that finds the measured code, the
held-out cases or the model configuration changed records nothing and exits, and the run starts
no further episode and stops with exit 2. Each public record carries the measured files' hash
it ran under. The report flags a results directory whose invocations ran under different
freezes, locks or commits.

**Resume.** An episode is finished when its public record (written last) and its evaluator record
exist and it was not aborted. Rerunning the same command on the same `--out` skips finished
episodes, clears and reruns unfinished and aborted ones, and refuses a directory whose
`plan.json` differs. Recorded timeouts and crashes are outcomes and are not rerun.

## Metrics

`metrics.suite_metrics` computes, per episode (from the trace's final state, receipts and tool
calls, and the scorer's public outcome) and per policy:

| Metric | Definition here |
| --- | --- |
| Goal completion (C01–C07) | the scorer's `goal_complete` (required activities by the deadline, no executed violation) |
| Appropriate infeasibility (C08) | goal not complete, an `infeasible` decision naming a blocking constraint in its structured details (`blocking_constraints`; never its text), no executed violation; who chose that decision is reported (`decided_by`: the model, the server's shared narration, or the deterministic policy) |
| Original-target attainment (T01–T02) | goal complete, every target attained on time, target unchanged, stock conserved |
| Supported partial fulfillment (T03–T04) | on-time fulfillment equals the evaluator's achievable quantity, an `infeasible` decision with blocking constraints whose structured shortfall for each short target (`shortfall_quantity` with `target_id`, or an item of `shortfalls`) equals that target's final deficit, target unchanged, stock conserved, no violation; `decided_by` as above |
| Invalid action attempts | the coordinator's tool calls rejected, by error code and tool |
| Executed violations | the scorer's violations |
| Unnecessary committed changes | on designated negative controls only (C02–C04, whose original plan the evaluator's replay at lock time confirmed to complete the goal unchanged): the coordinator's applied `apply_plan` receipts (with altered assignments and committed cents) |
| Plan churn | the coordinator's applied plan changes plus the previously valid assignments they altered: per change, the activities whose window or resources it changed, less those the kept plan already failed a hard check on in the planner's latest evaluation at or before the change's revision (repaired, not churned) |
| Verification effort | status checks, distinct (entity, fact) sources, repeated checks, failed checks, modeled minutes |
| Recovery delay | on cases requiring recovery: minutes from the first actionable update to the first applied plan change after it, when the outcome succeeded; otherwise unrecovered with the horizon (update to hard end). The per-policy median counts an unrecovered episode at its horizon (a lower bound, shown "≥"), with the median among recovered episodes beside it |
| Preparation cost | hold minutes, hold fees (part of committed money, never added to it again), reserved cents at the end, expired and still-active holds |
| Modeled cost | the committed event money, hold fees included |
| Computation cost | model calls, retries, failed calls, tokens, provider latency, provider-reported USD, tool calls, wall time, over the episodes it was measured on (a timed-out or crashed episode's calls are in the spend ledger only) |
| Pantry quantities | per target: original and current target, on time, late, distributed, service deficit, supply shortfall; per pool: opening, expected, reserved at end, received, transferred out, distributed, on hand, conservation; unnecessary reservations |
| Duplicate or unauthorized credit | executed effects: a stock receipt or distribution attested by the coordinator or under a grant without the tool, a credited reference repeated, a hold or shipment credited beyond its quantity |
| Receipt and evidence integrity | every credited receipt matches its hold or shipment, staff receipt, movements and handoff window or cutoff; every distribution its movement and deadline flag; every status-tool observation links to a successful check (whoever made it); every verify decision that reports a success cites a successful status check |
| Extraction labels | per annotated message: `correct`, `incorrect`, `abstained`, `malformed`, `rejected` or `not_recorded`, from the policy's first structured reading of it: P2/P3's recorded readings (a weighed claim's change spec names its observation in `evidence_refs`), P0's frozen parser replayed over the episode's observations (event profiles; the pantry baseline reads no notices); compared on the claimed change, resource, event, effective time and booking the reading states. P1 records none; a provider error is `not_recorded` |

Every metric is computed from the trace as read when the report is made: `run.load_results`
checks each trace against the hash in its record and the exporter's verification, and an
episode whose trace fails is `integrity_failed`, a failure in its class. A planned episode
without a record is *missing* and an `aborted` one is listed with it: both apart from the
denominators. The outcome-class shares count every recorded episode (a timeout, crash or failed
trace is a failure); the other aggregates are over the scored episodes, whose number the report
gives. No composite score is computed and no significance is claimed.

## The report

`plan-b eval report --results <dir>` writes `<dir>/report/metrics.json`,
`<dir>/report/evaluation_results.md` (the
[results template](../../../PEEAI_plan/templates/evaluation_results.md): run manifest, the suite's
aggregate display, counts and denominators per policy, verification and cost, the per-case
table, the pantry quantity and receipt ledger, extraction labels, missing episodes) and
`<dir>/report/figure.svg`: per case, for each policy, the episodes that met the case's outcome
class (labelled met/recorded) beside the mean status checks per episode, in two panels with
their own axes, readable in light and dark (`prefers-color-scheme`, with the light colours as
presentation attributes for renderers without CSS variables). The report is evaluator output,
like `runner_private/`: it names evaluator ids, outcome classes, negative-control designations
and why an episode missed its class, never case contents, predicates or messages. The public
part of a results directory is `plan.json`, `invocations.jsonl` and `episodes/`.

## Wave 3 freeze

`plan_b/evaluation/manifests/freeze.json` was written with `uv run plan-b eval freeze` on
2026-10-25 (`frozen_at` 2026-10-25T14:51:31Z), after the freeze audit and its fixes, on the
working tree whose parent commit is `603d7ed` (`git_head_at_freeze`), and committed together
with every file it hashes; `uv run plan-b eval verify-freeze` passes on the committed tree. It
covers 76 measured files, `files_sha256`
`7d41fada702f2172c39a968bb6a2a1d72b6cac4e6d23cb047133d47ce373596f`. Every file it hashes is now
frozen: a change to one, to a recorded setting or to the runtime is drift, invalidates the
freeze and any comparison made under it, and makes a held-out run refuse to start. No
`heldout.json` exists yet: the held-out cases are authored and locked against this freeze
afterwards (`plan-b eval lock-heldout`).

**What is frozen.** The policies P0 `rules/1.0.0` and `pantry-rules/1.1.0`, P1 `tool-use/1.1.0`
(prompt `tool_use.v3`), P2 `live/1.1.0` (`interpret.v1`, `choose_action.v1`,
`choose_action_pantry.v1`) and P3 `verify-all/1.1.0` with its relevance rule
`verify-all-relevance/1.0.0`; the shared attention rule (`agent/attention.py`), the menu, the
provider client and spend ledger, the tool registry and executor, the store and its migrations,
the clock engine, the planner, candidates, constraints, objective and both adapters, the
scoring, these metrics, the runner, policy host, world loader and this harness; `pyproject.toml`
and `uv.lock`. Not frozen (`manifest.EXCLUDED`): fixture data (the held-out lock covers it),
the manifests, the development records, the browser server, the CLI, the demo script and the
report formatter.

| Setting | Frozen value |
| --- | --- |
| Model and provider | `anthropic/claude-sonnet-5.5` via OpenRouter, `https://openrouter.ai/api/v1`, for P1, P2 and P3 alike |
| Generation | `max_tokens` 4096 on every call (P1's turn, P2/P3's choice and interpretation); no temperature or other sampling parameter (none of the model's endpoints accepts one); strict JSON schema output; `usage.include`; `provider.require_parameters` |
| Seeds | 101, 202, 303 for P1-P3, passed to `run_case(seed=...)` and recorded on every call; not sent to the provider (`seed_sent = false`: the model's endpoints refuse a seed), so the three trials of a case are independent runs, not reproducible ones (`08_evaluation.md`'s unsupported-seed case). Policy-order seed 20261025 |
| Episode caps | 48 tool calls and 8 model calls (every failed call, repair and retry counts); 0.50 USD per episode (the per-run spend cap, `model.max_run_cost_usd`); 900 s of wall time |
| Retry rules | `manifest.RETRY_RULES`: one repair of a malformed reply; a provider failure is a visible wait retried at a later wake (P1's own retry wake is its model turn); a retryable rejection is re-read and retried within a bound; P3 retries a failed source once and never waits for it; a reached cap is one host-recorded stop |
| Order | each case's runs shuffled over all four policies from the order seed |
| Runtime | CPython 3.12.11; fastapi 0.162.0, pydantic 2.14.1, pydantic-core 2.50.1, uvicorn 0.54.0 |
| Protocol | `plan_b.eval_protocol/1.0.0`; `model_response_cache: false` |

The cumulative spend cap (`PLAN_B_MODEL_MAX_TOTAL_COST_USD`) is a budget, not a frozen
setting: when it stops an episode's model calls the episode is `aborted` and rerun by a resume
once the budget is raised; it never becomes a policy's failure.

**Rules for the held-out evaluation.** A held-out run uses the three frozen seeds, the frozen
order seed and timeout, the frozen caps (phase `frozen`), no `--policy-factory`, and the frozen
model configuration key by key; both manifests must verify and the lock must have been made
against this `freeze.json` byte for byte. The held-out cases follow the rules of "Held-out
cases" above (protocol ids and classes, negative controls exactly C02-C04 and replayed at lock
time, opaque identifiers, no development world). The comparison runs all four policies in one
order; a run of a subset is marked. The held-out cases' contents, labels and expectations never
enter a prompt, a policy, the browser bundle or a public record.

**Metric definitions settled before the freeze** (where `08_evaluation.md` leaves room; they are
frozen with `metrics.py`):

* *Unnecessary committed changes* are the coordinator's applied `apply_plan` receipts on the
  designated negative controls C02-C04, and only where the evaluator's replay (a coordinator
  that changes nothing, `run.replay_original_plan`, run by `lock-heldout`) confirmed that the
  original plan completes the goal. `apply_plan` is the only committing tool the coordinator
  grants allow; the altered assignments and committed cents of each are reported with it.
* *Holds are preparation cost*, never unnecessary changes: the protocol counts a provisional
  hold's actual cost ("a cheap provisional action is still an action") and reserves the
  headline metric for the negative controls. Hold minutes, fees, expired and unreleased holds
  are reported; a hold that is committed by an `apply_plan` is counted once, there.
* *Recovery* counts only when the episode met its outcome class (the protocol's "until a valid
  recovery is committed"): the delay runs from the first actionable update (the evaluator's
  `actionable_record_ids`, else the first notice) to the first applied plan change after it.
  Otherwise the episode is unrecovered with the horizon (update to hard end), and the
  per-policy median counts it there as a lower bound.
* *Supported partial fulfillment* needs the on-time quantity to equal the evaluator's
  achievable quantity and an `infeasible` decision naming its blocking constraints whose
  structured shortfall for each short target equals that target's final deficit
  (`max(0, original - fulfilled by the deadline)`), with the target unchanged, stock conserved
  and no executed violation. No text of a summary counts.
* *Plan churn* counts previously valid assignments only (see Metrics). *Modeled cost* is the
  committed event money, which already includes hold fees.
* Who chose the decision that reports infeasibility or a shortfall is reported per episode
  (`decided_by`): P1 shares the server's narration of what the state determines (the shared
  attention rule), so on C08 and T03-T04 its result can rest on that narration; the report
  shows it.

**The held-out loader, audited.** It overrides `world.PRIVATE_DIR` and
`fixtures.PUBLIC_SCENARIOS` only inside each episode process (the parent is untouched, as the
tests assert). The copy it installs holds the private cases only, never the `*.eval.json`
evaluator data, and no policy has a filesystem tool or a route to `PRIVATE_DIR`: a policy sees
only tool responses, which the trace exporter's leak check and the public-boundary tests cover
as on development cases. A development case cannot be loaded as a held-out one (a reused ref, a
reused scenario id or an identical world is refused, and a run is held-out or development,
never both), and a held-out case cannot be run as a development one (its ref is not in the
development directory). The tests use temporary held-out directories and assert the real ones
unchanged.

**Development smoke of the frozen configuration** (paid, development cases only): one episode
each of P1, P2 and P3 on `dev01` and `pantry_dev01` through `plan-b eval run` with seed 101,
recorded in `plan_b/evaluation/development/wave3_freeze_smoke_{campus,pantry}/` and tabled in
`plan_b/evaluation/development/README.md`. All six completed and matched their development
expectation, every model call returned `ok` under the strict schema with `max_tokens` 4096 and
the seed recorded (`seed_sent = false`), the costs are the provider's usage reports, every
trace verified, and each invocation recorded the freeze as verified. Spend 0.464048 USD (the
ledger from 3.292082 to 3.756130 USD). These are development records, not results.

**Known limitations carried into the comparison.** P3's relevance set depends on the
interpretation of each notice (a notice read as no claim and proposing no check is not checked
by the relevance rule), so P3's verification count partly reflects interpretation; P1 has no
separate interpretation step and records no structured reading (its extraction labels are
`not_recorded`); P0's pantry baseline reads no notices; an HTTP error status is charged as not
billed (no completion is returned); a provider timeout's or crash's model calls are only in the
spend ledger; temperature is the provider's default and seeds are not sent, so trials vary.

