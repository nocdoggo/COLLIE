# COLLIE
Cost-aware OR–LLM Liaison for Inventory Exceptions

A selectively invoked frozen LLM commits to a typed exogenous shock hypothesis chosen from past
information only. A deterministic compiler maps that commitment into inventory-model inputs. A
future-only sequential test decides whether the commitment earns influence. A capped base-stock
controller computes every order.

> The LLM says what changed once. Statistics decides whether to trust it. OR decides what to do
> repeatedly.

## Start here

| If you are | Read |
|---|---|
| joining the build | [`docs/implementation/README.md`](docs/implementation/README.md), then your module document |
| writing code against the platform | [`docs/implementation/00-foundation.md`](docs/implementation/00-foundation.md) |
| reasoning about the benchmark | [`docs/env_contract.md`](docs/env_contract.md) |
| reasoning about the statistics | [`docs/derivation_note.md`](docs/derivation_note.md) |

## Quick start

```bash
make setup     # pinned submodule, LFS payload, environment
make test      # full suite
make gate1     # verify every foundation guarantee in one command
```

`make setup` requires `git-lfs`: all 1,320 benchmark instances are LFS-tracked, so without it you get
pointer files instead of data.

## What is established

| Result | Evidence |
|---|---|
| Our episode runner matches the official pipeline exactly, max abs diff `0.0` over 648 comparisons | [`reports/equivalence_report.md`](reports/equivalence_report.md) |
| Arm 1 reproduces the published OR baseline, all 1,320 order sequences bit for bit | [`reports/arm1_or_baseline.md`](reports/arm1_or_baseline.md) |
| The environment contract is audited from code and data, not from prose | [`docs/env_contract.md`](docs/env_contract.md) |
| The core contracts are frozen and guarded against undeclared change | `prereg/contract_freeze.json` |

One finding worth carrying into any comparison: the published OR figure of **0.4447** was generated
under `env.py` lost-order semantics, which we established by reproducing all 1,320 of its order
sequences exactly. Under the authoritative `eval/` submission path the same policy scores **0.5208**.
Any table citing the published figure must name the harness. See `docs/env_contract.md` §8.5.

## Layout

```
collie/          contracts, simulator, adapter, spec, control, verify, trigger, llm, arms, eval
docs/            environment contract, derivation note, implementation briefs
manifests/       audited benchmark manifest, committed instance sets
prereg/          preregistration, freeze records, deviations log
reports/         generated evidence
tools/           audit, selection, freeze, and run entry points
third_party/     pinned InventoryBench submodule, read-only
```

`third_party/InventoryBench` is read-only. Only `collie/adapter/` may reach it, by import or by path,
and both are enforced by test.

## Claim discipline

The activation guarantee is **model-conditional, anytime-valid, per-episode**. It is not dataset-wide
family-wise control, not a safety guarantee, not a profit guarantee, and it does not cover
wrong-family activation. `docs/implementation/README.md` lists the claims that are prohibited outright.

## License

MIT, see [`LICENSE`](LICENSE). The pinned benchmark carries its own terms; do not redistribute its
data.
