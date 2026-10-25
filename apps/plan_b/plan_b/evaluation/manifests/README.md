# Evaluation manifests

* `freeze.json`: written by `uv run plan-b eval freeze`; the hashes of every measured file and
  the frozen settings of the Wave 3 comparison.
* `heldout.json`: written by `uv run plan-b eval lock-heldout` after the held-out cases are
  authored; their ids and the hashes of their private, evaluator and public files.
* `freeze_v1_2.json`: the freeze of policy 1.2 (Wave 3b), written by
  `uv run plan-b eval freeze --out freeze_v1_2.json` at 2026-10-25T23:23:47Z from commit
  `1ea8ea1`. It also records the shared planner's version (`planner_version`).
* `heldout2.json`: the case-scoped lock of the second held-out set (C09 to C12, T05, T06,
  15 files under `eval/set2/`), written by `uv run plan-b eval lock-heldout --manifest
  heldout2.json --freeze freeze_v1_2.json --cases C09,C10,C11,C12,T05,T06` at
  2026-10-25T23:23:54Z, before any 1.2 model call on those cases.

`freeze.json` and `heldout.json` are the v1.1 records and verify at their own commits
(`3de5962` and `49e62b5`), not at later ones.

`uv run plan-b eval verify-freeze` recomputes both and fails on any drift; a held-out
`plan-b eval run` refuses to start unless both verify. See
[`docs/EVALUATION.md`](../../../docs/EVALUATION.md).
