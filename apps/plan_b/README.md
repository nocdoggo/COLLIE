# Plan B: The Show Must Go On — sandbox (Waves 1 to 3)

A deterministic, **fictional, local** sandbox for keeping a small campus event workable when a
delivery, a participant, or a resource changes. It verifies a decision-relevant fact, prepares a
reversible contingency, commits a feasible and authorized adjustment, keeps the plan when no
change is needed, or explains the unresolved constraint when recovery is impossible.

Every action is a real mutation of the local SQLite store and nothing else. No university
booking, purchase, delivery, or message is made. By default the coordinator is a documented
deterministic rule policy (`rules/1.0.0`, and `pantry-rules/1.1.0` for the pantry profile).
Wave 2 adds three optional model-driven policies, the P1-P3 of the evaluation plan: the **live
agent** (`live/1.1.0`, P2) interprets notices and chooses among server-built options with a
language model, including the pantry's stock options; the **tool-use agent** (`tool-use/1.1.0`,
P1) calls the tools itself; the **verify-all agent** (`verify-all/1.1.0`, P3) is P2 with every
relevant status check made first. These are the ids of the Wave 3 freeze
(`plan_b/evaluation/manifests/freeze.json` `policy_ids`); the recorded Wave 2 traces keep the
1.0.0 ids they ran under. They make **paid** model calls and are off unless selected.
Wave 2 also adds a second event configuration (a community skills exchange), a pantry profile
with consumable stock and staff-only attestations, participant check-ins and resource offers,
and per-episode caps for every policy.

Contract: [docs/RUNTIME_CONTRACT.md](docs/RUNTIME_CONTRACT.md) (runtime 1.1.0). Planning source:
[`PEEAI_plan/`](https://github.com/nocdoggo/COLLIE/blob/hackathon/peeaai-plan/PEEAI_plan/README.md). Audit packets:
[`PEEAI_plan/handoffs/wave_1/`](https://github.com/nocdoggo/COLLIE/blob/hackathon/peeaai-plan/PEEAI_plan/handoffs/wave_1/README.md) and
[`PEEAI_plan/handoffs/wave_2/`](https://github.com/nocdoggo/COLLIE/blob/hackathon/peeaai-plan/PEEAI_plan/handoffs/wave_2/README.md) and
[`PEEAI_plan/handoffs/wave_3/`](https://github.com/nocdoggo/COLLIE/blob/hackathon/peeaai-plan/PEEAI_plan/handoffs/wave_3/README.md).

## Requirements

* Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/) (tested with uv 0.9.18, Python 3.12.11)
* Node.js 22.18 or newer and npm (tested with Node 22.19.0)

The app has its own dependency boundary (`pyproject.toml` + `uv.lock`, `web/package-lock.json`).
It does not use or change the COLLIE research environment at the repository root.

## Setup

```bash
cd apps/plan_b
uv sync --all-groups --locked     # Python deps into apps/plan_b/.venv
(cd web && npm ci && npm run build)   # browser app into web/dist
```

After installation nothing needs network access, except the optional model-driven policies (below).

## Run the sandbox

```bash
cd apps/plan_b
uv run plan-b serve               # http://127.0.0.1:8765
```

The moderator code is generated on first start into `var/moderator_code.txt` (mode 0600), or
set `PLAN_B_MODERATOR_CODE`. Runtime state lives in `var/` (ignored by git).

### Core demo (browser)

1. Open http://127.0.0.1:8765, sign in as moderator, choose case `dev01` and click
   **Load episode**.
2. The board shows the goal, the 16:40 schedule, the projector notice, budget and readiness.
3. **Run deterministic policy**: it queries order P17 (two simulated minutes), reports a 17:25
   ETA, evaluates the finite candidate menu, and applies the free swap of demonstrations and
   skills exchange. The receipt and the fresh state read show revision 4 → 5.
4. For the facilitator and the presenter, click **Issue join code**, then **Open in new tab**.
   Each tab is a separate scoped session. Check in from those tabs (the facilitator before 17:10,
   the presenter before 17:30).
5. Advance the clock with the **+1 / +5 / +10 min** buttons, or set **Minutes** to 80 and click
   **Run 80 minutes with policy**. The projector arrival appears at 17:24. Activities start only
   when their readiness evidence holds, and closing completes at 18:00.
6. **Export trace**, then **Open replay** to play it back under the *Recorded replay* label.
7. To reset, click **Reset: load a clean episode…**, then confirm with **Close it and load case
   dev01**. The old episode is closed and its sessions stop working.

Other development cases: `dev02` (backup hold, organizer authorization, paid booking), `dev04`
(false alarm plus a stale and duplicated notice), `dev05` (no feasible recovery), `dev06`
(status service unavailable). Their hidden trajectories live in
`plan_b/scenarios/private/` and are never sent to the policy or the browser.

### Wave 2 demos (browser)

The case list names each case's scenario, and **Load episode** loads it on its own scenario.

* **Community skills exchange** (`skills_dev01`, scenario `dev_fixture_02`). Open a tab for the
  peer lead: the Participation view shows the volunteer alias, the role's declared window and one
  **Check in**. Checking in available only until 11:05 makes the planned 11:20 peer exchange
  infeasible, and the policy applies the free swap of practice and peer exchange. A tab for the
  kit steward can **Offer a resource**: a structured offer that states the registered window,
  capabilities and terms activates the preconfigured backup kit and reserves, spends and adds
  nothing. In an organizer tab a preference change creates a new goal version and marks older
  reports stale. `skills_dev02` changes the goal while the coordinator's apply is in flight.
* **Pantry continuity** (`pantry_dev01`, scenario `dev_fixture_03`). The pantry board keeps the
  pantry-controlled supply gap and the unfulfilled service target as separate counters and shows
  each pool's on-hand, reserved, available and expected (not stock) quantities. Run the policy: it
  holds the 16 partner kits. A tab for `fictional_staff` opens **Staff actions** (beside
  **Updates**): record the handoff (24/16 becomes 40/0), run the policy again (it commits the 40
  kits), advance to 13:40 and record the distribution (40 on time; the counters read 0/0; the 20
  expected kits stay unreceived). `pantry_dev02` hands off only 10 of 16 kits and ends with a
  disclosed 6-kit shortfall.
* **Policy switch.** Under **Policy for this episode** the moderator chooses the deterministic
  policy or a model-driven one (tool-use, live or verify-all agent) before the coordinator first
  acts. Selecting a model-driven policy calls no model; running it does (paid). Every decision card names the policy that ran, and a live card shows the
  model id as returned, latency, tokens, cost and the episode's usage against its caps, with the
  model's rationale labelled as untrusted text.

### Headless runs

```bash
uv run plan-b run-case all --db var/runs.sqlite3 --out var/out
uv run plan-b verify-trace var/out/traces/dev01_trace.json
uv run plan-b serve --replay-dir var/out/traces   # replay them; board exports in var/traces are always listed
```

`plan-b run-case <case|all> [--policy rules|tool-use|live|selective|verify-all]
[--max-episode-tool-calls N] [--max-episode-model-calls N]` runs development cases on their own
scenarios (`selective` is an alias of `live`). Every policy runs under the per-episode caps
(development values: 48 tool calls, 8 model calls); once one is reached the policy records a
`stop` and is not woken again. Every policy except `rules` makes paid model calls.

| Case | Scenario | What it exercises | Deterministic outcome |
| --- | --- | --- | --- |
| dev01, dev02, dev04, dev05, dev06 | `dev_fixture_01` | the Wave 1 campus cases above | unchanged from Wave 1 |
| skills_dev01 | `dev_fixture_02` | the peer lead's own check-in narrows their window to 10:05-11:05, so the planned 11:20 peer exchange no longer fits | the free swap of practice and peer exchange at 10:06; all activities complete; $0 |
| skills_dev02 | `dev_fixture_02` | the organizer switches to preserve_order (goal v2) at 10:06 while the coordinator's apply from a goal-v1 report is in flight | the stale apply is rejected; re-evaluated under goal v2 and applied at 10:07; $0 |
| pantry_dev01 | `dev_fixture_03` | target 40 kits, pantry 24, partner 16, a 20-kit shipment delayed past the session | hold 16, staff handoff (40/0), commit 40, 40 distributed on time; S20 stays 20 unreceived |
| pantry_dev02 | `dev_fixture_03` | staff hands off only 10 of the 16 held kits | 34 distributed, a disclosed 6-kit shortfall against the unchanged target 40 |

### Model-driven policies (optional, paid)

The tool-use, live and verify-all agents need an OpenAI-compatible endpoint (for example
OpenRouter; `PLAN_B_MODEL_PROVIDER`, `PLAN_B_MODEL_BASE_URL` and `PLAN_B_MODEL_KEY_FILE` have no
defaults). Its configuration is
read server-side from the environment, else from `.local/keys/model_endpoint.env` at the
repository root; see [`.env.example`](.env.example) for the names (`PLAN_B_MODEL_PROVIDER`,
`PLAN_B_MODEL_BASE_URL`, `PLAN_B_MODEL_KEY_FILE`, `PLAN_B_MODEL_ID`,
`PLAN_B_MODEL_MAX_RUN_COST_USD`, `PLAN_B_MODEL_MAX_TOTAL_COST_USD`). The key lives only in the
key file (mode 0600, ignored by git); the provider reads it per call and sends it only in the
`Authorization` header. It never reaches the browser, a trace, a log or a decision. A spend guard
refuses any call that could exceed the per-run (per-episode) cap, which a restarted server
resumes from the episode's recorded spend, or the cumulative cap of the ledger
`var/model_spend.json`, which records every call.

```bash
uv run python -m plan_b.agent.gate --out <file>                 # the G-LLM gate on a fresh dev01 episode (paid)
uv run plan-b run-case dev01 --policy live --db var/live.sqlite3 --out var/live_out   # paid
uv run python scripts/run_live_cases.py --out <dir> dev01 dev04 # recorded live runs with their records (paid)
uv run python scripts/run_live_cases.py --out <dir> --policy tool-use dev01   # the same for P1 (or verify-all, live)
uv run python scripts/write_development_results.py --evidence <evidence dir>  # the development results table (no model call)
```

`scripts/run_live_cases.py` runs each case once under the chosen policy (`live` by default),
exports and verifies the trace, and writes a run record: the outcome line, the model as requested and as returned, every
model call's latency, tokens and cost, the ledger before and after, the tool calls, the decisions,
and checks computed from the trace (useful tool calls, validated actions, fresh-state agreement,
the response to each notice). With `--policy`, the files are named after the policy
(`live_p1-tool-use_<case>`, `live_p2-live_<case>`, `live_p3-verify-all_<case>`). A recorded run is
never overwritten. Live runs are evidence of one run, not reproducible artifacts: replay is the
reproducible form. `scripts/write_development_results.py` reads the recorded P1-P3 runs from the
evidence directory and writes `plan_b/evaluation/development/development_runs.json` and its
`README.md` table, with one sentence per run (from `run_notes.json`, read from each trace). These
are development runs: one trial each, and no comparison between policies.

`plan-b verify-trace` checks the frame, chain and content hashes, the algorithm label
(`sha256`), `kind`, `trace_version`, and that the last frame's revision equals the final
state's. It reads the file's bytes, and also rejects a byte order mark, invalid UTF-8, lone
surrogates, nesting deeper than 256 levels and integers longer than 4300 digits. These are the
same checks the browser replay makes. The hashes are not signed: "intact" means consistent with
itself, not authentic.

### Evidence

```bash
uv run python scripts/collect_evidence.py --out <new-or-empty-dir>   # every check, cases, traces, walkthrough (Wave 1 set)
uv run python scripts/write_manifest.py --evidence <dir>             # the Wave 1 packet manifest, from that evidence and git
uv run python tests/e2e/walkthrough.py --out <dir>                   # the Wave 1 browser walkthrough on its own (41 checks)
uv run python tests/e2e/walkthrough_wave2.py --out <dir>             # the Wave 2 browser walkthrough (30 checks)
uv run python scripts/collect_wave2_evidence.py --out <new-or-empty-dir> \
    --live <run_live_cases.py output> --gate <gate record>           # the Wave 2 set (no paid call)
```

`walkthrough_wave2.py` covers the pantry staff flow, the community check-in and offer, and the
policy switch; it needs `npm run build` and selects, but never runs, the live agent (only the
presence of the endpoint configuration is checked). `collect_wave2_evidence.py` runs every check,
the deterministic cases, both walkthroughs, the pantry accounting check over the pantry traces,
the focused M2 test mapping and a check that dev01-dev06 print their Wave 1 lines; it copies the
recorded live runs and the gate record without calling a model, and scans everything it wrote for
local paths, identifiers and credential-shaped text.

The collector refuses a directory that already holds files. It writes local paths as
placeholders, and fails its last check if any evidence file names the host, the user or a local
path. A host or user name that is an ordinary word can be exempted with
`--allow-identifier WORD`.

## Wave 3: the frozen comparison, the held-out results and the showcase

* **Freeze.** `plan_b/evaluation/manifests/freeze.json` (commit `3de5962`, 76 measured files)
  fixes the code, prompts, model (`anthropic/claude-sonnet-5.5` via OpenRouter), caps (8 model,
  48 tool calls per episode), seeds and order. `uv run plan-b eval verify-freeze` checks it;
  `--require-heldout` also checks the case lock `heldout.json` (commit `49e62b5`).
* **Held-out results.** [`evaluation/results/wave3_heldout_20261025T1625Z/`](evaluation/results/wave3_heldout_20261025T1625Z/README.md):
  campus 80 of 80 and pantry 40 of 40 episodes recorded, the reports (`*/report/`), the figure
  and [`FAILURES.md`](evaluation/results/wave3_heldout_20261025T1625Z/FAILURES.md).
  `uv run plan-b eval report --results <suite dir> --out <dir>` recomputes a report from the
  committed raw records without a model call.
  This run of policy 1.1 stays the evaluation of record, and its 12 cases are spent.
* **Wave 3b, policy 1.2.** The fixes are in [`docs/RUNTIME_CONTRACT.md`](docs/RUNTIME_CONTRACT.md)
  section 21, frozen in `plan_b/evaluation/manifests/freeze_v1_2.json` with six fresh cases
  locked in `heldout2.json` (commit `5955243`), both before the first 1.2 model call. Two runs,
  labeled differently:
  [`evaluation/results/wave3b_fresh_20261025T2327Z/`](evaluation/results/wave3b_fresh_20261025T2327Z/README.md)
  is a new, small held-out check on C09 to C12, T05 and T06 (60 of 60 episodes recorded, 59 met
  their outcome). [`evaluation/results/wave3b_rerun_spent_20261025T2345Z/`](evaluation/results/wave3b_rerun_spent_20261025T2345Z/README.md)
  is a post-hoc diagnostic rerun after the fixes, on the spent cases. It is not a held-out
  result. Both give descriptive counts only and are not comparable with the 1.1 counts as an
  improvement. `uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout
  heldout2.json --require-heldout` checks the 1.2 freeze and lock.
* **Showcase.** The seven-minute script and runbook, the claims ledger and the rehearsal record
  are in [`PEEAI_plan/handoffs/wave_3/`](https://github.com/nocdoggo/COLLIE/blob/hackathon/peeaai-plan/PEEAI_plan/handoffs/wave_3/SHOWCASE.md).
  `uv run python tests/e2e/rehearsal.py --out <dir>` runs three automated rehearsals from a
  clean reset (one with a forced provider failure and the switch to the recorded replay);
  `tests/e2e/keyboard.py --out <dir>` is the keyboard check.
* **Release package.** `uv run python scripts/build_release.py --out <empty dir>` builds the
  local reviewable package from the allowlist [`release/manifest.json`](release/manifest.json)
  (no `.local`, no `var`, no held-out case files, no evaluator records) and starts it: the freeze
  verifies, the board and every packaged replay are served from the package. Nothing is hosted
  or submitted. The package carries no unit tests (`tests/*.py`, `web/tests/`): run the checks
  below from a repository clone.
* **Evidence.** `uv run python scripts/collect_wave3_evidence.py --out <empty dir>` regenerates
  the Wave 3 packet evidence with no paid call.

## Checks

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
(cd web && npm run typecheck && npm run build && npm test && npm run lint)
```

## Layout

| Path | Contents |
| --- | --- |
| `plan_b/domain/` | Runtime models, clock semantics, readiness, projection, planner (`candidates`, `constraints`, `objective`), campus and pantry adapters, stock accounting, planning-artifact mapping |
| `plan_b/store/` | SQLite database and migrations, repository, engine (clock and events), sessions, episodes, projections |
| `plan_b/tools/` | The single executor, per-tool handlers (stock and staff tools in `stock.py`), in-process client |
| `plan_b/world/` | Private world (status trajectories, timed events) and the leak checker |
| `plan_b/scenarios/` | Public fixtures (campus, skills exchange, pantry), private development cases, policy host with episode caps, runner |
| `plan_b/evaluation/` | Deterministic rule policies (campus and pantry) and parser, state-based scoring, trace export; `development/` holds the recorded development runs of P1-P3 |
| `plan_b/agent/` | Model-driven policies (Wave 2): endpoint configuration, provider and spend ledger, interpretation, closed action menu, the live orchestrator (P2), `policies/` (P1 tool-use, P2 selective, P3 verify-all), prompts, the G-LLM gate |
| `plan_b/api/` | FastAPI application, policy configuration, participation view |
| `web/` | React + TypeScript board and replay |
| `scripts/` | Evidence collectors (Waves 1-3), the Wave 1 manifest writer, recorded live runs, the development results writer, the demo preparation and the release builder |
| `release/` | The release allowlist (`manifest.json`) read by `scripts/build_release.py` |
| `evaluation/results/` | The Wave 3 held-out results and the Wave 3b version 1.2 runs (outside the frozen tree) |
| `tests/` | Focused tests against the real store and executor |

## License

Plan B is free software under the GNU General Public License, version 3 ([`LICENSE`](LICENSE)).
