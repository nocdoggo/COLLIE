"""Module 02 collaborators for the injected Module 06 ShockSpec arm.

Create a separate prompter/parser pair per arm. The parser reads the last
rendered prompt's evidence identifiers and never calls a model or stamps provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from collie.arms.protocols import ProposalPayload
from collie.contracts import PeriodObservation, assert_no_hidden_state
from collie.spec.parse import validate_extracted_payload
from collie.spec.prompt import PromptBundle, build_prompt, build_repair_prompt


@dataclass
class ShockSpecPrompter:
    """Accumulate observable periods, with explicit episode reset and one repair prompt."""

    product_context: str | None = None
    _observations: dict[int, PeriodObservation] = field(default_factory=dict, init=False)
    _bundle: PromptBundle | None = field(default=None, init=False)

    def reset(self) -> None:
        self._observations.clear()
        self._bundle = None

    def observe(self, obs: PeriodObservation) -> None:
        assert_no_hidden_state(obs, context="ShockSpec adapter observation")
        previous = self._observations.get(obs.period)
        if previous is not None and previous != obs:
            raise ValueError("conflicting observations for the same period")
        self._observations[obs.period] = obs

    @property
    def bundle(self) -> PromptBundle:
        if self._bundle is None:
            raise RuntimeError("render a proposal prompt before parsing or repairing")
        return self._bundle

    def prompt(self, obs: PeriodObservation) -> str:
        self.observe(obs)
        self._bundle = build_prompt(
            tuple(self._observations.values()),
            tau_j=obs.period,
            product_context=self.product_context,
        )
        return self._bundle.text

    def repair_prompt(self) -> str:
        return build_repair_prompt(self.bundle).text


@dataclass
class ShockSpecParser:
    """Pure validation against the paired prompter's exact visible evidence."""

    prompter: ShockSpecPrompter

    def parse(self, text: str) -> ProposalPayload | None:
        evidence_ids = self.prompter.bundle.evidence_ids
        try:
            payload = validate_extracted_payload(text, permitted_evidence_ids=evidence_ids)
        except (ValueError, TypeError):
            return None
        return ProposalPayload(**payload.model_dump())
