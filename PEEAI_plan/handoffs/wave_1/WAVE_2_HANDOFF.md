# Handoff to Wave 2

Wave 2 adds a live tool-using agent, community participation, the pantry domain adapter and
an optional MBTA read adapter ([waves/02_adaptation.md](../../waves/02_adaptation.md)). None of
that is implemented here. This file lists what Wave 1 provides for it, what must not change
silently, and the debt to clear first.

## Stable interfaces a live agent can use

| Interface | Where | Contract |
| --- | --- | --- |
| Tool client | `plan_b/evaluation/policies/base.py`: `ToolClient`, `TransportLost`, `Policy` | A policy gets only a client bound to a server-held coordinator session. `call(tool, arguments=…, idempotency_key=…, expected_revision=…, expected_goal_version=…) -> ToolEnvelope` |
| Tool surface | `docs/RUNTIME_CONTRACT.md` sections 4–5; `models.TOOL_ARGUMENT_MODELS`, `TOOL_REQUIREMENTS` | 10 common tools + 2 organizer controls; envelope and receipt vocabularies; durations |
| Policy host | `plan_b/scenarios/policy_host.py`: `PolicyHost(db, policy_factory)` | One policy instance per episode; decisions stored as narration; reset gives a fresh instance |
| Runner | `plan_b/scenarios/runner.py`: `tick_loop`, `run_case`, `ScriptedActors` | Minute ticks; policy woken on revision change or `wait_until`; scripted exogenous actors only through their own sessions |
| Observable state | `EventStateView` via `get_event_state` / `GET /api/state` | Role-filtered, private-free projection, including `status_checks` and `latest_evaluation` |
| Planner | `DomainAdapter.evaluate/revalidate` (via `evaluate_candidates` / `apply_plan`) | The agent never builds plans itself: it chooses among stored, server-evaluated candidates |
| Scoring | `plan_b/evaluation/scoring.py`: `score_episode(final, history, case)` | State-based; predicates runner-side only; `public_summary` for audiences |
| Trace/replay | `plan_b/evaluation/export_trace.py`, `web/src/replay/` | Trace 1.0.0 with integrity; replay is GET-only |

A live LLM policy implements `Policy.run(client, max_tool_calls)` and is passed to
`PolicyHost(db, policy_factory=...)` and `run_case(..., policy_factory=...)`. It must:

* never receive a database handle, the `World`, `PrivateCase`, file access to
  `scenarios/private/`, or another principal's session;
* reuse the same idempotency discipline: one key per intended request, reconcile a
  `TransportLost` with `get_action_receipt` and the original key, never mint a fresh key for an
  ambiguous outcome;
* apply only stored candidates by `(candidate_plan_id, constraint_report_ref)` with the
  evaluation's `revision` and `goal_version`;
* count failed calls and retries against the same caps (proposed eight model calls and sixteen
  tool calls per episode). Wave 1 does not enforce a per-episode cap yet. `max_tool_calls` (16)
  bounds one policy run, and a run that exhausts it is woken again with a fresh budget. The rule
  baseline already uses more than 16 tool calls per episode in every development case
  (VERIFICATION.md lists the counts). Add the per-episode caps to the runner for every policy,
  the rule baseline included, before any comparison.

The deterministic `RulePolicy` (`rules/1.0.0`) remains the P0 baseline. Its message grammar is
documented in the contract (section 11) and in `plan_b/evaluation/policies/parser.py`.

## How the pantry adapter extends the domain without a second executor

* Implement `plan_b/domain/adapters/pantry.py` against `DomainAdapter`
  (`plan_b/domain/adapters/base.py`) and register `pantry_continuity` in
  `plan_b/domain/adapters/registry.py`. The executor, sessions, idempotency, receipts, clock,
  snapshots and trace format are shared and must not be forked.
* The adapter is on the scoring and readiness paths. `score_episode` dispatches on the
  episode's profile to `score_outcome(final, history) -> DomainOutcome`, and the engine and the
  projection call `check_readiness` in `execution` and `preview` mode. A pantry adapter
  implements both, and `validate_config` for its fixtures.
* Two pieces of the core scorer are still campus-specific and must be generalized or routed
  through the adapter: `scoring.HARD_CHECK_IDS` (the `infeasibility_reported` predicate) and the
  `equipment_before_arrival` category of the `no_equipment_start_before_arrival` predicate.
* `record_stock_receipt` and `record_distribution` are new staff-only mutation tools. Add them to
  `MUTATION_TOOLS`, `TOOL_ARGUMENT_MODELS`, `TOOL_REQUIREMENTS`, `tools/handlers.py:HANDLERS`,
  and a staff principal/grant in the pantry fixture. They are absent from the coordinator grant,
  so the executor rejects them for the agent with `GRANT_REQUIRED` without any adapter code.
  Tool access is gated by `grant.allowed_tools`, so a staff grant on a participant-role principal
  works without a new role. If the board must show a distinct staff role, add `staff` to
  `PrincipalRole` and `SessionRole` in `domain/models.py` and to the web role handling. Also keep
  `READ_TOOLS`, `MUTATION_TOOLS` and `CONTROL_TOOLS` in `web/src/types.ts` in step with
  `models.py`.
* Consumable stock needs new ledger tables (stock movements, distribution ledger, expected
  shipment reconciliation) in a new numbered migration (`0001`–`0003` are taken; see
  `plan_b/store/migrations/`). Do not overload the money `ledger`.
  Quantity holds need `remaining_quantity` (planning 0.2.0 already defines it); the campus hold
  table has `quantity` and must gain a remainder column in that migration.
* The planning-schema pantry fields (`service_targets`, `consumable_stock`,
  `consumable_allocations`, `service_progress`, `expected_shipments`, `pantry_parameters`) are not
  in the runtime models yet. Add them as optional runtime fields (runtime 1.1.0), keep campus
  fixtures valid, and extend `planning_map.py` and its schema tests.
* Physical-reference uniqueness (receipt and distribution references) is separate from request
  idempotency, as `observations` uniqueness already is: add a unique index per event/source.

## Schema and migration implications

* The store is migration-based (`plan_b/store/migrations/`, `schema_migrations`). New tables and
  columns go in new numbered files; `0001_initial.sql` must stay unchanged once committed.
* Runtime contract changes bump `models.RUNTIME_VERSION` and are recorded in the contract.
  Additive fields get defaults so stored snapshots and traces still parse, as
  `status_checks`/`status_sources` did before the 1.0.0 release.
* Bumping the constant alone breaks validation. `PublicScenario`, `PrivateCase`, `ActionReceipt`,
  `ToolEnvelope` and `EventStateView` each declare `runtime_version: Literal["1.0.0"]`, and the
  server fills them from `RUNTIME_VERSION`. Widen each literal to accept both `"1.0.0"` and the
  new version, so stored 1.0.0 receipts and snapshots still parse.
* Trace format changes bump `TRACE_VERSION`; the browser verifier
  (`web/src/replay/integrity.ts`) and `export_trace.verify_trace` must change together and keep
  `web/tests/fixtures/canonical_vectors.json` in sync (`web/tests/make_vectors.py`). Their
  equivalence is tested: each shared `trace_cases` vector must fail exactly the same named check
  in both suites (`web/tests/integrity.test.ts`, `tests/test_trace_verifier.py`).

## LLM and API access still required

* G-LLM: credential supplied on 2026-10-23 for an OpenRouter (OpenAI-compatible) endpoint.
  * Key file: `.local/keys/openrouter.key` (mode 0600, directory 0700, ignored by
    `/.local/keys/` and `*.key`, absent from the Git index).
  * Non-secret config: `.local/keys/model_endpoint.env` (`PLAN_B_MODEL_PROVIDER=openrouter`,
    `PLAN_B_MODEL_BASE_URL=https://openrouter.ai/api/v1`, `PLAN_B_MODEL_KEY_FILE=...`).
  * One read-only, non-billed `GET /api/v1/key` returned HTTP 200: account limit 50, remaining
    50, usage 0, not free tier.
  * This establishes that the key is accepted. It does not pass G-LLM: no model has been chosen
    and no completion, structured-output or tool call was made.
  * Still open for Wave 2: choose the model id and a per-run spend cap below the account
    limit, then perform the gate's structured interpretation plus bounded tool call through the
    application adapter. Read the key server-side only. Never put it in browser code, traces,
    logs, screenshots or URLs.

  Wave 1 code never calls a model, reads `cloud_endpoint/`, or reads `.local/keys/`.
* G-MBTA (optional): the stored key must be read only by a server-side adapter behind
  `query_status`, in a separate live-clock event; the frozen November fixtures stay on the
  scenario clock.

## Tests that must keep passing

All of `apps/plan_b/tests/` (`uv run pytest`), in particular:

* `test_stateful_tools.py` (transactions, idempotency, holds and money, authority, provenance),
* `test_campus_workflow.py` (clock ordering, lifecycle, readiness, immutable history),
* `test_runner_isolation.py` (static import boundaries for policy/planner modules, leak scans of
  policy inputs, snapshots, traces and the browser bundle; reset; determinism; read-only replay),
* `test_dev_cases.py` (honest outcomes for dev01, dev02, dev04, dev05, dev06 and the
  rejected-actions run),
* `test_contracts.py` (planning traceability, digest convention, unchanged planning examples),
* web: `npm run typecheck`, `npm run build`, `npm test`, `npm run lint`; browser:
  `uv run python tests/e2e/walkthrough.py --out <dir>`.

The live-agent policy must be added to the isolation parametrization in
`test_runner_isolation.py::ISOLATED_MODULES`, and its envelopes must pass the same leak scan.

## Wave 1 debt to resolve before expansion

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for the full list. Items that affect Wave 2
design directly:

* Policy memory lives in the policy instance; after a server restart the host creates a fresh
  instance that re-derives from public state (it re-queries; status records dedupe). A live agent
  with conversation state needs an explicit, episode-scoped memory record.
* `AuthorizationRequest` has no stored open/answered state; the board derives it. Wave 2's
  organizer workflow should store requests and answers explicitly.
* No in-place late start: a missed start fails the activity. Recovery must happen before start.
* Authentication failures (missing, unknown, revoked or expired token) and moderator-session tool
  calls are not persisted. Every failure after session resolution is, as an attempt or a
  rejected receipt.
