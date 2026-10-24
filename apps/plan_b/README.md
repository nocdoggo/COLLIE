# Plan B: The Show Must Go On — Wave 1 sandbox

A deterministic, **fictional, local** sandbox for keeping a small campus event workable when a
delivery, a participant, or a resource changes. It verifies a decision-relevant fact, prepares a
reversible contingency, commits a feasible and authorized adjustment, keeps the plan when no
change is needed, or explains the unresolved constraint when recovery is impossible.

Every action is a real mutation of the local SQLite store and nothing else. No university
booking, purchase, delivery, or message is made. Wave 1 has **no LLM**: the coordinator is a
documented deterministic rule policy (`rules/1.0.0`).

Contract: [docs/RUNTIME_CONTRACT.md](docs/RUNTIME_CONTRACT.md). Planning source:
[`PEEAI_plan/`](../../PEEAI_plan/README.md). Audit packet:
[`PEEAI_plan/handoffs/wave_1/`](../../PEEAI_plan/handoffs/wave_1/README.md).

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

After installation nothing needs network access.

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

### Headless runs

```bash
uv run plan-b run-case all --db var/runs.sqlite3 --out var/out
uv run plan-b verify-trace var/out/traces/dev01_trace.json
uv run plan-b serve --replay-dir var/out/traces   # replay them; board exports in var/traces are always listed
```

`plan-b verify-trace` checks the frame, chain and content hashes, the algorithm label
(`sha256`), `kind`, `trace_version`, and that the last frame's revision equals the final
state's. It reads the file's bytes, and also rejects a byte order mark, invalid UTF-8, lone
surrogates, nesting deeper than 256 levels and integers longer than 4300 digits. These are the
same checks the browser replay makes. The hashes are not signed: "intact" means consistent with
itself, not authentic.

### Evidence

```bash
uv run python scripts/collect_evidence.py --out <new-or-empty-dir>   # every check, cases, traces, walkthrough
uv run python scripts/write_manifest.py --evidence <dir>             # the packet manifest, from that evidence and git
uv run python tests/e2e/walkthrough.py --out <dir>                   # the browser walkthrough on its own
```

The collector refuses a directory that already holds files. It writes local paths as
placeholders, and fails its last check if any evidence file names the host, the user or a local
path. A host or user name that is an ordinary word can be exempted with
`--allow-identifier WORD`.

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
| `plan_b/domain/` | Runtime models, clock semantics, readiness, projection, planner (`candidates`, `constraints`, `objective`), campus adapter, planning-artifact mapping |
| `plan_b/store/` | SQLite database and migrations, repository, engine (clock and events), sessions, episodes, projections |
| `plan_b/tools/` | The single executor, per-tool handlers, in-process client |
| `plan_b/world/` | Private world (status trajectories, timed events) and the leak checker |
| `plan_b/scenarios/` | Public fixture, private development cases, policy host, runner |
| `plan_b/evaluation/` | Deterministic rule policy and parser, state-based scoring, trace export |
| `plan_b/api/` | FastAPI application |
| `web/` | React + TypeScript board and replay |
| `tests/` | Focused tests against the real store and executor |
