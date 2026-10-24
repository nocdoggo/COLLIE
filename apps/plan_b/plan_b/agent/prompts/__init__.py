"""Versioned prompt files of the live agent.

A prompt file ``<name>.v<N>.txt`` holds a system part and a user template, separated by a line
``=== user ===``. The template has named slots (``{context}``, ``{observations}``, ``{state}``),
each filled with server-built JSON in which ``<``, ``>`` and ``&`` are escaped, so text inside a
slot cannot close the delimiters around it. Decisions record each prompt's id and SHA-256.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from plan_b.domain.digest import sha256_hex

USER_MARKER = "=== user ==="
_SLOT = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Prompt:
    prompt_id: str  # file stem, e.g. "choose_action.v1"
    system: str
    user_template: str
    sha256: str

    def render(self, **slots: Any) -> str:
        """One pass over the template, so slot text is never scanned for further slots."""
        names = set(_SLOT.findall(self.user_template))
        if names != set(slots):
            raise KeyError(f"prompt {self.prompt_id} has slots {sorted(names)}")
        return _SLOT.sub(lambda m: payload_json(slots[m.group(1)]), self.user_template)


def payload_json(payload: Any) -> str:
    """Canonical JSON with markup characters escaped (still valid JSON)."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


@cache
def load_prompt(prompt_id: str) -> Prompt:
    text = resources.files(__package__).joinpath(f"{prompt_id}.txt").read_text(encoding="utf-8")
    system, marker, user = text.partition(f"\n{USER_MARKER}\n")
    if not marker or not _SLOT.search(user):
        raise ValueError(f"prompt {prompt_id} lacks a user template with a slot")
    return Prompt(
        prompt_id=prompt_id,
        system=system.strip(),
        user_template=user.strip(),
        sha256=sha256_hex(text),
    )
