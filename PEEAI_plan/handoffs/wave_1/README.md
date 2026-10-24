# Wave 1 handoff: deterministic foundation

Plan B ("The Show Must Go On"), Wave 1. This is a fictional campus event (Thursday 5 November 2026,
America/New_York) run as a local SQLite sandbox. It has persistent state, scoped authority, a
modeled clock, stateful tools, a bounded deterministic planner, a documented rule policy, a
browser board, and sanitized read-only replay.

There is **no LLM, pantry, MBTA or community deployment** in this wave, and **no comparative
claim**. The coordinator is the deterministic rule policy `rules/1.0.0`, and the only cases run
are development cases.

| | |
| --- | --- |
| Branch | `hackathon/peeaai-plan` (local; nothing pushed) |
| Planning baseline | `65997ac` |
| Implementation | `63aee9d` (app), `25363fb` (evidence collector), `3028cbf` (verify-only rule), `8b7aea3` (`.gitignore` order), `afe502e` (audit fixes; the evidence commit) |
| Packet | the commit that adds this directory (see `manifest.json` and the delivery note) |
| Runtime contract | 1.0.0 ([`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md)) |
| Trace format | 1.0.0 |

## M1 status

**Passed on the recorded automated checks. This is self-assessed: an independent audit of this
final state is still to come.**

An earlier read-only audit of Wave 1 found 45 issues, none high. All are resolved in `afe502e` and
in this packet, and VERIFICATION.md section 3 lists each one. All ten mandatory checks in
`waves/01_foundation.md` have a recorded outcome from a clean checkout of `afe502e`. That
checkout was a fresh `git worktree`, followed by `uv sync --all-groups --locked`, `npm ci`, and
then `scripts/collect_evidence.py`. Every command exited 0:

* Python: 455 tests passed, 0 skipped.
* Web: 362 tests passed; typecheck, build and boundary lint passed.
* Linters: ruff, ruff format and mypy are clean.
* Development cases: all five matched their honest expectations with 0 invariant violations.
* Rejection demo: all 20 steps got their expected result.
* Traces: all six exported traces verified intact.
* Browser: the walkthrough passed 41/41 checks in Chromium. It covers every step of the minimum
  visible workflow.
* Evidence: the identifier scan found no host name, user name, git email or local path.

`manifest.json` computes the same status from the evidence and git. [VERIFICATION.md](VERIFICATION.md)
maps each M1 check to its tests and evidence.

**Not verified:**

* comprehension by a new viewer;
* screen readers;
* Firefox and Safari;
* Python 3.11, which is declared but was not run.

These are product and acceptance criteria outside the ten M1 checks. They are listed in
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and were not reclassified as passed.

## Requirements

Python module paths are under `apps/plan_b/plan_b/`. `web/`, `tests/`, `docs/` and `scripts/` are
under `apps/plan_b/`.

| Item | Status | Where |
| --- | --- | --- |
| W1.1 typed contracts, campus adapter, public and private fixtures | Done | `domain/models.py`, `docs/RUNTIME_CONTRACT.md`, `domain/adapters/campus.py`, `scenarios/public/campus_showcase.json`, `scenarios/private/dev0{1,2,4,5,6}.json`; loading validates every reference (`validate_config`, `world/validate.py`) |
| W1.2 persistent state, authority, clock, stateful tools | Done | `store/` (SQLite, migrations 0001–0003, engine, sessions), `tools/executor.py`, `tools/handlers.py` |
| W1.3 bounded deterministic planner | Done | `domain/candidates.py`, `constraints.py`, `objective.py`: keep, swap, ±10 min shift, approved substitute, alternate format (none configured in the fixture), at most 2 edits, cap 64 |
| W1.4 deterministic policy, runner, scoring | Done | `evaluation/policies/{parser,rules}.py`, `scenarios/{runner,policy_host}.py`, `evaluation/scoring.py` (through the adapter) |
| W1.5 browser board | Done | `web/` (React 18, TypeScript, Vite) |
| W1.6 sanitized replay, verification, clean startup, M1 record | Done | `evaluation/export_trace.py`, `web/src/replay/`, `scripts/collect_evidence.py`, `scripts/write_manifest.py`, this packet |

**Tools.**

* Read and planning tools: `get_event_state`, `get_action_receipt`, `list_resources`,
  `query_status`, `evaluate_candidates`.
* Mutation tools: `hold_resource`, `release_hold`, `apply_plan`, `check_in`,
  `submit_observation`.
* Organizer tools: `update_goal` and `update_grant`.
* Moderator HTTP controls: the episode reset, the clock, policy runs, role links and trace
  export. The replay listing is public and read-only.

**Development cases.**

| Case | What it exercises | Outcome |
| --- | --- | --- |
| dev01 | The supplied case: the projector order is delayed (ETA 17:25, private arrival 17:24) | The policy verifies the delay and applies the free swap of demonstrations and skills. All activities complete; committed spend $0. |
| dev02 | A distinct case: a long delay (ETA 17:45, later than either demonstrations slot) | The policy holds the backup, asks the organizer, receives authorization, then makes the paid booking. All activities complete; committed spend $35.00. |
| dev04 | Stale and duplicate variant: a false alarm, a stale P09 reminder and its re-delivery and forwarded copy | The plan is kept and no commitment changes. |
| dev05 | Impossible variant: P17 cancelled, backup booked elsewhere | Infeasibility is reported. Demonstrations and closing fail visibly; nothing is spent. |
| dev06 | The status service is unavailable | Two bounded failed queries, then a robust swap. All activities complete. |

`plan-b demo-rejections` exercises the rejection paths. It produces 7 rejected receipts and 2
attempts with no receipt, each with its expected code, and then completes the legitimate paid
path once.

## Start and reproduce

```bash
cd apps/plan_b
uv sync --all-groups --locked
(cd web && npm ci && npm run build)
uv run plan-b serve                     # http://127.0.0.1:8765
```

**Moderator code.** Use the code in `apps/plan_b/var/moderator_code.txt` (created 0600 on first
start), or set `PLAN_B_MODERATOR_CODE`.

**Demo.**

1. Sign in as moderator, choose `dev01` and click **Load episode**.
2. Click **Run deterministic policy**.
3. For the facilitator and presenter, click **Issue join code**, then **Open in new tab**, and
   check in from each tab.
4. Advance the clock with **+1 / +5 / +10 min**, or set **Minutes** to 80 and click
   **Run 80 minutes with policy**.

**Reset.** Click **Reset: load a clean episode…**, then confirm with **Close it and load case
…**. This closes the old episode and revokes its sessions.

**Replay.**

1. Click **Export trace**, then **Open replay**. Board exports land in `var/traces`, which is
   always listed.
2. For headless runs, `plan-b run-case dev01 --db var/r.sqlite3 --out var/out` writes traces to
   `var/out/traces`. Serve them with `uv run plan-b serve --replay-dir var/out/traces`.

Replay issues GET requests only. It checks the trace's hashes in the browser and marks the board
when a check fails. The hashes are not signed.

**Full evidence regeneration** takes about 4 minutes, into a new or empty directory:

```bash
uv run python scripts/collect_evidence.py --out <new-or-empty-dir>
uv run python scripts/write_manifest.py --evidence <that dir>
```

Exact commands, exit codes and the environment are in [VERIFICATION.md](VERIFICATION.md). The
auditor's procedure is in [AUDIT_GUIDE.md](AUDIT_GUIDE.md).

## Packet contents

| File | Purpose |
| --- | --- |
| [AUDIT_GUIDE.md](AUDIT_GUIDE.md) | **Start here if you are auditing.** Reading order, reproduction, highest-risk paths, probes, and accept/reject criteria for M1 |
| [VERIFICATION.md](VERIFICATION.md) | What ran, where, with which result; M1 check mapping; review and audit history; the verify-only comparison; what did not run |
| [IMPLEMENTATION_MAP.md](IMPLEMENTATION_MAP.md) | Requirement → code → test → evidence; persistence, API, boundary |
| [DECISIONS.md](DECISIONS.md) | Why each semantic was chosen; departures from the plan; decisions taken after the review and the audit |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Scope, accepted defects, unverified criteria, simplifications |
| [WAVE_2_HANDOFF.md](WAVE_2_HANDOFF.md) | Stable interfaces, pantry extension path, LLM access state, tests that must keep passing |
| [CHECKLIST.md](CHECKLIST.md) | The working checklist kept during the wave |
| [manifest.json](manifest.json) | Generated by `scripts/write_manifest.py` from `evidence/` and read-only git. See the list below. |
| `evidence/reports/` | `checks.json` (every command, exit code, summary), JUnit XML, public outcome reports, rejection steps, fixture hashes, environment |
| `evidence/traces/` | Sanitized traces: successful (dev01), paid booking (dev02), impossible (dev05), rejected actions |
| `evidence/screenshots/` | 21 walkthrough screenshots (256-colour PNG, join links masked) and `walkthrough_report.json` |
| `evidence/runner_private/` | **Evaluator-side** outcome reports with the cases' predicates and expectations. Never feed them to a policy or the browser. The private cases they come from are tracked under `scenarios/private/` too. |

`manifest.json` records:

* the commits since the planning baseline, with author, committer, subject and trailers;
* the push state and versions;
* every check and its exit code;
* the pytest and web test counts;
* the walkthrough totals and workflow steps;
* the development case outcomes;
* the fixture and lockfile hashes;
* the identifier scan;
* the sha256, size and visibility of every evidence file;
* the M1 status computed from all of the above.

## Blockers and what remains

Nothing blocks Wave 1. What Wave 2 needs:

* **G-LLM.** The OpenRouter key is stored in `.local/keys/` (0600, ignored). It was checked with
  one read-only key request only. Still to do: choose the model and a spend cap, then make the
  first real call.
* **Per-episode caps** for every policy, the rule baseline included (KNOWN_LIMITATIONS).
* **Pantry adapter.**
* **The optional MBTA adapter.**
* **The community experience.**
* **Held-out evaluation** (Wave 3).

See [WAVE_2_HANDOFF.md](WAVE_2_HANDOFF.md).
