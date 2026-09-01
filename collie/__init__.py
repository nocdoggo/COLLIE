"""COLLIE — Cost-aware OR-LLM Liaison for Inventory Exceptions.

A selectively invoked frozen LLM commits to a typed exogenous shock hypothesis
(a ShockSpec), chosen from past information only. A deterministic compiler maps that
commitment into inventory-model inputs. A future-only sequential test decides whether the
commitment earns influence. A capped base-stock controller computes every order.

    The LLM says what changed once. Statistics decides whether to trust it.
    OR decides what to do repeatedly.

Branch ownership of subpackages (the per-branch specs are kept off the repository):

    contracts, fakes, adapter, sim   A  collie-platform            P1
    data (generator, splits, ...)    B  collie-shock-generator     P2
    data (alerts, audit)             C  collie-alert-bank          P3
    spec                             D  collie-shockspec-interface P3
    control                          E  collie-or-compiler         P1
    verify                           F  collie-verifier            P4
    trigger, llm, arms               G  collie-arms-harness        P1
    eval                             H  collie-eval-prereg         P4
"""

__version__ = "0.1.0"

# Repository root of the pinned benchmark submodule, and the commit it must be at.
# Only collie.adapter may import from the submodule; everything else uses collie.contracts.
BENCHMARK_COMMIT = "62b1f1162f19a41d428d47c6cd4ca431f098f6f3"
