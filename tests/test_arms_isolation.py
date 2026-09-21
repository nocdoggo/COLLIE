"""Cross-arm isolation and seam discipline.

Grows over Waves 3-6: the reference-control stand-in's import ban and deletion pin (below),
then the full-ladder ``check_controller_isolation`` sweep once arms 5-10 exist.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARMS = REPO_ROOT / "collie" / "arms"
STAND_IN = "collie.arms.reference_control"


def test_no_arm_imports_the_reference_control_stand_in() -> None:
    """Module brief §3: the compiler and controller reach arms only by injection.

    The temporary module-04 stand-in this guard was named for is deleted — module 04's real
    implementation (``collie.control.mapping.GridCompiler`` /
    ``collie.control.controller.OrCompilerController``) is wired in ``tests/conftest.py`` and
    ``tools/run_arms.py`` instead. The guard stays, now pinning both halves of the swap: the
    stand-in file must not reappear, and no file under ``collie/arms/`` may import the module
    path, or a future regression would not be a clean compiler swap.

    Enforced by AST, in the style of
    ``tests/test_project_skeleton.py::test_only_the_adapter_imports_the_benchmark``.
    """
    stand_in_path = ARMS / "reference_control.py"
    assert not stand_in_path.exists(), (
        "collie/arms/reference_control.py was deleted when module 04 landed; do not reintroduce "
        "it — wire the real implementation by injection instead"
    )
    offenders: list[str] = []
    for py in sorted(ARMS.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name == STAND_IN or name.startswith(STAND_IN + "."):
                    offenders.append(f"{py.relative_to(REPO_ROOT)} imports {name}")
    assert offenders == [], f"arms must not import the stand-in: {offenders}"


# ---------------------------------------------------------------------------
# protocol signature conformance
# ---------------------------------------------------------------------------


def test_activation_policies_match_the_protocol_signature() -> None:
    """Every activation policy must accept exactly what the Protocol declares.

    A Protocol is not signature-checked at runtime, and ``isinstance`` against a
    ``runtime_checkable`` Protocol only tests method *presence*. So a policy whose ``register``
    takes different arguments than the Protocol advertises passes every test and every coverage
    check, and then raises ``TypeError`` the first time an arm registers a proposal. Module 05
    implements ``ActivationPolicy`` from the Protocol, so the Protocol is the contract and this
    test is what keeps it honest.
    """
    import inspect

    from collie.arms.protocols import ActivationPolicy
    from collie.arms.shockspec import (
        EProcessActivation,
        HeuristicRollbackActivation,
        ImmediateActivation,
    )
    from collie.fakes import FakeVerifier
    from collie.verify import VerifierActivationPolicy

    declared_register = inspect.signature(ActivationPolicy.register).parameters
    declared_observe = inspect.signature(ActivationPolicy.observe).parameters
    mismatches: list[str] = []
    for impl in (
        ImmediateActivation,
        HeuristicRollbackActivation,
        EProcessActivation,
        FakeVerifier,
        VerifierActivationPolicy,
    ):
        for method, declared in (("register", declared_register), ("observe", declared_observe)):
            actual = inspect.signature(getattr(impl, method)).parameters
            if set(declared) != set(actual):
                protocol_sig = inspect.signature(getattr(ActivationPolicy, method))
                mismatches.append(
                    f"{impl.__name__}.{method}{inspect.signature(getattr(impl, method))} "
                    f"!= Protocol {method}{protocol_sig}"
                )
    assert not mismatches, "activation policies diverge from their Protocol:\n  " + "\n  ".join(
        mismatches
    )


def test_a_protocol_conformant_policy_can_actually_be_registered() -> None:
    """The end-to-end form: the documented stand-in must survive the arm's real call.

    ``FakeVerifier`` is what module 05's consumers develop against, so if the arm's call breaks
    it, the seam is wrong no matter what the type annotations say.
    """
    from collie.contracts import LifecycleState
    from collie.fakes import FakeVerifier
    from tests.test_arms_shockspec import _spec  # the suite's ShockSpec builder

    verifier = FakeVerifier()
    verifier.register(_spec(), baseline=(100.0, 25.0))
    assert verifier.state is LifecycleState.PROPOSED
