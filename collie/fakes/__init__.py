"""Branch A (P1). Fakes that let every branch develop before its dependencies land.

Landed at Gate 1 and kept for the life of the project. The parallelism of the five-week plan
depends on these: the verifier branch can test activation without an LLM, the alert branch can
render conditions without a compiler, and the arms branch can wire a ladder without a generator.

Deliberately importable with no optional dependencies and no network.
"""

from collie.fakes.fake_generator import (
    FakeGenerator,
    fixture_episode,
    fixture_episodes,
)
from collie.fakes.fake_llm import FakeLLM, canned
from collie.fakes.fake_verifier import FakeVerifier
from collie.fakes.null_controller import ConstantController, NullController

__all__ = [
    "ConstantController",
    "FakeGenerator",
    "FakeLLM",
    "FakeVerifier",
    "NullController",
    "canned",
    "fixture_episode",
    "fixture_episodes",
]
