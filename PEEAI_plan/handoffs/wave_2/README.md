# Wave 2 handoff: live agent and bounded adaptation

Plan B ("The Show Must Go On"), Wave 2, built on the Wave 1 deterministic foundation
([`../wave_1/`](../wave_1/README.md)). Everything is still a fictional, local SQLite sandbox.
Plan B helps a community event stay on track when its plan is disrupted: a coordinator reads
notices, checks sources, holds reversible backups, asks the organizer for spending authority,
and commits only plans the server has checked, each with a receipt. Wave 1 built that loop with
a deterministic rule baseline (P0, `rules/1.0.0`). Wave 2 adds four things:

* **A live, model-driven coordinator** (`live/1.0.0`, P2). It interprets notices with a
  language model, then chooses among server-built options, the pantry's stock options included.
  Every action goes through the Wave 1 executor. The comparison policies P1 (`tool-use/1.0.0`)
  and P3 (`verify-all/1.0.0`) share its harness.
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
| Implementation | `bf71e43` (the app, committed by the integrator from the tree the evidence describes); the first version of this packet is the commit after it (`fd04d48`). The finishing step (2026-10-25: P1, P3, the pantry stock options of P2, the development runs, the demo runbook, and the audit step's P1 reruns and fixes) is committed by its integration step as `9158793` (the app) and `c4f7cd9` (this packet); the evidence is regenerated from a clean checkout of `c4f7cd9` in the commit after it |
| Runtime contract | 1.1.0 ([`apps/plan_b/docs/RUNTIME_CONTRACT.md`](../../../apps/plan_b/docs/RUNTIME_CONTRACT.md); sections 15–18 are new) |
| Trace format | 1.0.0 (unchanged) |
| Model | `anthropic/claude-sonnet-5.5` via OpenRouter (requested on every call, and returned on every answered call) |
| Paid spend | 2.91545 USD in the ledger (136 entries): 0.03509 for the G-LLM gate, 0.26397 for the 8 Wave 2 live runs, 1.66656 for the finishing step's 15 P1-P3 development runs and its P1 pantry rerun, 0.91328 for the audit step's 4 P1 reruns, and 0.03655 for its one browser press of **Run live agent** |

## M2 status

**Self-assessed. M2 is passed on the recorded checks.** The first version of this packet had
"Future comparison parity" partial and its live pantry run failed. The finishing step
(2026-10-25) built P1 and P3, gave P2 the pantry's stock options, and recorded one development
run each of P1, P2 and P3 on five cases, and reran P1's failed pantry run after fixing its
harness; the audit step reran P1's other four `tool_use.v1` runs under the shipped
`tool_use.v2`. The live pantry result is now the P2 run
`live_p2-live_pantry_dev01`, which completed 40 of 40 on time. W2.4 (MBTA) is a stretch item and
was not built. The details are in [VERIFICATION.md](VERIFICATION.md), sections 1b, 3 and 4.

| M2 check | Outcome |
| --- | --- |
| Live campus behavior | Pass: live dev01 recovery (query → consumed result → validated apply → fresh-state agreement); live dev04's stale P09 reminder was recorded `inapplicable` with its reasons, and its copy `duplicate` (Wave 2 runs from the `bf71e43` tree; reproduced with the finishing step's code by `live_p2-live_dev01` and `live_p2-live_dev04`) |
| Bounded failure behavior | Pass on 57 mapped tests (22 of them for P1–P3); a stale revision (skills_dev02) and a status outage (dev06) also occurred live, and so did malformed output and exhausted model-call caps in P1 runs |
| Community workflow | Pass |
| Shared pantry core | Pass; P1, P2 and P3 also completed pantry_dev01 live (P1 after a fix to its prompt and its turn token limit) |
| Stock and service accounting | Pass (24/16 → 40/0 in one staff receipt; target 40 throughout; service only at distribution) |
| Quantity failure checks | Pass |
| Staff boundary | Pass |
| Future comparison parity | Pass: P0–P3 read the same grant, tools and candidates and run through one executor (parity tests); P1–P3 ran end to end with the real model with recorded prompts (20 development runs, 15 current) |

The checks behind this table come from a clean checkout of the packet commit `c4f7cd9` on
2026-10-25 (`scripts/collect_wave2_evidence.py`; all 56 checks exited 0; VERIFICATION.md
sections 1, 1d and 2):

* **Python:** 764 tests passed, 0 skipped.
* **Web:** 392 tests passed; typecheck, build and boundary lint passed (25 read-only modules).
* **Linters:** ruff, ruff format and mypy are clean.
* **Development cases:** `plan-b run-case all` printed 9 lines, all `matches_expectation=True`,
  and the dev01–dev06 lines are byte-identical to the Wave 1 evidence.
* **Traces:** the 10 deterministic traces the collector regenerated (3 of them are kept in
  `evidence/traces/`) and the 28 recorded live traces are all `intact`.
* **Browser:** both walkthroughs passed, 41/41 (Wave 1) and 30/30 (Wave 2), and the demo
  storyboard 32/32, in Chromium.
* **M2 focused tests:** every mapped test passed (parity 101, bounded failure 57).
* **Scans:** the credential-pattern and identifier scans found nothing.

The recorded live runs were made once each, from working trees: the 8 Wave 2 runs before the
first commit, and the 20 P1–P3 development runs (15 current, all matching; 5 superseded P1 runs
under `tool_use.v1`) in the finishing and audit steps (VERIFICATION.md, sections 1b and 1c). The
rest of the evidence was regenerated from the clean checkout, with no paid call.
`environment.json` records `git_head = c4f7cd9…` and `app_tree_clean: true`. The same battery
also passed on the working tree before the integration step's commits (section 1d). The first
version of this packet was regenerated the same way from `fd04d48` on 2026-10-24.

For the first version, the integrator re-ran the full battery on the tree that `bf71e43` commits,
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
| W2.2: selective policy and community workflow | Done. The selective controller is `live/1.0.0` (P2); `agent/policies/selective.py` re-exports it | `agent/policies/selective.py`, `scenarios/public/community_skills_exchange.json`, `scenarios/private/skills_dev0{1,2}.json`, `api/participation.py`, resource offers in `tools/handlers.py`; web `views/Participation.tsx` and `components/DecisionCard.tsx` |
| W2.3: pantry adapter and staff controls | Done | `domain/adapters/pantry.py`, `domain/stock.py`, `tools/stock.py`, `store/migrations/0004_consumable_stock.sql`, `scenarios/public/pantry_continuity.json`, `scenarios/private/pantry_dev0{1,2}.json`, `evaluation/policies/pantry_rules.py`; web `components/PantryBoard.tsx` (in `components/` because the replay renders it) and `views/StaffActions.tsx`; tests `test_stock_conservation.py`, `test_pantry_workflow.py`, `test_pantry_fixture.py` |
| Per-episode caps and policy selection | Done | `scenarios/policy_host.py` (`EpisodeCaps` 48/8), `scenarios/runner.py`, `cli.py` (`--policy`), `api/app.py`; tests `test_integration_policy.py`, `test_integration_api.py` |
| W2.4: MBTA adapter (stretch) | **Not done** | — |
| W2.5: integrated adaptation gate | Done: live campus, community and pantry traces, a conserved pantry trace, failure checks, candidate and authority parity for P0–P3, the development results, and this M2 record | `tests/test_live_workflow.py`, `tests/test_policy_parity.py`, `tests/test_pantry_live_menu.py`, `plan_b/evaluation/development/`, `scripts/run_live_cases.py` (`--policy`), `scripts/write_development_results.py`, `scripts/collect_wave2_evidence.py`, `tests/e2e/walkthrough_wave2.py` |
| P1 and P3, and P2's pantry options (finishing step) | Done | `agent/policies/tool_use.py` (prompt `tool_use.v2`), `agent/policies/verify_all.py`, `agent/menu.py` and `agent/orchestrator.py` (prompt `choose_action_pantry.v1`), policy selection in `scenarios/policy_host.py`, `cli.py`, `api/`; tests `test_live_workflow.py`, `test_policy_parity.py`, `test_pantry_live_menu.py`, `test_comparison_policy_fixes.py`, `test_model_policy_surfaces.py`, `test_tool_use_hold_window.py`, `test_runner_isolation.py` |

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
uv run python tests/e2e/storyboard.py --out <dir>                    # the demo story (DEMO.md)
uv run python scripts/collect_wave2_evidence.py --out <empty dir> \
    --live ../../PEEAI_plan/handoffs/wave_2/evidence \
    --gate ../../PEEAI_plan/handoffs/wave_2/evidence/reports/g_llm_gate.json   # no paid call
```

Paid commands need `.local/keys/model_endpoint.env` and the key file. They respect the spend caps
of `PLAN_B_MODEL_MAX_RUN_COST_USD` and `PLAN_B_MODEL_MAX_TOTAL_COST_USD`:

```bash
uv run python -m plan_b.agent.gate --out <file>
uv run python scripts/run_live_cases.py --out <dir> dev01 dev04
uv run python scripts/run_live_cases.py --out <dir> --policy tool-use dev01   # or live, verify-all
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
| [DEMO.md](DEMO.md) | The seven-minute demo runbook: story, setup, run of show, fallbacks, claims and their evidence, and an automated dry-run record |
| `evidence/reports/` | `checks.json` (every command, exit code and summary; case lines; live runs); `m2_focused_tests.json`; `pantry_accounting.json`; `wave1_parity.json`; `model_spend_summary.json`; `g_llm_gate.json`; the live-run records `live_*_run.json`; the public outcome summaries; the rejection steps; the JUnit XML; fixture hashes; the environment |
| `evidence/traces/` | Sanitized traces: 8 Wave 2 live runs (`live_<case>`; one failed), 20 P1–P3 development runs (`live_p1-tool-use_*`, `live_p2-live_*`, `live_p3-verify-all_*`; five superseded), and the deterministic pantry_dev01 (conserved), pantry_dev02 (partial handoff) and skills_dev01 |
| `evidence/screenshots/` | 12 Wave 2 walkthrough screenshots (256-colour PNG, join links masked) and both walkthroughs' JSON reports |
| `evidence/storyboard/` | The demo's 24 captioned frames (256-colour PNG, join links masked) and `storyboard_report.json`, from `tests/e2e/storyboard.py`; DEMO.md links them |
| `evidence/runner_private/` | **Evaluator-side** outcome reports with the cases' predicates and expectations (deterministic and live). Never feed them to a policy or the browser. |
| [`apps/plan_b/plan_b/evaluation/development/`](../../../apps/plan_b/plan_b/evaluation/development/README.md) | The P1–P3 development runs as one JSON and one table, with a sentence per run read from its trace (no comparison) |

## What remains (Wave 3 and open items)

* **Freeze the caps** (development values 48 tool calls and 8 model calls), the prompts
  (P1's `tool_use.v2`, P3's relevance rule), the per-policy output-token limits (P1 4096 per
  turn; P2 and P3 1024 per choice, 2048 per interpretation), the model and the planner before
  any comparison. P1 reached the 8-call model cap in three of its five current development runs.
* **Wake every policy when the pantry handoff window opens** (P0–P3 alike; KNOWN_LIMITATIONS).
  Both development cases open it at load, so a Wave 3 case that opens it later needs this.
* **Run held-out evaluation** with repeated live trials of P1–P3 and P0 once per case.
* **Store `AuthorizationRequest` state explicitly.**
* **Optionally, the MBTA adapter (W2.4).**
