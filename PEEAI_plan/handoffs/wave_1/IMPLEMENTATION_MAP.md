# Implementation map

Python module paths (`domain/`, `store/`, `tools/`, `world/`, `scenarios/`, `evaluation/`, `api/`)
are relative to `apps/plan_b/plan_b/`. `web/`, `tests/`, `docs/` and `scripts/` are relative to
`apps/plan_b/`. Paths starting with `PEEAI_plan/` are from the repository root. Evidence paths are
relative to this packet (`evidence/`).

## Runtime architecture

```text
browser (web/, React)            in-process policy (RulePolicy)      headless runner
   |  bearer token per tab            |  ToolClient (server-held           |  scheduled actor actions
   v                                  v  coordinator session)              v  (actor's own sessions)
api/app.py (FastAPI) ----------> tools/executor.py: execute / execute_in  <---- store/engine.py
   moderator controls                 one BEGIN IMMEDIATE transaction per call
   GET /api/state                     session -> grant -> validation -> idempotency
                                      -> clock advance (engine) -> handler -> receipt
                                      -> snapshot -> tool-call log
                                         |                    |
                       tools/handlers.py |                    | domain/adapters/campus.py (pure)
                       (per-tool effects)|                    |   candidates / constraints /
                                         v                    |   objective / readiness
                                 store/ (SQLite, migrations, repo, projections, sessions)
                                         ^
                                 world/world.py (private case: status model, timed events)
```

One process, one SQLite file (`var/plan_b.sqlite3`), WAL. The browser never touches the
database; the policy only sees `ToolEnvelope`s; private input reaches tools only through
`world/world.py` answers allowed at the current scenario time.

## Requirement → code → test → evidence

| Requirement (task / planning) | Code (module: symbol) | Tests | Evidence |
| --- | --- | --- | --- |
| W1.1 typed contracts | `domain/models.py` (all models), `docs/RUNTIME_CONTRACT.md` | `test_contracts.py`, `test_planning_map.py` | `evidence/reports/fixture_hashes.json` |
| W1.1 public/private fixtures | `scenarios/public/campus_showcase.json`, `scenarios/private/dev0{1,2,4,5,6}.json`, `domain/fixtures.py:load_public_scenario`, `world/world.py:load_case` | `test_contracts.py::test_runtime_public_fixture_traces_to_planning_fixture`, `::test_dev01_private_case_traces_to_planning_evaluator`, `::test_private_cases_are_opaque_and_separate` | `evidence/reports/fixture_hashes.json` |
| W1.1 adapter interface | `domain/adapters/base.py:DomainAdapter`, `domain/adapters/registry.py:adapter_for`, `domain/adapters/campus.py:CampusAdapter` | `test_planner.py` | — |
| Planning artifact mapping | `domain/planning_map.py:to_planning_candidate/report/receipt/observation_record` | `test_planning_map.py` (validates against planning schema 0.2.0) | — |
| W1.2 persistence, migrations | `store/database.py:Database`, `store/migrations/0001_initial.sql`, `0002_scheduled_actions.sql`, `store/repo.py` | `test_stateful_tools.py::test_restart_preserves_state_receipts_and_idempotency`, `test_campus_workflow.py::test_setup_started_history_is_loaded_and_immutable` | — |
| W1.2 sessions, grants, authority | `store/sessions.py:issue_session/resolve/resolve_session_id/issue_join_code/redeem_join_code`, `tools/executor.py:_run_call` (grant checks), `tools/handlers.py` (scope checks) | `test_stateful_tools.py` (authority section), `test_api.py`, `test_review_fixes.py` | `evidence/traces/rejected_actions_trace.json` |
| W1.2 clock and events | `domain/clock.py:EVENT_ORDER`, `store/engine.py:advance_to/_process_instant/run_due_scheduled` | `test_campus_workflow.py::test_advancing_processes_intermediate_events_in_order`, `::test_genuine_disruption_recovers_through_state_transitions`, `test_stateful_tools.py::test_exact_hold_expiry_boundary` | traces |
| W1.2 stateful tools | `tools/executor.py:execute/execute_in`, `tools/handlers.py:HANDLERS` | `test_stateful_tools.py`, `test_campus_workflow.py` | traces |
| W1.2 atomic mutations, idempotency | `tools/executor.py` (BEGIN IMMEDIATE, savepoint, idempotency lookup before revision check), `domain/digest.py:request_digest` | `test_stateful_tools.py` (transactions section, races), `test_contracts.py::test_digest_convention_reproduces_planning_example` | — |
| W1.2 money and holds | `tools/handlers.py:hold_resource/release_hold/apply_plan`, `ledger` table + unique indexes, `store/repo.py:grant_usage/ledger_totals` | `test_stateful_tools.py` (holds and money section) | `evidence/traces/dev02_trace.json` |
| W1.3 candidate generation | `domain/candidates.py:single_edits/generate_edit_lists/apply_edits/candidate_ids` | `test_planner.py` | — |
| W1.3 constraints | `domain/constraints.py:assess_candidate` (+ `_no_past_change`, `_commitment_cutoff`, …), `required_holds`, `assess_authorization` | `test_planner.py` | `evidence/screenshots/02c_alternatives.png` |
| W1.3 ranking | `domain/objective.py:objective_components/rank_candidates/ranking_key` | `test_planner.py` | — |
| W1.4 rule policy | `evaluation/policies/rules.py:RulePolicy`, `evaluation/policies/parser.py:interpret_observation` | `test_policy_unit.py`, `test_parser.py`, `test_dev_cases.py` | traces |
| W1.4 runner | `scenarios/runner.py:run_case/tick_loop/ScriptedActors`, `scenarios/policy_host.py:PolicyHost` | `test_dev_cases.py`, `test_runner_isolation.py`, `test_review_fixes.py` | `evidence/reports/*_outcome.public.json` |
| W1.4 scoring | `evaluation/scoring.py:score_episode/public_summary` (counters, spend limits, predicates), dispatching through `adapter_for(profile_id).score_outcome` → `domain/adapters/campus_outcome.py:score_campus_outcome` (goal attainment, executed-rule violations); `domain/adapters/outcome.py:OutcomeRecords/DomainOutcome` | `test_scoring.py`, `test_dev_cases.py`, `test_audit_domain.py` | `evidence/reports/` |
| Scenario loading | `domain/adapters/campus.py:CampusAdapter.validate_config` (references, keep-candidate hard checks), `world/validate.py:validate_case` (private case against its scenario), called from `store/episodes.py:create_episode` and `scenarios/runner.py:run_case` | `test_audit_domain.py` | — |
| W1.5 board | `web/src/views/EventBoard.tsx`, `web/src/board/BoardView.tsx`, `web/src/components/*`, `web/src/panels/*`, `web/src/api.ts` | `tests/e2e/walkthrough.py`, `web/scripts/check-boundaries.mjs`, `npm run typecheck` | `evidence/screenshots/` |
| W1.6 trace export | `evaluation/export_trace.py:build_trace/verify_trace/rehydrate_state` | `test_runner_isolation.py::test_trace_is_sanitized_intact_and_matches_the_run` | `evidence/traces/` |
| W1.6 replay | `web/src/replay/{loader,integrity,ReplayView}.ts(x)`, `GET /api/replays*` | `web/tests/integrity.test.ts`, `test_runner_isolation.py::test_replay_endpoints_perform_no_writes`, walkthrough replay checks | `evidence/screenshots/07_recorded_replay.png` |
| Isolation | `world/leakcheck.py:find_leaks`, `store/projection_db.py` (no private tables), `episode_private` table | `test_runner_isolation.py`, `test_api.py::test_http_payloads_carry_no_private_case_data` | — |
| Reset | `store/episodes.py:create_episode/close_episode`, `api/app.py` (`POST /api/moderator/episodes`) | `test_api.py::test_clock_and_reset_isolate_episodes`, `test_runner_isolation.py::test_reset_clears_policy_memory_and_episode_records`, `test_review_fixes_round3.py::test_tick_loop_survives_a_reset_during_a_policy_run` | walkthrough |
| Review regressions | fixes across the modules above (see VERIFICATION.md, "Independent review") | `test_review_fixes.py` (round 1), `test_review_fixes_round3.py` (rounds 2 and 3), `test_verify_only_end_to_end.py` (verify-only rule) | — |
| Audit fixes | fixes across the modules above (VERIFICATION.md, section 3) | `test_audit_core.py`, `test_audit_domain.py`, `test_trace_verifier.py`, `test_receipt_consistency.py`, `test_evidence_gaps.py`, `test_alternate_format.py`, `test_evidence_tooling.py`; web `tests/boundaries.test.ts`, `tests/replay.test.ts` | — |
| Evidence collection | `scripts/collect_evidence.py` (all checks, cases, traces, browser walkthrough; redacts local paths) | itself (exit code 0 only if every check passes) | `evidence/reports/checks.json` |

## Persistence model (SQLite)

All operational rows are scoped by `episode_id`. Tables (`store/migrations/0001_initial.sql`,
`0002_scheduled_actions.sql`, `0003_history_guards.sql`):

| Table | Role | Integrity |
| --- | --- | --- |
| `episodes` | clock, revision, goal and plan versions, status, counters | revision changed only by compare-and-swap in `repo.bump_revision` |
| `episode_private`, `world_events_processed` | private linkage and world bookkeeping | read only by `world/` (the engine reaches it through `world/`) and by `evaluation/export_trace.py`, which loads the case only to leak-scan an export |
| `scenario_config` | validated public fixture per episode | — |
| `goals`, `plans`, `activities`, `activity_events` | versioned goal, plan versions, lifecycle and append-only history | triggers (0001/0003): no UPDATE or DELETE of goals, plans or activity_events. Activities: no DELETE; `episode_id`, `activity_id` and `definition_json` are fixed; lifecycle moves only planned/ready → planned/ready/started/failed/canceled and started → completed/failed |
| `resources` | status, basis, ETA per resource | newer-only status updates |
| `observations` | immutable observations | unique `(source_id, source_record_id)`; no UPDATE (0001) or DELETE (0003) |
| `checkins`, `holds`, `commitments` | readiness evidence and allocations | hold status leaves `active` once (0001), and a hold row is never deleted (0003); one commitment per hold; no triggers on checkins or commitments |
| `ledger` | authoritative money movements | no UPDATE or DELETE (0001); one reserve and one return per hold |
| `grants` | versioned grants | one current version per grant |
| `sessions`, `join_codes` | hashed tokens and one-time codes | — |
| `receipts`, `idempotency` | durable receipts and `(episode, actor, key)` → digest | receipts: no UPDATE (0001) or DELETE (0003) |
| `evaluations`, `candidates` | stored evaluations and candidates | candidates: no UPDATE (0001) or DELETE (0003) |
| `state_transitions`, `revision_snapshots` | one row per revision; sanitized public view per revision | — |
| `tool_calls`, `policy_decisions`, `runner_log` | sanitized call log, narration, harness log | — |
| `scheduled_actions` (`0002`) | scripted exogenous actor actions (private) | executed by the engine at their instant |

`store/database.py:Database.connect` sets `PRAGMA recursive_triggers = ON` on every connection, so
an `INSERT OR REPLACE`, `REPLACE INTO` or `UPDATE OR REPLACE` over an existing row of a table with
a DELETE trigger is refused too (`tests/test_audit_domain.py::test_replace_cannot_rewrite_a_guarded_row`).

## API and tool surface

`api/app.py:create_app` — endpoints in contract section 3. Tools: `get_event_state`,
`get_action_receipt`, `list_resources`, `query_status`, `evaluate_candidates`, `hold_resource`,
`release_hold`, `apply_plan`, `check_in`, `submit_observation`; organizer controls
`update_goal`, `update_grant`. Argument models: `models.TOOL_ARGUMENT_MODELS`; per-tool
requirements: `models.TOOL_REQUIREMENTS`; handlers: `tools/handlers.py:HANDLERS`.

## Sessions and grants

* Moderator: `POST /api/auth/moderator` with the code (`api/app.py:load_moderator_code`).
* Principals: moderator issues a one-time join code (`sessions.issue_join_code`); the tab
  exchanges it (`sessions.redeem_join_code`) for a bearer token bound to one principal, role,
  grant and episode. Coordinator session: `scenarios/policy_host.py:PolicyHost.client`.
* Grant checks: `tools/executor.py:_run_call` (`allowed_tools`, `grant_problem` for revoked and
  expired, before and after the duration); scope and limits in `tools/handlers.py` and the
  planner's `assess_authorization`.

## Candidate generation and ranking

Templates from `scenario.planning` → `candidates.single_edits` → `generate_edit_lists` (combos
≤ `max_combined_edits`, compatibility rules, cap/truncation) → `apply_edits` → `constraints.
assess_candidate` (hard checks, assumptions, preconditions, required holds, authorization) →
`objective.objective_components` → `objective.rank_candidates`. IDs `cand_NNNN_<sig8>` /
`rpt_NNNN_<sig8>`. Stored per evaluation; `apply_plan` reloads and revalidates
(`CampusAdapter.revalidate`).

## Activity lifecycle, clock and scoring

`domain/readiness.py:check_readiness` (preview/execution), reached through
`DomainAdapter.check_readiness(snapshot, activity_id, at, *, mode)`: the engine uses
`execution`, and `domain/projection.py:activity_views` uses `preview` with the episode's profile.
`store/engine.py:_process_instant`
records `started`/`completed`/`failed` with reasons and evidence; `refresh_ready` records
`planned`↔`ready`. Scoring reads only persisted visible records
(`evaluation/scoring.py:score_episode`, which takes the domain part from the adapter's
`score_outcome`); predicates are applied runner-side.

## Public/private projection boundary

* Public: `store/projection_db.py:build_view/build_snapshot` read only public tables;
  `EventStateView` visibility `audit` (organizer, moderator, trace) or `principal`.
* Private: `scenarios/private/*.json` → `world/world.py` (status answers at a time, due world
  events, steward confirmation of holds) and `scenarios/runner.py` (scheduled actor actions).
* Checks: static imports (`test_runner_isolation.py::test_policy_and_planner_cannot_reach_
  private_input`), payload scans (`world/leakcheck.py`).

## Trace export and replay path

`evaluation/export_trace.py:build_trace` (frames from `revision_snapshots`, sanitized
`tool_calls`, decisions, receipts, `evaluations` map, `final_state`, integrity hashes) →
`write_trace` → served by `GET /api/replays/{name}` → `web/src/replay/loader.ts` (GET only) →
`integrity.ts` (SubtleCrypto re-verification) → `ReplayView.tsx` (rehydrates evaluations,
renders `BoardView` read-only under the Recorded replay banner). CLI: `plan-b run-case`,
`plan-b demo-rejections`, `plan-b verify-trace`.
