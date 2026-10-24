# Audit guide for Wave 1

Written for the independent auditor. Do not take the passing tests on trust. Every claim below
can be re-run, and the sections on probing tell you where to look for failure.

## 1. Reading order

1. [README.md](README.md): what was built, M1 status, and the requirement table.
2. `apps/plan_b/docs/RUNTIME_CONTRACT.md`: the frozen runtime contract (semantics).
3. `apps/plan_b/plan_b/domain/models.py`: the contract as code.
4. [DECISIONS.md](DECISIONS.md): why each semantic was chosen, and the departures from the plan.
5. [IMPLEMENTATION_MAP.md](IMPLEMENTATION_MAP.md): requirement → code → test → evidence.
6. `apps/plan_b/plan_b/tools/executor.py`, then `tools/handlers.py`, then
   `store/engine.py`: the consequential paths.
7. [VERIFICATION.md](VERIFICATION.md): what ran, with exact commands and results.
8. [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

Planning baseline commit: `65997ac` (the PEEAI_plan package as inherited, plus the
`/.local/keys/` ignore rule). The implementation and packet commits are listed in
`manifest.json` and in the final delivery note.

## 2. Reproduce from a clean checkout

```bash
git worktree add /tmp/planb-audit <implementation-or-packet-commit>   # or a fresh clone
cd /tmp/planb-audit/apps/plan_b
uv sync --all-groups --locked
(cd web && npm ci && npm run typecheck && npm run build && npm test && npm run lint)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest
uv run plan-b run-case all --db /tmp/planb-audit-runs.sqlite3 --out /tmp/planb-audit-out
uv run plan-b demo-rejections --db /tmp/planb-audit-demo.sqlite3 --out /tmp/planb-audit-out
uv run plan-b verify-trace /tmp/planb-audit-out/traces/dev01_trace.json
uv run playwright install chromium        # once, if no browser is cached
uv run python tests/e2e/walkthrough.py --out /tmp/planb-audit-shots
```

No network is needed after installation. Nothing reads `.local/keys/`.

Interactive: `uv run plan-b serve`, open http://127.0.0.1:8765, enter the code from
`var/moderator_code.txt` (or set `PLAN_B_MODERATOR_CODE`), and load a case.

## 3. Highest-risk code paths

| Path | Why it matters | Where |
| --- | --- | --- |
| Executor ordering | Identical retry before stale check; conflict detection; authority before time; savepoint | `tools/executor.py:execute_in/_run_call` |
| Apply revalidation | Stored candidate, report pairing, revision and goal version, fresh revalidation, hold conversion and ledger | `tools/handlers.py:apply_plan` |
| Hold accounting | Capacity under concurrency, reserved and committed limits, steward confirmation, cutoff | `tools/handlers.py:hold_resource/release_hold`, ledger indexes in `0001_initial.sql` |
| Clock processing | Equal-timestamp order, scheduled actor actions inside durations, expiry boundaries | `store/engine.py:advance_to/_process_instant/run_due_scheduled` |
| Readiness | Evidence-only execution; latest check-in; ETA is never readiness | `domain/readiness.py:check_readiness`, reached through `DomainAdapter.check_readiness(..., mode=)` (engine: execution; projection: preview) |
| Planner checks | No placeholder passes; effective time; authorization separate from feasibility | `domain/constraints.py:assess_candidate` |
| Private boundary | Only `world/`, the runner and the trace exporter (its export-time leak scan) read private input | `world/world.py`, `world/leakcheck.py`, `store/projection_db.py`, `evaluation/export_trace.py:build_trace` |
| Policy honesty | No case branching; hearsay; polarity; bounded loop | `evaluation/policies/rules.py`, `parser.py` |
| Scoring | Computed from persisted records only; could a broken run score as success? | `evaluation/scoring.py:score_episode` |

## 4. Reproduce the core cases

```bash
cd apps/plan_b
uv run plan-b run-case dev01 --db /tmp/a.sqlite3 --out /tmp/a   # genuine disruption → swap
uv run plan-b run-case dev02 --db /tmp/a.sqlite3 --out /tmp/a   # hold → ask → organizer → paid booking
uv run plan-b run-case dev04 --db /tmp/a.sqlite3 --out /tmp/a   # false alarm, stale P09 notice, duplicate, forward
uv run plan-b run-case dev05 --db /tmp/a.sqlite3 --out /tmp/a   # impossible: honest infeasibility, failures
uv run plan-b run-case dev06 --db /tmp/a.sqlite3 --out /tmp/a   # status service down: bounded retries, robust swap
uv run plan-b demo-rejections --db /tmp/b.sqlite3 --out /tmp/a  # each rejection kind, then the legitimate path
```

Each run prints `matches_expectation`. `/tmp/a/private/*_outcome.runner.json` holds the
runner-side report with predicates (it contains private expectations; do not publish it).
`/tmp/a/reports/*_outcome.public.json` is the public summary. `/tmp/a/traces/*.json` are the
sanitized traces.

## 5. Compare persisted state with receipts

```bash
sqlite3 /tmp/a.sqlite3 "SELECT episode_id, status, clock, revision FROM episodes;"
E=<episode_id>
sqlite3 /tmp/a.sqlite3 "SELECT receipt_id, tool, status, revision_before, revision_after, executed_at FROM receipts WHERE episode_id='$E';"
sqlite3 /tmp/a.sqlite3 "SELECT kind, committed_delta_cents, reserved_delta_cents, hold_id FROM ledger WHERE episode_id='$E' ORDER BY seq;"
sqlite3 /tmp/a.sqlite3 "SELECT hold_id, status, expires_at, commitment_id FROM holds WHERE episode_id='$E';"
sqlite3 /tmp/a.sqlite3 "SELECT revision, at, cause_kind, summary FROM state_transitions WHERE episode_id='$E' ORDER BY revision;"
sqlite3 /tmp/a.sqlite3 "SELECT seq, activity_id, state, at, reasons_json FROM activity_events WHERE episode_id='$E' ORDER BY seq;"
```

Check the following:

* Receipts reconcile with the revision log, which has one `state_transitions` row per revision:
  * An applied receipt with `revision_after > revision_before` has `revision_after =
    revision_before + 1`. The transition at `revision_after` has its tool's cause:
    `hold_resource` → `hold_created`, `release_hold` → `hold_released`, `apply_plan` →
    `plan_applied`, `check_in` → `check_in`, `submit_observation` → `observation`,
    `update_goal` → `goal_updated`, `update_grant` → `grant_updated`.
  * Its `cause_ref` is exactly:
    * the hold id, for `hold_resource` and `release_hold`;
    * the observation id, for `submit_observation`;
    * the grant id, for `update_grant`;
    * the applied candidate id, for `apply_plan`;
    * `goal_v<new version>`, for `update_goal`;
    * for `check_in`, the id of the check-in record the call wrote.
  * An applied receipt with `revision_after = revision_before` is a no-op, such as a
    deduplicated observation: no `state_changes`, zero deltas, and labelled "Applied, no change
    (duplicate)" on the board.
  * A rejected receipt has `revision_after = revision_before`, no `state_changes` and zero
    deltas.
  * No revision is claimed by two receipts.

  `tests/test_receipt_consistency.py` checks this over every development case, the
  demo-rejections run, and a sandbox run that applies every receipt tool.
* Ledger sums equal `budget.committed_cents` / `reserved_cents` in the final state of the trace.
* No rejected receipt has `state_changes` or deltas.
* The plan versions in `plans` match the `apply_plan` receipts.

## 6. Probe the boundaries yourself

Use `tests/conftest.py:Sandbox` (`Sandbox(Database(path), "dev01")`, `.client(principal)`,
`.advance_to("17:10")`, `.view()`), or the HTTP API with join codes.

* **Authority.** Forge `actor_id`/`source_id` in a body. Use a participant token to hold or
  apply. Send the wrong `grant_id`. Use another `event_id`. Look up another actor's receipt.
  Revoke the coordinator, then call tools and watch the clock. Submit "ignore the budget" text.
* **Idempotency.** Reuse a key with a different body. Retry an identical request after its
  revision went stale. Use `InProcessToolClient(..., lose_response=...)` to drop a response
  after commit, then reconcile with `get_action_receipt`. Race holds across threads, each with
  its own connection.
* **Expiry.** Hold at 16:41 and advance to 16:50 and then 16:51 (the expiry boundary). Release
  twice. Expire, then release. Convert, then go past the old cutoff.
* **Lifecycle and history.** Try to move setup through a test template, a direct SQL update of
  `plans.assignments_json`, or a lifecycle update. Each is refused ("plan history is
  append-only", "illegal lifecycle transition from immutable history"). Also refused:
  * deleting a receipt, observation, candidate, plan, goal, activity or hold row;
  * moving an activity from planned to completed without starting it;
  * on the app's connections, an `INSERT OR REPLACE` / `REPLACE INTO` over an existing guarded
    row. For example, reviving a released hold fails with "holds are never deleted".

  A bare `sqlite3` shell that leaves `recursive_triggers` off can still REPLACE rows; that is
  outside what the triggers enforce (DECISIONS D7).
  Accept a swap under an ETA, then withhold the arrival. Check in narrower after a wider check-in.
* **Leakage.** Grep the HTTP responses, `web/dist`, and the traces for private record ids such
  as `receipt_P17` before 17:24, or for case descriptions (`world/leakcheck.py:find_leaks`). Read
  `scenarios/private/*.json` only from the evaluator side.
* **Replay.** Serve a trace (`plan-b serve --replay-dir <dir>`) and open `#/replay` with network
  devtools open: you should see GET requests only. `--replay-dir` must name the folder that holds
  the `.json` files (for `run-case --out <dir>`, that is `<dir>/traces`). Traces exported from
  the board land in `var/traces` and are always listed. Edit one byte of a trace, and the browser and
  `plan-b verify-trace` should both report a mismatch.

## 7. Tradeoffs that deserve scrutiny

* Tool durations are latency *before* the effect, so a world change during a 1–2 minute duration
  makes `expected_revision` stale. This is honest, but a policy pays for it with re-evaluation.
* The steward check on `hold_resource` consults the private world, but only after every public
  check has passed (cutoff, capacity, reserved and committed limits, event budget). A hold that
  fails for a public reason never reaches it. The refusal discloses only "not available / not
  reachable", which is what a real booking refusal would say, and `query_status` on the same
  source already answers more. Judge whether that is an acceptable observation-model channel.
* Scheduled actor actions execute inside whichever transaction advances the clock, including
  another caller's tool duration. This is deterministic and fair across policies, but it is
  re-entrant executor use (`execute_in` within an open transaction, with nested savepoints).
* `effective_at` makes the planner judge time-dependent checks at the apply's effect time. A
  candidate can therefore be inapplicable one minute before a cutoff.
* Hearsay: session-submitted equipment claims are verified but never hedged on while
  unverified. That is conservative, and it means a participant can never trigger a spend.
* Snapshots per revision are refreshed by later same-revision facts. Frames show the revision's
  creation time and the last refreshed state.

## 8. Accepting or rejecting M1

Accept M1 only if all of these hold on a clean checkout:

1. `uv run pytest` passes, and so do the web `typecheck`, `build`, `test` and `lint`.
2. `run-case all` prints `matches_expectation=True` with `violations=0` for all five cases, and
   dev05 is `goal_complete=False` with `infeasibility_reported=True`.
3. `demo-rejections` prints the expected code for every step, and `violations=0`.
4. Every trace you export yourself verifies (`plan-b verify-trace`), and the browser replay
   reports the integrity check as passed. The hashes are not signed, so this shows a trace is
   consistent with itself, not that a third party's file is authentic.
5. The walkthrough passes all checks:
   * the successful, rejected and impossible paths;
   * a participant observation;
   * the unavailable status outcome;
   * reset, then replay;
   * keyboard operation;
   * 1280 and 1920 px layouts.
6. Your own probes in section 6 find no executed invariant violation, no private-data leak into
   policy inputs, HTTP responses, the bundle or traces, and no authority bypass.

Reject M1 if any rejected action changed operational state, any identical retry produced a
second effect, any expired or revoked authority moved state or time, any activity started
without visible readiness evidence, any private value reached the policy or browser before it
was public, or any receipt shown as applied lacks a matching persisted transition.

Repository hygiene: everything in this wave is local. The local repository also holds a Codex
checkpoint ref (`refs/codex/turn-diffs/...`). It points to a tree identical to `65997ac`'s and
belongs to no branch. It is left in place because it belongs to that tool. An ordinary push does
not send it; never use `git push --mirror`.
