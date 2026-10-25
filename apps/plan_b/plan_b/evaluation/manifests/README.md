# Evaluation manifests

* `freeze.json`: written by `uv run plan-b eval freeze`; the hashes of every measured file and
  the frozen settings of the Wave 3 comparison.
* `heldout.json`: written by `uv run plan-b eval lock-heldout` after the held-out cases are
  authored; their ids and the hashes of their private, evaluator and public files.

`uv run plan-b eval verify-freeze` recomputes both and fails on any drift; a held-out
`plan-b eval run` refuses to start unless both verify. See
[`docs/EVALUATION.md`](../../../docs/EVALUATION.md).
