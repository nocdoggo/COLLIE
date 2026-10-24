# Wave 1 working checklist

The durable task list kept during implementation, preserved as a record of the sequence.
`[x]` means done and checked.

## Preflight (2026-10-23)

- [x] Workspace: the COLLIE repository, branch `hackathon/peeaai-plan`, HEAD `65997ac`, worktree clean.
- [x] Planning baseline already committed as `65997ac` (PEEAI_plan/ + `/.local/keys/` ignore rule), author and committer `Noctis <45600261+nocdoggo@users.noreply.github.com>`.
- [x] Repo-local git identity = Noctis noreply; the machine's global git identity is never used. No `GIT_AUTHOR_*`/`GIT_COMMITTER_*` overrides in the environment.
- [x] Local commit settings add no trailers or footers; every commit is checked for trailers before and after.
- [x] `.local/keys/mbta.key` ignored, 0600, dir 0700; never read.
- [x] Required reading complete.
- [x] Planning digest convention reproduced (eb37a604…a123).

## Contract freeze

- [x] `apps/plan_b/docs/RUNTIME_CONTRACT.md`, `plan_b/domain/models.py`
- [x] Runtime public fixture + private dev cases (dev01, dev02, dev04, dev05, dev06)
- [x] Migrations `0001_initial.sql`, `0002_scheduled_actions.sql`
- [x] Adapter interface, fixture loader, readiness, projection

## Build (parallel workers with disjoint ownership)

- [x] Planner (candidates, constraints, objective, campus adapter, planning map)
- [x] Rule policy, parser, scoring
- [x] Browser board and replay
- [x] Integrator: store, engine, sessions, executor, handlers, world, API, policy host, runner, demos, export

## Verification and review

- [x] Integration tests (state/transactions, holds/money, authority, lifecycle, isolation, replay, API, contracts, dev cases)
- [x] Independent review: 5 areas, adversarially verified (33 findings: 14 confirmed, 17 partial, 2 refuted)
- [x] Fixes for all confirmed/partial findings, with regression tests
- [x] Re-check of all 33 items (28 closed, 4 partly closed, 1 accepted limitation); 7 regressions found and fixed
- [x] Second-round verification of the regression fixes (4 closed, 2 partial, 1 new regression; parser redesigned as strict forms)
- [x] Round 3: strict-forms parser implemented and independently verified (1 high and 1 medium regression found and fixed)
- [x] Verify-only rule: three candidates, two independent verifiers, 3,131-variant comparison; final rule committed (`3028cbf`)
- [x] Wave 1 audit: 45 verified findings (0 high, 6 confirmed medium); all resolved (`afe502e` and this packet)
- [x] Four audit-fix rounds, each independently verified; remaining lint evasions documented and pinned by tests
- [x] Browser walkthrough (Playwright, Chromium) 41/41, every step of the minimum visible workflow
- [x] ruff, ruff format, mypy, pytest 455; web typecheck, build, 362 tests, boundary lint

## Delivery

- [x] Implementation commit `63aee9d` (sole author, explicit file list)
- [x] Evidence-collector follow-up `25363fb` (local paths redacted, screenshots compressed, pytest after the build)
- [x] Verify-only rule `3028cbf` and `.gitignore` order `8b7aea3`
- [x] Audit fixes `afe502e` (59 files, sole author, explicit file list, no trailers)
- [x] Clean-checkout reproduction at `afe502e` and evidence collection into an empty directory (18/18 checks)
- [x] Manifest generated (`M1 passed_on_recorded_automated_checks`)
- [x] Handoff packet (README, IMPLEMENTATION_MAP, DECISIONS, VERIFICATION, AUDIT_GUIDE, KNOWN_LIMITATIONS, WAVE_2_HANDOFF, manifest.json, evidence/)
- [ ] Packet commit and final authorship audit
- [ ] Scratch worktree removed
- [ ] Nothing pushed (pushing needs separate explicit authorization)
