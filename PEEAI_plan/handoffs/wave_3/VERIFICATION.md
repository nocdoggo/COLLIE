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
`evidence/`. The integrate step ran it from a clean checkout of `3442874`, the submission
commit after this packet's: `git worktree add --detach <scratch>/clean HEAD`, then
`uv sync --all-groups --locked` and `npm ci`, with the repository ledger copied into the
worktree's `var/`. `PLAN_B_MODEL_KEY_FILE` named the main checkout's key file by its absolute
path, for the presence check only. No model call was made. `environment.json` records
`app_tree_clean: true` and git head `3442874`, and the worktree was still clean afterwards.
Exit 0, **all checks passed** (22 of 22, each with exit code 0), read from `evidence/reports/checks.json`. The results
summary, the Wave 1 parity record and the recomputation record are byte-identical to the story
audit's working-tree run. Only timings and provenance changed. The ledger's sha256 was the same
before and after.

| Check | Result |
| --- | --- |
| `ruff check` / `ruff format --check` / `mypy` | All checks passed / 139 files already formatted / no issues in 90 source files |
| web typecheck, build, tests, boundary lint | 0 / built / **396/396** / "Boundary check passed: 25 read-only modules, 40 sources, dist bundle scanned." |
| pytest (JUnit) | **896 passed**, 0 failures, 0 errors, 0 skipped (562 s) |
| `plan-b run-case all` | 9 case lines, all `matches_expectation=True`. Cases dev01, dev02, dev04, dev05 and dev06 are identical to the Wave 1 evidence (`reports/wave1_parity.json`) |
| `plan-b eval verify-freeze --require-heldout` | freeze.json verified, and heldout.json verified (28 files) |
| `plan-b eval report` on the committed raw records, campus and pantry | both reports (metrics.json, evaluation_results.md, figure.svg) **identical byte for byte** to the committed `report/` (`reports/results_recomputed.json`) |
| results summary | `reports/results_summary.json`. Campus met/recorded: P0 6/8, P1 24/24, P2 18/24, P3 21/24. Cases with all trials met 6/8/6/7. Pantry: 4/4, 6/12, 9/12, 6/12. Cases 4/2/3/2. These are the numbers `SHOWCASE.md` and `CLAIMS.md` cite |
| `scripts/build_release.py` | 14/14 checks. 615 files, 59,623,985 bytes, tree clean (`.env.example` added, and the scan widened to .xml, .log, .csv, .sh, PDFs and more key and path shapes). Excluded: 71 cache files, 231 evaluator records, 25 held-out case files. Served and replayed from the package (`release/release_report.json`) |
| walkthrough.py / walkthrough_wave2.py / storyboard.py / keyboard.py | **41/41**, **30/30**, **32/32**, **19/19** (`browser/`) |
| rehearsal.py | **3/3** rehearsals. Identical receipts and final states. Expected outcomes held. Repository ledger unchanged (`rehearsal/rehearsal_report.json`, see REHEARSALS.md) |
| evidence credential pattern scan / identifier scan | 13 text files, no key prefix or bearer token / 14 text files, no host name, user name, git email or local path |

Spend: **0 USD**. No model call was made, and the ledger (`apps/plan_b/var/model_spend.json`) was
not touched by any W3.4 run: the forced failure used a temporary ledger.

## Not rerun here

- The held-out evaluation itself. That is W3.2's, committed in `c052338`. Only its reports were
  recomputed.
- Any human rehearsal (pending, see REHEARSALS.md).

## Wave 3b: version 1.2 (addendum)

The Wave 3b steps ran these checks. Each row names the step that ran it and what it reported.
All Python ran from `apps/plan_b` after `unset VIRTUAL_ENV`. `<scratch>` is the step's scratch
directory.

| Step | Command | Result |
| --- | --- | --- |
| audit2 (before the freeze) | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy plan_b` | All checks passed, 142 files already formatted, no issues in 71 files |
| audit2 | `uv run pytest -p no:cacheprovider -W ignore -o addopts= -q <files>` in 12 shards over all 57 `tests/test_*.py` modules | **950 passed**, 0 failed |
| audit2 | `uv run plan-b run-case all --db <scratch>/p0.sqlite3 --out <scratch>/p0_audit`, twice (before its fixes and on the committed code) | 9 cases `matches_expectation=True`. 27 files, 0 differing from the pre-1.2 baseline once run ids are masked |
| audit2 | in `web/`: `npm run -s typecheck`, `test`, `lint`, `build`. `uv run --group e2e python tests/e2e/{walkthrough,walkthrough_wave2,keyboard,storyboard}.py` | all exit 0. 41/41, 30/30, 21/21, 32/32 |
| audit2 | `uv run plan-b eval freeze --out freeze_v1_2.json`, then `uv run plan-b eval lock-heldout --manifest heldout2.json --freeze freeze_v1_2.json --cases C09,C10,C11,C12,T05,T06` | freeze at 23:23:47Z (76 files, git head `1ea8ea1`), lock at 23:23:54Z (15 files). Committed in `5955243` |
| audit2 | `uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout heldout2.json --require-heldout`, in the tree and from a clean `git archive` of `5955243` | both verified, rc 0 |
| eval2 | `uv run plan-b eval run --suite campus --freeze freeze_v1_2.json --heldout heldout2.json --out <scratch>/results/wave3b_fresh_20261025T2327Z/campus --jobs 1`, and the same for `--suite pantry`, in a clean detached worktree of `5955243` | 40 of 40 and 20 of 20 completed, rc 0. First model call 23:27:31.78Z |
| eval2 | `uv run plan-b eval lock-heldout --manifest <scratch>/diag/diagnostic_lock_spent_v1_2.json --freeze freeze_v1_2.json --cases C01,...,T04`, then `uv run plan-b eval run ... --heldout <scratch>/diag/diagnostic_lock_spent_v1_2.json --jobs 2` per suite | the post-hoc diagnostic rerun on spent cases, not held-out: campus 80 of 80 (76 completed, 4 capped), pantry 40 of 40 (25 completed, 15 capped), rc 0 |
| audit_eval2 | an independent recount from every raw `record.json` and `trace.json.gz` (a script that does not import `plan_b`) | **no mismatches** with `metrics.json`, `evaluation_results.md`, the READMEs, `FAILURES.md` and `spend_extract.json` |
| audit_eval2 | integrity: timestamps, `verify-freeze` with both locks, seeds and order against the plans, generation ids, model settings, the 429 entries | all checks pass. 663 unique generation ids, none shared with the v1.1 run. One model configuration. The 61 HTTP 429 answers cost 0 USD and counted toward no cap |
| audit_eval2 | `uv run plan-b eval report --results evaluation/results/<run>/<suite> --out <scratch>/regen/<run>/<suite>` for both runs and both suites | 12 of 12 report files identical by sha256 |
| audit_eval2 | `git status --porcelain` and `git diff --stat HEAD` on `wave3_heldout_20261025T1625Z` | empty: the v1.1 record is unchanged |
| results2 | `python3 make_results.py` (in `PEEAI_plan/submission`), then `cmp` of `results_numbers.tex`, `fig_results.tex`, `fig_results_v.tex` and `results.json` against copies taken before | the four v1.1 outputs byte-identical. New: `results_numbers_v12.tex` and `results_v12.json`, with the counts above |

Commits, still local when this addendum was written on October 25, 2026: `1ea8ea1` (the 1.2 code and the fresh
cases), `5955243` (the freeze and the lock) and `f715dfc` (the two results directories, 584
files). Each was checked for author and committer, empty trailers and a staged-blob scan with 0
hits.

Spend: the fresh run 3.608150 USD and the rerun 8.944586 USD. The ledger stands at 26.433970
USD with 0 open reservations. The audits and results2 made no paid call.

### Not rerun by results2

- No evaluation run, no recount and no report regeneration. results2 read the committed
  `metrics.json` files through `make_results.py` and relied on audit_eval2 for the recount.
- No pytest, browser or web check. audit2's battery ran in the working tree of `1ea8ea1`, with
  the polish step's files uncommitted in it. The battery should run once more on the merged tree
  before the push.
- The packet's `evidence/` directory is still the Wave 3 collector's output from `3442874`. It
  covers v1.1 only.

### Merged-tree battery before the Wave 3b push

The integrate step ran the battery on October 25, 2026, from `apps/plan_b` after
`unset VIRTUAL_ENV`, in the working tree that held every Wave 3b change (the polish, results2
and audit3 files on top of `f715dfc`). No model call was made.

| Command | Result |
| --- | --- |
| `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy plan_b` | All checks passed, 144 files already formatted, no issues in 71 source files |
| `uv run pytest -p no:cacheprovider -W ignore -o addopts= -q <files>` in 12 shards over all 55 `tests/test_*.py` files | **951 passed**, 0 failed, every shard rc 0 |
| `uv run plan-b run-case all --db <scratch>/p0.sqlite3 --out <scratch>/p0` | 9 cases `matches_expectation=True`. 27 files, none differing from the pre-1.2 baseline beyond run-to-run fields |
| `uv run plan-b eval verify-freeze --freeze freeze_v1_2.json --heldout heldout2.json --require-heldout` | both verified (76 files, and 15 files for C09 to C12, T05 and T06), rc 0 |
| in `web/`: `npm run -s typecheck`, `test`, `lint`, `build` | all rc 0. **397/397** tests. Boundary check passed |
| `uv run --group e2e python tests/e2e/{walkthrough,walkthrough_wave2,storyboard,keyboard}.py` | 41/41, 30/30, 32/32, 21/21, all rc 0. `walkthrough_wave2.py` had the model settings for presence only, a closed port on 127.0.0.1 and a placeholder key |
| `uv run --group e2e python tests/e2e/rehearsal.py --out <scratch>/reh` | 3/3 rehearsals passed. Same receipts and final states, expected outcomes and an unchanged repository ledger: all true |
| `uv run python scripts/build_release.py --out <scratch>/release` | first run: 13 of 14 checks, because `freeze.json verifies in the package` failed. The 1.1 freeze verifies only at its own commit since the 1.2 code (by design, `docs/EVALUATION.md`). The integrate step pointed that check at `freeze_v1_2.json` (commit `a132517`). Rerun: **14/14 checks**, 620 files, rc 0 |
| in `PEEAI_plan/submission`: `make_results.py`, `latexmk` for the deck and the poster, `build_doc.py`, `check_writing.py`, `timing.py` | all rc 0. Deck 23 pages and poster 1 page, 0 Overfull each. The v1.1 outputs of `make_results.py` unchanged. 15 files, 0 lines with a forbidden character. Script 932 words (about 399 s of 420), pitch 267 words (about 114 s of 120) |

The integrate step's commits: `7f8e602` (the polish step's app and web files), `a132517` (the
release check above), then this packet and the submission files. Each was checked for author and
committer, empty trailers and a names-only staged-blob scan (key bytes, credential patterns, local
paths, host and user names, attribution) with 0 hits.
