"""A scriptable stand-in for the language model.

Returns raw strings, exactly as a real client would, so branch D's extraction, validation,
repair, and fallback logic is exercised end to end rather than bypassed. The canned corpus
deliberately includes the ways real models fail: prose around the JSON, fenced blocks,
truncation, extra fields, wrong types, and a smuggled ``threshold`` that must be rejected
because the model is never permitted to choose its own test.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

__all__ = ["FakeLLM", "canned"]


def _payload(**overrides: Any) -> dict[str, Any]:
    """A schema-valid payload. Provenance fields are the system's job, never the model's."""
    base: dict[str, Any] = {
        "target_stream": "arrival",
        "shock_family": "transit_pause",
        "direction": "arrival_interrupted",
        "onset_window": [-1, 1],
        "magnitude_bin": "medium",
        "persistence": "transient",
        "duration_bin": "4_8",
        "evidence_refs": ["alert_17", "obs_t17"],
        "prospective_signature": "sig_arrival_stall",
    }
    base.update(overrides)
    return base


class canned:
    """Named response fixtures. Use these instead of inventing strings per test."""

    VALID = json.dumps(_payload())

    ABSTENTION = json.dumps(
        {
            "target_stream": "none",
            "shock_family": "no_change",
            "direction": "none",
            "onset_window": None,
            "magnitude_bin": None,
            "persistence": "unknown",
            "duration_bin": "none",
            "evidence_refs": [],
            "prospective_signature": "sig_demand_level_up",
        }
    )

    #: A cooperative model writing "none" where null was meant. Must normalise, not fail.
    ABSTENTION_NONE_SPELLING = json.dumps(
        {
            "target_stream": "none",
            "shock_family": "no_change",
            "direction": "none",
            "onset_window": None,
            "magnitude_bin": "none",
            "persistence": "unknown",
            "duration_bin": "none",
            "evidence_refs": [],
            "prospective_signature": "sig_demand_level_up",
        }
    )

    DEMAND_UP = json.dumps(
        _payload(
            target_stream="demand",
            shock_family="demand_level",
            direction="demand_up",
            magnitude_bin="high",
            persistence="persistent",
            duration_bin="longer",
            prospective_signature="sig_demand_level_up",
        )
    )

    #: Valid JSON wrapped in the prose models like to add.
    PROSE_WRAPPED = (
        "Looking at the pipeline discrepancy, here is my assessment:\n\n"
        f"{json.dumps(_payload())}\n\nLet me know if you need more detail."
    )

    #: Valid JSON inside a fenced code block.
    FENCED = f"```json\n{json.dumps(_payload())}\n```"

    MALFORMED_JSON = '{"target_stream": "arrival", "shock_family": '

    TRUNCATED = json.dumps(_payload())[:-25]

    #: Unknown field. Must be REJECTED, not silently ignored.
    EXTRA_FIELD = json.dumps(_payload(confidence=0.91))

    #: The dangerous one: a self-chosen test threshold. Rejecting this is the whole point of a
    #: closed schema, because a model-chosen falsifier would make post-selection validity fake.
    SMUGGLED_THRESHOLD = json.dumps(_payload(threshold=2.5))

    #: A model trying to write its own falsifier in free text.
    SMUGGLED_FALSIFIER = json.dumps(
        _payload(prospective_signature="if arrivals < 0.5 * expected for 3 periods then true")
    )

    WRONG_TYPE = json.dumps(_payload(onset_window="minus one to one"))

    UNKNOWN_ENUM = json.dumps(_payload(shock_family="port_strike"))

    #: Inconsistent abstention: claims no_change but supplies an onset.
    INCOHERENT_ABSTENTION = json.dumps(
        _payload(shock_family="no_change", target_stream="none", direction="none")
    )

    #: evidence_refs pointing at an identifier that was never in the prompt.
    PHANTOM_EVIDENCE = json.dumps(_payload(evidence_refs=["obs_t99", "alert_404"]))

    EMPTY = ""

    #: Ordered corpus for property/fuzz tests over the invalid space.
    INVALID_CORPUS: tuple[str, ...] = (
        MALFORMED_JSON,
        TRUNCATED,
        EXTRA_FIELD,
        SMUGGLED_THRESHOLD,
        WRONG_TYPE,
        UNKNOWN_ENUM,
        INCOHERENT_ABSTENTION,
        EMPTY,
    )


@dataclass
class FakeLLM:
    """Scripted client satisfying :class:`collie.contracts.LLMClient`.

    Two modes. With ``responses``, each call pops the next scripted string, which is how a
    repair-then-succeed sequence is expressed. With ``default`` only, every call returns the
    same string.

    Records every prompt it saw so tests can assert prompt legality and prompt identity between
    arms without reaching into transport internals.
    """

    responses: list[str] = field(default_factory=list)
    default: str = canned.VALID
    model_id: str = "fake-open-weight-7b"
    prompts: list[str] = field(default_factory=list)
    decoding_hashes: list[str] = field(default_factory=list)
    fail_after: int | None = None
    """If set, raise :class:`RuntimeError` once this many calls have been served, so retry and
    error-accounting paths can be exercised."""

    _n: int = 0

    @classmethod
    def repair_then_succeed(cls, **kw: Any) -> FakeLLM:
        """First response is unusable, second is valid: the one-repair-attempt happy path."""
        return cls(responses=[canned.MALFORMED_JSON, canned.VALID], **kw)

    @classmethod
    def always_invalid(cls, **kw: Any) -> FakeLLM:
        """Both attempts fail, so the arm must fall back to unchanged OR."""
        return cls(responses=[canned.MALFORMED_JSON, canned.EXTRA_FIELD], **kw)

    @classmethod
    def cycling(cls, items: Iterable[str], **kw: Any) -> FakeLLM:
        return cls(responses=list(items), **kw)

    @property
    def n_calls(self) -> int:
        return self._n

    def complete(self, prompt: str, *, decoding_hash: str = "det-v1") -> str:
        self._n += 1
        if self.fail_after is not None and self._n > self.fail_after:
            raise RuntimeError(f"FakeLLM: simulated transport failure on call {self._n}")
        self.prompts.append(prompt)
        self.decoding_hashes.append(decoding_hash)
        if self.responses:
            return self.responses.pop(0)
        return self.default

    def __iter__(self) -> Iterator[str]:
        return iter(self.prompts)
