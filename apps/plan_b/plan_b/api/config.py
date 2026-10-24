"""Server-side configuration of the coordinator policies the API hosts.

The per-episode caps apply to every policy. They come from ``PLAN_B_EPISODE_MAX_TOOL_CALLS``
and ``PLAN_B_EPISODE_MAX_MODEL_CALLS`` when set, else the Wave 2 development values (48 tool
calls, 8 model calls) that Wave 3 freezes. The live policy's endpoint configuration is
``plan_b.agent.config`` (environment, else ``.local/keys/model_endpoint.env``). It is read here,
on the server; the key file is never read here, and only the public form of the configuration
(no key, no absolute local path) ever leaves the process.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from plan_b.agent.config import ModelConfig, ModelConfigError, load_model_config
from plan_b.evaluation.policies.base import Policy
from plan_b.scenarios.policy_host import (
    DEVELOPMENT_CAPS,
    EpisodeCaps,
    PolicyChoice,
    policy_factory_for,
)

CAP_ENV = {
    "max_tool_calls": "PLAN_B_EPISODE_MAX_TOOL_CALLS",
    "max_model_calls": "PLAN_B_EPISODE_MAX_MODEL_CALLS",
}

ConfigLoader = Callable[[], ModelConfig]
FactoryFor = Callable[[PolicyChoice, str], Callable[[], Policy]]


def load_episode_caps(env: Mapping[str, str] | None = None) -> EpisodeCaps:
    environ = os.environ if env is None else env
    values: dict[str, int] = {}
    for field, name in CAP_ENV.items():
        raw = environ.get(name)
        if raw is None or raw == "":
            values[field] = getattr(DEVELOPMENT_CAPS, field)
            continue
        try:
            values[field] = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
    return EpisodeCaps(**values, phase=DEVELOPMENT_CAPS.phase)


@dataclass(frozen=True)
class LiveAvailability:
    available: bool
    model_id: str | None
    reason: str | None
    config: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "live_available": self.available,
            "model_id": self.model_id,
            "reason": self.reason,
            "live_config": self.config,
        }


def live_availability(loader: ConfigLoader = load_model_config) -> LiveAvailability:
    """Whether the live policy could be selected now. Nothing is sent to the provider and the
    key file is only checked for presence."""
    try:
        config = loader()
    except ModelConfigError as exc:
        return LiveAvailability(False, None, str(exc), None)
    public = config.public()
    if not public["key_file_present"]:
        return LiveAvailability(
            False, config.model_id, "the configured key file is not present", public
        )
    return LiveAvailability(True, config.model_id, None, public)


def factory_for(caps: EpisodeCaps, loader: ConfigLoader = load_model_config) -> FactoryFor:
    """``rules`` gives the profile's deterministic baseline; ``live`` reads the endpoint
    configuration when the policy is selected (``ModelConfigError`` when it is missing)."""

    def make(choice: PolicyChoice, profile_id: str) -> Callable[[], Policy]:
        config = loader() if choice == "live" else None
        return policy_factory_for(choice, profile_id, caps=caps, live_config=config)

    return make
