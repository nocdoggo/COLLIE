# Wave 1 decisions

Each entry gives the decision, the reason, and where it is enforced. The authoritative runtime
semantics are in [`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md);
this file records why those semantics were chosen and where the plan was extended or departed.

## D1. Stack, packaging and dependency boundary

* **Python 3.11–3.12, FastAPI, Pydantic v2, uvicorn; stdlib `sqlite3`.** This is the planned
  default (architecture doc). Locked versions: FastAPI 0.162.0, Pydantic 2.14.1, uvicorn 0.54.0,
  Starlette 1.9.0 (`apps/plan_b/uv.lock`). Dev: pytest 8, httpx, ruff 0.15, mypy, jsonschema;
  e2e: Playwright 1.64.1 (Chromium 1248) and Pillow 12.3.0, used only by
  `scripts/collect_evidence.py` to re-encode screenshots as 256-colour PNGs.
* **Independent boundary.** `apps/plan_b/pyproject.toml` + `uv.lock` create `apps/plan_b/.venv`.
  The repository-root COLLIE environment, its lockfile and research modules are untouched; no
  COLLIE module is imported (the reuse audit named only patterns, not code, as transferable to
  the event domain).
* **Browser:** React 18 + TypeScript (strict) + Vite, npm with a committed `package-lock.json`
  and exact versions. Built to `web/dist` (ignored) and served by the same FastAPI process, so
  production is one local process with no external service.
* **Layout departure.** The suggested tree (`api/`, `domain/`, …) sits under an importable package
  `apps/plan_b/plan_b/` so that names like `api`, `tools` and `domain` cannot collide with other
  top-level packages. `web/`, `tests/` and `docs/` sit beside it. Module names follow the wave
  plan where possible (`domain/candidates.py`, `domain/constraints.py`, `domain/objective.py`,
  `domain/adapters/{base,campus}.py`, `scenarios/runner.py`, `evaluation/policies/rules.py`,
  `evaluation/scoring.py`, `evaluation/export_trace.py`). The wave plan's `store/database.py`,
  `tools/` and `api/` exist; `domain/authority.py` is folded into `store/sessions.py` (session
  resolution) and `tools/executor.py` (grant checks) so authorization lives on the single
  executor path.

## D2. Runtime contract versus planning schema 0.2.0

The planning bundle describes selected artifacts and forbids additional properties, so the
runtime defines its own versioned contract (**runtime 1.0.0**) that *contains* planning fields
unchanged and adds runtime fields beside them. The planning schema and all 11 planning examples
are unchanged and still validate (`tests/test_contracts.py`). Runtime candidates, constraint
reports, receipts and observation records project back to planning-valid artifacts
(`plan_b/domain/planning_map.py`, validated against the planning schema in
`tests/test_planning_map.py`). Mapping table: contract section 1.

Gaps resolved explicitly (not by weakening an invariant):

| Gap in the planning bundle | Resolution |
| --- | --- |
| Only `apply_plan` had a request shape | One `ToolRequest` shape for all tools; per-tool argument models and a requirement table (`TOOL_REQUIREMENTS`) |
| Resource terms were only `booking_cost_cents` | `ResourceTerms`: booking requirement, commitment cost (= booking_cost_cents), hold fee, reserved exposure, hold lifetime, commitment cutoff, refundability, booking reference, status source |
| Edit templates, objective and tie-breaks were prose | Typed `PlanningConfig` and integer `ObjectiveWeights` in the public fixture |
| No tool durations | `tool_durations_minutes` in the public fixture (query 2 min; hold, release, apply 1 min; others 0) |
| No lifecycle or readiness records | `activity_events` (append-only) and `ReadinessReport` (preview/execution modes) |
| No sessions | Server sessions with hashed tokens, one-time join codes, a moderator code |
| Scenario controls and replay records | Moderator endpoints; trace format 1.0.0 with integrity hashes |
| Check vocabulary was open-ended | Fixed check ids with `passed/failed/not_applicable/unsupported` |
| Mutations "additionally require `expected_revision`, `idempotency_key` and `grant_id`" (`06_tool_contracts.md`) | A deliberate departure. `grant_id` is never required: the server-held session determines the grant, and a body that names a different one is refused (`GRANT_MISMATCH`). `expected_revision` is required for `hold_resource`, `release_hold`, `apply_plan`, `update_goal` and `update_grant`, and optional for `check_in` and `submit_observation`. Those two only append the caller's own declarations, so a concurrent change cannot make them wrong, and they still need an idempotency key. The requirements table is `TOOL_REQUIREMENTS` in `domain/models.py`. |

## D3. Fixture extensions (public `campus_showcase.json`)

Every extension is listed in the fixture's `fixture_extensions` with its reason, and
`derived_from` pins the planning fixture's SHA-256. Shared values are checked field by field
against the planning fixture (`test_runtime_public_fixture_traces_to_planning_fixture`).

* **x01 resource terms**: see D2. The backup projector: booking required, free hold for at most
  10 simulated minutes, 3500 cents reserved while held, 3500 cents committed on conversion,
  commitment cutoff 15 minutes before use. The projector order is booking reference `P17`.
* **x02 setup started**: planning `started: true` becomes an immutable `started` record at 16:30.
* **x03 host check-in**: planning `checked_in_roles: ["host"]` becomes a check-in record labeled
  `fixture_initial_state` (authored setup, not a runtime check-in). Presenter and facilitator are
  *not* checked in: their catalog availability is declared availability, not presence.
* **x04 presenter and host grants**: the planning fixture had a self-scoped grant only for the
  facilitator. `grant_presenter_self` and `grant_host_self` mirror it exactly (own check-in,
  observations, own receipts; no plan, goal, or other-participant changes; zero money).
* **x05 organizer grant**: the fixture's `review_required_for` items name organizer decisions but
  no organizer principal existed. `grant_organizer_demo` may change goal preferences and other
  principals' grants (`update_goal`, `update_grant`) bounded by the 15000-cent event budget, read
  any receipt (review authority), evaluate and submit observations. It cannot apply plans or hold
  resources.
* **x06 principals**: explicit registry of five demo principals, each bound to one role and grant.
* **x07 goal preferences**: `preference_preset` + integer weights (balanced 1/10/4/1000/5).
* **x08 planning menu**: keep; swap of the two independent middle activities; ±10-minute shifts
  of each middle activity; substitution of the approved backup projector; at most two combined
  edits; cap 64. No alternate format is configured for this event. The template exists, and
  `tests/test_alternate_format.py` exercises it on scratch configurations: generation, the
  combination rule, duration and resource effects, revalidation and apply through the executor,
  execution readiness and the scored final state.
* **x09 status sources**, **x10 tool durations**, **x11 program flag**.

The **coordinator grant is unchanged**: committed limit 0, reserved limit 3500, no `check_in`,
no `submit_observation`. It is never widened by fixture; only an authenticated organizer
`update_grant` (a recorded version, receipt and revision) can change it.

## D4. Private development cases

Private cases are runtime `PrivateCase` files under `plan_b/scenarios/private/` with opaque
names. DEV01 is derived from the planning evaluator (`derived_from` hash; the 16:40 status record
with ETA 17:25 and `order_P17_revision_4`; the 17:24 arrival with `receipt_P17`). Additions to
DEV01, recorded in its description: participant check-ins at 17:05 (facilitator) and 17:20
(presenter) as scripted exogenous actions, and the same simulated-organizer rule every case has.

| Case | Hidden condition | Distinct trajectory |
| --- | --- | --- |
| dev01 (DEV01) | ETA 17:25, arrival 17:24 | verify → swap the middle activities |
| dev02 (DEV02) | ETA 17:45, arrival 17:44 | verify → swap infeasible → verify backup → free hold → ask organizer → organizer raises the committed limit → paid backup booking at the original times |
| dev04 | P17 on schedule (16:58); stale P09 notice, its re-delivery and a forwarded copy | false alarm and stale/duplicate handling → keep, no spend |
| dev05 | P17 cancelled; backup booked elsewhere | no feasible candidate → explicit infeasibility; demonstrations and closing fail |
| dev06 | status service unavailable until 17:30; arrival 17:20 | bounded retries → robust choice over the declared outcomes |

All five share the same public start (the planning fixture's 16:40 state and notice), so the
policy cannot tell them apart except through what it observes. DEV03 is reserved for the pantry
case. The community skills-exchange profile is not a campus development case. These are
development fixtures, separate from the future C01–C08 held-out cases; passing them establishes
nothing about comparative policy performance.

**Scripted exogenous actors.** A check-in must come from the participant's own session through
`check_in`; the runner never writes check-ins. In headless runs, the private case schedules
those participant actions and a simulated organizer who answers an in-bounds authorization
request after a declared latency. Each is registered as a *scheduled actor action* (migration
`0002`) with the actor's own server-held session, and the clock engine executes it at its exact
instant through the same executor, even inside another caller's tool duration. That makes an
action's timing independent of what the policy happens to be doing (review finding
clock_execution-04/06). These are labeled harness inputs, identical for every policy. In the
browser, people perform them in separate role tabs.

## D5. Time, expiry and revisions

* One stored scenario clock per episode, UTC, whole minutes; display in `America/New_York`.
* Equal-timestamp order: completions → world events → scheduled actor actions → hold expiries →
  grant expiries → starts → event close. This makes the 18:00 deadline inclusive for completion
  while grants (which expire at 18:00) are already invalid for new actions at 18:00, and lets an
  arrival or a check-in at a start instant count for that start.
* Holds and grants are valid strictly before `expires_at`. Expiry is persisted when the clock
  reaches it (with a ledger entry and a revision); reads additionally compute effective status
  against the clock, so a missed cleanup could not make an expired hold look usable.
* One revision per state-changing event; reads, duplicate records, and empty clock moves never
  increment it. Readiness previews are recorded at the current revision without an increment.
* Tool durations are latency before the effect: the clock advances (processing events) and the
  request is then validated at the new time. A world change during that latency makes an
  `expected_revision` stale, which is the honest outcome.
* A missed start is a `failed` lifecycle record; Wave 1 has no in-place late start.

## D6. Idempotency, digests and receipts

* Scope `(episode, authenticated actor, key)`; digest = SHA-256 of canonical JSON of the
  validated `ToolRequest` (sorted keys, compact separators, UTF-8). The same function reproduces
  the planning example digest.
* Identical completed request → original receipt (`replayed_receipt: true`) **before** the stale
  revision is checked. Same key, different body → `IDEMPOTENCY_CONFLICT`, no receipt.
* Rejections past authentication and idempotency are durable `rejected` receipts that a retry
  returns again. That includes `SCOPE_VIOLATION` from a mutation tool.
* Failures after the session is resolved but before a receipt exists are recorded in the
  tool-call log as attempts without receipts. They are: episode closed, validation, unknown tool,
  event or grant mismatch, idempotency conflict, a tool outside the grant, and scope failures of
  `query_status` and `get_action_receipt`.
* Authentication failures (missing, unknown, revoked or expired token) and calls with a moderator
  session are answered but not persisted: before the session is resolved there is no actor and
  no episode to record them against.
* `get_action_receipt` returns `found` or `not_found`; `pending` is reserved because the receipt
  and idempotency record commit atomically. No outcome authorizes a fresh key.
* Observation and status-record identity is separate from request identity: a re-delivered or
  re-queried `(source_id, source_record_id)` returns the existing observation without a new
  revision; reusing a record id for different content is rejected.

## D7. Concurrency and transactions

Every tool call runs in one `BEGIN IMMEDIATE` transaction on a fresh connection
(`isolation_level=None`, so `sqlite3` never opens implicit transactions; WAL; busy timeout 30 s).
SQLite's write lock is taken before any read, so two requests cannot both read the same
capacity, budget or revision. Every connection also sets `foreign_keys` and `recursive_triggers`
on.

Database triggers (migrations 0001 and 0003) refuse, per table:

* `activity_events`, `ledger`: any UPDATE or DELETE (0001).
* `observations`, `receipts`, `candidates`: any UPDATE (0001) or DELETE (0003).
* `plans`, `goals`: any UPDATE or DELETE (0003). A new plan or goal version is a new row.
* `activities`:
  * any DELETE, and any UPDATE that sets `episode_id`, `activity_id` or `definition_json` (0003);
  * any lifecycle UPDATE other than planned/ready → planned, ready, started, failed or canceled,
    and started → completed or failed (0001 and 0003).
* `holds`: any DELETE (0003), and any UPDATE that sets `status` once the hold has left `active`
  (0001).

An UPSERT's DO UPDATE counts as an UPDATE. REPLACE conflict resolution (`INSERT OR REPLACE`,
`REPLACE INTO`, `UPDATE OR REPLACE`) deletes the conflicting row. SQLite fires DELETE triggers for
that delete only with `recursive_triggers` on, which every store connection sets. So a REPLACE
over an existing row of these tables is refused, but a connection without the pragma (for example
a bare `sqlite3` shell) can still replace rows.

These writes are not refused:

* inserting a new row;
* updating a hold's columns other than `status`;
* any write to the tables without triggers: `episodes` (including its `plan_version` and
  `goal_version` pointers), `episode_private`, `world_events_processed`, `scenario_config`,
  `resources`, `checkins`, `commitments`, `grants`, `sessions`, `join_codes`, `idempotency`,
  `evaluations`, `state_transitions`, `revision_snapshots`, `tool_calls`, `policy_decisions`,
  `runner_log` and `scheduled_actions`.

Unique indexes allow one reservation and one return per hold. The application never deletes or
rewrites any of these rows; the triggers are a second line of defense against direct edits.

## D8. Planner and policy

Planner: contract section 10, implemented in `domain/candidates.py`, `domain/constraints.py`,
`domain/objective.py`, `domain/adapters/campus.py`. Clarifications made during implementation
(none weakens a check):

* Checks with nothing in scope report `not_applicable` (omitted from planning projections), never
  a placeholder pass.
* `dependencies` also fails when a predecessor has failed or been canceled (it can never complete).
* `substitute_compatibility` fails when the original resource is not in the activity's active
  assignment.
* Two alternate-format edits on one activity are never combined.
* A hold or commitment that belongs to a candidate assignment (same resource and activity, window
  covering) is not counted again as extra capacity use.
* Applying a candidate that changes nothing is rejected (`UNSUPPORTED_ACTION`): keeping the plan
  needs no mutation.

Policy: contract section 11 (`evaluation/policies/rules.py`, `parser.py`). It is a documented
rule policy for the supported message forms, not a natural-language reasoner.

## D9a. Decisions taken in response to the independent review

The first review round (VERIFICATION.md, section 3) produced 33 findings. Fixing them required these
semantic decisions, each recorded in the contract:

* **Authority before time.** A grant that is revoked or expired when a request arrives is
  rejected before the tool's modeled duration, so a principal without authority cannot move the
  shared clock. One's own receipts stay readable after revocation or expiry, so a lost response
  can always be reconciled.
* **Steward confirmation.** `hold_resource` on a booking-required resource asks its steward (the
  resource's registered status source in the private world). If the steward reports the
  resource unavailable, the hold is refused with no private record disclosed. Before this, a
  backup that the world said was booked elsewhere could be held, booked and "used" on catalog
  availability alone. The steward is asked last, immediately before the hold is written (audit
  M1-INV-01), so a hold past its cutoff or beyond the requester's authority is refused for that
  public reason.
* **Latest check-in.** A person's latest check-in is their current declaration (readiness,
  planner and scorer agree), so a later, narrower availability supersedes an earlier one.
* **Effective time.** The planner judges time-dependent checks (no past change, commitment
  cutoff, hold liveness, grant validity) at the time an apply issued now would take effect. A
  candidate reported applicable is then still valid when its apply executes.
* **Hearsay.** A participant's or organizer's claim about the supplier's equipment may be
  verified, but on its own never triggers holds, asks or robust plan changes. Equipment
  delivery claims are spoken for by the supplier contact and the registered status source.
* **Strict message forms instead of cue lists.** Two rounds of cue-list patches (a whole-sentence
  negation guard, then clause scoping) each failed independent verification in a different
  direction: genuine claims rejected, or "If the van breaks down, order P17 will be cancelled."
  asserted. The rule policy now accepts a claim only when its whole sentence matches a supported
  template and every other sentence is a status pointer or a greeting
  (`rules-parser/1.2.0`). Anything else is `unresolved`, which is what the plan asks of P0
  ("parse supported fixture messages conservatively"). On an independent 80-message corpus and
  67 adversarial texts it asserts nothing wrongly.
* **Verify-only for unsupported wording.** An unresolved notice that says something about
  delivery status and identifies exactly one equipment resource may trigger a status query
  (contract section 11, commit `3028cbf`). The notice is never weighed as a claim; only the typed
  status the query returns drives planning.
  * It is answered only by a check *requested* at or after it arrived, since a check answers as
    of its request time. A check already in flight does not count.
  * It joins a supported claim's check of the same resource. Otherwise its check runs *after*
    the decision step, so supplier chatter cannot delay a hold, an ask or a commit.
  * No check is made, and a `not_checked` decision says why, when the notice is session text and
    the resource's status is fresh, or when fresh typed status already rules the resource out for
    every activity that would use it.

  Two earlier rules were rejected on measured evidence. A 30-minute freshness skip never verified
  a genuine notice arriving after the 16:40 check. Verifying every notice at once let chatter push
  dev02's backup hold past its cutoff. Across 3,131 scratch scenario variants the chosen rule
  loses no case the freshness skip won and recovers 59 that it lost (VERIFICATION.md, section 4).
* **Exogenous wake.** After a policy run, any revision the policy did not produce itself
  re-wakes it on the next tick, as does an incomplete run or an exhausted tool budget.
* **Reset races.** A closed episode's clock never moves, no session is issued for it, nothing
  is recorded into it, and moderator controls racing a reset answer 409 `EPISODE_CLOSED`.
* **Failure containment.** Each tool call runs inside a savepoint: an unexpected server error
  rolls back the call's effects and is recorded as an `INTERNAL_ERROR` attempt. A domain
  rejection raised inside a handler also rolls back that handler's writes, through a
  per-handler savepoint (audit M1-INV-02). The tool duration, the rejected receipt, the
  idempotency record and the call log are kept. Request-argument
  times must be whole minutes, and the log stores validated requests only (field names for
  rejected bodies).

## D9b. Decisions taken in response to the Wave 1 audit

The audit found 45 issues, none high (VERIFICATION.md, section 3). Besides the steward order and
the handler rollback above, these semantic decisions came from it. Each is recorded in the
contract.

* **Loading refuses broken references** (REQ-01). `validate_config` resolves every reference in
  a public scenario and refuses an initial plan that fails a hard check, except the two
  evidence-dependent checks (`resource_status`, `arrival_assumptions`).
  `world/validate.py:validate_case` checks a private case against its scenario, so a typo in a
  status entity can no longer run silently and still report `matches_expectation=True`.
* **Scoring through the adapter** (REQ-03, F3). `score_episode` takes goal attainment and domain
  violations from `DomainAdapter.score_outcome`. Preview readiness goes through the adapter for
  the episode's own profile. Outputs on every development case are byte-identical to before.
* **Status lineage** (REQ-11). A status observation joins the correlation group its source
  record names (`projector_delivery_01` for order P17), so the runtime reproduces the planning
  example `observation_after_query.json`. Records that name none keep `<entity_id>_status`.
* **No policy wake after close** (REQ-12). The runner does not wake the policy at or after the
  event close, or once its grant has expired. Clean runs no longer end with a rejected
  `GRANT_EXPIRED` read, so `rejected_attempts_without_receipt` is 0 for every successful
  development case (it was 1).
* **History guards** (F9). Migration `0003` adds the triggers listed in D7.
* **Exports name the policy that ran** (WEB-5). `source.policy_id` comes from the episode's
  recorded decisions: `null` for a clock-only episode.
* **Equivalent trace verifiers** (WEB-3). The browser and `plan-b verify-trace` make the same
  checks and are tested on shared vectors. Their hashes are not signed (KNOWN_LIMITATIONS).
* **Join codes off the page** (C1). The moderator panel shows a four-character prefix; the full
  code is only in the link target, and evidence screenshots mask the links.

## D9. Public/private boundary

Private input is loaded only by `plan_b/world/`, the runner, and `evaluation/export_trace.py`. The
exporter loads the case only to refuse an export that would leak it; the CLI and the moderator
export endpoint both reach it. Its episode linkage is a
separate table (`episode_private`) that no projection reads. The policy and planner modules are
checked statically for forbidden imports. Every envelope the policy received, every planner
snapshot, HTTP state payloads, the built browser bundle and exported traces are scanned for
private markers: structural keys, the case description, and any status record or world event
value that was not yet public at that payload's scenario time.

## D10. Research sources used for implementation details

| Source | Used for |
| --- | --- |
| [SQLite: Transaction](https://www.sqlite.org/lang_transaction.html) | `BEGIN IMMEDIATE` takes the write lock at `BEGIN`, preventing read-then-write races between connections |
| [Python 3.12 `sqlite3`](https://docs.python.org/3.12/library/sqlite3.html) | `isolation_level=None` disables implicit transactions on 3.11 and 3.12 (the `autocommit` attribute is 3.12-only); `executescript` behavior for migrations |
| Planning bundle `PEEAI_plan/` 0.2.0 | Source of truth for scope, semantics and fixtures |
