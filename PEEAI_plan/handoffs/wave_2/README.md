# Wave 2 handoff: live agent and bounded adaptation

Plan B ("The Show Must Go On"), Wave 2, built on the Wave 1 deterministic foundation
([`../wave_1/`](../wave_1/README.md)). Everything is still a fictional, local SQLite sandbox.
Wave 2 adds four things:

* **A live, model-driven coordinator** (`live/1.0.0`). It interprets notices with a language
  model, then chooses among server-built options. Every action goes through the Wave 1 executor.
* **A second event configuration** (a community skills exchange), with participant check-ins,
  resource offers and organizer goal versions.
* **The pantry profile**, with consumable stock, quantity reservations, staff-only receipts and
  distributions, and service scoring.
* **Per-episode caps and policy selection** for every coordinator policy.

All of it is **development evidence**: development cases, single live trials, and no held-out
evaluation or comparative claim. It is **not community validation**.

| | |
| --- | --- |
| Branch | `hackathon/peeaai-plan` (local; nothing pushed) |
| Base | `d6b9256` (the Wave 1 packet) |
| Implementation | `bf71e43` (the app, committed by the integrator from the tree the evidence describes); this packet is the commit after it |
| Runtime contract | 1.1.0 ([`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md); sections 15–17 are new) |
| Trace format | 1.0.0 (unchanged) |
| Model | `anthropic/claude-sonnet-5.5` via OpenRouter (requested and returned on every call) |
| Paid spend | 0.29906 USD in the ledger: 0.03509 for the G-LLM gate and 0.26397 for the 8 recorded live runs |

## M2 status

**Self-assessed. M2 is passed on the recorded checks except "Future comparison parity", which
is partial, and the live pantry run, which failed.** The details are in
[VERIFICATION.md](VERIFICATION.md), section 3.

| M2 check | Outcome |
| --- | --- |
| Live campus behavior | Pass: live dev01 recovery (query → consumed result → validated apply → fresh-state agreement); live dev04's stale P09 reminder was recorded `inapplicable` with its reasons, and its copy `duplicate` |
| Bounded failure behavior | Pass on 35 focused tests; a stale revision (skills_dev02) and a status outage (dev06) also occurred live |
| Community workflow | Pass |
| Shared pantry core | Pass |
| Stock and service accounting | Pass (24/16 → 40/0 in one staff receipt; target 40 throughout; service only at distribution) |
| Quantity failure checks | Pass |
| Staff boundary | Pass |
| Future comparison parity | **Partial**: P1 and P3 are not built, and the live policy has no stock options (the live pantry run reached 0 of 40) |

The checks behind this, all from the working tree on 2026-10-24
(`scripts/collect_wave2_evidence.py`, every command exited 0):

* **Python:** 634 tests passed, 0 skipped.
* **Web:** 379 tests passed; typecheck, build and boundary lint passed (25 read-only modules).
* **Linters:** ruff, ruff format and mypy are clean.
* **Development cases:** `plan-b run-case all` printed 9 lines, all `matches_expectation=True`,
  and the dev01–dev06 lines are byte-identical to the Wave 1 evidence.
* **Traces:** all 10 deterministic and 8 live traces are `intact`.
* **Browser:** both walkthroughs passed, 41/41 (Wave 1) and 30/30 (Wave 2), in Chromium.
* **Scans:** the credential-pattern and identifier scans found nothing.

The evidence was produced before the integrator's commit, so `environment.json` records
`app_tree_clean: false`. A clean-checkout regeneration needs no paid call (VERIFICATION.md,
section 8).

Before committing, the integrator re-ran the full battery on the tree that `bf71e43` commits,
with the same results: ruff, ruff format and mypy clean; 634 Python tests passed; web
typecheck, 379 tests, build and lint passed; `run-case all` printed 9 matching lines with the
dev01–dev06 lines identical to Wave 1, and all 9 traces verified `intact`; both walkthroughs
passed (41/41 and 30/30) with no model spend. On a clean sparse checkout of `bf71e43`, pytest
again passed 634 tests and `run-case all` printed the same 9 matching lines. The evidence
files themselves were not regenerated.

## Requirements

Module paths are under `apps/plan_b/plan_b/`.

| Item | Status | Where |
| --- | --- | --- |
| G-LLM gate | Passed once, 3 calls, 0.03509 USD (`evidence/reports/g_llm_gate.json`) | `agent/gate.py` |
| W2.1: provider and bounded live loop | Done | `agent/config.py`, `agent/provider.py` (strict structured output, spend guard and ledger), `agent/interpret.py`, `agent/menu.py`, `agent/orchestrator.py`, `agent/prompts/`, `.env.example`, `api/config.py`; tests `test_agent_boundary.py` and `test_agent_provider.py` |
| W2.2: selective policy and community workflow | Done, with one departure: the selective controller is `live/1.0.0` itself; no separate `agent/policies/selective.py` exists | `scenarios/public/community_skills_exchange.json`, `scenarios/private/skills_dev0{1,2}.json`, `api/participation.py`, resource offers in `tools/handlers.py`; web `views/Participation.tsx` and `components/DecisionCard.tsx` |
| W2.3: pantry adapter and staff controls | Done | `domain/adapters/pantry.py`, `domain/stock.py`, `tools/stock.py`, `store/migrations/0004_consumable_stock.sql`, `scenarios/public/pantry_continuity.json`, `scenarios/private/pantry_dev0{1,2}.json`, `evaluation/policies/pantry_rules.py`; web `components/PantryBoard.tsx` (in `components/` because the replay renders it) and `views/StaffActions.tsx`; tests `test_stock_conservation.py`, `test_pantry_workflow.py`, `test_pantry_fixture.py` |
| Per-episode caps and policy selection | Done | `scenarios/policy_host.py` (`EpisodeCaps` 48/8), `scenarios/runner.py`, `cli.py` (`--policy`), `api/app.py`; tests `test_integration_policy.py`, `test_integration_api.py` |
| W2.4: MBTA adapter (stretch) | **Not done** | — |
| W2.5: integrated adaptation gate | Partly done: this packet (live campus and community traces, a conserved pantry trace, failure checks, this M2 record). `tests/test_live_workflow.py` and `evaluation/development/` were not created, and parity is partial | `scripts/run_live_cases.py`, `scripts/collect_wave2_evidence.py`, `tests/e2e/walkthrough_wave2.py` |

**Development cases.** The campus dev01–dev06 cases are unchanged from Wave 1. The new cases:

| Case | Scenario | What it exercises |
| --- | --- | --- |
| skills_dev01 | `dev_fixture_02` | The peer lead's own check-in (until 11:05) breaks the planned 11:20 peer exchange; free swap of practice and peer exchange |
| skills_dev02 | `dev_fixture_02` | The organizer's goal-version change (preserve_order) lands while the coordinator's apply is in flight; the stale apply is rejected and the plan is re-decided |
| pantry_dev01 | `dev_fixture_03` | Target 40 kits; pantry 24, partner 16, shipment S20 (20) late; hold 16, staff handoff, commit 40, 40 distributed on time |
| pantry_dev02 | `dev_fixture_03` | Staff hands off only 10 of 16; 34 distributed and a disclosed 6-kit shortfall |

## Start and reproduce

```bash
cd apps/plan_b
uv sync --all-groups --locked
(cd web && npm ci && npm run build)
uv run plan-b serve                                   # http://127.0.0.1:8765
uv run plan-b run-case all --db var/r.sqlite3 --out var/out          # deterministic baselines
uv run python tests/e2e/walkthrough_wave2.py --out <dir>             # Wave 2 browser walkthrough
uv run python scripts/collect_wave2_evidence.py --out <empty dir> \
    --live ../../PEEAI_plan/handoffs/wave_2/evidence \
    --gate ../../PEEAI_plan/handoffs/wave_2/evidence/reports/g_llm_gate.json   # no paid call
```

Paid commands need `.local/keys/model_endpoint.env` and the key file. They respect the spend caps
of `PLAN_B_MODEL_MAX_RUN_COST_USD` and `PLAN_B_MODEL_MAX_TOTAL_COST_USD`:

```bash
uv run python -m plan_b.agent.gate --out <file>
uv run python scripts/run_live_cases.py --out <dir> dev01 dev04
uv run plan-b run-case dev01 --policy live --db var/live.sqlite3
```

The browser demos for the skills exchange, the pantry staff flow and the policy switch are in
[`apps/plan_b/README.md`](../../../apps/plan_b/README.md#wave-2-demos-browser).

## Packet contents

| File | Purpose |
| --- | --- |
| [VERIFICATION.md](VERIFICATION.md) | What ran and with which result; the M2 table; live runs; pantry accounting; spend; what did not run |
| [DECISIONS.md](DECISIONS.md) | Why each Wave 2 semantic was chosen, and where it departs from the plan |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Unpassed and partial items, live-run limits, simplifications, unverified criteria, disclosures |
| `evidence/reports/` | `checks.json` (every command, exit code and summary; case lines; live runs); `m2_focused_tests.json`; `pantry_accounting.json`; `wave1_parity.json`; `model_spend_summary.json`; `g_llm_gate.json`; the live-run records `live_*_run.json`; the public outcome summaries; the rejection steps; the JUnit XML; fixture hashes; the environment |
| `evidence/traces/` | Sanitized traces: 8 recorded live runs (`live_*`; one failed) and the deterministic pantry_dev01 (conserved), pantry_dev02 (partial handoff) and skills_dev01 |
| `evidence/screenshots/` | 12 Wave 2 walkthrough screenshots (256-colour PNG, join links masked) and both walkthroughs' JSON reports |
| `evidence/runner_private/` | **Evaluator-side** outcome reports with the cases' predicates and expectations (deterministic and live). Never feed them to a policy or the browser. |

## What remains (Wave 3 and open items)

* **Freeze the caps** (development values 48 tool calls and 8 model calls), the prompts, the
  model and the planner before any comparison.
* **Build P1 and P3**, and give every LLM policy the same pantry quantity options as P0, or keep
  the pantry suite out of any comparison.
* **Run held-out evaluation** with repeated live trials.
* **Store `AuthorizationRequest` state explicitly.**
* **Optionally, the MBTA adapter.**
* **The integrator's items:** the tree is committed (`bf71e43`). Still open: optionally add
  the agent modules to `tests/test_runner_isolation.py::ISOLATED_MODULES`, and regenerate the
  evidence from a clean checkout if a commit-pinned record is wanted.
