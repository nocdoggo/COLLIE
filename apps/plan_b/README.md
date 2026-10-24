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
* Node.js 22 and npm (tested with Node 22.19.0)

The app has its own dependency boundary (`pyproject.toml` + `uv.lock`, `web/package-lock.json`).
It does not use or change the COLLIE research environment at the repository root.

## Setup

```bash
cd apps/plan_b
uv sync --all-groups              # Python deps into apps/plan_b/.venv
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

1. Open http://127.0.0.1:8765, sign in as moderator, and **Load** case `dev01`.
2. The board shows the goal, the 16:40 schedule, the projector notice, budget and readiness.
3. **Run deterministic policy**: it queries order P17 (two simulated minutes), reports a 17:25
   ETA, evaluates the finite candidate menu, and applies the free swap of demonstrations and
   skills exchange. The receipt and the fresh state read show revision 4 → 5.
4. **Open role tabs** for the facilitator and presenter; each tab is a separate scoped session.
   Check in from those tabs (the facilitator before 17:10, the presenter before 17:30).
5. Advance the clock (or **Run N minutes with policy**). The projector arrival appears at 17:24;
   activities start only when their readiness evidence holds; closing completes at 18:00.
6. **Export trace**, then open **Replay** to play it back under the *Recorded replay* label.
7. **Load** again to reset into a new, clean episode.

Other development cases: `dev02` (backup hold, organizer authorization, paid booking), `dev04`
(false alarm plus a stale and duplicated notice), `dev05` (no feasible recovery), `dev06`
(status service unavailable). Their hidden trajectories live in
`plan_b/scenarios/private/` and are never sent to the policy or the browser.

### Headless runs

```bash
uv run plan-b run-case all --db var/runs.sqlite3 --out var/out
uv run plan-b verify-trace var/out/traces/dev01_trace.json
```

## Checks

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
(cd web && npm run typecheck && npm run build)
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
