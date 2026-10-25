# Verification (Wave 3, W3.4: presentation and release)

All commands run from `apps/plan_b` after `unset VIRTUAL_ENV`, on the working tree at
`c052338` plus the uncommitted W3.4 files. They made no paid call and used no network beyond
127.0.0.1 servers the scripts start and stop. No key was read: the forced failure uses a
placeholder key file.

## The new scripts, run once from the working tree

| Command | Result |
| --- | --- |
| `uv run python tests/e2e/rehearsal.py --out <scratch>/reh1` | exit 0. 3/3 rehearsals passed (34/34, 42/42, 34/34 checks). Same receipts and final states: true. Its expected-outcome check then keyed the episodes by scenario id. It was rewritten to key them by case before the next run |
| `uv run python tests/e2e/rehearsal.py --out <scratch>/reh2` | exit 0. 3/3 passed (34/34, 42/42, 34/34). Same receipts and final states: true. All 6 expected outcomes true. 133.8 s in all |
| `uv run python scripts/build_release.py --out <scratch>/rel1` (first try) | FileNotFoundError: the patterns ending in `**` matched only directories (Python 3.12 `Path.glob`). Fixed by globbing `**/*` |
| `uv run python scripts/build_release.py --out <scratch>/rel1` | exit 0. 14/14 checks passed. 600 files, 59,290,237 bytes. Excluded: 71 cache files, 231 evaluator records (`runner_private/`), 25 held-out case files. The scans were clean: no credential, local path or local user or host name. No held-out ref or scenario id in the browser bundle. From the package: `plan_b` imported from it, freeze.json verified, demo_prep, serve, the board's index.html, 9 replays served byte for byte, verify-trace 9/9 |
| `uv run python scripts/collect_wave3_evidence.py --out ../../PEEAI_plan/handoffs/wave_3/evidence` | see "Collector run" below |
| `uv run ruff check .` / `uv run ruff format --check .` | All checks passed / 139 files already formatted (before the collector run) |

## Collector run (the packet's `evidence/`)

Command: `uv run python scripts/collect_wave3_evidence.py --out <empty dir>`, then copied over
`evidence/`. The story audit regenerated it after its fixes (to `rehearsal.py`,
`build_release.py`, `release/manifest.json`, the submission items and this packet). It ran from
the working tree, so `environment.json` records `app_tree_clean: false` and git head `c052338`.
Exit 0, **all checks passed**, read from `evidence/reports/checks.json`. The collector's ruff and
mypy stages ran before the audit's last `build_release.py` edit. `ruff check` and
`ruff format --check` passed on the edited file separately (mypy's scope does not include
`scripts/`).

| Check | Result |
| --- | --- |
| `ruff check` / `ruff format --check` / `mypy` | All checks passed / 139 files already formatted / no issues in 90 source files |
| web typecheck, build, tests, boundary lint | 0 / built / **396/396** / "Boundary check passed: 25 read-only modules, 40 sources, dist bundle scanned." |
| pytest (JUnit) | **896 passed**, 0 failures, 0 errors, 0 skipped (556 s) |
| `plan-b run-case all` | 9 case lines, all `matches_expectation=True`. Cases dev01, dev02, dev04, dev05 and dev06 are identical to the Wave 1 evidence (`reports/wave1_parity.json`) |
| `plan-b eval verify-freeze --require-heldout` | freeze.json verified, and heldout.json verified (28 files) |
| `plan-b eval report` on the committed raw records, campus and pantry | both reports (metrics.json, evaluation_results.md, figure.svg) **identical byte for byte** to the committed `report/` (`reports/results_recomputed.json`) |
| results summary | `reports/results_summary.json`. Campus met/recorded: P0 6/8, P1 24/24, P2 18/24, P3 21/24. Cases with all trials met 6/8/6/7. Pantry: 4/4, 6/12, 9/12, 6/12. Cases 4/2/3/2. These are the numbers `SHOWCASE.md` and `CLAIMS.md` cite |
| `scripts/build_release.py` | 14/14 checks. 615 files, 59,613,420 bytes (`.env.example` added, and the scan widened to .xml, .log, .csv, .sh, PDFs and more key and path shapes). Excluded: 71 cache files, 231 evaluator records, 25 held-out case files. Served and replayed from the package (`release/release_report.json`) |
| walkthrough.py / walkthrough_wave2.py / storyboard.py / keyboard.py | **41/41**, **30/30**, **32/32**, **19/19** (`browser/`) |
| rehearsal.py | **3/3** rehearsals. Identical receipts and final states. Expected outcomes held. Repository ledger unchanged (`rehearsal/rehearsal_report.json`, see REHEARSALS.md) |
| evidence credential pattern scan / identifier scan | 13 text files, no key prefix or bearer token / 14 text files, no host name, user name, git email or local path |

Spend: **0 USD**. No model call was made, and the ledger (`apps/plan_b/var/model_spend.json`) was
not touched by any W3.4 run: the forced failure used a temporary ledger.

## Not rerun here

- The held-out evaluation itself. That is W3.2's, committed in `c052338`. Only its reports were
  recomputed.
- A clean-checkout run of the collector. The integrate step does it.
- Any human rehearsal (pending, see REHEARSALS.md).
